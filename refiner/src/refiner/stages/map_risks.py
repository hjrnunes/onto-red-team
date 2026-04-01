import logging

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

SYSTEM_PROMPT = """\
You are mapping client content policies to known AI risk entries from a knowledge graph.

Given a policy definition and a list of candidate risks, select the 2-3 most relevant risks and classify their relevance:
- primary: Directly addresses the policy concern
- supporting: Related but not the primary match
- tangential: Loosely related

IMPORTANT: Keep risk_name values SHORT (max 5 words, use the key concept only). Keep justifications to one sentence."""


class _RiskSelection(BaseModel):
    matched_risks: list[RiskMatch]


def map_risks(
        classifications: list[PolicyClassification],
        client: instructor.Instructor,
        config: LLMConfig,
        risk_handlers: dict,
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
            enriched_candidates.append({**details, "related": related})

        if not enriched_candidates:
            mappings.append(PolicyRiskMapping(
                policy_concept=cls.policy_concept,
                policy_type=cls.policy_type,
                matched_risks=[],
            ))
            continue

        # Build context for LLM
        candidate_lines = []
        for ec in enriched_candidates:
            name = ec['name'][:80]
            desc = ec.get('description', '')[:120]
            line = f"- {ec['id']}: {name} — {desc}"
            if ec.get("concern"):
                line += f" (Concern: {ec['concern'][:80]})"
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

        # Post-processing: validate risk IDs exist
        valid_ids = set(risk_details_cache.keys())
        valid_risks = []
        for rm in result.matched_risks:
            if rm.risk_id in valid_ids:
                valid_risks.append(rm)
            else:
                logger.warning("Filtering hallucinated risk_id: %s", rm.risk_id)

        # Stitch back metadata the LLM doesn't need to produce
        mappings.append(PolicyRiskMapping(
            policy_concept=cls.policy_concept,
            policy_type=cls.policy_type,
            matched_risks=valid_risks,
        ))

    return mappings, risk_details_cache, seen_risk_ids, related_risks
