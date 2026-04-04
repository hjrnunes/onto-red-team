import logging
from typing import Protocol, runtime_checkable

import instructor
from pydantic import BaseModel
from refiner.llm import LLMConfig
from refiner.models import (
    PolicyRiskMapping,
    RiskVariationAxes,
    VariationAxis,
)
from refiner import debug
from refiner.stages.identify_domains import derive_source_ontology, ALWAYS_INCLUDED

logger = logging.getLogger(__name__)

# BFO classes are maximally abstract ontological primitives — useful for role
# derivation via superclass chains but never appropriate as candidate axes
# (they produce vague, jargon-laden scenarios like "generically dependent continuant").
_BFO_URI_PREFIX = "http://purl.obolibrary.org/obo/BFO_"

# LKIF normative deontic-status classes describe permissibility categories
# (allowed/disallowed/obliged), not domain concepts that can ground adversarial
# scenarios. When sampled, they leak raw taxonomy labels into prompts.
# Legal instrument classes (Statute, Directive, Code, Contract) are kept.
_LKIF_PREFIX = "http://www.estrellaproject.org/lkif-core/"
_LKIF_NORMATIVE_URIS: set[str] = {
                                     # Deontic status meta-labels — describe permissibility, not domain concepts
                                     f"{_LKIF_PREFIX}norm.owl#{name}"
                                     for name in (
        "Disallowed", "Disallowed_Intention", "Strictly_Disallowed",
        "Allowed", "Allowed_And_Disallowed", "Strictly_Allowed",
        "Observation_of_Violation", "Belief_In_Violation", "Obliged",
    )
                                 } | {
                                     # Upper-ontology primitives — too abstract to ground scenarios
                                     f"{_LKIF_PREFIX}expression.owl#Intention",
                                     f"{_LKIF_PREFIX}expression.owl#Belief",
                                     f"{_LKIF_PREFIX}action.owl#Agent",
                                     f"{_LKIF_PREFIX}process.owl#Mental_Process",
                                 }


def _is_excluded_uri(uri: str, generic_safety_uris: set[str]) -> bool:
    """Check if a URI should be excluded from candidate pools.

    Excludes BFO upper-ontology classes (always), LKIF normative deontic-status
    classes (always), and generic safety URIs (when set).
    """
    if uri.startswith(_BFO_URI_PREFIX):
        return True
    if uri in _LKIF_NORMATIVE_URIS:
        return True
    if generic_safety_uris and uri in generic_safety_uris:
        return True
    return False


# BFO/CCO/Commons category → semantic roles mapping.
# More specific categories are checked first (via superclass walk),
# falling back to broader categories.
_CATEGORY_ROLES: dict[str, list[str]] = {
    # CCO categories (more specific — checked first)
    "https://www.commoncoreontologies.org/ont00001017": ["agent"],  # Agent
    "https://www.commoncoreontologies.org/ont00000995": ["object", "instrument"],  # Material Artifact
    "https://www.commoncoreontologies.org/ont00000005": ["object"],  # Act (process)
    "https://www.commoncoreontologies.org/ont00000958": ["object", "instrument"],  # Information Content Entity
    "https://www.commoncoreontologies.org/ont00000192": ["location"],  # Facility (not bridged — Material Artifact, not spatial)
    # BFO categories (broader fallback)
    "http://purl.obolibrary.org/obo/BFO_0000040": ["agent", "object"],  # material entity
    "http://purl.obolibrary.org/obo/BFO_0000015": ["object"],  # process
    "http://purl.obolibrary.org/obo/BFO_0000023": ["agent"],  # role (bearer acts)
    "http://purl.obolibrary.org/obo/BFO_0000016": ["instrument"],  # disposition
    "http://purl.obolibrary.org/obo/BFO_0000031": ["object"],  # generically dependent continuant
    "http://purl.obolibrary.org/obo/BFO_0000019": ["object"],  # quality
    "http://purl.obolibrary.org/obo/BFO_0000029": ["location"],  # site
    "http://purl.obolibrary.org/obo/BFO_0000006": ["location"],  # spatial region
    "http://purl.obolibrary.org/obo/BFO_0000141": ["location"],  # immaterial entity
    "http://purl.obolibrary.org/obo/BFO_0000008": ["temporal"],  # temporal region
    # Commons categories (reached via FIBO superclass chains)
    "https://www.omg.org/spec/Commons/PartiesAndSituations/Agent": ["agent"],
    "https://www.omg.org/spec/Commons/PartiesAndSituations/Party": ["agent"],
    "https://www.omg.org/spec/Commons/PartiesAndSituations/PartyRole": ["agent"],
    "https://www.omg.org/spec/Commons/RolesAndCompositions/Role": ["agent"],
    "https://www.omg.org/spec/Commons/RolesAndCompositions/FunctionalRole": ["agent", "instrument"],
    "https://www.omg.org/spec/Commons/RolesAndCompositions/StructuralRole": ["agent"],
    "https://www.omg.org/spec/Commons/Organizations/Organization": ["agent"],
    "https://www.omg.org/spec/Commons/Organizations/FormalOrganization": ["agent"],
    "https://www.omg.org/spec/Commons/Organizations/LegalEntity": ["agent"],
    "https://www.omg.org/spec/Commons/Organizations/LegalPerson": ["agent"],
    "https://www.omg.org/spec/Commons/Documents/Document": ["object"],
    "https://www.omg.org/spec/Commons/Documents/LegalDocument": ["object"],
    "https://www.omg.org/spec/Commons/Identifiers/Identifier": ["object", "instrument"],
    "https://www.omg.org/spec/Commons/Locations/Location": ["location"],
}


def derive_roles(class_uri: str, onto_handlers: dict, max_depth: int = 10) -> list[str] | None:
    """Walk superclass chain looking for BFO/CCO/Commons categories. Returns roles or None."""
    visited = {class_uri}
    current = class_uri

    for _ in range(max_depth):
        if current in _CATEGORY_ROLES:
            return _CATEGORY_ROLES[current]

        superclasses = onto_handlers["get_superclasses"](current)
        if not superclasses:
            break

        # Follow first named superclass
        next_uri = None
        for s in superclasses:
            uri = s.get("uri", "")
            if uri and uri not in visited:
                next_uri = uri
                break
        if next_uri is None:
            break
        visited.add(next_uri)
        current = next_uri

    return None


@runtime_checkable
class SearchMergeStrategy(Protocol):
    """Protocol for merging per-domain search results into a candidate list."""

    def merge(
            self,
            per_domain_candidates: dict[str, list[dict]],
            selected_domains: list[str],
            max_candidates: int,
            risk_context: dict,
            generic_safety_uris: set[str],
    ) -> list[dict]: ...


class WeightedMergeStrategy:
    """Domain-selected ontologies get guaranteed quota slots, always-included fill remaining.

    Distance thresholds prevent irrelevant candidates from consuming slots:
    - DISTANCE_CEILING: raw distance above which candidates are always rejected
    - ZSCORE_THRESHOLD: z-score above which candidates are rejected (when
      per-domain normalization is available, i.e. n >= 2 with nonzero std)

    generic_safety_uris: URIs of ontology classes that are only relevant for
    generic AI safety testing (e.g. CSO DangerousInformation branch). Filtered
    out when set is non-empty.
    """

    DISTANCE_CEILING = 0.6
    ZSCORE_THRESHOLD = 1.0

    def __init__(self, always_included: list[str] | None = None):
        self._always_included = set(always_included or ALWAYS_INCLUDED)

    @staticmethod
    def _normalize_distances(candidates: list[dict]) -> None:
        """Add normalized_distance (z-score) to each candidate. Lower = better match.

        For n < 2 or uniform distances, assigns 0.0 (neutral) — the raw
        DISTANCE_CEILING handles filtering in those cases.
        """
        if len(candidates) < 2:
            for c in candidates:
                c["normalized_distance"] = 0.0
            return
        distances = [c.get("best_distance", 1.0) for c in candidates]
        mean = sum(distances) / len(distances)
        variance = sum((d - mean) ** 2 for d in distances) / len(distances)
        std = variance ** 0.5
        if std < 1e-9:
            for c in candidates:
                c["normalized_distance"] = 0.0
            return
        for c in candidates:
            c["normalized_distance"] = (c.get("best_distance", 1.0) - mean) / std

    def _passes_threshold(self, c: dict, generic_safety_uris: set[str]) -> bool:
        """Check if candidate passes distance thresholds and context filter."""
        if _is_excluded_uri(c.get("uri", ""), generic_safety_uris):
            return False
        if c.get("best_distance", 1.0) >= self.DISTANCE_CEILING:
            return False
        if c.get("normalized_distance", 0.0) >= self.ZSCORE_THRESHOLD:
            return False
        return True

    def merge(
            self,
            per_domain_candidates: dict[str, list[dict]],
            selected_domains: list[str],
            max_candidates: int,
            risk_context: dict,
            generic_safety_uris: set[str],
    ) -> list[dict]:
        selected_set = set(selected_domains)
        domain_selected = sorted(selected_set - self._always_included)

        # Normalize distances per domain for fair cross-domain comparison
        for candidates in per_domain_candidates.values():
            self._normalize_distances(candidates)

        result: list[dict] = []
        seen: set[str] = set()
        remaining = max_candidates

        # Domain-selected ontologies get guaranteed quota (with distance threshold)
        if domain_selected:
            quota_per = max(1, max_candidates // (len(domain_selected) + 1))
            for domain in domain_selected:
                for c in per_domain_candidates.get(domain, []):
                    if (c["uri"] not in seen
                            and remaining > 0
                            and self._passes_threshold(c, generic_safety_uris)
                            and len([r for r in result if r.get("domain") == domain]) < quota_per):
                        result.append(c)
                        seen.add(c["uri"])
                        remaining -= 1

        # Always-included domains fill remaining by best normalized distance
        pool = []
        for domain in sorted(self._always_included):
            if domain in selected_set:
                pool.extend(per_domain_candidates.get(domain, []))
        pool.sort(key=lambda c: (-c.get("hit_count", 0), c.get("normalized_distance", 0.0)))

        for c in pool:
            if c["uri"] not in seen and remaining > 0 and self._passes_threshold(c, generic_safety_uris):
                result.append(c)
                seen.add(c["uri"])
                remaining -= 1

        return result


class GroupedMergeStrategy:
    """Equal slots per domain, round-robin distribution."""

    def __init__(self, always_included: list[str] | None = None):
        self._always_included = set(always_included or ALWAYS_INCLUDED)

    def merge(
            self,
            per_domain_candidates: dict[str, list[dict]],
            selected_domains: list[str],
            max_candidates: int,
            risk_context: dict,
            generic_safety_uris: set[str],
    ) -> list[dict]:
        active_domains = [d for d in selected_domains if d in per_domain_candidates]
        if not active_domains:
            return []

        per_domain_quota = max(1, max_candidates // len(active_domains))
        result: list[dict] = []
        seen: set[str] = set()

        for domain in active_domains:
            taken = 0
            for c in per_domain_candidates.get(domain, []):
                uri = c["uri"]
                if uri in seen:
                    continue
                if _is_excluded_uri(uri, generic_safety_uris):
                    continue
                if taken < per_domain_quota:
                    result.append(c)
                    seen.add(uri)
                    taken += 1

        return result[:max_candidates]


_MERGE_SYSTEM_PROMPT = """\
You are selecting ontology classes relevant to an AI risk.

Given a risk (with description, concern, and policy context) and a numbered list of candidate ontology classes with definitions, select the classes most relevant to this specific risk. Return their indices.

Each candidate is tagged with a role — agent (who acts), object (what is affected), or instrument (method/tool used). Select a diverse set covering at least two different roles IF and WHEN possible. Selecting multiple classes with the same role produces repetitive scenarios, but single-role scenarios may be plausible/desirable.

Select up to {max_candidates} classes. Prefer classes that directly relate to the risk over tangentially related ones."""

# Human-readable domain descriptors for LLM merge prompts.
_DOMAIN_DISPLAY: dict[str, str] = {
    "CCO": "core concepts",
    "Commons": "organizations/roles",
    "D3FEND": "cyber defense",
    "CSO": "AI safety/security",
    "FIBO": "financial industry",
    "OBO": "biomedical/social",
    "IOF": "industrial",
    "LKIF": "legal/regulatory",
}


def _truncate_definition(text: str, max_words: int = 25) -> str:
    """Truncate a definition to max_words, appending '...' if truncated."""
    if not text:
        return ""
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + "..."


class _MergeSelection(BaseModel):
    selected: list[int]


class LLMMergeStrategy:
    """LLM-judged contextual relevance selection.

    Pre-filters by distance ceiling and generic safety URIs, then asks the LLM
    to select the most relevant candidates for the given risk context.
    Falls back to distance-sorted order on LLM failure.
    """

    DISTANCE_CEILING = 0.8

    def __init__(self, client: instructor.Instructor, config: LLMConfig,
                 onto_handlers: dict | None = None):
        self._client = client
        self._config = config
        self._onto_handlers = onto_handlers

    def merge(
            self,
            per_domain_candidates: dict[str, list[dict]],
            _selected_domains: list[str],
            max_candidates: int,
            risk_context: dict,
            generic_safety_uris: set[str],
    ) -> list[dict]:
        # Pre-filter: distance ceiling + BFO/safety URI exclusion
        pool: list[dict] = []
        for domain in sorted(per_domain_candidates):
            for c in per_domain_candidates[domain]:
                if c.get("best_distance", 1.0) >= self.DISTANCE_CEILING:
                    continue
                if _is_excluded_uri(c.get("uri", ""), generic_safety_uris):
                    continue
                pool.append(c)

        pool.sort(key=lambda c: (-c.get("hit_count", 0), c.get("best_distance", 1.0)))

        if not pool:
            return []

        # Enrich pool with definitions and roles if onto_handlers available
        get_defn = (self._onto_handlers or {}).get("get_class_definition")
        if get_defn:
            for c in pool:
                if "definition" not in c:
                    defn = get_defn(c.get("uri", ""))
                    c["definition"] = defn.get("definition", "") if defn else ""
        if self._onto_handlers and "get_superclasses" in self._onto_handlers:
            for c in pool:
                if "roles" not in c:
                    c["roles"] = derive_roles(c.get("uri", ""), self._onto_handlers) or ["object"]

        # Build numbered candidate list for LLM
        lines = []
        for idx, c in enumerate(pool):
            domain_display = _DOMAIN_DISPLAY.get(c.get("domain", ""), c.get("domain", ""))
            role_tag = "/".join(c.get("roles", ["object"]))
            definition = _truncate_definition(c.get("definition", ""))
            line = f"{idx}. {c.get('label', '')} [{domain_display}, {role_tag}]"
            if definition:
                line += f" — {definition}"
            lines.append(line)

        # Build user content with conditional concern
        header_lines = [f"Risk: {risk_context.get('description', '')}"]
        concern = risk_context.get("concern")
        if concern:
            header_lines.append(f"Concern: {concern}")
        header_lines.append(f"Policy: {risk_context.get('policy_concept', '')}")

        user_content = "\n".join(header_lines) + "\n\nCandidate classes:\n" + "\n".join(lines)

        messages = [
            {"role": "system", "content": _MERGE_SYSTEM_PROMPT.format(max_candidates=max_candidates)},
            {"role": "user", "content": user_content},
        ]

        try:
            result = self._client.chat.completions.create(
                model=self._config.model,
                response_model=_MergeSelection,
                messages=messages,
                temperature=self._config.temperature,
                max_retries=self._config.max_retries,
                max_tokens=self._config.max_tokens,
            )
            debug.log_call("merge", messages, result, context={
                "policy_concept": risk_context.get("policy_concept", ""),
                "pool_size": len(pool),
                "selected_count": len(result.selected),
            })

            selected = []
            for idx in result.selected:
                if 0 <= idx < len(pool):
                    selected.append(pool[idx])
            return selected[:max_candidates]

        except Exception:
            logger.warning("LLM merge failed, falling back to distance-sorted order", exc_info=True)
            return pool[:max_candidates]


# CSO DangerousInformation branch — physical harm classes that are only relevant
# for generic AI safety testing.  Filtered out in domain-specific policy runs.
_CSO_DANGEROUS_INFO_URI = "http://taxonomy-refiner.io/ontologies/cso#DangerousInformation"


def build_generic_safety_uris(onto_handlers: dict) -> set[str]:
    """Build set of CSO DangerousInformation URIs from the ontology graph.

    Returns the parent URI plus all descendants (depth 3 covers the full branch).
    Returns empty set if get_subclasses is unavailable.
    """
    get_subclasses = onto_handlers.get("get_subclasses")
    if not get_subclasses:
        return set()
    descendants = get_subclasses(_CSO_DANGEROUS_INFO_URI, depth=3)
    uris = {_CSO_DANGEROUS_INFO_URI}
    for d in descendants:
        uri = d.get("uri", "")
        if uri:
            uris.add(uri)
    return uris


# --- BFO category labels (lightweight replacement for _CATEGORY_ROLES) ---

_BFO_CATEGORIES: dict[str, str] = {
    "http://purl.obolibrary.org/obo/BFO_0000040": "MaterialEntity",
    "http://purl.obolibrary.org/obo/BFO_0000015": "Process",
    "http://purl.obolibrary.org/obo/BFO_0000031": "GenericallyDependentContinuant",
    "http://purl.obolibrary.org/obo/BFO_0000020": "Quality",
    "http://purl.obolibrary.org/obo/BFO_0000023": "Role",
    "http://purl.obolibrary.org/obo/BFO_0000016": "Disposition",
    "http://purl.obolibrary.org/obo/BFO_0000017": "RealizableEntity",
    "http://purl.obolibrary.org/obo/BFO_0000029": "Site",
    "http://purl.obolibrary.org/obo/BFO_0000006": "SpatialRegion",
    "http://purl.obolibrary.org/obo/BFO_0000141": "ImmaterialEntity",
    "http://purl.obolibrary.org/obo/BFO_0000008": "TemporalRegion",
    "http://purl.obolibrary.org/obo/BFO_0000019": "Quality",
    # CCO shortcuts
    "https://www.commoncoreontologies.org/ont00000958": "InformationContentEntity",
    "https://www.commoncoreontologies.org/ont00001017": "Agent",
    "https://www.commoncoreontologies.org/ont00000995": "MaterialArtifact",
    "https://www.commoncoreontologies.org/ont00000192": "Facility",
    "https://www.commoncoreontologies.org/ont00000005": "Act",
}


def derive_bfo_category(class_uri: str, onto_handlers: dict, max_depth: int = 10) -> str:
    """Walk superclass chain to find BFO/CCO category name. Returns '' if not found."""
    visited = set()
    current = class_uri
    for _ in range(max_depth):
        if current in _BFO_CATEGORIES:
            return _BFO_CATEGORIES[current]
        if current in visited:
            break
        visited.add(current)
        supers = onto_handlers["get_superclasses"](current)
        named = [s for s in supers if s.get("uri") and s["uri"] not in visited]
        if not named:
            break
        current = named[0]["uri"]
    return ""


def navigate_from_seeds(
    seed_mappings: list[dict],
    onto_handlers: dict,
    selected_domains: list[str] | None,
    generic_safety_uris: set[str] | None = None,
) -> list[dict]:
    """Structural navigation from SSSOM seed URIs. Returns candidate dicts."""
    candidates = []
    safety = generic_safety_uris or set()

    for mapping in seed_mappings:
        seed_uri = mapping["object_id"]
        predicate = mapping["predicate_id"]
        confidence = mapping.get("effective_confidence", mapping.get("confidence", 0.5))
        vocab_concept = mapping.get("vocabulary_concept")
        vocab_label = mapping.get("vocabulary_label")

        if predicate == "skos:broadMatch":
            discovered = onto_handlers["get_subclasses"](seed_uri, depth=2)
            for cls in discovered:
                uri = cls["uri"]
                if _is_excluded_uri(uri, safety):
                    continue
                if selected_domains:
                    domain = derive_source_ontology(uri)
                    if domain and domain not in selected_domains:
                        continue
                candidates.append({
                    "uri": uri,
                    "label": cls.get("label", ""),
                    "source": "structural",
                    "path": [seed_uri, uri],
                    "seed_uri": seed_uri,
                    "effective_confidence": confidence,
                    "predicate": predicate,
                    "vocabulary_concept": vocab_concept,
                    "vocabulary_label": vocab_label,
                })

        elif predicate == "skos:relatedMatch":
            # Seed itself is a candidate
            defn = onto_handlers["get_class_definition"](seed_uri)
            if defn:
                candidates.append({
                    "uri": seed_uri,
                    "label": defn.get("label", mapping.get("object_label", "")),
                    "source": "structural",
                    "path": [seed_uri],
                    "seed_uri": seed_uri,
                    "effective_confidence": confidence,
                    "predicate": predicate,
                    "vocabulary_concept": vocab_concept,
                    "vocabulary_label": vocab_label,
                })
            # Navigate restrictions
            if onto_handlers.get("get_restrictions"):
                for r in onto_handlers["get_restrictions"](seed_uri):
                    filler = r.get("filler", "")
                    if not filler or _is_excluded_uri(filler, safety):
                        continue
                    filler_defn = onto_handlers["get_class_definition"](filler)
                    if filler_defn:
                        candidates.append({
                            "uri": filler,
                            "label": filler_defn.get("label", ""),
                            "source": "structural",
                            "path": [seed_uri, filler],
                            "seed_uri": seed_uri,
                            "effective_confidence": confidence * 0.9,
                            "predicate": predicate,
                            "vocabulary_concept": vocab_concept,
                            "vocabulary_label": vocab_label,
                            "restriction_property": r.get("property", ""),
                        })
            # Navigate siblings
            for s in onto_handlers["get_siblings"](seed_uri):
                s_uri = s["uri"]
                if _is_excluded_uri(s_uri, safety):
                    continue
                if selected_domains:
                    domain = derive_source_ontology(s_uri)
                    if domain and domain not in selected_domains:
                        continue
                candidates.append({
                    "uri": s_uri,
                    "label": s.get("label", ""),
                    "source": "structural",
                    "path": [seed_uri, s_uri],
                    "seed_uri": seed_uri,
                    "effective_confidence": confidence * 0.8,
                    "predicate": predicate,
                    "vocabulary_concept": vocab_concept,
                    "vocabulary_label": vocab_label,
                })

        elif predicate in ("skos:exactMatch", "skos:closeMatch"):
            defn = onto_handlers["get_class_definition"](seed_uri)
            if defn:
                candidates.append({
                    "uri": seed_uri,
                    "label": defn.get("label", mapping.get("object_label", "")),
                    "source": "structural",
                    "path": [seed_uri],
                    "seed_uri": seed_uri,
                    "effective_confidence": confidence,
                    "predicate": predicate,
                    "vocabulary_concept": vocab_concept,
                    "vocabulary_label": vocab_label,
                })
            if predicate == "skos:closeMatch":
                for sub in onto_handlers["get_subclasses"](seed_uri, depth=1):
                    candidates.append({
                        "uri": sub["uri"],
                        "label": sub.get("label", ""),
                        "source": "structural",
                        "path": [seed_uri, sub["uri"]],
                        "seed_uri": seed_uri,
                        "effective_confidence": confidence * 0.9,
                        "predicate": predicate,
                        "vocabulary_concept": vocab_concept,
                        "vocabulary_label": vocab_label,
                    })

    # Deduplicate by URI, keep highest confidence
    seen: dict[str, dict] = {}
    for c in candidates:
        uri = c["uri"]
        if uri not in seen or c["effective_confidence"] > seen[uri]["effective_confidence"]:
            seen[uri] = c
    return list(seen.values())


def constrained_search(
    risk_description: str,
    seed_mappings: list[dict],
    onto_handlers: dict,
    selected_domains: list[str] | None,
    top_k: int = 8,
) -> list[dict]:
    """ChromaDB search scoped to domains containing seed URIs."""
    if not onto_handlers.get("search_domains") or not selected_domains:
        return []

    seed_domains = set()
    for m in seed_mappings:
        domain = derive_source_ontology(m["object_id"])
        if domain:
            seed_domains.add(domain)
    search_domains = list(seed_domains & set(selected_domains))
    if not search_domains:
        return []

    raw = onto_handlers["search_domains"](risk_description, search_domains, top_k_per_domain=top_k)
    results = []
    for domain, hits in raw.items():
        if not isinstance(hits, list):
            continue
        for hit in hits:
            results.append({
                "uri": hit["uri"],
                "label": hit.get("label", ""),
                "source": "search",
                "best_distance": hit.get("distance", 1.0),
                "domain": domain,
                "vocabulary_concept": None,
                "vocabulary_label": None,
            })
    return results


def check_structural_connection(
    candidate_uri: str,
    seed_uris: list[str],
    onto_handlers: dict,
    max_hops: int = 3,
) -> dict:
    """Check if candidate shares a common ancestor with any seed URI."""
    def _walk(uri, depth):
        ancestors = set()
        visited = set()
        frontier = [uri]
        for _ in range(depth):
            next_frontier = []
            for u in frontier:
                if u in visited:
                    continue
                visited.add(u)
                supers = onto_handlers["get_superclasses"](u)
                for s in supers:
                    s_uri = s["uri"]
                    ancestors.add(s_uri)
                    next_frontier.append(s_uri)
            frontier = next_frontier
        return ancestors

    cand_ancestors = _walk(candidate_uri, max_hops)
    cand_ancestors.add(candidate_uri)
    for seed_uri in seed_uris:
        seed_ancestors = _walk(seed_uri, max_hops)
        seed_ancestors.add(seed_uri)
        common = cand_ancestors & seed_ancestors
        if common:
            return {"connected": True, "common_ancestor": next(iter(common))}
    return {"connected": False}


def merge_tiered(
    structural: list[dict],
    search_connected: list[dict],
    search_only: list[dict],
    max_total: int = 12,
) -> list[dict]:
    """Three-tier merge with vocabulary diversity check."""
    result = []
    seen = set()

    # Tier 1: structural, sorted by effective confidence then path length
    for c in sorted(structural, key=lambda c: (-c.get("effective_confidence", 0), len(c.get("path", [])))):
        if c["uri"] not in seen and len(result) < 8:
            result.append(c)
            seen.add(c["uri"])

    # Tier 2: search-connected, sorted by distance
    for c in sorted(search_connected, key=lambda c: c.get("best_distance", 1.0)):
        if c["uri"] not in seen and len(result) < 10:
            result.append(c)
            seen.add(c["uri"])

    # Tier 3: search-only, sorted by distance
    for c in sorted(search_only, key=lambda c: c.get("best_distance", 1.0)):
        if c["uri"] not in seen and len(result) < max_total:
            result.append(c)
            seen.add(c["uri"])

    # Vocabulary diversity check
    vocab_categories = {
        c.get("vocabulary_concept", "").split(":")[0]
        for c in result if c.get("vocabulary_concept")
    }
    if len(vocab_categories) < 2:
        all_remaining = [
            c for pool in [structural, search_connected, search_only]
            for c in pool if c["uri"] not in seen and c.get("vocabulary_concept")
        ]
        for c in all_remaining:
            cat = c["vocabulary_concept"].split(":")[0]
            if cat not in vocab_categories:
                result.append(c)
                seen.add(c["uri"])
                vocab_categories.add(cat)
                if len(vocab_categories) >= 2:
                    break

    return result


def _search_per_domain(
        queries: list[tuple[str, str]],
        onto_handlers: dict,
        selected_domains: list[str],
        top_k_per_query: int,
) -> tuple[dict[str, list[dict]], int, int]:
    """Run queries against per-domain collections, merge by URI within each domain.

    Returns (per_domain_sorted, raw_total, unique_total).
    """
    per_domain: dict[str, dict[str, dict]] = {}
    raw_total = 0

    for query_text, source_label in queries:
        domain_results = onto_handlers["search_domains"](
            query_text, selected_domains, top_k_per_domain=top_k_per_query,
        )
        for domain, results in domain_results.items():
            raw_total += len(results)
            if domain not in per_domain:
                per_domain[domain] = {}
            for r in results:
                uri = r.get("uri", "")
                if not uri:
                    continue
                if uri not in per_domain[domain]:
                    per_domain[domain][uri] = {
                        "uri": uri,
                        "label": r.get("label", ""),
                        "hit_count": 0,
                        "best_distance": float("inf"),
                        "query_sources": [],
                        "domain": domain,
                    }
                entry = per_domain[domain][uri]
                entry["hit_count"] += 1
                dist = r.get("distance", 1.0)
                if dist < entry["best_distance"]:
                    entry["best_distance"] = dist
                if source_label not in entry["query_sources"]:
                    entry["query_sources"].append(source_label)

    sorted_per_domain = {
        domain: sorted(uris.values(), key=lambda c: (-c["hit_count"], c["best_distance"]))
        for domain, uris in per_domain.items()
    }
    unique_total = sum(len(v) for v in sorted_per_domain.values())

    return sorted_per_domain, raw_total, unique_total


SYSTEM_PROMPT = """\
You are identifying variation axes for AI risk concepts using ontology classes.

A variation axis is an ontology class that represents a dimension along which diverse prompts can be generated. Each axis has a semantic role relative to the risk:
- agent: Who performs or is affected by the action
- object: What is acted upon
- instrument: What tool/means is used
- location: Where it occurs
- temporal: When it occurs

Given a risk (with description and concern) and candidate ontology classes (with definitions and siblings), select the classes that are most semantically relevant to the risk.

Reference each selected class by its candidate ID (e.g. C1). Use the class name as the class_label.

Return 2-3 axes max."""


class _SlimAxis(BaseModel):
    class_id: str
    class_label: str
    role: str
    rationale: str


class _AnchorResponse(BaseModel):
    axes: list[_SlimAxis]


def expand_candidates(
        description: str,
        concern: str,
        action_descriptions: list[str],
        cross_mapped_descriptions: list[str],
        onto_handlers: dict,
        selected_domains: list[str] | None,
        merge_strategy: SearchMergeStrategy | None = None,
        top_k_per_query: int = 10,
        max_candidates: int = 5,
        policy_concept: str = "",
        generic_safety_uris: set[str] | None = None,
) -> tuple[list[dict], dict]:
    """Run multiple ontology searches, merge by URI, annotate with hit count."""
    queries: list[tuple[str, str]] = []
    if description and description.strip():
        queries.append((description, "description"))
    if concern and concern.strip():
        queries.append((concern, "concern"))
    for a in action_descriptions:
        if a.strip():
            queries.append((a, "action"))
    for d in cross_mapped_descriptions:
        if d.strip():
            queries.append((d, "cross_mapping"))

    # Per-domain search path: route queries to domain collections, merge via strategy
    if merge_strategy and onto_handlers.get("search_domains") and selected_domains:
        per_domain, raw_total, unique_total = _search_per_domain(
            queries, onto_handlers, selected_domains, top_k_per_query,
        )
        kept = merge_strategy.merge(
            per_domain, selected_domains, max_candidates,
            risk_context={
                "description": description,
                "concern": concern,
                "policy_concept": policy_concept,
            },
            generic_safety_uris=generic_safety_uris or set(),
        )
        stats = {
            "queries_run": len(queries),
            "raw_total": raw_total,
            "unique_after_dedup": unique_total,
            "kept_after_filter": len(kept),
            "search_strategy": type(merge_strategy).__name__,
        }
    else:
        # Legacy path: single collection search + post-filter by domain
        by_uri: dict[str, dict] = {}
        raw_total = 0
        for query_text, source_label in queries:
            results = onto_handlers["search_classes"](query_text, top_k=top_k_per_query)
            raw_total += len(results)
            for r in results:
                uri = r.get("uri", "")
                if not uri:
                    continue
                if uri not in by_uri:
                    by_uri[uri] = {
                        "uri": uri,
                        "label": r.get("label", ""),
                        "hit_count": 0,
                        "best_distance": float("inf"),
                        "query_sources": [],
                    }
                entry = by_uri[uri]
                entry["hit_count"] += 1
                dist = r.get("distance", 1.0)
                if dist < entry["best_distance"]:
                    entry["best_distance"] = dist
                if source_label not in entry["query_sources"]:
                    entry["query_sources"].append(source_label)

        if selected_domains:
            filtered = {
                uri: c for uri, c in by_uri.items()
                if derive_source_ontology(uri) in selected_domains
            }
        else:
            filtered = by_uri

        sorted_candidates = sorted(
            filtered.values(),
            key=lambda c: (-c["hit_count"], c["best_distance"]),
        )
        kept = sorted_candidates[:max_candidates]
        stats = {
            "queries_run": len(queries),
            "raw_total": raw_total,
            "unique_after_dedup": len(by_uri),
            "kept_after_filter": len(kept),
        }

    # Restriction/equivalence expansion (common to both paths)
    restriction_added = 0
    if onto_handlers.get("get_restrictions"):
        restriction_candidates = []
        seen_uris = {c["uri"] for c in kept}
        for c in kept:
            for r in onto_handlers["get_restrictions"](c["uri"]):
                filler = r.get("filler", "")
                if not filler or filler in seen_uris:
                    continue
                if filler.startswith(_BFO_URI_PREFIX):
                    continue
                defn = onto_handlers["get_class_definition"](filler)
                if defn is None:
                    continue
                seen_uris.add(filler)
                restriction_candidates.append({
                    "uri": filler,
                    "label": defn.get("label", ""),
                    "hit_count": 0,
                    "best_distance": 0.0,
                    "query_sources": ["restriction"],
                    "restriction_property": r.get("property", ""),
                    "restriction_from": c["uri"],
                })

        if onto_handlers.get("get_equivalent_axioms"):
            for c in kept:
                for eq in onto_handlers["get_equivalent_axioms"](c["uri"]):
                    for member in eq.get("members", []):
                        if member in seen_uris:
                            continue
                        if member.startswith(_BFO_URI_PREFIX):
                            continue
                        defn = onto_handlers["get_class_definition"](member)
                        if defn is None:
                            continue
                        seen_uris.add(member)
                        restriction_candidates.append({
                            "uri": member,
                            "label": defn.get("label", ""),
                            "hit_count": 0,
                            "best_distance": 0.0,
                            "query_sources": ["equivalence"],
                        })

        # Domain filter restriction candidates
        if selected_domains and restriction_candidates:
            restriction_candidates = [
                c for c in restriction_candidates
                if derive_source_ontology(c["uri"]) in selected_domains
            ]

        # Cap at 3 additional candidates
        restriction_candidates = restriction_candidates[:3]
        kept = kept + restriction_candidates
        restriction_added = len(restriction_candidates)

    stats["restriction_candidates_added"] = restriction_added
    stats["kept_after_filter"] = len(kept)

    return kept, stats


def anchor(
        risk_mappings: list[PolicyRiskMapping],
        risk_details: dict[str, dict],
        client: instructor.Instructor,
        config: LLMConfig,
        onto_handlers: dict,
        selected_domains: list[str] | None = None,
        risk_actions: dict[str, list[str]] | None = None,
        related_risks: dict[str, list[dict]] | None = None,
        merge_strategy: SearchMergeStrategy | None = None,
        report=None,
        generic_safety_uris: set[str] | None = None,
) -> list[RiskVariationAxes]:
    if not risk_mappings:
        return []

    results: list[RiskVariationAxes] = []
    axes_cache: dict[str, list[VariationAxis]] = {}  # risk_id -> cached axes

    for mapping in risk_mappings:
        for rm in mapping.matched_risks:
            if rm.risk_id in axes_cache:
                logger.debug("Cache hit for risk_id=%s, reusing axes", rm.risk_id)
                if report:
                    report.events.append({"stage": "anchor", "event": "cache_hit", "risk_id": rm.risk_id})
                results.append(RiskVariationAxes(
                    risk_id=rm.risk_id,
                    risk_name=rm.risk_name,
                    policy_concept=mapping.policy_concept,
                    axes=axes_cache[rm.risk_id],
                ))
                continue

            details = risk_details.get(rm.risk_id, {})
            description = details.get("description", rm.risk_name)
            concern = details.get("concern", "")

            # Expand candidates via multi-query search (description + concern + actions + cross-mappings)
            actions = risk_actions.get(rm.risk_id, []) if risk_actions else []
            cross_mapped_descs = []
            if related_risks:
                for rel in related_risks.get(rm.risk_id, []):
                    desc = rel.get("description", "")
                    if desc:
                        cross_mapped_descs.append(desc)

            candidates, expansion_stats = expand_candidates(
                description=description,
                concern=concern,
                action_descriptions=actions,
                cross_mapped_descriptions=cross_mapped_descs,
                onto_handlers=onto_handlers,
                selected_domains=selected_domains,
                merge_strategy=merge_strategy,
                policy_concept=mapping.policy_concept,
                generic_safety_uris=generic_safety_uris,
            )

            if report and expansion_stats.get("restriction_candidates_added", 0) > 0:
                report.events.append({
                    "stage": "anchor", "event": "restriction_expansion",
                    "risk_id": rm.risk_id,
                    "source_uri": "",  # multiple sources
                    "candidates_added": expansion_stats["restriction_candidates_added"],
                    "source_type": "restriction",
                })

            if report:
                report.events.append({
                    "stage": "anchor", "event": "candidate_expansion",
                    "risk_id": rm.risk_id, **expansion_stats,
                })
                for c in candidates:
                    report.events.append({
                        "stage": "anchor", "event": "multi_query_hit",
                        "risk_id": rm.risk_id,
                        "uri": c["uri"],
                        "hit_count": c["hit_count"],
                        "best_distance": c["best_distance"],
                        "query_sources": c["query_sources"],
                    })

            # Enrich candidates with definitions and siblings
            enriched = []
            known_uris = set()
            for c in candidates:
                defn = onto_handlers["get_class_definition"](c["uri"])
                if defn is None:
                    continue
                known_uris.add(c["uri"])
                siblings = onto_handlers["get_siblings"](c["uri"])
                for s in siblings:
                    known_uris.add(s.get("uri", ""))
                enriched.append({**defn, "siblings": siblings})

            if not enriched:
                if report:
                    report.events.append({"stage": "anchor", "event": "empty_axes", "risk_id": rm.risk_id})
                axes_cache[rm.risk_id] = []
                results.append(RiskVariationAxes(
                    risk_id=rm.risk_id,
                    risk_name=rm.risk_name,
                    policy_concept=mapping.policy_concept,
                    axes=[],
                ))
                continue

            # Build context for LLM — assign short IDs, use Markdown format
            id_to_uri = {}
            class_lines = []
            for idx, ec in enumerate(enriched, 1):
                cand_id = f"C{idx}"
                id_to_uri[cand_id] = ec["uri"]
                cand = next((c for c in candidates if c["uri"] == ec["uri"]), None)

                lines = [f"## {cand_id}: {ec.get('label', '')}"]
                lines.append(f"Definition: {ec.get('definition', '')}")

                if cand and cand.get("restriction_from"):
                    prop_label = cand.get("restriction_property", "").split("#")[-1].split("/")[-1]
                    from_label = cand.get("restriction_from", "").split("#")[-1].split("/")[-1]
                    lines.append(f"Source: restriction ({prop_label} on {from_label})")
                elif cand and "equivalence" in cand.get("query_sources", []):
                    lines.append("Source: equivalence")
                elif cand and cand.get("hit_count", 1) > 1:
                    ratio = cand["hit_count"] / expansion_stats["queries_run"]
                    label = "high" if ratio >= 0.5 else "medium"
                    lines.append(f"Relevance: {label}")

                if ec.get("siblings"):
                    sibs = ", ".join(s.get("label", s.get("uri", "")) for s in ec["siblings"][:3])
                    lines.append(f"Siblings: {sibs}")

                class_lines.append("\n".join(lines))

            user_content = (
                    f"Risk: {rm.risk_name}\n"
                    f"Description: {description}\n"
                    f"Concern: {concern}\n"
                    f"Policy: {mapping.policy_concept}\n\n"
                    f"Candidate classes:\n\n" + "\n\n".join(class_lines)
            )

            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ]
            result = client.chat.completions.create(
                model=config.model,
                response_model=_AnchorResponse,
                messages=messages,
                temperature=config.temperature,
                max_retries=config.max_retries,
                max_tokens=config.max_tokens,
            )
            debug.log_call("anchor", messages, result, context={
                "policy_concept": mapping.policy_concept,
                "risk_id": rm.risk_id,
                "risk_name": rm.risk_name,
                "num_candidates": len(enriched),
            })

            # Post-processing: map short IDs back to URIs, validate, derive roles
            valid_axes = []
            for axis in result.axes:
                actual_uri = id_to_uri.get(axis.class_id)
                if actual_uri is None:
                    logger.warning("Filtering unknown class_id: %s", axis.class_id)
                    continue
                check = onto_handlers["get_class_definition"](actual_uri)
                if check is None:
                    logger.warning("Filtering invalid URI for class_id %s: %s", axis.class_id, actual_uri)
                    continue
                derived = derive_roles(actual_uri, onto_handlers)
                if report:
                    report.events.append({
                        "stage": "anchor", "event": "role_derivation",
                        "uri": actual_uri,
                        "method": "derived" if derived is not None else "llm_fallback",
                    })
                roles = derived if derived is not None else [axis.role]
                valid_axes.append(VariationAxis(
                    cco_class_uri=actual_uri,
                    cco_class_label=axis.class_label,
                    roles=roles,
                    rationale=axis.rationale,
                ))

            # Cache axes by risk_id for deduplication
            axes_cache[rm.risk_id] = valid_axes

            # Stitch back metadata the LLM doesn't need to produce
            results.append(RiskVariationAxes(
                risk_id=rm.risk_id,
                risk_name=rm.risk_name,
                policy_concept=mapping.policy_concept,
                axes=valid_axes,
            ))

    return results
