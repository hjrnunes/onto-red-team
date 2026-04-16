import logging
from typing import Literal

import instructor
from pydantic import BaseModel
from refiner.llm import LLMConfig
from refiner.models import (
    Policy,
    PolicyRiskMapping,
    RiskMatch,
    CoverageGap,
)
from refiner import debug

logger = logging.getLogger(__name__)

WEAK_MATCH_THRESHOLD = 0.6
GAP_SCORE_THRESHOLD = 0.65


def compute_gap_score(
    min_distance: float,
    primary_count: int,
    has_decomposition: bool,
) -> float:
    return (
        0.45 * min_distance
        + 0.35 * (1.0 if primary_count == 0 else 0.0)
        + 0.20 * (1.0 if has_decomposition else 0.0)
    )


SYSTEM_PROMPT = """\
You are mapping client content policies to known AI risk entries from a knowledge graph.

Given a policy definition and a numbered list of candidate risks, select the most relevant risks (1-3) by their number and classify their relevance:
- primary: Directly addresses the policy concern
- supporting: Related but not the primary match
- tangential: Loosely related

Only include risks that genuinely match the policy — it is better to return 1 strong match than 3 weak ones.

IMPORTANT: Use the candidate NUMBER (not the ID) for risk_index. Keep risk_name values SHORT (max 5 words). Keep justifications to one sentence."""


class _SlimRiskMatch(BaseModel):
    risk_index: int
    risk_name: str
    relevance: Literal["primary", "supporting", "tangential"]
    justification: str


class _RiskSelection(BaseModel):
    matched_risks: list[_SlimRiskMatch]


GAP_TYPE_WEIGHTS = {
    "domain_specialization": 1.0,
    "compositional": 0.6,
    "novel": 1.0,
}


class _GapClassification(BaseModel):
    gap_type: Literal["domain_specialization", "compositional", "novel"]
    reasoning: str


GAP_CHARACTERIZATION_PROMPT = """\
You are classifying a coverage gap in an AI risk taxonomy.

A policy concern was not well matched to any existing risk in the knowledge graph. Your job is to determine WHY.

Three gap types:
- domain_specialization: The concern is a domain-specific variant of an existing risk (e.g. "AI triage liability" is healthcare-specific "Liability"). The risk concept exists but needs domain narrowing.
- compositional: The concern can be fully expressed as a combination of multiple existing risks (e.g. "automated hiring discrimination via training data bias" = "Bias" + "Discrimination"). No new risk concept is needed.
- novel: The concern names a fundamentally different failure mode not covered by existing risks, even in combination (e.g. "multi-agent collusion", "AI welfare").

Prefer domain_specialization over compositional. Prefer compositional over novel. Only classify as novel if the concern truly cannot be expressed using existing risks.

Return the gap_type and a one-sentence reasoning."""


def characterize_gap(
    policy_concept: str,
    concept_definition: str,
    nearest_candidates: list[dict],
    client: instructor.Instructor,
    config: LLMConfig,
) -> _GapClassification:
    candidate_lines = []
    for c in nearest_candidates[:5]:
        line = f"- {c.get('name', '?')}: {c.get('description', '')}"
        if c.get("distance") is not None:
            line += f" (distance: {c['distance']:.3f})"
        candidate_lines.append(line)

    user_content = (
        f"Policy concern: {policy_concept}\n"
        f"Definition: {concept_definition}\n\n"
        f"Nearest existing risks (none matched well):\n"
        + "\n".join(candidate_lines)
    )

    messages = [
        {"role": "system", "content": GAP_CHARACTERIZATION_PROMPT},
        {"role": "user", "content": user_content},
    ]
    result = client.chat.completions.create(
        model=config.model,
        response_model=_GapClassification,
        messages=messages,
        temperature=config.temperature,
        max_retries=config.max_retries,
        max_tokens=config.max_tokens,
    )
    debug.log_call("characterize_gap", messages, result, context={
        "policy_concept": policy_concept,
    })
    return result


def map_risks(
        policies: list[Policy],
        client: instructor.Instructor,
        config: LLMConfig,
        risk_handlers: dict,
        report=None,
) -> tuple[list[PolicyRiskMapping], dict[str, dict], set[str], dict[str, list[dict]], dict[str, list[str]], list[CoverageGap]]:
    if not policies:
        return [], {}, set(), {}, {}, []

    risk_details_cache: dict[str, dict] = {}
    seen_risk_ids: set[str] = set()  # all risk IDs shown to the model (candidates + related)
    related_risks: dict[str, list[dict]] = {}  # risk_id -> related risk entries from knowledge graph
    risk_actions_cache: dict[str, list[str]] = {}
    coverage_gaps: list[CoverageGap] = []
    mappings: list[PolicyRiskMapping] = []

    for pol in policies:
        # 1. Semantic search for candidate risks
        candidates = risk_handlers["search_risks"](pol.concept_definition, top_k=5)

        # 2. Get full details for each candidate
        enriched_candidates = []
        for c in candidates:
            details = risk_handlers["get_risk_details"](c["id"])
            if details is None:
                continue
            risk_details_cache[c["id"]] = details
            seen_risk_ids.add(c["id"])
            # 3. Get cross-framework mappings (stored for structure stage)
            related = risk_handlers["get_related_risks"](c["id"])
            related_risks[c["id"]] = related
            for r in related:
                seen_risk_ids.add(r["id"])
            # 4. Get related actions (stored for anchor stage)
            actions = risk_handlers["get_related_actions"](c["id"])
            risk_actions_cache[c["id"]] = [a.get("description", "") for a in actions if a.get("description")]
            enriched_candidates.append({**details, "distance": c.get("distance"), "related": related})

        if not enriched_candidates:
            mappings.append(PolicyRiskMapping(
                policy_concept=pol.policy_concept,
                matched_risks=[],
            ))
            continue

        # Build context for LLM — use sequential indices instead of IDs
        index_to_id = {}
        index_to_distance = {}
        candidate_lines = []
        for i, ec in enumerate(enriched_candidates, 1):
            index_to_id[i] = ec['id']
            index_to_distance[i] = ec.get('distance')
            name = ec['name']
            desc = ec.get('description', '')
            line = f"- {i}: {name} — {desc}"
            if ec.get("concern"):
                line += f" (Concern: {ec['concern']})"
            candidate_lines.append(line)

        user_content = (
                f"Policy: {pol.policy_concept}\n"
                f"Definition: {pol.concept_definition}\n\n"
                f"Candidate risks:\n" + "\n".join(candidate_lines)
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
        result = client.chat.completions.create(
            model=config.model,
            response_model=_RiskSelection,
            messages=messages,
            temperature=config.temperature,
            max_retries=config.max_retries,
            max_tokens=config.max_tokens,
        )
        debug.log_call("map_risks", messages, result, context={
            "policy_concept": pol.policy_concept,
            "num_candidates": len(enriched_candidates),
        })

        # Post-processing: map indices back to risk IDs
        valid_risks = []
        for rm in result.matched_risks:
            actual_id = index_to_id.get(rm.risk_index)
            if actual_id is not None:
                distance = index_to_distance.get(rm.risk_index)
                valid_risks.append(RiskMatch(
                    risk_id=actual_id,
                    risk_name=rm.risk_name,
                    relevance=rm.relevance,
                    justification=rm.justification,
                    match_distance=distance,
                ))
                if distance is not None and distance > WEAK_MATCH_THRESHOLD:
                    logger.warning(
                        "Weak match for policy '%s': risk '%s' (distance=%.3f > %.2f)",
                        pol.policy_concept, actual_id, distance, WEAK_MATCH_THRESHOLD,
                    )
                    if report:
                        report.events.append({
                            "stage": "map_risks", "event": "weak_match",
                            "risk_id": actual_id, "distance": distance,
                        })
            else:
                logger.warning("Filtering invalid risk_index: %s", rm.risk_index)
                if report:
                    report.events.append({
                        "stage": "map_risks", "event": "invalid_risk_index",
                        "raw_index": rm.risk_index,
                    })

        # Stitch back metadata the LLM doesn't need to produce
        if report:
            report.events.append({
                "stage": "map_risks", "event": "match_count",
                "policy_concept": pol.policy_concept, "count": len(valid_risks),
            })
        mappings.append(PolicyRiskMapping(
            policy_concept=pol.policy_concept,
            matched_risks=valid_risks,
        ))

        # --- Coverage gap detection ---
        min_distance = min(
            (ec.get("distance") or 0.0) for ec in enriched_candidates
        ) if enriched_candidates else 1.0
        primary_count = sum(1 for r in valid_risks if r.relevance == "primary")
        has_decomposition = (
            pol.decomposition is not None
            and bool(pol.decomposition.agent or pol.decomposition.activity or pol.decomposition.entity)
        )

        gap_score = compute_gap_score(min_distance, primary_count, has_decomposition)
        if gap_score >= GAP_SCORE_THRESHOLD:
            nearest = [
                {"id": ec["id"], "name": ec.get("name", ""), "distance": ec.get("distance")}
                for ec in enriched_candidates[:3]
            ]
            classification = characterize_gap(
                pol.policy_concept,
                pol.concept_definition,
                enriched_candidates[:5],
                client,
                config,
            )
            adjusted_confidence = gap_score * GAP_TYPE_WEIGHTS[classification.gap_type]
            gap = CoverageGap(
                policy_concept=pol.policy_concept,
                concept_definition=pol.concept_definition,
                gap_type=classification.gap_type,
                confidence=round(adjusted_confidence, 3),
                nearest_risks=nearest,
                reasoning=classification.reasoning,
                decomposition=pol.decomposition,
            )
            coverage_gaps.append(gap)
            logger.info(
                "Coverage gap detected for '%s': type=%s confidence=%.3f",
                pol.policy_concept, classification.gap_type, adjusted_confidence,
            )
            if report:
                report.events.append({
                    "stage": "map_risks", "event": "coverage_gap",
                    "policy_concept": pol.policy_concept,
                    "gap_type": classification.gap_type,
                    "confidence": round(adjusted_confidence, 3),
                    "gap_score_raw": round(gap_score, 3),
                    "nearest_risks": nearest,
                })

    return mappings, risk_details_cache, seen_risk_ids, related_risks, risk_actions_cache, coverage_gaps
