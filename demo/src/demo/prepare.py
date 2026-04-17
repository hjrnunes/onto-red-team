"""Prepare ORT data from a refiner run.

Reads the refiner run artifacts (domain-context.yaml, policy-document.json,
adversarial-prompts.jsonl) and produces an ORT run directory with:

- intent_mapping.json — S-number → risk metadata + cross-mappings
- stubs.jsonl — adversarial prompts with stub IDs
- data/cas/trait_typology.json — garak intent taxonomy
- data/cas/intent_stubs/*.json — garak prompt arrays per intent

Usage::

    ort prepare --run-dir ../runs/rdash-nhs-gemma-4-26b-a4b-it-g12

Functions are importable for notebook use::

    from demo.prepare import build_intent_mapping, build_stubs, write_garak_cas
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

import yaml

CURIE_MAP = {
    "airo": "https://w3id.org/airo#",
    "cco": "https://www.commoncoreontologies.org/",
    "obo": "http://purl.obolibrary.org/obo/",
    "d3fend": "http://d3fend.mitre.org/ontologies/d3fend.owl#",
    "cso": "http://taxonomy-refiner.io/ontologies/cso#",
    "lkif": "http://www.estrellaproject.org/lkif-core/",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sanitize_intent_name(name: str) -> str:
    # Match garak intent name regex: S([0-9]{3}([a-z]+)?) — letters only after prefix
    return re.sub(r"[^a-z]", "", str(name).lower())


def _find_file(directory: Path, pattern: str) -> Path:
    matches = list(directory.glob(pattern))
    if not matches:
        raise FileNotFoundError(f"No {pattern} in {directory}")
    return matches[0]


def write_jsonl(entries: list[dict], path: Path) -> None:
    with open(path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    entries: list[dict] = []
    with open(path) as f:
        for line in f:
            if line.strip():
                entries.append(json.loads(line))
    return entries


# ---------------------------------------------------------------------------
# Intent mapping
# ---------------------------------------------------------------------------


def build_intent_mapping(run_dir: Path) -> dict:
    """Build ORT intent mapping from a refiner run's domain context and policy doc.

    Returns a dict ready to serialize as intent_mapping.json, containing:
    - version, ort_run, policy_source, curie_map
    - intent_map: S-number → {nexus_risk_id, risk_name, risk_framework,
      risk_group, cross_mappings}
    """
    dc_path = _find_file(run_dir, "*-domain-context.yaml")
    pd_path = _find_file(run_dir, "*-policy-document.json")

    with open(dc_path) as f:
        dc = yaml.safe_load(f)
    with open(pd_path) as f:
        pd = json.load(f)

    run_slug = dc.get("run_slug", run_dir.name)
    risks = dc.get("risks", [])

    intent_map: dict[str, dict] = {}
    risk_id_to_intent: dict[str, str] = {}

    for i, risk in enumerate(risks):
        intent_id = f"S{i + 1:03d}{_sanitize_intent_name(risk['risk_name'])}"
        risk_id = risk["risk_id"]
        cross_mappings = [
            {
                "id": cm["id"],
                "name": cm["name"],
                "taxonomy": cm["taxonomy"],
                "mapping_type": cm["mapping_type"],
            }
            for cm in risk.get("cross_mappings", [])
        ]
        risk_id_to_intent[risk_id] = intent_id
        intent_map[intent_id] = {
            "nexus_risk_id": risk_id,
            "risk_name": risk["risk_name"],
            "risk_framework": risk["risk_framework"],
            "cross_mappings": cross_mappings,
        }

    # Derive risk groups from policy_contexts
    for pc in dc.get("policy_contexts", []):
        concept = pc.get("policy_concept", "Unknown")
        for rg in pc.get("risk_groundings", []):
            rid = rg.get("risk_id", "")
            intent_id = risk_id_to_intent.get(rid)
            if intent_id and intent_id in intent_map:
                intent_map[intent_id]["risk_group"] = concept

    # Fill missing risk groups
    for info in intent_map.values():
        info.setdefault("risk_group", "Unknown")

    policy_source = {
        "organization": pd.get("organization", {}).get("name", "Unknown"),
        "domain": pd.get("domain", "unknown"),
    }

    return {
        "version": "0.1",
        "ort_run": run_slug,
        "policy_source": policy_source,
        "curie_map": CURIE_MAP,
        "intent_map": intent_map,
    }


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


def _generate_stub_id(risk_id: str, technique: str, index: int) -> str:
    technique_slug = technique.replace("_", "-")
    return f"{risk_id}:{technique_slug}:{index}"


def build_stubs(run_dir: Path) -> list[dict]:
    """Load adversarial prompts from a refiner run and assign stub IDs.

    Returns a list of stub dicts, each with: id, risk_id, risk_name,
    risk_framework, technique, technique_description, policy_concept,
    prompt, sampled_axes, decomposition.
    """
    prompts_path = _find_file(run_dir, "*-adversarial-prompts.jsonl")
    entries = read_jsonl(prompts_path)

    group_counters: dict[tuple[str, str], int] = defaultdict(int)
    stubs: list[dict] = []

    for entry in entries:
        key = (entry["risk_id"], entry["technique"])
        idx = group_counters[key]
        group_counters[key] += 1

        stub_id = entry.get("prompt_id") or _generate_stub_id(entry["risk_id"], entry["technique"], idx)

        stubs.append({
            "id": stub_id,
            "risk_id": entry["risk_id"],
            "risk_name": entry.get("risk_name", ""),
            "risk_framework": entry.get("risk_framework", ""),
            "technique": entry["technique"],
            "technique_description": entry.get("technique_description", ""),
            "policy_concept": entry.get("policy_concept", ""),
            "prompt": entry.get("prompt", ""),
            "sampled_axes": [
                {
                    "cco_class_uri": ax.get("cco_class_uri", ""),
                    "cco_class_label": ax.get("cco_class_label", ""),
                    "bfo_category": ax.get("bfo_category", ""),
                    "sampled_label": ax.get("sampled_label", ""),
                    "source_ontology": ax.get("source_ontology", ""),
                    "relevance": ax.get("relevance", ""),
                }
                for ax in entry.get("sampled_axes", [])
            ],
            "decomposition": entry.get("decomposition", {}),
        })

    return stubs


# ---------------------------------------------------------------------------
# Garak CAS format
# ---------------------------------------------------------------------------


def _risk_id_to_intent(
    intent_mapping: dict,
) -> dict[str, str]:
    """Build reverse lookup: nexus_risk_id → intent S-number."""
    return {
        info["nexus_risk_id"]: intent_id
        for intent_id, info in intent_mapping["intent_map"].items()
    }


def write_garak_cas(
    stubs: list[dict],
    intent_mapping: dict,
    output_dir: Path,
    *,
    cas_subdir: str = "data/cas",
    take_per_intent: int | None = None,
) -> Path:
    """Write garak CAS format: trait_typology.json + intent_stubs/*.json.

    Returns the path to the CAS directory.
    """
    cas_dir = output_dir / cas_subdir
    stubs_dir = cas_dir / "intent_stubs"
    stubs_dir.mkdir(parents=True, exist_ok=True)

    rid_to_intent = _risk_id_to_intent(intent_mapping)

    # Build trait typology
    typology: dict[str, dict] = {}
    for intent_id, info in intent_mapping["intent_map"].items():
        typology[intent_id] = {
            "name": info["risk_name"],
            "descr": info.get("risk_group", ""),
        }

    # Group stubs by intent (dict format with IDs for garak stub-id support)
    stubs_by_intent: dict[str, list[dict]] = defaultdict(list)
    for stub in stubs:
        intent_id = rid_to_intent.get(stub["risk_id"])
        if intent_id and stub.get("prompt"):
            stubs_by_intent[intent_id].append({
                "content": stub["prompt"],
                "id": stub["id"],
            })

    # Apply take_per_intent limit
    if take_per_intent:
        for intent_id in stubs_by_intent:
            stubs_by_intent[intent_id] = stubs_by_intent[intent_id][:take_per_intent]

    # Write files
    with open(cas_dir / "trait_typology.json", "w") as f:
        json.dump(typology, f, indent=2, ensure_ascii=False)

    for intent_id, prompts in stubs_by_intent.items():
        with open(stubs_dir / f"{intent_id}.json", "w") as f:
            json.dump(prompts, f, indent=2, ensure_ascii=False)

    return cas_dir


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def prepare(
    run_dir: Path,
    output_dir: Path,
    *,
    take_per_intent: int | None = None,
) -> dict:
    """Run the full prepare stage.

    Returns a summary dict with counts.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Building intent mapping from {run_dir.name} ...")
    mapping = build_intent_mapping(run_dir)
    print(f"  {len(mapping['intent_map'])} intents mapped")

    with open(output_dir / "intent_mapping.json", "w") as f:
        json.dump(mapping, f, indent=2, ensure_ascii=False)

    print("Building stubs ...")
    stubs = build_stubs(run_dir)
    print(f"  {len(stubs)} stubs loaded")

    write_jsonl(stubs, output_dir / "stubs.jsonl")

    print("Writing garak CAS format ...")
    cas_dir = write_garak_cas(
        stubs, mapping, output_dir, take_per_intent=take_per_intent,
    )
    intent_stubs_dir = cas_dir / "intent_stubs"
    n_files = len(list(intent_stubs_dir.glob("*.json")))
    print(f"  {n_files} intent stub files in {cas_dir}")

    # Summary
    risk_ids = {s["risk_id"] for s in stubs}
    techniques = {s["technique"] for s in stubs}

    summary = {
        "intents": len(mapping["intent_map"]),
        "stubs": len(stubs),
        "risks": len(risk_ids),
        "techniques": len(techniques),
        "cas_dir": str(cas_dir),
    }

    print(f"\n  Risks:       {summary['risks']}")
    print(f"  Techniques:  {summary['techniques']}")
    print(f"  Total stubs: {summary['stubs']}")
    print(f"\nOutputs: {output_dir}")

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare ORT data from a refiner run")
    parser.add_argument(
        "--run-dir", type=Path, required=True,
        help="Path to a refiner run directory",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=None,
        help="Output directory (default: demo_runs/<run-slug>)",
    )
    parser.add_argument(
        "--take-per-intent", type=int, default=None,
        help="Max stubs per intent in garak CAS (default: all)",
    )
    args = parser.parse_args()

    run_dir = args.run_dir.resolve()
    output_dir = args.output_dir
    if output_dir is None:
        dc_path = _find_file(run_dir, "*-domain-context.yaml")
        with open(dc_path) as f:
            dc = yaml.safe_load(f)
        slug = dc.get("run_slug", run_dir.name)
        output_dir = Path("demo_runs") / slug

    prepare(run_dir, output_dir.resolve(), take_per_intent=args.take_per_intent)


if __name__ == "__main__":
    main()
