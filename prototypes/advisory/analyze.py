"""Stage 1: Read refiner output or canned scenario, query AIROO, compute coverage."""
import argparse
import json
import sys
from pathlib import Path

import yaml

try:
    from ontology.query import OntologyQuery
    _oq = None

    def _get_oq():
        global _oq
        if _oq is None:
            _oq = OntologyQuery()
        return _oq
except ImportError:
    def _get_oq():
        raise RuntimeError("AIROO not installed. Install with: uv sync --extra airoo")


def extract_risks(taxonomy: dict, domain_context: dict) -> list[dict]:
    """Extract risks from refiner taxonomy + domain context files."""
    # Build group_id -> group_name lookup
    group_names = {g["id"]: g["name"] for g in taxonomy.get("groups", [])}

    # Build risk_id -> domain context profile lookup
    dc_profiles = {}
    for profile in domain_context.get("profiles", []):
        dc_profiles[profile["risk_id"]] = profile

    risks = []
    for entry in taxonomy.get("entries", []):
        risk_id = entry["id"]
        group_id = entry.get("isPartOf", "")
        policy_concept = group_names.get(group_id, "Unknown")

        # Cross-mappings become alternative framings
        alternative_framings = []
        for mapping_type in ("related_mappings", "close_mappings", "broad_mappings", "exact_mappings", "narrow_mappings"):
            for mapped_id in entry.get(mapping_type, []):
                alternative_framings.append({
                    "risk_id": mapped_id,
                    "taxonomy": _infer_taxonomy(mapped_id),
                    "mapping_type": mapping_type.replace("_mappings", ""),
                })

        # Attack dimensions from domain context
        attack_dimensions = []
        dc_summary = entry.get("domain_context_summary", {})
        dc_profile = dc_profiles.get(risk_id)
        if dc_profile:
            for axis in dc_profile.get("axes", []):
                enum_count = len(axis.get("enumerations", []))
                terms = [e["class_label"] for e in axis.get("enumerations", [])]
                attack_dimensions.append({
                    "cco_class": axis["cco_class_label"],
                    "cco_class_uri": axis["cco_class_uri"],
                    "role": axis.get("bfo_category", ""),
                    "term_count": enum_count,
                    "terms": terms,
                })
        elif dc_summary:
            for axis in dc_summary.get("axes", []):
                attack_dimensions.append({
                    "cco_class": axis["class"],
                    "cco_class_uri": axis.get("uri", ""),
                    "role": "",
                    "term_count": axis.get("enumeration_count", 0),
                    "terms": [],
                })

        risks.append({
            "risk_id": risk_id,
            "risk_name": entry["name"],
            "policy_concept": policy_concept,
            "alternative_framings": alternative_framings,
            "attack_dimensions": attack_dimensions,
        })

    return risks


def _infer_taxonomy(risk_id: str) -> str:
    """Infer taxonomy from risk ID prefix."""
    prefixes = {
        "atlas-": "ibm-risk-atlas",
        "nist-": "nist-ai-rmf",
        "granite-": "granite-guardian",
        "llm0": "owasp-llm",
        "ail-": "ai-luminiate",
        "air-": "air-2024",
        "mit-": "mit-ai-risk",
        "credo-": "credo-ai",
    }
    for prefix, taxonomy in prefixes.items():
        if risk_id.startswith(prefix):
            return taxonomy
    return "unknown"


def extract_risks_from_scenario(scenario_path: Path) -> list[dict]:
    """Load risks from a canned scenario JSON file."""
    with open(scenario_path) as f:
        scenario = json.load(f)
    return scenario["risks"]


def query_coverage(risk_id: str) -> dict:
    """Query AIROO for probes, guardrails, and benchmarks matching a risk ID."""
    oq = _get_oq()

    probes = []
    for p in oq.get_probes_for_risk(risk_id):
        probes.append({
            "probe_id": p.get("probe_name", p.get("id", "")),
            "platform": "garak",
            "mapping_source": _infer_mapping_source("probe", p),
            "description": p.get("description", ""),
            "garak_tier": p.get("garak_tier", ""),
        })

    guardrails = []
    for g in oq.get_guardrails_for_risk(risk_id):
        guardrails.append({
            "guardrail_id": g.get("id", ""),
            "detector_name": g.get("detector_name", ""),
            "platform": g.get("platform", ""),
            "mapping_source": _infer_mapping_source("guardrail", g),
            "description": g.get("description", ""),
        })

    benchmarks = []
    for b in oq.get_evals_for_risk(risk_id):
        benchmarks.append({
            "benchmark_id": b.get("id", ""),
            "task_name": b.get("task_name", ""),
            "platform": b.get("provider", ""),
            "mapping_source": _infer_mapping_source("benchmark", b),
            "description": b.get("description", ""),
        })

    return {"probes": probes, "guardrails": guardrails, "benchmarks": benchmarks}


def _infer_mapping_source(entity_type: str, entity: dict) -> str:
    """Infer mapping source from entity type and metadata.

    AIROO uses: garak_tags (probes), platform_docs (guardrails),
    benchmark_scope or garak_tags (benchmarks).
    """
    if entity_type == "probe":
        return "garak_tags"
    elif entity_type == "guardrail":
        return "platform_docs"
    elif entity_type == "benchmark":
        provider = entity.get("provider", "")
        return "garak_tags" if provider == "garak" else "benchmark_scope"
    return "unknown"


def _classify_coverage(coverage: dict, attack_dimensions: list[dict]) -> dict:
    """Classify coverage gaps for a risk."""
    has_probes = len(coverage["probes"]) > 0
    has_guardrails = len(coverage["guardrails"]) > 0
    has_benchmarks = len(coverage["benchmarks"]) > 0

    # All dimensions are "uncovered" at the probe level for now —
    # AIROO maps at risk level, not dimension level
    uncovered_dimensions = [d["cco_class"] for d in attack_dimensions]

    return {
        "has_probes": has_probes,
        "has_guardrails": has_guardrails,
        "has_benchmarks": has_benchmarks,
        "uncovered_dimensions": uncovered_dimensions,
    }


def build_analysis(
    run_dir: Path | None = None,
    policy_file: Path | None = None,
    scenario: Path | None = None,
) -> dict:
    """Build full coverage analysis from refiner output or canned scenario."""
    if scenario:
        with open(scenario) as f:
            scenario_data = json.load(f)
        client = scenario_data.get("client", "unknown")
        domain = scenario_data.get("domain", "unknown")
        source = {
            "scenario": str(scenario),
            "source_type": "scenario",
        }
        risks = extract_risks_from_scenario(scenario)
    elif run_dir:
        client, taxonomy, domain_ctx = _load_run(run_dir)
        domain = _infer_domain(policy_file) if policy_file else "unknown"
        source = {
            "run_dir": str(run_dir),
            "policy_file": str(policy_file) if policy_file else None,
            "source_type": "refiner_run",
        }
        risks = extract_risks(taxonomy, domain_ctx)
    else:
        raise ValueError("Either run_dir or scenario must be provided")

    # Query AIROO for each risk
    analyzed_risks = []
    for risk in risks:
        risk_id = risk["risk_id"]

        # Query with the risk's own ID first
        coverage = query_coverage(risk_id)

        # If no direct coverage, try alternative framings
        if not coverage["probes"] and not coverage["guardrails"]:
            for framing in risk.get("alternative_framings", []):
                alt_coverage = query_coverage(framing["risk_id"])
                coverage["probes"].extend(alt_coverage["probes"])
                coverage["guardrails"].extend(alt_coverage["guardrails"])
                coverage["benchmarks"].extend(alt_coverage["benchmarks"])

        # Deduplicate
        coverage["probes"] = _dedup(coverage["probes"], "probe_id")
        coverage["guardrails"] = _dedup(coverage["guardrails"], "guardrail_id")
        coverage["benchmarks"] = _dedup(coverage["benchmarks"], "benchmark_id")

        gaps = _classify_coverage(coverage, risk.get("attack_dimensions", []))

        analyzed_risks.append({
            **risk,
            "coverage": {**coverage, "gaps": gaps},
        })

    # Summary
    total = len(analyzed_risks)
    with_probes = sum(1 for r in analyzed_risks if r["coverage"]["gaps"]["has_probes"])
    with_guardrails = sum(1 for r in analyzed_risks if r["coverage"]["gaps"]["has_guardrails"])
    with_benchmarks = sum(1 for r in analyzed_risks if r["coverage"]["gaps"]["has_benchmarks"])
    fully_covered = sum(
        1 for r in analyzed_risks
        if r["coverage"]["gaps"]["has_probes"] and r["coverage"]["gaps"]["has_guardrails"]
    )
    no_coverage = sum(
        1 for r in analyzed_risks
        if not r["coverage"]["gaps"]["has_probes"] and not r["coverage"]["gaps"]["has_guardrails"]
    )
    partial_gaps = total - fully_covered - no_coverage

    # Count amplified risks
    amplified = sum(len(r.get("alternative_framings", [])) for r in analyzed_risks)

    return {
        "client": client,
        "domain": domain,
        "source": source,
        "risks": analyzed_risks,
        "summary": {
            "total_risks": total,
            "amplified_risks": amplified,
            "risks_with_probes": with_probes,
            "risks_with_guardrails": with_guardrails,
            "risks_with_benchmarks": with_benchmarks,
            "fully_covered": fully_covered,
            "partial_gaps": partial_gaps,
            "no_coverage": no_coverage,
        },
    }


def _load_run(run_dir: Path) -> tuple[str, dict, dict]:
    """Load taxonomy and domain context from a refiner run directory."""
    # Find the taxonomy and domain context files
    taxonomy_files = list(run_dir.glob("*-enriched-taxonomy.yaml"))
    dc_files = list(run_dir.glob("*-enriched-domain-context.yaml"))

    if not taxonomy_files:
        raise FileNotFoundError(f"No taxonomy file found in {run_dir}")

    taxonomy_path = taxonomy_files[0]
    client_slug = taxonomy_path.name.replace("-enriched-taxonomy.yaml", "")

    with open(taxonomy_path) as f:
        taxonomy = yaml.safe_load(f)

    domain_ctx = {"profiles": []}
    if dc_files:
        with open(dc_files[0]) as f:
            domain_ctx = yaml.safe_load(f)

    return client_slug, taxonomy, domain_ctx


def _infer_domain(policy_file: Path) -> str:
    """Infer domain from policy file name or content."""
    name = policy_file.stem.lower()
    domain_map = {
        "swb": "finance",
        "healthcare": "healthcare",
        "generic": "general",
        "aramco": "energy",
        "dhs": "government",
    }
    for key, domain in domain_map.items():
        if key in name:
            return domain
    return "general"


def _dedup(items: list[dict], key: str) -> list[dict]:
    """Deduplicate list of dicts by a key field."""
    seen = set()
    result = []
    for item in items:
        k = item[key]
        if k not in seen:
            seen.add(k)
            result.append(item)
    return result


def main():
    parser = argparse.ArgumentParser(description="Stage 1: Coverage analysis")
    parser.add_argument("run_dir", nargs="?", type=Path, help="Refiner run directory")
    parser.add_argument("--policy", type=Path, help="Policy file (for domain identification)")
    parser.add_argument("--scenario", type=Path, help="Canned scenario JSON (fallback)")
    parser.add_argument("--output", type=Path, required=True, help="Output directory")
    args = parser.parse_args()

    if not args.run_dir and not args.scenario:
        parser.error("Either run_dir or --scenario must be provided")

    analysis = build_analysis(
        run_dir=args.run_dir,
        policy_file=args.policy,
        scenario=args.scenario,
    )

    args.output.mkdir(parents=True, exist_ok=True)
    out_path = args.output / "analysis.json"
    with open(out_path, "w") as f:
        json.dump(analysis, f, indent=2)

    print(f"Analysis written to {out_path}")
    s = analysis["summary"]
    print(f"  {s['total_risks']} risks, {s['amplified_risks']} amplified")
    print(f"  {s['fully_covered']} fully covered, {s['partial_gaps']} partial, {s['no_coverage']} uncovered")


if __name__ == "__main__":
    main()
