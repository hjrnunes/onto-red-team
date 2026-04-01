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


class _AnchorResponse(BaseModel):
    axes: list[VariationAxis]


def anchor(
    risk_mappings: list[PolicyRiskMapping],
    risk_details: dict[str, dict],
    client: instructor.Instructor,
    config: LLMConfig,
    onto_handlers: dict,
    selected_domains: list[str] | None = None,
) -> list[RiskVariationAxes]:
    if not risk_mappings:
        return []

    results: list[RiskVariationAxes] = []

    for mapping in risk_mappings:
        for rm in mapping.matched_risks:
            details = risk_details.get(rm.risk_id, {})
            description = details.get("description", rm.risk_name)
            concern = details.get("concern", "")

            # Search ontology for candidate classes, filtering to selected domains
            raw_candidates = onto_handlers["search_classes"](description, top_k=10)
            if selected_domains:
                candidates = [c for c in raw_candidates
                              if derive_source_ontology(c.get("uri", "")) in selected_domains][:3]
            else:
                candidates = raw_candidates[:3]

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
                line = f"- {ec['uri']}: {ec.get('label', '')} — {ec.get('definition', '')}"
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

            # Post-processing: validate URIs exist in ontology
            valid_axes = []
            for axis in result.axes:
                check = onto_handlers["get_class_definition"](axis.cco_class_uri)
                if check is not None:
                    valid_axes.append(axis)
                else:
                    logger.warning("Filtering invalid cco_class_uri: %s", axis.cco_class_uri)

            # Stitch back metadata the LLM doesn't need to produce
            results.append(RiskVariationAxes(
                risk_id=rm.risk_id,
                risk_name=rm.risk_name,
                policy_concept=mapping.policy_concept,
                axes=valid_axes,
            ))

    return results
