import logging
from typing import Literal

import instructor
from pydantic import BaseModel
from refiner.llm import LLMConfig
from refiner.models import (
    PolicyClassification,
    PolicyRiskMapping,
    RiskMatch,
)
from refiner import debug

logger = logging.getLogger(__name__)

WEAK_MATCH_THRESHOLD = 0.6

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


def map_risks(
        classifications: list[PolicyClassification],
        client: instructor.Instructor,
        config: LLMConfig,
        risk_handlers: dict,
        report=None,
) -> tuple[list[PolicyRiskMapping], dict[str, dict], set[str], dict[str, list[dict]]]:
    if not classifications:
        return [], {}, set(), {}

    risk_details_cache: dict[str, dict] = {}
    seen_risk_ids: set[str] = set()  # all risk IDs shown to the model (candidates + related)
    related_risks: dict[str, list[dict]] = {}  # risk_id -> related risk entries from knowledge graph
    mappings: list[PolicyRiskMapping] = []

    for cls in classifications:
        # 1. Semantic search for candidate risks
        candidates = risk_handlers["search_risks"](cls.concept_definition, top_k=5)

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
            enriched_candidates.append({**details, "distance": c.get("distance"), "related": related})

        if not enriched_candidates:
            mappings.append(PolicyRiskMapping(
                policy_concept=cls.policy_concept,
                policy_type=cls.policy_type,
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
            if ec["related"]:
                xm = ", ".join(f"{x['id']}[{x['mapping_type']}]" for x in ec["related"][:3])
                line += f"\n  Cross-mappings: {xm}"
            candidate_lines.append(line)

        user_content = (
                f"Policy: {cls.policy_concept}\n"
                f"Definition: {cls.concept_definition}\n"
                f"Policy Type: {cls.policy_type}\n\n"
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
            "policy_concept": cls.policy_concept,
            "policy_type": cls.policy_type,
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
                        cls.policy_concept, actual_id, distance, WEAK_MATCH_THRESHOLD,
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
                "policy_concept": cls.policy_concept, "count": len(valid_risks),
            })
        mappings.append(PolicyRiskMapping(
            policy_concept=cls.policy_concept,
            policy_type=cls.policy_type,
            matched_risks=valid_risks,
        ))

    return mappings, risk_details_cache, seen_risk_ids, related_risks
