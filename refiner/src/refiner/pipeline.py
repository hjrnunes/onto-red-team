from dataclasses import dataclass, field

import instructor
from refiner.llm import LLMConfig
from refiner.models import (
    Policy,
    PolicyClassification,
    PolicyRiskMapping,
    RiskVariationAxes,
    DomainContextProfile,
)
from refiner.stages.classify import classify
from refiner.stages.map_risks import map_risks
from refiner.stages.anchor import anchor
from refiner.stages.contextualize import contextualize

STAGES = ("classify", "map_risks", "anchor", "contextualize")


@dataclass
class PipelineState:
    policies: list[Policy]
    classifications: list[PolicyClassification] | None = None
    risk_mappings: list[PolicyRiskMapping] | None = None
    risk_details: dict[str, dict] | None = None
    variation_axes: list[RiskVariationAxes] | None = None
    domain_context: list[DomainContextProfile] | None = None


def run_pipeline(
    policies: list[Policy],
    client: instructor.Instructor,
    config: LLMConfig,
    risk_handlers: dict,
    onto_handlers: dict,
    until: str | None = None,
) -> PipelineState:
    state = PipelineState(policies=policies)

    state.classifications = classify(state.policies, client, config)
    if until == "classify":
        return state

    state.risk_mappings, state.risk_details = map_risks(
        state.classifications, client, config, risk_handlers
    )
    if until == "map_risks":
        return state

    state.variation_axes = anchor(
        state.risk_mappings, state.risk_details, client, config, onto_handlers
    )
    if until == "anchor":
        return state

    state.domain_context = contextualize(
        state.variation_axes, client, config, onto_handlers
    )
    return state
