"""Stage 3: Render advisory report from analysis + generated configs."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

TEMPLATES_DIR = Path(__file__).parent / "templates"


def generate_report(analysis: dict, output_dir: Path):
    """Render advisory-report.md from analysis data."""
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), keep_trailing_newline=True)
    template = env.get_template("report.md.j2")

    # Classify risks by coverage status
    for risk in analysis["risks"]:
        gaps = risk["coverage"]["gaps"]
        if gaps["has_probes"] and gaps["has_guardrails"]:
            risk["status"] = "Covered"
        elif gaps["has_probes"] or gaps["has_guardrails"]:
            risk["status"] = "Partial Gap"
        else:
            risk["status"] = "**Gap**"

    uncovered_risks = []
    partial_risks = []
    for risk in analysis["risks"]:
        if risk["status"] == "**Gap**":
            risk["dimension_labels"] = ", ".join(
                d["cco_class"] for d in risk.get("attack_dimensions", [])
            ) or "none identified"
            uncovered_risks.append(risk)
        elif risk["status"] == "Partial Gap":
            partial_risks.append(risk)

    # Collect uncovered attack dimensions across all risks
    uncovered_dimensions = []
    for risk in analysis["risks"]:
        for dim in risk.get("attack_dimensions", []):
            uncovered_dimensions.append({
                "risk_name": risk["risk_name"],
                "dimension": dim["cco_class"],
                "term_count": dim.get("term_count", 0),
            })

    # Probe groups for the config summary section
    probe_map = {}
    for risk in analysis["risks"]:
        for probe in risk["coverage"]["probes"]:
            pid = probe["probe_id"]
            if pid not in probe_map:
                probe_map[pid] = {**probe, "risk_name": risk["risk_name"], "risk_id": risk["risk_id"]}

    # Simple grouping by name prefix
    probe_groups = _group_probes(probe_map)

    # NeMo rails summary
    nemo_rails = []
    seen_rails = set()
    for risk in analysis["risks"]:
        for g in risk["coverage"]["guardrails"]:
            if g["platform"] == "nemo" and g["guardrail_id"] not in seen_rails:
                seen_rails.add(g["guardrail_id"])
                nemo_rails.append({
                    "flow_name": g["detector_name"],
                    "position": "input",
                    "risk_id": risk["risk_id"],
                    "mapping_source": g["mapping_source"],
                })

    input_rail_count = sum(1 for r in nemo_rails if r["position"] == "input")
    output_rail_count = sum(1 for r in nemo_rails if r["position"] == "output")

    # Source label
    source = analysis.get("source", {})
    if source.get("source_type") == "scenario":
        source_label = f"scenario: {source.get('scenario', 'unknown')}"
    else:
        source_label = f"run: {source.get('run_dir', 'unknown')}"

    content = template.render(
        client=analysis["client"],
        domain=analysis["domain"],
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        source_label=source_label,
        summary=analysis["summary"],
        risks=analysis["risks"],
        uncovered_risks=uncovered_risks,
        partial_risks=partial_risks,
        uncovered_dimensions=uncovered_dimensions,
        total_probes=len(probe_map),
        probe_dimension_count=len(probe_groups),
        probe_groups=probe_groups,
        nemo_rails=nemo_rails,
        input_rail_count=input_rail_count,
        output_rail_count=output_rail_count,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "advisory-report.md").write_text(content)


def _group_probes(probe_map: dict) -> list[dict]:
    """Group probes by dimension heuristic."""
    groups = {}
    for pid, info in probe_map.items():
        dim = _infer_dimension(pid)
        if dim not in groups:
            groups[dim] = {"dimension": dim, "probes": []}
        groups[dim]["probes"].append(info)
    return list(groups.values())


def _infer_dimension(probe_id: str) -> str:
    """Infer AIROO dimension from probe ID prefix."""
    probe_lower = probe_id.lower()
    patterns = {
        "jailbreak": ["dan.", "tap.", "suffix.", "dra.", "spo."],
        "harmful_content": ["realtoxicityprompts.", "lmrc.profanity", "lmrc.bullying", "lmrc.slurusage", "continuation."],
        "pii_leakage": ["leakreplay.", "web_injection."],
        "bias_fairness": ["lmrc.sexualisation", "lmrc.deadnaming"],
        "hallucination": ["packagehallucination.", "snowball.", "misleading."],
    }
    for dim, prefixes in patterns.items():
        for prefix in prefixes:
            if probe_lower.startswith(prefix.lower()):
                return dim
    return "other"


def main():
    parser = argparse.ArgumentParser(description="Stage 3: Advisory report")
    parser.add_argument("output_dir", type=Path, help="Directory containing analysis.json and configs")
    parser.add_argument("--output", type=Path, help="Output directory (defaults to same as input)")
    args = parser.parse_args()

    analysis_path = args.output_dir / "analysis.json"
    if not analysis_path.exists():
        raise FileNotFoundError(f"analysis.json not found in {args.output_dir}")

    with open(analysis_path) as f:
        analysis = json.load(f)

    out_dir = args.output or args.output_dir
    generate_report(analysis, out_dir)
    print(f"Report written to {out_dir / 'advisory-report.md'}")


if __name__ == "__main__":
    main()
