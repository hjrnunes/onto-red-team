# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml", "pydantic"]
# ///
"""Build a combined HTML report from a pipeline run directory.

Discovers and embeds: evaluation metrics, adversarial prompts, domain context,
enriched taxonomy, and enriched policy into a single tabbed HTML report.

Usage:
    uv run scripts/build_combined_report.py runs/gen5/generic-gemma-3-12b-it-g5
    uv run scripts/build_combined_report.py runs/gen5/generic-gemma-3-12b-it-g5 --output /tmp/report.html
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

# Add refiner to path so we can import from it
sys.path.insert(0, str(Path(__file__).parent / "../refiner/src"))

from refiner.ingest_report import build_report_data
from refiner.models import PolicyProfile, RunReport


TEMPLATE = Path(__file__).parent / "../refiner/src/refiner/combined_report_template.html"


def _discover(run_dir: Path, glob: str) -> Path | None:
    matches = sorted(run_dir.glob(glob))
    return matches[0] if matches else None


def _load_json(path: Path | None) -> dict | list:
    if not path or not path.exists():
        return {}
    return json.loads(path.read_text())


def _load_jsonl(path: Path | None) -> list[dict]:
    if not path or not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _load_yaml(path: Path | None) -> dict:
    if not path or not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def _title_from_dir(run_dir: Path) -> str:
    return run_dir.name.replace("-", " ").replace("_", " ").title()


def build_combined_report(
    run_dir: Path,
    output: Path | None = None,
    title: str | None = None,
) -> Path:
    """Build a combined HTML report from all artifacts in a run directory.

    Parameters
    ----------
    run_dir : Path
        The run directory containing pipeline artifacts.
    output : Path, optional
        Output HTML file path. Defaults to ``run_dir/<slug>-combined-report.html``.
    title : str, optional
        Page title. Derived from directory name when omitted.

    Returns
    -------
    Path
        Path to the written HTML file.
    """
    run_dir = Path(run_dir)
    if not run_dir.is_dir():
        print(f"Error: {run_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    # Discover artifacts
    eval_json = _discover(run_dir, "*-evaluation.json")
    adv_prompts = _discover(run_dir, "*-adversarial-prompts.jsonl")
    risk_landscape = _discover(run_dir, "*-risk-landscape.yaml")
    domain_ctx = _discover(run_dir, "*-domain-context.yaml")
    taxonomy = _discover(run_dir, "*-taxonomy.json") or _discover(run_dir, "*-taxonomy.yaml")
    enriched_policy = _discover(run_dir, "*-policy-profile.json") or _discover(run_dir, "*-policy-document.json") or _discover(run_dir, "*-enriched.json")

    # Load data
    report_data = _load_json(eval_json)
    explorer_data = _load_jsonl(adv_prompts)
    rl_data = _load_yaml(risk_landscape)
    dc_data = _load_yaml(domain_ctx)
    tax_data = _load_json(taxonomy) if taxonomy and taxonomy.suffix == ".json" else _load_yaml(taxonomy)

    # Enrich policy data with confidence scores, stakeholder groups, and summary
    run_report_yaml = _discover(run_dir, "*-run-report.yaml")
    if enriched_policy:
        raw_policy = _load_json(enriched_policy)
        rr_data = _load_yaml(run_report_yaml)
        doc = PolicyProfile(**raw_policy)
        rr = RunReport(
            model=rr_data.get("model", ""),
            policy_set=rr_data.get("policy_set", ""),
            timestamp=rr_data.get("timestamp", ""),
            stages_completed=rr_data.get("stages_completed", []),
            events=rr_data.get("events", []),
            token_usage=rr_data.get("token_usage"),
        )
        meta = {"model": rr.model, "policy_set": rr.policy_set, "timestamp": rr.timestamp}
        policy_data = build_report_data(doc, rr, meta)
    else:
        policy_data = {}

    # Report what was found
    found = []
    if eval_json:
        found.append(f"evaluation ({eval_json.name})")
    if adv_prompts:
        found.append(f"prompts ({len(explorer_data)} records)")
    if risk_landscape:
        found.append(f"risk landscape ({len(rl_data.get('risks', []))} risks)")
    if domain_ctx:
        found.append(f"domain context ({len(dc_data.get('policy_contexts', []))} policy contexts)")
    if taxonomy:
        found.append(f"taxonomy ({len(tax_data.get('entries', []))} entries)")
    if enriched_policy:
        found.append(f"policy ({enriched_policy.name})")

    if not found:
        print(f"Warning: no artifacts found in {run_dir}", file=sys.stderr)

    print(f"Found: {', '.join(found)}")

    # Load template
    template_path = TEMPLATE.resolve()
    if not template_path.exists():
        print(f"Error: template not found at {template_path}", file=sys.stderr)
        sys.exit(1)
    template = template_path.read_text()

    # Build title
    title = title or _title_from_dir(run_dir)

    # Transform domain context: flatten policy_contexts[].risk_groundings[]
    # into profiles[] for the combined template
    if "policy_contexts" in dc_data and "profiles" not in dc_data:
        risks_by_id = {r["risk_id"]: r for r in dc_data.get("risks", [])}
        profiles = []
        for ctx in dc_data.get("policy_contexts", []):
            for grounding in ctx.get("risk_groundings", []):
                risk_meta = risks_by_id.get(grounding["risk_id"], {})
                profiles.append({
                    "risk_id": grounding["risk_id"],
                    "risk_name": risk_meta.get("risk_name", grounding["risk_id"]),
                    "risk_description": risk_meta.get("risk_description"),
                    "risk_concern": risk_meta.get("risk_concern"),
                    "risk_framework": risk_meta.get("risk_framework"),
                    "policy_concept": ctx.get("policy_concept"),
                    "axes": grounding.get("axes", []),
                    "cross_mappings": risk_meta.get("cross_mappings", []),
                })
        dc_data["profiles"] = profiles

    # Enrich taxonomy entries with risk_id when missing (retroactive for
    # runs generated before structure.py emitted risk_id)
    if tax_data and dc_data:
        # Build axis-URI-set → risk_id from domain context groundings
        axis_uris_to_rid: dict[frozenset[str], str] = {}
        for ctx in dc_data.get("policy_contexts", []):
            for grounding in ctx.get("risk_groundings", []):
                uris = frozenset(a.get("cco_class_uri", "") for a in grounding.get("axes", []))
                if uris:
                    axis_uris_to_rid[uris] = grounding["risk_id"]
        for entry in tax_data.get("entries", []):
            if entry.get("risk_id"):
                continue
            summary = entry.get("domain_context_summary", {})
            entry_uris = frozenset(a.get("uri", "") for a in summary.get("axes", []))
            if entry_uris and entry_uris in axis_uris_to_rid:
                entry["risk_id"] = axis_uris_to_rid[entry_uris]

    # Substitute placeholders
    html = template
    html = html.replace("__REPORT_TITLE__", title)
    html = html.replace("__REPORT_DATA__", json.dumps(report_data))
    html = html.replace("__EXPLORER_DATA__", json.dumps(explorer_data, separators=(",", ":")))
    html = html.replace("__RISK_LANDSCAPE_DATA__", json.dumps(rl_data))
    html = html.replace("__DOMAIN_CONTEXT_DATA__", json.dumps(dc_data))
    html = html.replace("__TAXONOMY_DATA__", json.dumps(tax_data))
    html = html.replace("__POLICY_DATA__", json.dumps(policy_data))

    # Write output
    if output:
        output = Path(output)
    else:
        dc = _discover(run_dir, "*-domain-context.yaml")
        slug = dc.name.replace("-domain-context.yaml", "") if dc else "combined"
        output = run_dir / f"{slug}-combined-report.html"
    output.write_text(html)
    print(f"Written: {output} ({len(found)} data sources)")
    return output


def main():
    parser = argparse.ArgumentParser(
        description="Build a combined HTML report from a pipeline run directory.",
    )
    parser.add_argument("run_dir", help="Path to the run directory")
    parser.add_argument("--output", "-o", help="Output HTML path (default: <run_dir>/<slug>-combined-report.html)")
    parser.add_argument("--title", "-t", help="Override page title")
    args = parser.parse_args()

    build_combined_report(
        run_dir=Path(args.run_dir),
        output=Path(args.output) if args.output else None,
        title=args.title,
    )


if __name__ == "__main__":
    main()
