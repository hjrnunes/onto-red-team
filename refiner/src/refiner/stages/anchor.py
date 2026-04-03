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

# BFO/CCO/Commons category → semantic roles mapping.
# More specific categories are checked first (via superclass walk),
# falling back to broader categories.
_CATEGORY_ROLES: dict[str, list[str]] = {
    # CCO categories (more specific — checked first)
    "https://www.commoncoreontologies.org/ont00001017": ["agent"],               # Agent
    "https://www.commoncoreontologies.org/ont00000995": ["object", "instrument"],  # Material Artifact
    "https://www.commoncoreontologies.org/ont00000005": ["object"],               # Act (process)
    "https://www.commoncoreontologies.org/ont00000958": ["object", "instrument"],  # Information Content Entity
    "https://www.commoncoreontologies.org/ont00000192": ["location"],             # Facility (not bridged — Material Artifact, not spatial)
    # BFO categories (broader fallback)
    "http://purl.obolibrary.org/obo/BFO_0000040": ["agent", "object"],   # material entity
    "http://purl.obolibrary.org/obo/BFO_0000015": ["object"],            # process
    "http://purl.obolibrary.org/obo/BFO_0000023": ["agent"],             # role (bearer acts)
    "http://purl.obolibrary.org/obo/BFO_0000016": ["instrument"],        # disposition
    "http://purl.obolibrary.org/obo/BFO_0000031": ["object"],            # generically dependent continuant
    "http://purl.obolibrary.org/obo/BFO_0000019": ["object"],            # quality
    "http://purl.obolibrary.org/obo/BFO_0000029": ["location"],          # site
    "http://purl.obolibrary.org/obo/BFO_0000006": ["location"],          # spatial region
    "http://purl.obolibrary.org/obo/BFO_0000141": ["location"],          # immaterial entity
    "http://purl.obolibrary.org/obo/BFO_0000008": ["temporal"],          # temporal region
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
    ) -> list[dict]: ...


class WeightedMergeStrategy:
    """Domain-selected ontologies get guaranteed quota slots, always-included fill remaining.

    Distance thresholds prevent irrelevant candidates from consuming slots:
    - DISTANCE_CEILING: raw distance above which candidates are always rejected
    - ZSCORE_THRESHOLD: z-score above which candidates are rejected (when
      per-domain normalization is available, i.e. n >= 2 with nonzero std)
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

    def _passes_threshold(self, c: dict) -> bool:
        """Check if candidate passes both raw distance ceiling and z-score threshold."""
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
                        and self._passes_threshold(c)
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
            if c["uri"] not in seen and remaining > 0 and self._passes_threshold(c):
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
                if c["uri"] not in seen and taken < per_domain_quota:
                    result.append(c)
                    seen.add(c["uri"])
                    taken += 1

        return result[:max_candidates]


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

Return 2-3 axes max."""


class _SlimAxis(BaseModel):
    cco_class_uri: str
    cco_class_label: str
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
        kept = merge_strategy.merge(per_domain, selected_domains, max_candidates)
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

            # Build context for LLM
            class_lines = []
            for ec in enriched:
                cand = next((c for c in candidates if c["uri"] == ec["uri"]), None)
                hit_info = ""
                if cand and cand.get("restriction_from"):
                    prop_label = cand.get("restriction_property", "").split("#")[-1].split("/")[-1]
                    from_label = cand.get("restriction_from", "").split("#")[-1].split("/")[-1]
                    hit_info = f" [from restriction: {prop_label} on {from_label}]"
                elif cand and "equivalence" in cand.get("query_sources", []):
                    hit_info = " [from equivalence]"
                elif cand and cand.get("hit_count", 1) > 1:
                    hit_info = f" [found by {cand['hit_count']}/{expansion_stats['queries_run']} queries]"
                line = f"- {ec['uri']}: {ec.get('label', '')} — {ec.get('definition', '')}{hit_info}"
                if ec.get("siblings"):
                    sibs = ", ".join(s.get("label", s.get("uri", "")) for s in ec["siblings"][:3])
                    line += f"\n  Siblings: {sibs}"
                class_lines.append(line)

            user_content = (
                f"Risk: {rm.risk_name}\n"
                f"Description: {description}\n"
                f"Concern: {concern}\n"
                f"Policy: {mapping.policy_concept}\n\n"
                f"Candidate ontology classes:\n" + "\n".join(class_lines)
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

            # Post-processing: validate URIs, derive roles from BFO/CCO hierarchy
            valid_axes = []
            for axis in result.axes:
                check = onto_handlers["get_class_definition"](axis.cco_class_uri)
                if check is None:
                    logger.warning("Filtering invalid cco_class_uri: %s", axis.cco_class_uri)
                    continue
                derived = derive_roles(axis.cco_class_uri, onto_handlers)
                if report:
                    report.events.append({
                        "stage": "anchor", "event": "role_derivation",
                        "uri": axis.cco_class_uri,
                        "method": "derived" if derived is not None else "llm_fallback",
                    })
                roles = derived if derived is not None else [axis.role]
                valid_axes.append(VariationAxis(
                    cco_class_uri=axis.cco_class_uri,
                    cco_class_label=axis.cco_class_label,
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
