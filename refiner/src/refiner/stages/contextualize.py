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
    RunReport,
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


def _relevance_rank(relevance: str) -> int:
    return {"high": 3, "medium": 2, "low": 1}.get(relevance, 0)


def contextualize(
    variation_axes: list[RiskVariationAxes],
    client: instructor.Instructor,
    config: LLMConfig,
    onto_handlers: dict,
    selected_domains: list[str] | None = None,
    risk_details: dict[str, dict] | None = None,
    report: RunReport | None = None,
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

        # Build lookup of input axes by URI for stitching back metadata
        input_axes_by_uri = {axis.cco_class_uri: axis for axis in rva.axes}
        axis_provenance: dict[str, str] = {}  # axis URI -> "subclass" or "sibling"

        # Gather candidates for each axis — subclasses first, siblings as fallback
        axis_context = []
        for axis in rva.axes:
            subclasses = onto_handlers["get_subclasses"](axis.cco_class_uri, depth=1)
            if subclasses:
                candidates = subclasses[:10]
                source = "Subclasses"
                axis_provenance[axis.cco_class_uri] = "subclass"
            else:
                siblings = onto_handlers["get_siblings"](axis.cco_class_uri)
                candidates = [s for s in siblings if s.get("uri") != axis.cco_class_uri][:10]
                source = "Siblings"
                axis_provenance[axis.cco_class_uri] = "sibling"
                if report:
                    report.events.append({
                        "stage": "contextualize", "event": "sibling_fallback",
                        "axis_uri": axis.cco_class_uri, "sibling_count": len(candidates),
                    })
            candidate_lines = []
            for c in candidates:
                candidate_lines.append(f"  - {c.get('uri', '')}: {c.get('label', '')}")
            axis_context.append(
                f"Axis: {axis.cco_class_label} ({axis.cco_class_uri})\n"
                f"Roles: {', '.join(axis.roles)}\n"
                f"{source}:\n" + ("\n".join(candidate_lines) if candidate_lines else "  (none)")
            )

        details = risk_details.get(rva.risk_id, {}) if risk_details else {}
        description = details.get("description", "")
        concern = details.get("concern", "")

        user_content = (
            f"Risk: {rva.risk_name} (ID: {rva.risk_id})\n"
            f"Description: {description}\n"
            f"Concern: {concern}\n"
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
                    if report:
                        report.events.append({
                            "stage": "contextualize", "event": "self_reference_filtered",
                            "axis_uri": input_axis.cco_class_uri,
                        })
                    continue  # skip self-reference
                # Domain filtering: check enumeration URI against selected domains
                if selected_domains:
                    enum_domain = derive_source_ontology(enum.class_uri)
                    if enum_domain not in selected_domains:
                        logger.info(
                            "Filtering enumeration %s (domain %s) — not in selected domains %s",
                            enum.class_uri, enum_domain, selected_domains,
                        )
                        if report:
                            report.events.append({
                                "stage": "contextualize", "event": "enumeration_domain_filtered",
                                "axis_uri": input_axis.cco_class_uri,
                                "enum_uri": enum.class_uri,
                                "enum_domain": enum_domain,
                                "selected_domains": selected_domains,
                            })
                        continue
                check = onto_handlers["get_class_definition"](enum.class_uri)
                if check is not None:
                    valid_enums.append(AxisEnumeration(
                        class_uri=enum.class_uri,
                        class_label=enum.class_label,
                        source_ontology=derive_source_ontology(enum.class_uri),
                        relevance=enum.relevance,
                        provenance=axis_provenance.get(input_axis.cco_class_uri, "subclass"),
                    ))
                else:
                    logger.warning("Filtering invalid enumeration class_uri: %s", enum.class_uri)

            # Disjointness filter
            if onto_handlers.get("get_disjoint_classes"):
                filtered_by_disjoint = []
                removed_uris: set[str] = set()
                for enum in valid_enums:
                    if enum.class_uri in removed_uris:
                        continue
                    disjoints = set(onto_handlers["get_disjoint_classes"](enum.class_uri))
                    conflicting = [e for e in valid_enums if e.class_uri in disjoints and e.class_uri not in removed_uris]
                    for conflict in conflicting:
                        if _relevance_rank(enum.relevance) >= _relevance_rank(conflict.relevance):
                            removed_uris.add(conflict.class_uri)
                        else:
                            removed_uris.add(enum.class_uri)
                            break
                    if enum.class_uri not in removed_uris:
                        filtered_by_disjoint.append(enum)
                if removed_uris and report:
                    report.events.append({
                        "stage": "contextualize", "event": "disjoint_filtered",
                        "risk_id": rva.risk_id,
                        "axis_uri": input_axis.cco_class_uri,
                        "kept": [e.class_uri for e in filtered_by_disjoint],
                        "filtered": list(removed_uris),
                    })
                valid_enums = filtered_by_disjoint

            validated_axes.append(DomainContextAxis(
                cco_class_uri=input_axis.cco_class_uri,
                cco_class_label=input_axis.cco_class_label,
                roles=input_axis.roles,
                enumerations=valid_enums,
            ))

        # Emit event for empty enumerations
        for va in validated_axes:
            if not va.enumerations and report:
                report.events.append({
                    "stage": "contextualize", "event": "empty_enumerations",
                    "risk_id": rva.risk_id, "axis_uri": va.cco_class_uri,
                })

        context_cache[rva.risk_id] = validated_axes

        results.append(DomainContextProfile(
            risk_id=rva.risk_id,
            risk_name=rva.risk_name,
            policy_concept=rva.policy_concept,
            axes=validated_axes,
        ))

    return results
