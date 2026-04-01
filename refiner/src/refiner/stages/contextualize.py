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

For each variation axis (a CCO ontology class), you are given its subclasses from domain ontologies. These subclasses form the enumeration space — the specific values that can be substituted when generating diverse prompts.

Filter out irrelevant subclasses and annotate each remaining one with:
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

        # Gather subclasses for each axis — cap to avoid context overflow
        axis_context = []
        for axis in rva.axes:
            subclasses = onto_handlers["get_subclasses"](axis.cco_class_uri, depth=1)
            sub_lines = []
            for sc in subclasses[:10]:
                sub_lines.append(f"  - {sc.get('uri', '')}: {sc.get('label', '')} (depth {sc.get('depth', '?')})")
            axis_context.append(
                f"Axis: {axis.cco_class_label} ({axis.cco_class_uri})\n"
                f"Role: {axis.role}\n"
                f"Subclasses:\n" + ("\n".join(sub_lines) if sub_lines else "  (none)")
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
