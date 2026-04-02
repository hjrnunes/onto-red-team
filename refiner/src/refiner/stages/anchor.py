import logging

import instructor
from pydantic import BaseModel
from refiner.llm import LLMConfig
from refiner.models import (
    PolicyRiskMapping,
    RiskVariationAxes,
    VariationAxis,
)
from refiner import debug
from refiner.stages.identify_domains import derive_source_ontology

logger = logging.getLogger(__name__)

# BFO/CCO category → semantic roles mapping.
# More specific CCO categories are checked first (via superclass walk),
# falling back to broader BFO categories.
# For non-BFO ontologies (FIBO, Commons), the walk won't hit these,
# so we fall back to the LLM-assigned role.
_CATEGORY_ROLES: dict[str, list[str]] = {
    # CCO categories (more specific — checked first)
    "https://www.commoncoreontologies.org/ont00001017": ["agent"],               # Agent
    "https://www.commoncoreontologies.org/ont00000995": ["object", "instrument"],  # Material Artifact
    "https://www.commoncoreontologies.org/ont00000005": ["object"],               # Act (process)
    "https://www.commoncoreontologies.org/ont00000958": ["object", "instrument"],  # Information Content Entity
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
}


def derive_roles(class_uri: str, onto_handlers: dict, max_depth: int = 10) -> list[str] | None:
    """Walk superclass chain looking for BFO/CCO categories. Returns roles or None."""
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

    # Restriction/equivalence expansion
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

    stats = {
        "queries_run": len(queries),
        "raw_total": raw_total,
        "unique_after_dedup": len(by_uri),
        "kept_after_filter": len(kept),
        "restriction_candidates_added": restriction_added,
    }

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
