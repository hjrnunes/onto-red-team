#!/usr/bin/env python3
"""Mock ORT-enriched garak data generator.

Takes an existing garak report/hitlog and an ORT Refiner run, then produces
re-keyed outputs where generic safety intents (S00Xfraud, etc.) are replaced
with Nexus risk-backed intents and linked to adversarial prompt stubs.

Usage::

    cd refiner
    uv run python ../prototypes/garak/mock_ort_garak_data.py --run-dir ../runs/rdash-nhs-gemma-4-26b-a4b-it-g12

Output files (in prototypes/garak/mock_runs/<run-slug>/):
  - report.jsonl          — re-keyed garak report
  - hitlog.jsonl          — re-keyed garak hitlog
  - intent_mapping.json   — intent mapping with cross-framework data
  - stubs.jsonl           — adversarial prompt stubs with stub IDs
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from itertools import cycle
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent

GARAK_REPORT = (
    SCRIPT_DIR
    / "garak_runs"
    / "garak.0e04280f-b86a-45d3-b741-f763219cc2c3.report.jsonl"
)
GARAK_HITLOG = (
    SCRIPT_DIR
    / "garak_runs"
    / "garak.0e04280f-b86a-45d3-b741-f763219cc2c3.hitlog.jsonl"
)

# The 8 generic intents in the existing garak report
OLD_INTENTS = [
    "S001fraud",
    "S002hatespeech",
    "S003illegalactivity",
    "S004misinformation",
    "S005securitymalware",
    "S006selfharm",
    "S007sexuallyexplicit",
    "S008violence",
]


# ---------------------------------------------------------------------------
# Derive mappings from run data
# ---------------------------------------------------------------------------


def _sanitize_intent_name(name: str) -> str:
    """Turn a risk name into a lowercase S-number suffix."""
    return re.sub(r"[^a-z0-9]", "", name.lower())[:30]


def derive_mappings(run_dir: Path) -> tuple[
    dict[str, str],           # intent_rekey: old_intent -> new_intent
    dict[str, dict[str, str]],  # intent_to_risk: new_intent -> risk info
    dict[str, list[str]],     # risk_groups: group_name -> [risk_ids]
    dict[str, str],           # risk_to_group: risk_id -> group_name
    dict,                     # policy_source metadata
    str,                      # run slug
]:
    """Derive all mappings from a Refiner run's domain context and policy doc."""
    # Find files by glob (names are prefixed with the run slug)
    dc_files = list(run_dir.glob("*-domain-context.yaml"))
    if not dc_files:
        raise FileNotFoundError(f"No domain-context.yaml in {run_dir}")
    dc_path = dc_files[0]

    pd_files = list(run_dir.glob("*-policy-document.json"))
    if not pd_files:
        raise FileNotFoundError(f"No policy-document.json in {run_dir}")
    pd_path = pd_files[0]

    with open(dc_path) as f:
        dc = yaml.safe_load(f)

    with open(pd_path) as f:
        pd = json.load(f)

    run_slug = dc.get("run_slug", run_dir.name)

    # Extract risks (capped at 8 to match garak S-number slots)
    risks = dc.get("risks", [])[:8]

    # Build intent_rekey and intent_to_risk
    intent_rekey: dict[str, str] = {}
    intent_to_risk: dict[str, dict[str, str]] = {}
    for i, risk in enumerate(risks):
        old_intent = OLD_INTENTS[i]
        new_intent = f"S{i + 1:03d}{_sanitize_intent_name(risk['risk_name'])}"
        intent_rekey[old_intent] = new_intent
        intent_to_risk[new_intent] = {
            "nexus_risk_id": risk["risk_id"],
            "risk_name": risk["risk_name"],
            "risk_framework": risk["risk_framework"],
        }

    # Build risk groups from policy_contexts
    risk_groups: dict[str, list[str]] = {}
    for pc in dc.get("policy_contexts", []):
        concept = pc.get("policy_concept", "Unknown")
        group_risk_ids = []
        for rg in pc.get("risk_groundings", []):
            rid = rg.get("risk_id", "")
            # Only include risks that are in our mapped set
            if rid and any(
                r["nexus_risk_id"] == rid for r in intent_to_risk.values()
            ):
                group_risk_ids.append(rid)
        if group_risk_ids:
            risk_groups[concept] = group_risk_ids

    # Reverse lookup
    risk_to_group: dict[str, str] = {
        rid: group
        for group, rids in risk_groups.items()
        for rid in rids
    }

    # Policy source
    policy_source = {
        "organization": pd.get("organization", {}).get("name", "Unknown"),
        "domain": pd.get("domain", "unknown"),
    }

    return (
        intent_rekey, intent_to_risk, risk_groups, risk_to_group,
        policy_source, run_slug,
    )


# ---------------------------------------------------------------------------
# Stub ID generation
# ---------------------------------------------------------------------------


def generate_stub_id(risk_id: str, technique: str, index: int) -> str:
    """Generate a deterministic stub ID from risk, technique, and index."""
    technique_slug = technique.replace("_", "-")
    return f"{risk_id}:{technique_slug}:{index}"


# ---------------------------------------------------------------------------
# Load adversarial prompts and assign stub IDs
# ---------------------------------------------------------------------------


def load_adversarial_prompts(run_dir: Path) -> list[dict]:
    """Load adversarial prompts JSONL from a run dir and assign stub IDs."""
    prompt_files = list(run_dir.glob("*-adversarial-prompts.jsonl"))
    if not prompt_files:
        raise FileNotFoundError(f"No adversarial-prompts.jsonl in {run_dir}")

    entries: list[dict] = []
    with open(prompt_files[0]) as f:
        for line in f:
            if line.strip():
                entries.append(json.loads(line))

    group_counters: dict[tuple[str, str], int] = defaultdict(int)
    for entry in entries:
        key = (entry["risk_id"], entry["technique"])
        idx = group_counters[key]
        entry["stub_id"] = generate_stub_id(
            entry["risk_id"], entry["technique"], idx,
        )
        group_counters[key] += 1

    return entries


# ---------------------------------------------------------------------------
# Cross-mapping loader
# ---------------------------------------------------------------------------


def load_cross_mappings(run_dir: Path) -> dict[str, list[dict]]:
    """Load cross-mappings from domain-context.yaml."""
    dc_files = list(run_dir.glob("*-domain-context.yaml"))
    with open(dc_files[0]) as f:
        dc = yaml.safe_load(f)

    result: dict[str, list[dict]] = {}
    for risk in dc.get("risks", []):
        risk_id = risk["risk_id"]
        mappings = []
        for cm in risk.get("cross_mappings", []):
            mappings.append({
                "id": cm["id"],
                "name": cm["name"],
                "taxonomy": cm["taxonomy"],
                "mapping_type": cm["mapping_type"],
            })
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


def rekey_report(
    report_path: Path,
    prompts: list[dict],
    intent_rekey: dict[str, str],
    intent_to_risk: dict[str, dict[str, str]],
) -> list[dict]:
    """Re-key a garak report.jsonl with ORT semantic data."""
    risk_stubs = build_risk_to_stubs(prompts)

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
                if old_intent not in intent_rekey:
                    continue  # skip attempts for unmapped intents
                new_intent = intent_rekey[old_intent]
                risk_info = intent_to_risk.get(new_intent)

                entry["intent"] = new_intent

                notes = entry.get("notes", {})
                if not isinstance(notes, dict):
                    notes = {}
                if "stub" not in notes:
                    notes["stub"] = {}
                if not isinstance(notes["stub"], dict):
                    notes["stub"] = {}
                notes["stub"]["intent"] = new_intent
                entry["notes"] = notes

                if risk_info:
                    risk_id = risk_info["nexus_risk_id"]
                    if risk_id in stub_cycles:
                        stub = next(stub_cycles[risk_id])
                        notes["stub"]["id"] = stub["stub_id"]

            elif entry_type == "eval_intent":
                old_intent = entry.get("intent", "")
                if old_intent not in intent_rekey:
                    continue  # skip eval_intent for unmapped intents
                new_intent = intent_rekey[old_intent]
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


def build_intent_mapping(
    intent_to_risk: dict[str, dict[str, str]],
    risk_to_group: dict[str, str],
    cross_mappings: dict[str, list[dict]],
    policy_source: dict,
    run_slug: str,
) -> dict:
    """Build the ort_intent_mapping.json structure."""
    intent_map: dict[str, dict] = {}
    for intent_id, risk_info in intent_to_risk.items():
        risk_id = risk_info["nexus_risk_id"]
        intent_map[intent_id] = {
            "nexus_risk_id": risk_id,
            "risk_name": risk_info["risk_name"],
            "risk_framework": risk_info["risk_framework"],
            "risk_group": risk_to_group.get(risk_id, "Unknown"),
            "cross_mappings": cross_mappings.get(risk_id, []),
        }

    return {
        "version": "0.1",
        "ort_run": run_slug,
        "policy_source": policy_source,
        "curie_map": {
            "airo": "https://w3id.org/airo#",
            "cco": "https://www.commoncoreontologies.org/",
            "obo": "http://purl.obolibrary.org/obo/",
            "d3fend": "http://d3fend.mitre.org/ontologies/d3fend.owl#",
            "cso": "http://taxonomy-refiner.io/ontologies/cso#",
            "lkif": "http://www.estrellaproject.org/lkif-core/",
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
    parser = argparse.ArgumentParser(description="Mock ORT garak data generator")
    parser.add_argument(
        "--run-dir", type=Path, required=True,
        help="Path to a Refiner run directory",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=None,
        help="Output directory (default: mock_runs/<run-slug>)",
    )
    args = parser.parse_args()

    run_dir = args.run_dir.resolve()

    # Derive all mappings from run data
    print(f"Deriving mappings from {run_dir.name} ...")
    (
        intent_rekey, intent_to_risk, risk_groups, risk_to_group,
        policy_source, run_slug,
    ) = derive_mappings(run_dir)
    print(f"  {len(intent_to_risk)} risks mapped to S-number intents")
    print(f"  {len(risk_groups)} risk groups")

    output_dir = args.output_dir or (SCRIPT_DIR / "mock_runs" / run_slug)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load adversarial prompts with stub IDs
    print(f"Loading adversarial prompts ...")
    prompts = load_adversarial_prompts(run_dir)
    print(f"  Loaded {len(prompts)} prompts")

    # 2. Load cross-mappings
    print(f"Loading cross-mappings ...")
    cross_mappings = load_cross_mappings(run_dir)
    total_mappings = sum(len(v) for v in cross_mappings.values())
    print(f"  {len(cross_mappings)} risks, {total_mappings} total mappings")

    # 3. Re-key report
    print(f"Re-keying report ...")
    report_entries = rekey_report(
        GARAK_REPORT, prompts, intent_rekey, intent_to_risk,
    )
    attempt_count = sum(
        1 for e in report_entries if e.get("entry_type") == "attempt"
    )
    print(f"  Re-keyed {attempt_count} attempts")

    # 4. Re-key hitlog
    print(f"Re-keying hitlog ...")
    hitlog_entries = rekey_hitlog(GARAK_HITLOG)
    print(f"  {len(hitlog_entries)} hitlog entries")

    # 5. Build intent mapping
    print("Building intent mapping ...")
    intent_mapping = build_intent_mapping(
        intent_to_risk, risk_to_group, cross_mappings,
        policy_source, run_slug,
    )
    print(f"  {len(intent_mapping['intent_map'])} intents mapped")

    # 6. Write outputs
    write_jsonl(report_entries, output_dir / "report.jsonl")
    write_jsonl(hitlog_entries, output_dir / "hitlog.jsonl")

    with open(output_dir / "intent_mapping.json", "w") as f:
        json.dump(intent_mapping, f, indent=2, ensure_ascii=False)

    stub_entries = []
    for p in prompts:
        stub_entries.append({
            "id": p["stub_id"],
            "risk_id": p["risk_id"],
            "risk_name": p.get("risk_name", ""),
            "risk_framework": p.get("risk_framework", ""),
            "technique": p["technique"],
            "technique_description": p.get("technique_description", ""),
            "policy_concept": p.get("policy_concept", ""),
            "prompt": p.get("prompt", ""),
            "sampled_axes": [
                {
                    "cco_class_uri": ax.get("cco_class_uri", ""),
                    "cco_class_label": ax.get("cco_class_label", ""),
                    "bfo_category": ax.get("bfo_category", ""),
                    "sampled_label": ax.get("sampled_label", ""),
                    "source_ontology": ax.get("source_ontology", ""),
                    "relevance": ax.get("relevance", ""),
                }
                for ax in p.get("sampled_axes", [])
            ],
            "decomposition": p.get("decomposition", {}),
        })
    write_jsonl(stub_entries, output_dir / "stubs.jsonl")

    # Summary
    print(f"\n--- {run_slug} ---")
    print(f"  Report entries:  {len(report_entries)}")
    print(f"  Stubs:           {len(stub_entries)}")
    print(f"  Intents:         {len(intent_mapping['intent_map'])}")
    print(f"  Risk groups:     {len(risk_groups)}")
    print(f"  Cross-mappings:  {total_mappings}")

    intent_dist: Counter[str] = Counter()
    for e in report_entries:
        if e.get("entry_type") == "attempt":
            intent_dist[e.get("intent", "")] += 1
    print("\n  Intent distribution:")
    for intent, count in sorted(intent_dist.items()):
        risk_info = intent_to_risk.get(intent, {})
        name = risk_info.get("risk_name", "?")
        print(f"    {intent}: {count} -> {name}")

    print(f"\nOutputs: {output_dir}")


if __name__ == "__main__":
    main()
