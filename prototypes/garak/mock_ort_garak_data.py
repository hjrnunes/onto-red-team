#!/usr/bin/env python3
"""Mock ORT-enriched garak data generator.

Takes an existing garak report/hitlog and an ORT Refiner run, then produces
re-keyed outputs where generic safety intents (S00Xfraud, etc.) are replaced
with Nexus risk-backed intents and linked to adversarial prompt stubs.

Output files (in prototypes/garak/mock_runs/):
  - ort-rdash.report.jsonl   — re-keyed garak report
  - ort-rdash.hitlog.jsonl    — re-keyed garak hitlog
  - ort_intent_mapping.json   — intent mapping with cross-framework data
  - ort_stubs.jsonl           — adversarial prompt stubs with stub IDs
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from itertools import cycle
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

GARAK_REPORT = (
    REPO_ROOT
    / "prototypes/garak/garak_runs"
    / "garak.0e04280f-b86a-45d3-b741-f763219cc2c3.report.jsonl"
)
GARAK_HITLOG = (
    REPO_ROOT
    / "prototypes/garak/garak_runs"
    / "garak.0e04280f-b86a-45d3-b741-f763219cc2c3.hitlog.jsonl"
)
ORT_RUN_DIR = REPO_ROOT / "runs/rdash-nhs-gemma-4-26b-a4b-it-g12"
OUTPUT_DIR = REPO_ROOT / "prototypes/garak/mock_runs"

# ---------------------------------------------------------------------------
# Intent re-keying: old generic intents -> new Nexus-backed intents
# ---------------------------------------------------------------------------

INTENT_REKEY: dict[str, str] = {
    "S001fraud": "S001regulatorycompliance",
    "S002hatespeech": "S002dataprivacy",
    "S003illegalactivity": "S003nondisclosure",
    "S004misinformation": "S004personalinformation",
    "S005securitymalware": "S005sensitiveinfo",
    "S006selfharm": "S006accountability",
    "S007sexuallyexplicit": "S007privacycompromise",
    "S008violence": "S008governancefailure",
}

# ---------------------------------------------------------------------------
# Nexus risk info per new intent
# ---------------------------------------------------------------------------

INTENT_TO_RISK: dict[str, dict[str, str]] = {
    "S001regulatorycompliance": {
        "risk_id": "credo-risk-023",
        "risk_name": "Regulatory compliance",
        "risk_framework": "Credo AI",
    },
    "S002dataprivacy": {
        "risk_id": "nist-data-privacy",
        "risk_name": "Data Privacy",
        "risk_framework": "NIST AI RMF",
    },
    "S003nondisclosure": {
        "risk_id": "atlas-non-disclosure",
        "risk_name": "Non-disclosure",
        "risk_framework": "IBM Risk Atlas",
    },
    "S004personalinformation": {
        "risk_id": "atlas-personal-information-in-data",
        "risk_name": "Personal information in data",
        "risk_framework": "IBM Risk Atlas",
    },
    "S005sensitiveinfo": {
        "risk_id": "credo-risk-037",
        "risk_name": "Compromised sensitive information",
        "risk_framework": "Credo AI",
    },
    "S006accountability": {
        "risk_id": "atlas-accountability-agentic",
        "risk_name": "Accountability of AI agent actions",
        "risk_framework": "IBM Risk Atlas",
    },
    "S007privacycompromise": {
        "risk_id": "mit-ai-risk-subdomain-2.1",
        "risk_name": "Compromise of privacy",
        "risk_framework": "MIT AI Risk Repository",
    },
    "S008governancefailure": {
        "risk_id": "mit-ai-risk-subdomain-6.5",
        "risk_name": "Governance failure",
        "risk_framework": "MIT AI Risk Repository",
    },
}

# ---------------------------------------------------------------------------
# Taxonomy risk groups
# ---------------------------------------------------------------------------

RISK_GROUPS: dict[str, list[str]] = {
    "Clinical Decision-Making & Care Planning": [
        "atlas-accountability-agentic",
        "credo-risk-023",
    ],
    "Protected Health Information & Data Privacy": [
        "nist-data-privacy",
        "atlas-personal-information-in-data",
        "credo-risk-037",
    ],
    "Research & Clinical Governance": [
        "mit-ai-risk-subdomain-6.5",
    ],
    "Patient Consent": [
        "mit-ai-risk-subdomain-2.1",
        "atlas-non-disclosure",
    ],
}

# Reverse lookup: risk_id -> group name
RISK_TO_GROUP: dict[str, str] = {
    risk_id: group
    for group, risk_ids in RISK_GROUPS.items()
    for risk_id in risk_ids
}


# ---------------------------------------------------------------------------
# Stub ID generation
# ---------------------------------------------------------------------------


def generate_stub_id(risk_id: str, technique: str, index: int) -> str:
    """Generate a deterministic stub ID from risk, technique, and index.

    Format: ``{risk_id}:{technique_slug}:{index}``
    where technique_slug has underscores replaced with hyphens.
    """
    technique_slug = technique.replace("_", "-")
    return f"{risk_id}:{technique_slug}:{index}"


# ---------------------------------------------------------------------------
# Load adversarial prompts and assign stub IDs
# ---------------------------------------------------------------------------


def load_adversarial_prompts(path: Path) -> list[dict]:
    """Load adversarial prompts JSONL and assign stub IDs.

    Stubs are grouped by (risk_id, technique) and indexed within each group.
    """
    entries: list[dict] = []
    with open(path) as f:
        for line in f:
            entries.append(json.loads(line))

    # Group by (risk_id, technique) to assign sequential indices
    group_counters: dict[tuple[str, str], int] = defaultdict(int)
    for entry in entries:
        key = (entry["risk_id"], entry["technique"])
        idx = group_counters[key]
        entry["stub_id"] = generate_stub_id(entry["risk_id"], entry["technique"], idx)
        group_counters[key] += 1

    return entries


# ---------------------------------------------------------------------------
# Cross-mapping loader
# ---------------------------------------------------------------------------


def load_cross_mappings(domain_ctx_path: Path) -> dict[str, list[dict]]:
    """Load cross-mappings from domain-context.yaml.

    Returns ``{nexus_risk_id: [{id, name, taxonomy, mapping_type}]}``.
    """
    with open(domain_ctx_path) as f:
        dc = yaml.safe_load(f)

    result: dict[str, list[dict]] = {}
    for risk in dc.get("risks", []):
        risk_id = risk["risk_id"]
        mappings = []
        for cm in risk.get("cross_mappings", []):
            mappings.append(
                {
                    "id": cm["id"],
                    "name": cm["name"],
                    "taxonomy": cm["taxonomy"],
                    "mapping_type": cm["mapping_type"],
                }
            )
        result[risk_id] = mappings
    return result


# ---------------------------------------------------------------------------
# Build risk-to-stubs index
# ---------------------------------------------------------------------------


def build_risk_to_stubs(prompts: list[dict]) -> dict[str, list[dict]]:
    """Group prompts by Nexus risk ID."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for p in prompts:
        groups[p["risk_id"]].append(p)
    return dict(groups)


# ---------------------------------------------------------------------------
# Re-key garak report
# ---------------------------------------------------------------------------


def rekey_report(report_path: Path, prompts: list[dict]) -> list[dict]:
    """Re-key a garak report.jsonl with ORT semantic data.

    - Maps old intents to new intents via INTENT_REKEY
    - Assigns stub IDs (cycling through stubs per risk)
    - Injects stub ID into notes.stub.id
    - Updates eval_intent entries with new intent IDs
    - Preserves all other fields
    """
    risk_stubs = build_risk_to_stubs(prompts)

    # Build cycling iterators per risk_id for stub assignment
    stub_cycles: dict[str, cycle] = {}
    for risk_id, stubs in risk_stubs.items():
        stub_cycles[risk_id] = cycle(stubs)

    entries: list[dict] = []
    with open(report_path) as f:
        for line in f:
            entry = json.loads(line)
            entry_type = entry.get("entry_type", "")

            if entry_type == "attempt":
                old_intent = entry.get("intent", "")
                new_intent = INTENT_REKEY.get(old_intent, old_intent)
                risk_info = INTENT_TO_RISK.get(new_intent)

                entry["intent"] = new_intent

                # Update notes.stub.intent
                if "notes" in entry and "stub" in entry["notes"]:
                    entry["notes"]["stub"]["intent"] = new_intent

                    # Assign a stub ID by cycling through available stubs
                    if risk_info:
                        risk_id = risk_info["risk_id"]
                        if risk_id in stub_cycles:
                            stub = next(stub_cycles[risk_id])
                            entry["notes"]["stub"]["id"] = stub["stub_id"]

            elif entry_type == "eval_intent":
                old_intent = entry.get("intent", "")
                new_intent = INTENT_REKEY.get(old_intent, old_intent)
                entry["intent"] = new_intent

            entries.append(entry)

    return entries


# ---------------------------------------------------------------------------
# Re-key garak hitlog
# ---------------------------------------------------------------------------


def rekey_hitlog(hitlog_path: Path) -> list[dict]:
    """Load hitlog entries (no intent field to re-key)."""
    entries: list[dict] = []
    with open(hitlog_path) as f:
        for line in f:
            entries.append(json.loads(line))
    return entries


# ---------------------------------------------------------------------------
# Build intent mapping JSON
# ---------------------------------------------------------------------------


def build_intent_mapping(cross_mappings: dict[str, list[dict]]) -> dict:
    """Build the ort_intent_mapping.json structure."""
    intent_map: dict[str, dict] = {}
    for intent_id, risk_info in INTENT_TO_RISK.items():
        risk_id = risk_info["risk_id"]
        intent_map[intent_id] = {
            "risk_id": risk_id,
            "risk_name": risk_info["risk_name"],
            "risk_framework": risk_info["risk_framework"],
            "risk_group": RISK_TO_GROUP.get(risk_id, "Unknown"),
            "cross_mappings": cross_mappings.get(risk_id, []),
        }

    return {
        "version": "0.1",
        "ort_run": "rdash-nhs-gemma-4-26b-a4b-it-g12",
        "policy_source": {
            "organization": "Rotherham Doncaster and South Humber NHS Foundation Trust (RDaSH)",
            "domain": "healthcare",
        },
        "curie_map": {
            "atlas": "https://www.ibm.com/docs/en/watsonx/saas?topic=risks/",
            "credo": "https://www.credo.ai/risk-catalog/",
            "nist": "https://airc.nist.gov/AI_RMF/",
            "mit": "https://airisk.mit.edu/",
            "granite-guardian": "https://github.com/ibm-granite/granite-guardian/",
        },
        "intent_map": intent_map,
    }


# ---------------------------------------------------------------------------
# JSONL writer
# ---------------------------------------------------------------------------


def write_jsonl(entries: list[dict], path: Path) -> None:
    """Write a list of dicts as JSONL."""
    with open(path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


def main() -> None:
    """Orchestrate ORT mock data generation."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Load adversarial prompts with stub IDs
    prompts_path = ORT_RUN_DIR / "rdash-nhs-adversarial-prompts.jsonl"
    print(f"Loading adversarial prompts from {prompts_path} ...")
    prompts = load_adversarial_prompts(prompts_path)
    print(f"  Loaded {len(prompts)} prompts")

    # 2. Load cross-mappings from domain context
    domain_ctx_path = ORT_RUN_DIR / "rdash-nhs-domain-context.yaml"
    print(f"Loading cross-mappings from {domain_ctx_path} ...")
    cross_mappings = load_cross_mappings(domain_ctx_path)
    total_mappings = sum(len(v) for v in cross_mappings.values())
    print(f"  Loaded cross-mappings for {len(cross_mappings)} risks ({total_mappings} total)")

    # 3. Re-key report
    print(f"Re-keying report from {GARAK_REPORT} ...")
    report_entries = rekey_report(GARAK_REPORT, prompts)
    attempt_count = sum(1 for e in report_entries if e.get("entry_type") == "attempt")
    print(f"  Re-keyed {attempt_count} attempts")

    # 4. Re-key hitlog
    print(f"Re-keying hitlog from {GARAK_HITLOG} ...")
    hitlog_entries = rekey_hitlog(GARAK_HITLOG)
    print(f"  Loaded {len(hitlog_entries)} hitlog entries")

    # 5. Build intent mapping
    print("Building intent mapping ...")
    intent_mapping = build_intent_mapping(cross_mappings)
    print(f"  {len(intent_mapping['intent_map'])} intents mapped")

    # 6. Write outputs
    report_out = OUTPUT_DIR / "ort-rdash.report.jsonl"
    hitlog_out = OUTPUT_DIR / "ort-rdash.hitlog.jsonl"
    mapping_out = OUTPUT_DIR / "ort_intent_mapping.json"
    stubs_out = OUTPUT_DIR / "ort_stubs.jsonl"

    write_jsonl(report_entries, report_out)
    print(f"  Wrote {len(report_entries)} entries to {report_out}")

    write_jsonl(hitlog_entries, hitlog_out)
    print(f"  Wrote {len(hitlog_entries)} entries to {hitlog_out}")

    with open(mapping_out, "w") as f:
        json.dump(intent_mapping, f, indent=2, ensure_ascii=False)
    print(f"  Wrote intent mapping to {mapping_out}")

    # Write stubs (prompts with stub IDs, without the full generation_prompt)
    stub_entries = []
    for p in prompts:
        stub_entries.append(
            {
                "stub_id": p["stub_id"],
                "risk_id": p["risk_id"],
                "risk_name": p.get("risk_name", ""),
                "risk_framework": p.get("risk_framework", ""),
                "technique": p["technique"],
                "technique_description": p.get("technique_description", ""),
                "policy_concept": p.get("policy_concept", ""),
                "prompt": p.get("prompt", ""),
                "sampled_axes": [
                    {
                        "cco_class_label": ax.get("cco_class_label", ""),
                        "sampled_label": ax.get("sampled_label", ""),
                        "source_ontology": ax.get("source_ontology", ""),
                        "relevance": ax.get("relevance", ""),
                    }
                    for ax in p.get("sampled_axes", [])
                ],
                "decomposition": p.get("decomposition", {}),
            }
        )
    write_jsonl(stub_entries, stubs_out)
    print(f"  Wrote {len(stub_entries)} stubs to {stubs_out}")

    # Summary
    print("\n--- Summary ---")
    print(f"  Report entries:  {len(report_entries)}")
    print(f"  Hitlog entries:  {len(hitlog_entries)}")
    print(f"  Stubs:           {len(stub_entries)}")
    print(f"  Intents mapped:  {len(intent_mapping['intent_map'])}")
    print(f"  Risk groups:     {len(RISK_GROUPS)}")
    print(f"  Cross-mappings:  {total_mappings}")

    # Intent distribution in re-keyed report
    intent_dist: Counter[str] = Counter()
    for e in report_entries:
        if e.get("entry_type") == "attempt":
            intent_dist[e.get("intent", "")] += 1
    print("\n  Intent distribution (attempts):")
    for intent, count in sorted(intent_dist.items()):
        risk_info = INTENT_TO_RISK.get(intent, {})
        risk_id = risk_info.get("risk_id", "?")
        print(f"    {intent}: {count} -> {risk_id}")

    print(f"\nOutputs written to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
