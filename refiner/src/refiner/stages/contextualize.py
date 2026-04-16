import logging
from typing import Literal

import instructor
from pydantic import BaseModel
from refiner.llm import LLMConfig
from refiner.models import (
    Policy,
    RiskLandscape,
    RiskVariationAxes,
    DomainContext,
    PolicyDomainContext,
    RiskGrounding,
    RiskSummary,
    DomainContextAxis,
    AxisEnumeration,
    RunReport,
)
from refiner import debug
from refiner.stages.identify_domains import derive_source_ontology

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are generating domain-specific concept terms for an AI risk axis.

Given:
- A risk description and concern
- A policy with boundaries and controls
- An ontology class (the variation axis) with BFO category and vocabulary context
- Optional subclass examples from the ontology

Generate 5-8 diverse concept-level terms that name types or categories
relevant to this axis, risk, and policy. Match the style of ontology class
labels: short categorical noun phrases (2-6 words), NOT scenarios,
instructions, or sentences.

Good: "palliative sedation therapy", "advance directive consultation"
Bad: "Drafting a morphine dosage schedule for patient Jane Doe"

Do not include named entities, personal names, or specific actions.
Each term should name a kind of thing, not describe a situation.

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


def _collect_ontology_enumerations(
    axis_uri: str,
    onto_handlers: dict,
    selected_domains: list[str] | None,
    max_enumerations: int = 10,
) -> list[AxisEnumeration]:
    """Collect enumerations from ontology subclasses, with sibling fallback for leaf nodes."""
    enumerations: list[AxisEnumeration] = []

    subclasses = onto_handlers["get_subclasses"](axis_uri, depth=1)
    for sc in subclasses:
        uri = sc.get("uri", "")
        if not uri:
            continue
        domain = derive_source_ontology(uri)
        if selected_domains and domain and domain not in selected_domains:
            continue
        defn = onto_handlers["get_class_definition"](uri)
        if defn is None:
            continue
        label = defn.get("label", sc.get("label", ""))
        if not label:
            continue
        enumerations.append(AxisEnumeration(
            class_uri=uri, class_label=label,
            source_ontology=domain or "unknown", relevance="high", provenance="subclass",
        ))
        if len(enumerations) >= max_enumerations:
            break

    if not enumerations:
        siblings = onto_handlers["get_siblings"](axis_uri)
        for sib in siblings:
            uri = sib.get("uri", "")
            if not uri or uri == axis_uri:
                continue
            domain = derive_source_ontology(uri)
            if selected_domains and domain and domain not in selected_domains:
                continue
            defn = onto_handlers["get_class_definition"](uri)
            if defn is None:
                continue
            label = defn.get("label", sib.get("label", ""))
            if not label:
                continue
            enumerations.append(AxisEnumeration(
                class_uri=uri, class_label=label,
                source_ontology=domain or "unknown", relevance="medium", provenance="sibling",
            ))
            if len(enumerations) >= max_enumerations:
                break

    return enumerations


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
    run_slug: str = "",
    timestamp: str = "",
    risk_landscape: RiskLandscape | None = None,
    enumerations_per_axis: int = 8,
) -> DomainContext:
    # Extract fields from RiskLandscape if provided
    if risk_landscape is not None:
        selected_domains = selected_domains or risk_landscape.selected_domains
        risk_details = risk_details or {
            r.risk_id: {
                "id": r.risk_id, "name": r.risk_name,
                "description": r.risk_description or "",
                "concern": r.risk_concern or "",
            }
            for r in risk_landscape.risks
        }
        run_slug = run_slug or risk_landscape.run_slug
        timestamp = timestamp or risk_landscape.timestamp

    if not variation_axes:
        return DomainContext()

    context_cache: dict[str, list[DomainContextAxis]] = {}  # risk_id -> cached axes
    policy_groundings: dict[str, list[RiskGrounding]] = {}
    seen_risk_ids: set[str] = set()
    risk_names: dict[str, str] = {}

    for rva in variation_axes:
        if rva.risk_id in context_cache:
            logger.debug("Cache hit for risk_id=%s, reusing context", rva.risk_id)
            grounding = RiskGrounding(risk_id=rva.risk_id, axes=context_cache[rva.risk_id], axis_groups=rva.axis_groups)
            policy_groundings.setdefault(rva.policy_concept, []).append(grounding)
            seen_risk_ids.add(rva.risk_id)
            risk_names[rva.risk_id] = rva.risk_name
            continue

        if not rva.axes:
            context_cache[rva.risk_id] = []
            grounding = RiskGrounding(risk_id=rva.risk_id, axes=[], axis_groups=[])
            policy_groundings.setdefault(rva.policy_concept, []).append(grounding)
            seen_risk_ids.add(rva.risk_id)
            risk_names[rva.risk_id] = rva.risk_name
            continue

        details = risk_details.get(rva.risk_id, {}) if risk_details else {}
        description = details.get("description", "")
        concern = details.get("concern", "")

        policy = _find_policy(policies, rva.policy_concept)
        vocab_ctx = (vocabulary_contexts or {}).get(rva.risk_id, {})

        populated_axes = []
        for axis in rva.axes:
            # Collect ontology enumerations first
            onto_enums = _collect_ontology_enumerations(
                axis.cco_class_uri, onto_handlers, selected_domains, max_enumerations=enumerations_per_axis
            )

            if report:
                subclass_count = sum(1 for e in onto_enums if e.provenance == "subclass")
                sibling_count = sum(1 for e in onto_enums if e.provenance == "sibling")
                report.events.append({
                    "stage": "contextualize", "event": "ontology_enumerations",
                    "risk_id": rva.risk_id,
                    "axis_uri": axis.cco_class_uri,
                    "subclass_count": subclass_count,
                    "sibling_count": sibling_count,
                })

            enumerations = []
            # If we have enough ontology enumerations, skip LLM
            if len(onto_enums) >= enumerations_per_axis:
                enumerations = onto_enums[:enumerations_per_axis]
            else:
                # Hybrid: supplement with LLM
                needed = enumerations_per_axis - len(onto_enums)

                # Get subclass examples for prompt
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

                # Adjust prompt based on whether we already have ontology enums
                if onto_enums:
                    onto_labels = [e.class_label for e in onto_enums]
                    axis_block += f"Already found from ontology: {', '.join(onto_labels)}\n"
                    axis_block += f"Generate {needed} additional diverse variations.\n"
                elif subclass_examples:
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
                llm_response = client.chat.completions.create(
                    model=config.model,
                    response_model=_ContextResponse,
                    messages=messages,
                    temperature=config.temperature,
                    max_retries=config.max_retries,
                    max_tokens=config.max_tokens,
                )
                debug.log_call("contextualize", messages, llm_response, context={
                    "risk_id": rva.risk_id,
                    "axis_uri": axis.cco_class_uri,
                    "axis_label": axis.cco_class_label,
                })

                llm_enums = []
                for var in llm_response.variations[:needed]:
                    llm_enums.append(AxisEnumeration(
                        class_uri=f"generated:{var.instance.lower().replace(' ', '_')}",
                        class_label=var.instance,
                        source_ontology="generated",
                        relevance=var.relevance,
                        provenance="generated",
                        generated_by=config.model,
                    ))

                enumerations = onto_enums + llm_enums

            if report:
                onto_count = sum(1 for e in enumerations if e.provenance in ("subclass", "sibling"))
                generated_count = sum(1 for e in enumerations if e.provenance == "generated")
                report.events.append({
                    "stage": "contextualize", "event": "enumerations_populated",
                    "risk_id": rva.risk_id,
                    "axis_uri": axis.cco_class_uri,
                    "total": len(enumerations),
                    "ontology": onto_count,
                    "generated": generated_count,
                })

            if enumerations:
                populated_axes.append(DomainContextAxis(
                    cco_class_uri=axis.cco_class_uri,
                    cco_class_label=axis.cco_class_label,
                    bfo_category=axis.bfo_category,
                    vocabulary_concept=axis.vocabulary_concept,
                    vocabulary_label=axis.vocabulary_label,
                    vocabulary_context=vocab_ctx,
                    derivation=axis.derivation,
                    enumerations=enumerations,
                ))
            elif report:
                report.events.append({
                    "stage": "contextualize", "event": "empty_variations",
                    "risk_id": rva.risk_id,
                    "axis_uri": axis.cco_class_uri,
                })

        context_cache[rva.risk_id] = populated_axes

        # Filter axis_groups to only include axes that survived
        populated_uris = {a.cco_class_uri for a in populated_axes}
        filtered_groups = [[uri for uri in group if uri in populated_uris] for group in rva.axis_groups]
        filtered_groups = [g for g in filtered_groups if len(g) >= 2]

        grounding = RiskGrounding(risk_id=rva.risk_id, axes=context_cache[rva.risk_id], axis_groups=filtered_groups)
        policy_groundings.setdefault(rva.policy_concept, []).append(grounding)
        seen_risk_ids.add(rva.risk_id)
        risk_names[rva.risk_id] = rva.risk_name

    # Build risk_framework and cross_mappings lookup from RiskLandscape
    landscape_risks = {}
    if risk_landscape is not None:
        landscape_risks = {r.risk_id: r for r in risk_landscape.risks}

    risks = []
    for rid in seen_risk_ids:
        details = risk_details.get(rid, {}) if risk_details else {}
        lr = landscape_risks.get(rid)
        risks.append(RiskSummary(
            risk_id=rid,
            risk_name=risk_names.get(rid, ""),
            risk_description=details.get("description", ""),
            risk_concern=details.get("concern", ""),
            risk_framework=lr.risk_framework if lr else None,
            cross_mappings=lr.cross_mappings if lr else [],
        ))

    policy_contexts = [
        PolicyDomainContext(policy_concept=pc, risk_groundings=groundings)
        for pc, groundings in policy_groundings.items()
    ]

    return DomainContext(
        model=config.model,
        timestamp=timestamp,
        run_slug=run_slug,
        selected_domains=selected_domains or [],
        risks=risks,
        policy_contexts=policy_contexts,
    )
