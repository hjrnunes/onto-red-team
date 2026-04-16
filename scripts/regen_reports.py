# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml", "pydantic"]
# ///
"""Regenerate all HTML reports from existing data artifacts in run directories.

Re-renders every HTML report using the current templates, without re-running
the pipeline. Useful after template changes (e.g. tooltip additions).

Usage:
    uv run scripts/regen_reports.py runs/swb-gemma-4-26b-a4b-it-g12
    uv run scripts/regen_reports.py runs/*-g12       # shell glob
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

# Add refiner to path so we can import from it
sys.path.insert(0, str(Path(__file__).parent / "../refiner/src"))

from refiner.artifact_reports import (
    build_dataset_report,
    build_domain_context_report,
    build_risk_landscape_report,
    build_run_report_html,
    build_taxonomy_report,
)
from refiner.evaluate import build_html_report
from refiner.ingest_report import build_ingest_report
from refiner.models import PolicyProfile, RunReport

# Add scripts dir to path so we can import the combined report builder
sys.path.insert(0, str(Path(__file__).parent))

from build_combined_report import build_combined_report


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text()) or {}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def regen_run(run_dir: Path) -> None:
    """Regenerate all HTML reports in a single run directory."""
    slug = None
    regenerated = []

    # Discover the slug from any artifact
    for f in run_dir.glob("*-domain-context.yaml"):
        slug = f.name.replace("-domain-context.yaml", "")
        break
    if not slug:
        for f in run_dir.glob("*-run-report.yaml"):
            slug = f.name.replace("-run-report.yaml", "")
            break
    if not slug:
        print(f"  Skipping {run_dir.name}: no artifacts found")
        return

    # Risk landscape
    rl_yaml = run_dir / f"{slug}-risk-landscape.yaml"
    if rl_yaml.exists():
        out = run_dir / f"{slug}-risk-landscape.html"
        build_risk_landscape_report(_load_yaml(rl_yaml), out)
        regenerated.append("risk-landscape")

    # Domain context
    dc_yaml = run_dir / f"{slug}-domain-context.yaml"
    if dc_yaml.exists():
        out = run_dir / f"{slug}-domain-context.html"
        build_domain_context_report(_load_yaml(dc_yaml), out)
        regenerated.append("domain-context")

    # Taxonomy
    tax_yaml = run_dir / f"{slug}-taxonomy.yaml"
    tax_json = run_dir / f"{slug}-taxonomy.json"
    if tax_yaml.exists():
        out = run_dir / f"{slug}-taxonomy.html"
        build_taxonomy_report(_load_yaml(tax_yaml), out)
        regenerated.append("taxonomy")
    elif tax_json.exists():
        out = run_dir / f"{slug}-taxonomy.html"
        build_taxonomy_report(_load_json(tax_json), out)
        regenerated.append("taxonomy")

    # Run report
    rr_yaml = run_dir / f"{slug}-run-report.yaml"
    if rr_yaml.exists():
        out = run_dir / f"{slug}-run-report.html"
        build_run_report_html(_load_yaml(rr_yaml), out)
        regenerated.append("run-report")

    # Dataset
    ds_jsonl = run_dir / f"{slug}-dataset.jsonl"
    if ds_jsonl.exists():
        out = run_dir / f"{slug}-dataset.html"
        rows = _load_jsonl(ds_jsonl)
        build_dataset_report(rows, out)
        regenerated.append(f"dataset ({len(rows)} rows)")

    # Evaluation
    eval_json = run_dir / f"{slug}-policy-profile-evaluation.json"
    if not eval_json.exists():
        eval_json = run_dir / f"{slug}-policy-document-evaluation.json"
    if eval_json.exists():
        out = run_dir / f"{slug}-policy-profile-evaluation.html"
        build_html_report(_load_json(eval_json), out)
        regenerated.append("evaluation")

    # Ingest report (from policy profile JSON + run report YAML)
    policy_json = run_dir / f"{slug}-policy-profile.json"
    if not policy_json.exists():
        policy_json = run_dir / f"{slug}-policy-document.json"
    if policy_json.exists() and rr_yaml.exists():
        out = run_dir / f"{slug}-ingest-report.html"
        doc = PolicyProfile(**_load_json(policy_json))
        rr_data = _load_yaml(rr_yaml)
        report = RunReport(
            model=rr_data.get("model", ""),
            policy_set=rr_data.get("policy_set", ""),
            timestamp=rr_data.get("timestamp", ""),
            stages_completed=rr_data.get("stages_completed", []),
            events=rr_data.get("events", []),
            token_usage=rr_data.get("token_usage"),
        )
        meta = {"model": report.model, "policy_set": report.policy_set, "timestamp": report.timestamp}
        build_ingest_report(doc, report, out, meta)
        regenerated.append("ingest")

    # Combined report
    build_combined_report(run_dir)
    regenerated.append("combined")

    print(f"  {run_dir.name}: regenerated {len(regenerated)} reports: {', '.join(regenerated)}")


def main():
    if len(sys.argv) < 2:
        print("Usage: uv run scripts/regen_reports.py <run_dir> [run_dir ...]")
        sys.exit(1)

    dirs = [Path(d) for d in sys.argv[1:]]
    for d in dirs:
        if not d.is_dir():
            print(f"  Skipping {d}: not a directory")
            continue
        regen_run(d)


if __name__ == "__main__":
    main()
