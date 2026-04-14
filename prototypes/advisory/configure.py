"""Stage 2: Generate Garak + NeMo config files from coverage analysis."""
import argparse
import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

TEMPLATES_DIR = Path(__file__).parent / "templates"

# Guardrail composition: cost-ordered, input vs output, trigger values
NEMO_RAIL_DEFS = {
    "nemo-jailbreak-heuristics": {
        "flow_name": "check_jailbreak_heuristic",
        "detector_name": "jailbreak_detection_heuristics",
        "trigger_value": "jailbreak",
        "refusal_type": "jailbreak",
        "position": "input",
        "cost_order": 1,
    },
    "nemo-sensitive-data": {
        "flow_name": "check_sensitive_data",
        "detector_name": "sensitive_data_detection",
        "trigger_value": "pii_detected",
        "refusal_type": "pii",
        "position": "both",
        "cost_order": 2,
    },
    "nemo-injection-detection": {
        "flow_name": "check_injection",
        "detector_name": "injection_detection",
        "trigger_value": "injection",
        "refusal_type": "injection",
        "position": "input",
        "cost_order": 3,
    },
    "nemo-self-check-input": {
        "flow_name": "check_input_safety",
        "detector_name": "self_check_input",
        "trigger_value": "unsafe",
        "refusal_type": "unsafe_input",
        "position": "input",
        "cost_order": 4,
    },
    "nemo-content-safety": {
        "flow_name": "check_content_safety",
        "detector_name": "content_safety",
        "trigger_value": "unsafe",
        "refusal_type": "content_safety",
        "position": "input",
        "cost_order": 5,
    },
    "nemo-self-check-output": {
        "flow_name": "check_output_safety",
        "detector_name": "self_check_output",
        "trigger_value": "unsafe",
        "refusal_type": "unsafe_output",
        "position": "output",
        "cost_order": 6,
    },
    "nemo-hallucination-detection": {
        "flow_name": "check_hallucination",
        "detector_name": "hallucination_detection",
        "trigger_value": "hallucination",
        "refusal_type": "hallucination",
        "position": "output",
        "cost_order": 7,
    },
    "nemo-fact-checking": {
        "flow_name": "check_facts",
        "detector_name": "fact_checking",
        "trigger_value": "ungrounded",
        "refusal_type": "hallucination",
        "position": "output",
        "cost_order": 8,
    },
}

REFUSAL_MESSAGES = {
    "jailbreak": "I cannot process this request. Your input has been flagged as a potential jailbreak attempt.",
    "pii": "I've detected sensitive personal information in the request. I cannot process it to protect privacy.",
    "injection": "I cannot process this request. A potential prompt injection has been detected.",
    "unsafe_input": "I cannot process this request as it may involve unsafe content.",
    "content_safety": "I cannot provide a response to this request due to content safety concerns.",
    "unsafe_output": "I've filtered my response as it contained potentially unsafe content.",
    "hallucination": "I'm not confident in the accuracy of my response. Please verify with authoritative sources.",
}

# AIROO dimensions for grouping probes
DIMENSION_ORDER = ["jailbreak", "harmful_content", "pii_leakage", "bias_fairness", "hallucination"]


def generate_garak_config(analysis: dict, output_dir: Path):
    """Generate garak.yaml from analysis."""
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), keep_trailing_newline=True)
    template = env.get_template("garak.yaml.j2")

    # Collect and group probes by dimension
    probe_map = {}
    for risk in analysis["risks"]:
        for probe in risk["coverage"]["probes"]:
            pid = probe["probe_id"]
            if pid not in probe_map:
                probe_map[pid] = {
                    **probe,
                    "risk_id": risk["risk_id"],
                    "risk_name": risk["risk_name"],
                }

    # Group probes by AIROO dimension
    probe_groups = []
    grouped_probes = set()

    for dim in DIMENSION_ORDER:
        dim_probes = []
        for pid, info in probe_map.items():
            if pid in grouped_probes:
                continue
            if _probe_matches_dimension(pid, dim):
                dim_probes.append(info)
                grouped_probes.add(pid)
        if dim_probes:
            probe_groups.append({"dimension": dim, "probes": dim_probes})

    # Any ungrouped probes
    ungrouped = [info for pid, info in probe_map.items() if pid not in grouped_probes]
    if ungrouped:
        probe_groups.append({"dimension": "other", "probes": ungrouped})

    # Uncovered risks
    uncovered = [
        {"risk_id": r["risk_id"], "risk_name": r["risk_name"],
         "dimension_count": len(r.get("attack_dimensions", []))}
        for r in analysis["risks"]
        if not r["coverage"]["gaps"]["has_probes"]
    ]

    content = template.render(
        client=analysis["client"],
        domain=analysis["domain"],
        total_risks=analysis["summary"]["total_risks"],
        total_probes=len(probe_map),
        probe_groups=probe_groups,
        uncovered_risks=uncovered,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "garak.yaml").write_text(content)


def generate_nemo_config(analysis: dict, output_dir: Path):
    """Generate NeMo config.yml + rails.co from analysis."""
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), keep_trailing_newline=True)

    # Collect unique NeMo guardrails from analysis
    nemo_guardrails = {}
    for risk in analysis["risks"]:
        for g in risk["coverage"]["guardrails"]:
            if g["platform"] == "nemo" and g["guardrail_id"] in NEMO_RAIL_DEFS:
                gid = g["guardrail_id"]
                if gid not in nemo_guardrails:
                    nemo_guardrails[gid] = {
                        **NEMO_RAIL_DEFS[gid],
                        "guardrail_id": gid,
                        "risk_id": risk["risk_id"],
                        "mapping_source": g["mapping_source"],
                    }

    # Sort by cost order
    sorted_rails = sorted(nemo_guardrails.values(), key=lambda r: r["cost_order"])

    input_rails = [r for r in sorted_rails if r["position"] in ("input", "both")]
    output_rails = [r for r in sorted_rails if r["position"] in ("output", "both")]

    # Add source field for template (same as mapping_source)
    for rail in input_rails:
        rail["source"] = rail["mapping_source"]
    for rail in output_rails:
        rail["source"] = rail["mapping_source"]

    # Determine which guard models are needed
    needs_hap = any(r["guardrail_id"] == "nemo-content-safety" for r in sorted_rails)
    needs_injection = any(r["guardrail_id"] in ("nemo-injection-detection", "nemo-jailbreak-heuristics") for r in sorted_rails)

    # Policy concepts for system prompt
    policy_concepts = sorted(set(r["policy_concept"] for r in analysis["risks"]))

    # Uncovered risks
    uncovered = [
        {"risk_id": r["risk_id"], "risk_name": r["risk_name"]}
        for r in analysis["risks"]
        if not r["coverage"]["gaps"]["has_guardrails"]
    ]

    # Refusals needed
    refusal_types = set(r["refusal_type"] for r in sorted_rails)
    refusals = [{"type": t, "message": REFUSAL_MESSAGES.get(t, "I cannot process this request.")}
                for t in sorted(refusal_types)]

    # Render config.yml
    config_template = env.get_template("nemo_config.yml.j2")
    config_content = config_template.render(
        client=analysis["client"],
        domain=analysis["domain"],
        needs_hap_guard=needs_hap,
        needs_injection_guard=needs_injection,
        policy_concepts=policy_concepts,
        input_rails=input_rails,
        output_rails=output_rails,
    )

    # Render rails.co
    rails_template = env.get_template("nemo_rails.co.j2")
    rails_content = rails_template.render(
        client=analysis["client"],
        domain=analysis["domain"],
        all_rails=sorted_rails,
        refusals=refusals,
        uncovered_risks=uncovered,
    )

    nemo_dir = output_dir / "nemo"
    nemo_dir.mkdir(parents=True, exist_ok=True)
    (nemo_dir / "config.yml").write_text(config_content)
    (nemo_dir / "rails.co").write_text(rails_content)


def _probe_matches_dimension(probe_id: str, dimension: str) -> bool:
    """Heuristic: match probe to AIROO dimension by probe name patterns."""
    probe_lower = probe_id.lower()
    patterns = {
        "jailbreak": ["dan.", "tap.", "suffix.", "dra.", "spo."],
        "harmful_content": ["realtoxicityprompts.", "lmrc.profanity", "lmrc.bullying", "lmrc.slurusage", "continuation."],
        "pii_leakage": ["leakreplay.", "web_injection."],
        "bias_fairness": ["lmrc.sexualisation", "lmrc.deadnaming"],
        "hallucination": ["packagehallucination.", "snowball.", "misleading."],
    }
    for pattern in patterns.get(dimension, []):
        if probe_lower.startswith(pattern.lower()):
            return True
    return False


def main():
    parser = argparse.ArgumentParser(description="Stage 2: Config generation")
    parser.add_argument("analysis", type=Path, help="Path to analysis.json from Stage 1")
    parser.add_argument("--output", type=Path, required=True, help="Output directory")
    args = parser.parse_args()

    with open(args.analysis) as f:
        analysis = json.load(f)

    generate_garak_config(analysis, args.output)
    generate_nemo_config(analysis, args.output)

    print(f"Configs written to {args.output}")
    print(f"  garak.yaml")
    print(f"  nemo/config.yml")
    print(f"  nemo/rails.co")


if __name__ == "__main__":
    main()
