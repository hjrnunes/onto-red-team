"""Two-layer SSSOM seed mapping loader and resolver.

Layer 1: RiskGroup → AIRO/DPV vocabulary concepts (structured LLM context)
Layer 2: AIRO/DPV → Domain Ontology branches (structural navigation targets)
"""

import csv
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Namespace → vocabulary category mapping
_VOCAB_CATEGORIES = {
    "eu-aiact": "stakeholders",
    "tech": "stakeholders",
    "airo": "risk_concepts",
    "pd": "data_sensitivity",
    "eu-rights": "rights",
    "justifications": "justifications",
    "sector-finance": "sector_purposes",
    "sector-health": "sector_purposes",
    "sector-law": "sector_purposes",
    "sector-education": "sector_purposes",
    "sector-infra": "sector_purposes",
    "sector-publicservices": "sector_purposes",
    "risk": "risk_concepts",
}

# EU AI Act concepts that are prohibited practices, not stakeholder roles
_PROHIBITED_PRACTICES = {"eu-aiact:DeepFake", "eu-aiact:EmotionRecognition"}


def _expand_curie(value: str, curie_map: dict[str, str]) -> str:
    """Expand a CURIE (e.g. 'cco:Organization') to a full URI using curie_map."""
    if ":" not in value or value.startswith("http://") or value.startswith("https://"):
        return value
    prefix, _, local = value.partition(":")
    if prefix in curie_map:
        return curie_map[prefix] + local
    return value


@dataclass(frozen=True)
class SSSOMMapping:
    subject_id: str
    subject_label: str
    predicate_id: str
    object_id: str
    object_label: str
    mapping_justification: str
    confidence: float


class SSSOMIndex:
    """Index of SSSOM mappings, keyed by subject_id for fast lookup."""

    def __init__(self, mappings: list[SSSOMMapping]):
        self.mappings = mappings
        self._by_subject: dict[str, list[SSSOMMapping]] = {}
        for m in mappings:
            self._by_subject.setdefault(m.subject_id, []).append(m)

    @classmethod
    def from_tsv(cls, path: Path, *, expand_objects: bool = False) -> "SSSOMIndex":
        curie_map: dict[str, str] = {}
        mappings = []
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter="\t")
            header_seen = False
            for row in reader:
                if not row:
                    continue
                line = row[0]
                if line.startswith("#"):
                    if expand_objects:
                        # Parse curie_map entries: "#   prefix: uri"
                        stripped = line.lstrip("#").strip()
                        if ":" in stripped and stripped[0] != "{" and stripped != "curie_map:":
                            prefix, _, uri = stripped.partition(":")
                            prefix = prefix.strip()
                            uri = uri.strip()
                            if uri and not uri.startswith("#"):
                                curie_map[prefix] = uri
                    continue
                if not header_seen:
                    header_seen = True
                    continue  # skip header row
                if len(row) < 7:
                    continue
                object_id = row[3].strip()
                if expand_objects:
                    object_id = _expand_curie(object_id, curie_map)
                mappings.append(SSSOMMapping(
                    subject_id=row[0].strip(),
                    subject_label=row[1].strip(),
                    predicate_id=row[2].strip(),
                    object_id=object_id,
                    object_label=row[4].strip(),
                    mapping_justification=row[5].strip(),
                    confidence=float(row[6].strip()),
                ))
        return cls(mappings)

    def get_by_subject(self, subject_id: str) -> list[SSSOMMapping]:
        return list(self._by_subject.get(subject_id, []))


def categorize_vocabulary(vocab_seeds: list[SSSOMMapping]) -> dict[str, list[dict]]:
    """Categorize AIRO/DPV vocabulary seeds by namespace for structured LLM context."""
    categories: dict[str, list[dict]] = {
        "stakeholders": [],
        "data_sensitivity": [],
        "rights": [],
        "justifications": [],
        "sector_purposes": [],
        "risk_concepts": [],
        "prohibited_practices": [],
    }
    seen = set()
    for seed in vocab_seeds:
        concept_id = seed.object_id
        if concept_id in seen:
            continue
        seen.add(concept_id)

        entry = {
            "concept_id": concept_id,
            "label": seed.object_label,
            "confidence": seed.confidence,
        }

        # Check for prohibited practices first (override namespace-based categorization)
        if concept_id in _PROHIBITED_PRACTICES:
            categories["prohibited_practices"].append(entry)
            continue

        prefix = concept_id.split(":")[0] if ":" in concept_id else ""
        category = _VOCAB_CATEGORIES.get(prefix, "risk_concepts")
        categories[category].append(entry)

    return categories


def load_bfo_fallbacks(path: Path) -> dict[str, str]:
    """Load ontology-to-BFO SSSOM mappings as a URI → category lookup.

    The object_id column in this file contains BFO category *labels* (e.g.
    ``Act``, ``InformationContentEntity``) rather than URIs, so we use them
    directly.
    """
    index = SSSOMIndex.from_tsv(path)
    fallbacks: dict[str, str] = {}
    for m in index.mappings:
        if m.subject_id not in fallbacks:
            fallbacks[m.subject_id] = m.object_id
    return fallbacks


def _deduplicate_seeds(seeds: list[dict], key: str = "object_id") -> list[dict]:
    """Deduplicate seed dicts, keeping highest effective_confidence per key."""
    best: dict[str, dict] = {}
    for s in seeds:
        k = s[key]
        if k not in best or s.get("effective_confidence", 0) > best[k].get("effective_confidence", 0):
            best[k] = s
    return list(best.values())


def resolve_seeds(
    risk_id: str,
    risk_group_id: str | None,
    nexus_handlers: dict,
    layer1_mappings: SSSOMIndex,
    layer2_mappings: SSSOMIndex,
) -> tuple[dict[str, list[dict]], list[dict]]:
    """Resolve two-layer SSSOM seed mappings for a risk.

    Returns:
        vocabulary_context: categorized AIRO/DPV concepts for LLM context
        ontology_seeds: domain ontology branch URIs for structural navigation
    """
    # --- Layer 1: Risk → AIRO/DPV vocabulary ---
    vocab_seeds: list[SSSOMMapping] = []

    # 1. Direct risk-level vocabulary mappings
    vocab_seeds += layer1_mappings.get_by_subject(risk_id)

    # 2. RiskGroup-level vocabulary mappings
    if risk_group_id:
        vocab_seeds += layer1_mappings.get_by_subject(risk_group_id)

    # 3. Cross-taxonomy fallback: resolve non-IBM risks to IBM equivalents
    if not vocab_seeds and not risk_id.startswith("ibm-risk-atlas"):
        related = nexus_handlers["get_related_risks"](risk_id)
        for rel in related:
            rel_id = rel["id"]
            rel_taxonomy = rel.get("taxonomy", "")
            if rel_taxonomy == "ibm-risk-atlas" or rel_id.startswith("atlas-"):
                details = nexus_handlers["get_risk_details"](rel_id)
                if details and details.get("group"):
                    ibm_group = details["group"]
                    vocab_seeds += layer1_mappings.get_by_subject(ibm_group)
                    vocab_seeds += layer1_mappings.get_by_subject(rel_id)
                break

    # Deduplicate vocab seeds by object_id, keeping highest confidence
    seen_vocab: dict[str, SSSOMMapping] = {}
    for vs in vocab_seeds:
        if vs.object_id not in seen_vocab or vs.confidence > seen_vocab[vs.object_id].confidence:
            seen_vocab[vs.object_id] = vs
    vocab_seeds = list(seen_vocab.values())

    # --- Layer 2: AIRO/DPV → Domain Ontology ---
    ontology_seeds: list[dict] = []
    for vs in vocab_seeds:
        layer2_hits = layer2_mappings.get_by_subject(vs.object_id)
        for hit in layer2_hits:
            ontology_seeds.append({
                "subject_id": hit.subject_id,
                "subject_label": hit.subject_label,
                "predicate_id": hit.predicate_id,
                "object_id": hit.object_id,
                "object_label": hit.object_label,
                "confidence": hit.confidence,
                "effective_confidence": vs.confidence * hit.confidence,
                "vocabulary_concept": vs.object_id,
                "vocabulary_label": vs.object_label,
            })

    # Direct fallback seeds (RiskGroup → Ontology, no intermediate)
    if risk_group_id:
        direct = layer2_mappings.get_by_subject(risk_group_id)
        for ds in direct:
            ontology_seeds.append({
                "subject_id": ds.subject_id,
                "subject_label": ds.subject_label,
                "predicate_id": ds.predicate_id,
                "object_id": ds.object_id,
                "object_label": ds.object_label,
                "confidence": ds.confidence,
                "effective_confidence": ds.confidence,
                "vocabulary_concept": None,
                "vocabulary_label": None,
            })

    ontology_seeds = _deduplicate_seeds(ontology_seeds)

    # --- Build vocabulary context for LLM ---
    vocabulary_context = categorize_vocabulary(vocab_seeds)

    return vocabulary_context, ontology_seeds
