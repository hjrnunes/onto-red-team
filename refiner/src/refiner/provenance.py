"""PROV-O-style provenance sidecar writer.

Reads pipeline outputs (domain-context YAML, dataset JSONL) and writes a
provenance.jsonl capturing the derivation chain from policy through risk,
axis selection, enumeration, and sampling — in structured, queryable triples.

Convention: PROV-O relationship names (wasGeneratedBy, wasDerivedFrom,
wasAttributedTo, used, wasAssociatedWith) used as keys. Entities, Activities,
and Agents are plain string identifiers. Queryable with jq, compatible with
PROV-O JSON-LD export if needed later.
"""

import json
import logging
from pathlib import Path

import yaml

from refiner.models import DomainContextProfile

logger = logging.getLogger(__name__)


def _load_profiles(domain_context_path: Path) -> list[DomainContextProfile]:
    raw = yaml.safe_load(domain_context_path.read_text())
    return [DomainContextProfile(**p) for p in raw["profiles"]]


def write_provenance(
    domain_context_path: Path,
    dataset_path: Path,
    output_path: Path,
    model: str = "",
) -> None:
    """Write provenance.jsonl from domain-context YAML and dataset JSONL."""
    profiles = _load_profiles(domain_context_path)
    triples: list[dict] = []

    # --- Profile-level provenance (risk → axes → enumerations) ---
    for profile in profiles:
        profile_id = f"profile:{profile.risk_id}"

        triples.append({
            "entity": profile_id,
            "type": "DomainContextProfile",
            "risk_id": profile.risk_id,
            "risk_name": profile.risk_name,
            "policy_concept": profile.policy_concept,
            "wasGeneratedBy": "contextualize",
            "wasAssociatedWith": model,
        })

        for axis in profile.axes:
            axis_id = f"axis:{profile.risk_id}:{axis.cco_class_uri}"

            axis_triple: dict = {
                "entity": axis_id,
                "type": "DomainContextAxis",
                "cco_class_uri": axis.cco_class_uri,
                "cco_class_label": axis.cco_class_label,
                "bfo_category": axis.bfo_category,
                "wasGeneratedBy": "anchor",
                "wasAssociatedWith": model,
                "partOf": profile_id,
            }

            if axis.vocabulary_concept:
                axis_triple["wasDerivedFrom"] = axis.vocabulary_concept
                axis_triple["vocabulary_label"] = axis.vocabulary_label

            if axis.derivation:
                d = axis.derivation
                axis_triple["derivation_source"] = d.source
                if d.seed_uri:
                    axis_triple["derivation_seed"] = d.seed_uri
                if d.path:
                    axis_triple["derivation_path"] = d.path
                if d.effective_confidence:
                    axis_triple["derivation_confidence"] = d.effective_confidence
                if d.best_distance is not None:
                    axis_triple["derivation_distance"] = d.best_distance
                if d.domain:
                    axis_triple["derivation_domain"] = d.domain

            triples.append(axis_triple)

            for enum in axis.enumerations:
                enum_id = f"enum:{profile.risk_id}:{enum.class_uri}"
                enum_triple: dict = {
                    "entity": enum_id,
                    "type": "AxisEnumeration",
                    "class_uri": enum.class_uri,
                    "class_label": enum.class_label,
                    "source_ontology": enum.source_ontology,
                    "provenance": enum.provenance,
                    "relevance": enum.relevance,
                    "partOf": axis_id,
                }
                if enum.generated_by:
                    enum_triple["wasAssociatedWith"] = enum.generated_by
                triples.append(enum_triple)

    # --- Prompt-level provenance (sampled axes → prompts) ---
    if dataset_path.exists():
        with open(dataset_path) as f:
            for i, line in enumerate(f):
                row = json.loads(line)
                prompt_id = f"prompt:{i}"
                prompt_triple: dict = {
                    "entity": prompt_id,
                    "type": "AdversarialPrompt",
                    "wasGeneratedBy": "emit",
                    "risk_id": row.get("risk_id", ""),
                    "policy_concept": row.get("policy_concept", ""),
                    "technique": row.get("technique", ""),
                    "wasDerivedFrom": f"profile:{row.get('risk_id', '')}",
                }

                sampled = row.get("sampled_axes", [])
                if sampled:
                    prompt_triple["used"] = [
                        f"enum:{row.get('risk_id', '')}:{sa.get('sampled_uri', '')}"
                        for sa in sampled
                    ]

                triples.append(prompt_triple)

    # --- Write ---
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for t in triples:
            f.write(json.dumps(t) + "\n")

    logger.info("Wrote %d provenance triples to %s", len(triples), output_path)
