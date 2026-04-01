import logging

import instructor
from refiner.llm import LLMConfig
from refiner.models import (
    PolicyClassification,
    PolicyRiskMapping,
    RiskMatch,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are mapping client content policies to known AI risk entries from a knowledge graph.

Given a policy definition and a list of candidate risks, select the 2-3 most relevant risks and classify their relevance:
- primary: Directly addresses the policy concern
- supporting: Related but not the primary match
- tangential: Loosely related

Include up to 2 cross-framework mappings that add genuine coverage.

IMPORTANT: Keep risk_name values SHORT (max 5 words, use the key concept only). Keep justifications to one sentence. Return a PolicyRiskMapping with matched_risks and cross_mappings."""


def map_risks(
    classifications: list[PolicyClassification],
    client: instructor.Instructor,
    config: LLMConfig,
    risk_handlers: dict,
) -> tuple[list[PolicyRiskMapping], dict[str, dict]]:
    if not classifications:
        return [], {}

    risk_details_cache: dict[str, dict] = {}
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
            # 3. Get cross-framework mappings
            related = risk_handlers["get_related_risks"](c["id"])
            enriched_candidates.append({**details, "cross_mappings": related})

        if not enriched_candidates:
            mappings.append(PolicyRiskMapping(
                policy_concept=cls.policy_concept,
                policy_type=cls.policy_type,
                matched_risks=[],
                cross_mappings=[],
            ))
            continue

        # Build context for LLM — truncate long names to keep within token limits
        candidate_lines = []
        for ec in enriched_candidates:
            name = ec['name'][:80]
            desc = ec.get('description', '')[:120]
            line = f"- {ec['id']}: {name} — {desc}"
            if ec.get("concern"):
                line += f" (Concern: {ec['concern'][:80]})"
            if ec["cross_mappings"]:
                xm = ", ".join(f"{x['id']}[{x['mapping_type']}]" for x in ec["cross_mappings"][:3])
                line += f"\n  Cross-mappings: {xm}"
            candidate_lines.append(line)

        user_content = (
            f"Policy: {cls.policy_concept}\n"
            f"Definition: {cls.concept_definition}\n"
            f"Policy Type: {cls.policy_type}\n\n"
            f"Candidate risks:\n" + "\n".join(candidate_lines)
        )

        result = client.chat.completions.create(
            model=config.model,
            response_model=PolicyRiskMapping,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=config.temperature,
            max_retries=config.max_retries,
            max_tokens=config.max_tokens,
        )

        # Post-processing: validate risk IDs exist
        valid_ids = set(risk_details_cache.keys())
        valid_risks = []
        for rm in result.matched_risks:
            if rm.risk_id in valid_ids:
                valid_risks.append(rm)
            else:
                logger.warning("Filtering hallucinated risk_id: %s", rm.risk_id)
        result = result.model_copy(update={"matched_risks": valid_risks})

        mappings.append(result)

    return mappings, risk_details_cache
