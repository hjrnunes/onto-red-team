import logging

import instructor
from refiner.llm import LLMConfig
from refiner.models import (
    RiskVariationAxes,
    DomainContextProfile,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are generating domain context profiles for AI risk variation axes.

For each variation axis (a CCO ontology class), you are given its subclasses from domain ontologies. These subclasses form the enumeration space — the specific values that can be substituted when generating diverse prompts.

Filter out irrelevant subclasses and annotate each remaining one with:
- source_ontology: Which ontology it comes from (e.g., "FIBO", "CCO", "OBO", "IOF")
- relevance: "high" (directly relevant), "medium" (potentially relevant), "low" (edge case)

Return a DomainContextProfile preserving the risk_id, risk_name, and policy_concept."""


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

        # Gather subclasses for each axis
        axis_context = []
        for axis in rva.axes:
            subclasses = onto_handlers["get_subclasses"](axis.cco_class_uri, depth=2)
            sub_lines = []
            for sc in subclasses:
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

        result = client.chat.completions.create(
            model=config.model,
            response_model=DomainContextProfile,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=config.temperature,
            max_retries=config.max_retries,
        )

        # Post-processing: validate enumeration URIs resolve in ontology
        validated_axes = []
        for axis in result.axes:
            valid_enums = []
            for enum in axis.enumerations:
                check = onto_handlers["get_class_definition"](enum.class_uri)
                if check is not None:
                    valid_enums.append(enum)
                else:
                    logger.warning("Filtering invalid enumeration class_uri: %s", enum.class_uri)
            validated_axes.append(axis.model_copy(update={"enumerations": valid_enums}))
        result = result.model_copy(update={"axes": validated_axes})

        results.append(result)

    return results
