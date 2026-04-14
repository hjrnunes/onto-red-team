import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

import instructor

logger = logging.getLogger(__name__)
from refiner.llm import LLMConfig
from refiner.models import (
    Policy,
    PolicyDocument,
    PolicyRiskMapping,
    RiskLandscape,
    RiskVariationAxes,
    DomainContextDocument,
    RunReport,
)
from refiner.stages.identify_domains import identify_domains
from refiner.stages.map_risks import map_risks
from refiner.stages.anchor import anchor, build_generic_safety_uris
from refiner.stages.identify_domains import ALWAYS_INCLUDED
from refiner.stages.contextualize import contextualize
from refiner.stages.build_landscape import build_risk_landscape

STAGES = ("identify_domains", "map_risks", "anchor", "contextualize")


@dataclass
class PipelineState:
    policies: list[Policy]
    selected_domains: list[str] | None = None
    risk_mappings: list[PolicyRiskMapping] | None = None
    risk_details: dict[str, dict] | None = None
    seen_risk_ids: set[str] | None = None
    related_risks: dict[str, list[dict]] | None = None
    risk_actions: dict[str, list[str]] | None = None
    risk_landscape: RiskLandscape | None = None
    variation_axes: list[RiskVariationAxes] | None = None
    domain_context: DomainContextDocument | None = None
    run_slug: str = ""
    vocabulary_contexts: dict[str, dict] = field(default_factory=dict)
    report: RunReport | None = None
    doc_context: PolicyDocument | None = None

    @property
    def risk_mappings_resolved(self) -> list[PolicyRiskMapping] | None:
        if self.risk_mappings is not None:
            return self.risk_mappings
        if self.risk_landscape is not None:
            return self.risk_landscape.policy_mappings
        return None

    @property
    def risk_details_resolved(self) -> dict[str, dict] | None:
        if self.risk_details is not None:
            return self.risk_details
        if self.risk_landscape is not None:
            return {
                r.risk_id: {
                    "id": r.risk_id, "name": r.risk_name,
                    "description": r.risk_description or "",
                    "concern": r.risk_concern or "",
                }
                for r in self.risk_landscape.risks
            }
        return None

    @property
    def risk_actions_resolved(self) -> dict[str, list[str]] | None:
        if self.risk_actions is not None:
            return self.risk_actions
        if self.risk_landscape is not None:
            return {
                r.risk_id: r.related_actions
                for r in self.risk_landscape.risks if r.related_actions
            }
        return None

    @property
    def related_risks_resolved(self) -> dict[str, list[dict]] | None:
        if self.related_risks is not None:
            return self.related_risks
        if self.risk_landscape is not None:
            return {
                r.risk_id: r.cross_mappings
                for r in self.risk_landscape.risks if r.cross_mappings
            }
        return None


def run_pipeline(
    policies: list[Policy],
    client: instructor.Instructor,
    config: LLMConfig,
    risk_handlers: dict,
    onto_handlers: dict,
    until: str | None = None,
    report: RunReport | None = None,
    layer1_mappings=None,
    layer2_mappings=None,
    bfo_fallbacks: dict[str, str] | None = None,
    run_slug: str = "",
) -> PipelineState:
    state = PipelineState(policies=policies, report=report, run_slug=run_slug)

    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _stage_done(name: str, started: str) -> None:
        if report:
            report.stages_completed.append(name)
            report.events.append({
                "stage": name, "event": "stage_completed",
                "started_at": started, "completed_at": _now(),
                "model": config.model,
            })

    t0 = _now()
    state.selected_domains = identify_domains(state.policies, client, config, report=report)
    _stage_done("identify_domains", t0)

    # Compute CSO DangerousInformation filter for domain-specific runs
    generic_safety_uris: set[str] = set()
    if state.selected_domains:
        domain_specific = set(state.selected_domains) - set(ALWAYS_INCLUDED)
        if domain_specific:
            uris = build_generic_safety_uris(onto_handlers)
            if uris:
                generic_safety_uris = uris
                logger.info(
                    "Filtering %d CSO generic-safety URIs (domain-specific: %s)",
                    len(uris), ", ".join(sorted(domain_specific)),
                )

    if until == "identify_domains":
        return state

    t0 = _now()
    state.risk_mappings, state.risk_details, state.seen_risk_ids, state.related_risks, state.risk_actions = map_risks(
        state.policies, client, config, risk_handlers, report=report
    )
    _stage_done("map_risks", t0)
    state.risk_landscape = build_risk_landscape(
        mappings=state.risk_mappings,
        risk_details_cache=state.risk_details,
        related_risks=state.related_risks,
        risk_actions=state.risk_actions,
        selected_domains=state.selected_domains,
        model=config.model,
        run_slug=run_slug,
        timestamp=report.timestamp if report else "",
    )
    if until == "map_risks":
        return state

    t0 = _now()
    state.variation_axes, state.vocabulary_contexts = anchor(
        state.risk_mappings, state.risk_details, client, config, onto_handlers,
        selected_domains=state.selected_domains,
        risk_actions=state.risk_actions,
        related_risks=state.related_risks,
        nexus_handlers=risk_handlers,
        layer1_mappings=layer1_mappings,
        layer2_mappings=layer2_mappings,
        report=report,
        generic_safety_uris=generic_safety_uris,
        policies=policies,
        bfo_fallbacks=bfo_fallbacks,
    )
    _stage_done("anchor", t0)
    if until == "anchor":
        return state

    t0 = _now()
    state.domain_context = contextualize(
        state.variation_axes, client, config, onto_handlers,
        selected_domains=state.selected_domains,
        risk_details=state.risk_details,
        report=report,
        policies=policies,
        vocabulary_contexts=state.vocabulary_contexts,
        run_slug=state.run_slug,
        timestamp=report.timestamp if report else "",
    )
    _stage_done("contextualize", t0)
    return state
