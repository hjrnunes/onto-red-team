import logging
from typing import Literal

import instructor
from pydantic import BaseModel
from refiner.llm import LLMConfig
from refiner.models import (
    RiskVariationAxes,
    DomainContextProfile,
    DomainContextAxis,
    AxisEnumeration,
)
from refiner import debug
from refiner.stages.identify_domains import derive_source_ontology

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are generating domain context profiles for AI risk variation axes.

For each variation axis (an ontology class), you are given candidate classes that form the enumeration space — the specific values that can be substituted when generating diverse prompts.

Candidates may be subclasses (specializations) or siblings (parallel concepts at the same level). Both are valid enumeration values.

Filter out irrelevant candidates and annotate each remaining one with:
- relevance: "high" (directly relevant), "medium" (potentially relevant), "low" (edge case)

Return one entry per axis using the axis URI as a key, with the filtered enumerations."""


class _EnumResponse(BaseModel):
    class_uri: str
    class_label: str
    relevance: Literal["high", "medium", "low"]


class _AxisResponse(BaseModel):
    cco_class_uri: str  # matching key to input axis
    enumerations: list[_EnumResponse]


class _ContextResponse(BaseModel):
    axes: list[_AxisResponse]


def contextualize(
    variation_axes: list[RiskVariationAxes],
    client: instructor.Instructor,
    config: LLMConfig,
    onto_handlers: dict,
) -> list[DomainContextProfile]:
    if not variation_axes:
        return []

    results: list[DomainContextProfile] = []

    for rva in variation_axes:
        if not rva.axes:
            results.append(DomainContextProfile(
                risk_id=rva.risk_id,
                risk_name=rva.risk_name,
                policy_concept=rva.policy_concept,
                axes=[],
            ))
            continue

        # Build lookup of input axes by URI for stitching back metadata
        input_axes_by_uri = {axis.cco_class_uri: axis for axis in rva.axes}

        # Gather candidates for each axis — subclasses first, siblings as fallback
        axis_context = []
        for axis in rva.axes:
            subclasses = onto_handlers["get_subclasses"](axis.cco_class_uri, depth=1)
            if subclasses:
                candidates = subclasses[:10]
                source = "Subclasses"
            else:
                siblings = onto_handlers["get_siblings"](axis.cco_class_uri)
                candidates = [s for s in siblings if s.get("uri") != axis.cco_class_uri][:10]
                source = "Siblings"
            candidate_lines = []
            for c in candidates:
                candidate_lines.append(f"  - {c.get('uri', '')}: {c.get('label', '')}")
            axis_context.append(
                f"Axis: {axis.cco_class_label} ({axis.cco_class_uri})\n"
                f"Role: {axis.role}\n"
                f"{source}:\n" + ("\n".join(candidate_lines) if candidate_lines else "  (none)")
            )

        user_content = (
            f"Risk: {rva.risk_name} (ID: {rva.risk_id})\n"
            f"Policy: {rva.policy_concept}\n\n"
            + "\n\n".join(axis_context)
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
        result = client.chat.completions.create(
            model=config.model,
            response_model=_ContextResponse,
            messages=messages,
            temperature=config.temperature,
            max_retries=config.max_retries,
            max_tokens=config.max_tokens,
        )
        debug.log_call("contextualize", messages, result, context={
            "risk_id": rva.risk_id,
            "risk_name": rva.risk_name,
            "policy_concept": rva.policy_concept,
            "num_axes": len(rva.axes),
        })

        # Post-processing: validate enumeration URIs, derive source_ontology,
        # stitch back axis metadata from input
        validated_axes = []
        for resp_axis in result.axes:
            input_axis = input_axes_by_uri.get(resp_axis.cco_class_uri)
            if input_axis is None:
                logger.warning("LLM returned unknown axis URI: %s", resp_axis.cco_class_uri)
                continue

            valid_enums = []
            for enum in resp_axis.enumerations:
                if enum.class_uri == input_axis.cco_class_uri:
                    continue  # skip self-reference
                check = onto_handlers["get_class_definition"](enum.class_uri)
                if check is not None:
                    valid_enums.append(AxisEnumeration(
                        class_uri=enum.class_uri,
                        class_label=enum.class_label,
                        source_ontology=derive_source_ontology(enum.class_uri),
                        relevance=enum.relevance,
                    ))
                else:
                    logger.warning("Filtering invalid enumeration class_uri: %s", enum.class_uri)

            validated_axes.append(DomainContextAxis(
                cco_class_uri=input_axis.cco_class_uri,
                cco_class_label=input_axis.cco_class_label,
                role=input_axis.role,
                enumerations=valid_enums,
            ))

        results.append(DomainContextProfile(
            risk_id=rva.risk_id,
            risk_name=rva.risk_name,
            policy_concept=rva.policy_concept,
            axes=validated_axes,
        ))

    return results
