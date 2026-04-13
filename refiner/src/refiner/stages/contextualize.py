import logging
from typing import Literal

import instructor
from pydantic import BaseModel
from refiner.llm import LLMConfig
from refiner.models import (
    Policy,
    RiskVariationAxes,
    DomainContextProfile,
    DomainContextAxis,
    AxisEnumeration,
    RunReport,
)
from refiner import debug

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are generating concrete domain-specific variations for an AI risk axis.

Given:
- A risk description and concern
- A policy with boundaries and controls
- An ontology class (the variation axis) with BFO category and vocabulary context
- Optional subclass examples from the ontology

Generate 5-8 specific, diverse instances that represent concrete ways
this axis manifests in the real world, relevant to the risk and policy.

Each instance should be a short phrase (3-10 words) that could substitute
into a prompt template. Prefer specific, concrete instances over abstract ones.

Annotate each with relevance: "high" (directly tests policy), "medium"
(indirectly relevant), "low" (edge case worth exploring)."""


class _Variation(BaseModel):
    instance: str
    relevance: Literal["high", "medium", "low"]


class _ContextResponse(BaseModel):
    variations: list[_Variation]


def _format_vocabulary_context(vocab_ctx: dict) -> str:
    """Format vocabulary context dict into prompt block."""
    if not vocab_ctx:
        return ""
    lines = ["Vocabulary context:"]
    for key, label in [
        ("stakeholders", "Stakeholders"),
        ("data_sensitivity", "Data sensitivity"),
        ("rights", "Rights at stake"),
        ("sector_purposes", "Sector"),
    ]:
        items = vocab_ctx.get(key, [])
        if items:
            labels = ", ".join(c["label"] for c in items)
            lines.append(f"  {label}: {labels}")
    return "\n".join(lines)


def _find_policy(policies: list[Policy] | None, policy_concept: str) -> Policy | None:
    """Find the matching policy by concept name."""
    if not policies:
        return None
    for p in policies:
        if p.policy_concept == policy_concept:
            return p
    return None


def contextualize(
    variation_axes: list[RiskVariationAxes],
    client: instructor.Instructor,
    config: LLMConfig,
    onto_handlers: dict,
    selected_domains: list[str] | None = None,
    risk_details: dict[str, dict] | None = None,
    report: RunReport | None = None,
    policies: list[Policy] | None = None,
    vocabulary_contexts: dict[str, dict] | None = None,
) -> list[DomainContextProfile]:
    if not variation_axes:
        return []

    results: list[DomainContextProfile] = []
    context_cache: dict[str, list[DomainContextAxis]] = {}  # risk_id -> cached axes

    for rva in variation_axes:
        if rva.risk_id in context_cache:
            logger.debug("Cache hit for risk_id=%s, reusing context", rva.risk_id)
            results.append(DomainContextProfile(
                risk_id=rva.risk_id,
                risk_name=rva.risk_name,
                policy_concept=rva.policy_concept,
                axes=context_cache[rva.risk_id],
            ))
            continue

        if not rva.axes:
            context_cache[rva.risk_id] = []
            results.append(DomainContextProfile(
                risk_id=rva.risk_id,
                risk_name=rva.risk_name,
                policy_concept=rva.policy_concept,
                axes=[],
            ))
            continue

        details = risk_details.get(rva.risk_id, {}) if risk_details else {}
        description = details.get("description", "")
        concern = details.get("concern", "")

        policy = _find_policy(policies, rva.policy_concept)
        vocab_ctx = (vocabulary_contexts or {}).get(rva.risk_id, {})

        populated_axes = []
        for axis in rva.axes:
            # Get optional subclass examples as reference
            subclass_examples = []
            subclasses = onto_handlers["get_subclasses"](axis.cco_class_uri, depth=1)
            for sc in subclasses[:5]:
                defn = onto_handlers["get_class_definition"](sc.get("uri", ""))
                if defn:
                    subclass_examples.append(defn.get("label", sc.get("label", "")))

            # Build prompt
            vocab_block = _format_vocabulary_context(vocab_ctx)
            bfo_tag = f" [{axis.bfo_category}]" if axis.bfo_category else ""
            vocab_tag = ""
            if axis.vocabulary_concept:
                vocab_tag = f" (via {axis.vocabulary_label or axis.vocabulary_concept})"

            axis_block = (
                f"Axis: {axis.cco_class_label}{bfo_tag}{vocab_tag}\n"
                f"Rationale: {axis.rationale}\n"
            )
            if subclass_examples:
                axis_block += f"Ontology examples: {', '.join(subclass_examples)}\n"

            policy_block = ""
            if policy:
                policy_block = f"\nPolicy: {policy.policy_concept}\n"
                policy_block += f"Definition: {policy.concept_definition}\n"
                if policy.boundary_examples:
                    boundary = policy.boundary_examples[0]
                    policy_block += f"Prohibited: {boundary.prohibited}\n"
                    policy_block += f"Acceptable: {boundary.acceptable}\n"
                if policy.acceptable_uses:
                    policy_block += f"Acceptable uses: {', '.join(policy.acceptable_uses[:3])}\n"
                if policy.risk_controls:
                    policy_block += f"Controls: {', '.join(policy.risk_controls[:3])}\n"

            user_content = (
                f"Risk: {rva.risk_name}\n"
                f"Description: {description}\n"
                + (f"Concern: {concern}\n" if concern else "")
                + "\n"
                + axis_block
                + (f"\n{vocab_block}\n" if vocab_block else "")
                + policy_block
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
                "axis_uri": axis.cco_class_uri,
                "axis_label": axis.cco_class_label,
            })

            if report:
                report.events.append({
                    "stage": "contextualize", "event": "variations_generated",
                    "risk_id": rva.risk_id,
                    "axis_uri": axis.cco_class_uri,
                    "count": len(result.variations),
                })

            enumerations = []
            for var in result.variations:
                enumerations.append(AxisEnumeration(
                    class_uri=f"generated:{var.instance.lower().replace(' ', '_')}",
                    class_label=var.instance,
                    source_ontology="generated",
                    relevance=var.relevance,
                    provenance="generated",
                ))

            if enumerations:
                populated_axes.append(DomainContextAxis(
                    cco_class_uri=axis.cco_class_uri,
                    cco_class_label=axis.cco_class_label,
                    bfo_category=axis.bfo_category,
                    vocabulary_concept=axis.vocabulary_concept,
                    vocabulary_label=axis.vocabulary_label,
                    vocabulary_context=vocab_ctx,
                    enumerations=enumerations,
                    roles=[],
                ))
            elif report:
                report.events.append({
                    "stage": "contextualize", "event": "empty_variations",
                    "risk_id": rva.risk_id,
                    "axis_uri": axis.cco_class_uri,
                })

        context_cache[rva.risk_id] = populated_axes

        results.append(DomainContextProfile(
            risk_id=rva.risk_id,
            risk_name=rva.risk_name,
            policy_concept=rva.policy_concept,
            axes=populated_axes,
        ))

    return results
