from dataclasses import dataclass

import instructor
from refiner.llm import LLMConfig
from refiner.models import (
    Policy,
    PolicyClassification,
    PolicyDocument,
    PolicyRiskMapping,
    RiskVariationAxes,
    DomainContextProfile,
    RunReport,
)
from refiner.stages.classify import classify
from refiner.stages.identify_domains import identify_domains
from refiner.stages.map_risks import map_risks
from refiner.stages.anchor import anchor, SearchMergeStrategy
from refiner.stages.contextualize import contextualize

STAGES = ("classify", "identify_domains", "map_risks", "anchor", "contextualize")


@dataclass
class PipelineState:
    policies: list[Policy]
    classifications: list[PolicyClassification] | None = None
    selected_domains: list[str] | None = None
    risk_mappings: list[PolicyRiskMapping] | None = None
    risk_details: dict[str, dict] | None = None
    seen_risk_ids: set[str] | None = None
    related_risks: dict[str, list[dict]] | None = None
    risk_actions: dict[str, list[str]] | None = None
    variation_axes: list[RiskVariationAxes] | None = None
    domain_context: list[DomainContextProfile] | None = None
    report: RunReport | None = None
    doc_context: PolicyDocument | None = None


def run_pipeline(
    policies: list[Policy],
    client: instructor.Instructor,
    config: LLMConfig,
    risk_handlers: dict,
    onto_handlers: dict,
    until: str | None = None,
    report: RunReport | None = None,
    merge_strategy: SearchMergeStrategy | None = None,
) -> PipelineState:
    state = PipelineState(policies=policies, report=report)

    state.classifications = classify(state.policies, client, config, report=report)
    if report:
        report.stages_completed.append("classify")
    if until == "classify":
        return state

    state.selected_domains = identify_domains(state.classifications, client, config, report=report)
    if report:
        report.stages_completed.append("identify_domains")
    if until == "identify_domains":
        return state

    state.risk_mappings, state.risk_details, state.seen_risk_ids, state.related_risks, state.risk_actions = map_risks(
        state.classifications, client, config, risk_handlers, report=report
    )
    if report:
        report.stages_completed.append("map_risks")
    if until == "map_risks":
        return state

    state.variation_axes = anchor(
        state.risk_mappings, state.risk_details, client, config, onto_handlers,
        selected_domains=state.selected_domains,
        risk_actions=state.risk_actions,
        related_risks=state.related_risks,
        merge_strategy=merge_strategy,
        report=report,
    )
    if report:
        report.stages_completed.append("anchor")
    if until == "anchor":
        return state

    state.domain_context = contextualize(
        state.variation_axes, client, config, onto_handlers,
        selected_domains=state.selected_domains,
        risk_details=state.risk_details,
        report=report,
    )
    if report:
        report.stages_completed.append("contextualize")
    return state
