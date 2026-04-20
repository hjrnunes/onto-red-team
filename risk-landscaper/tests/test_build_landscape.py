import pytest
from risk_landscaper.models import (
    RiskLandscape, RiskDetail, PolicyRiskMapping, RiskMatch,
    PolicySourceRef, PolicyProfile, Stakeholder,
)


def test_build_risk_landscape_basic():
    from risk_landscaper.stages.build_landscape import build_risk_landscape

    mappings = [
        PolicyRiskMapping(
            policy_concept="Executive Compensation",
            matched_risks=[
                RiskMatch(
                    risk_id="atlas-personal-info",
                    risk_name="Personal information",
                    relevance="primary",
                    justification="Direct PII concern",
                    match_distance=0.234,
                ),
            ],
        ),
    ]
    risk_details_cache = {
        "atlas-personal-info": {
            "id": "atlas-personal-info",
            "name": "Personal information",
            "description": "Personal information or sensitive...",
            "concern": "If personal information is included...",
        },
    }
    related_risks = {
        "atlas-personal-info": [
            {"id": "nist-data-privacy", "name": "Data Privacy",
             "taxonomy": "nist-ai-rmf", "mapping_type": "broad"},
        ],
    }
    risk_actions = {
        "atlas-personal-info": ["Minimize personal data in prompts"],
    }
    selected_domains = ["CCO", "Commons", "FIBO", "D3FEND", "CSO", "LKIF"]

    landscape = build_risk_landscape(
        mappings=mappings,
        risk_details_cache=risk_details_cache,
        related_risks=related_risks,
        risk_actions=risk_actions,
        selected_domains=selected_domains,
        model="gemma-3-12b-it",
        run_slug="swb-enriched",
        timestamp="2026-04-14T12:00:00Z",
    )

    assert isinstance(landscape, RiskLandscape)
    assert landscape.model == "gemma-3-12b-it"
    assert landscape.selected_domains == selected_domains
    assert len(landscape.risks) == 1
    assert landscape.risks[0].risk_id == "atlas-personal-info"
    assert landscape.risks[0].risk_framework == "IBM Risk Atlas"
    assert landscape.risks[0].related_actions == ["Minimize personal data in prompts"]
    assert landscape.risks[0].cross_mappings == related_risks["atlas-personal-info"]
    assert len(landscape.policy_mappings) == 1
    assert landscape.policy_mappings[0].policy_concept == "Executive Compensation"


def test_build_risk_landscape_deduplicates_risks():
    from risk_landscaper.stages.build_landscape import build_risk_landscape

    # Same risk matched from two policies
    mappings = [
        PolicyRiskMapping(
            policy_concept="Policy A",
            matched_risks=[
                RiskMatch(risk_id="r1", risk_name="Risk One",
                          relevance="primary", justification="test"),
            ],
        ),
        PolicyRiskMapping(
            policy_concept="Policy B",
            matched_risks=[
                RiskMatch(risk_id="r1", risk_name="Risk One",
                          relevance="supporting", justification="test2"),
            ],
        ),
    ]
    risk_details_cache = {
        "r1": {"id": "r1", "name": "Risk One", "description": "desc"},
    }

    landscape = build_risk_landscape(
        mappings=mappings,
        risk_details_cache=risk_details_cache,
        model="test-model",
        run_slug="test",
        timestamp="2026-04-14T12:00:00Z",
    )

    # Risk stored once, referenced from both policy mappings
    assert len(landscape.risks) == 1
    assert len(landscape.policy_mappings) == 2


def test_build_risk_landscape_weak_matches():
    from risk_landscaper.stages.build_landscape import build_risk_landscape

    mappings = [
        PolicyRiskMapping(
            policy_concept="Policy A",
            matched_risks=[
                RiskMatch(risk_id="r1", risk_name="Risk One",
                          relevance="primary", justification="test",
                          match_distance=0.75),
            ],
        ),
    ]
    risk_details_cache = {
        "r1": {"id": "r1", "name": "Risk One", "description": "desc"},
    }

    landscape = build_risk_landscape(
        mappings=mappings,
        risk_details_cache=risk_details_cache,
        model="test-model",
        run_slug="test",
        timestamp="2026-04-14T12:00:00Z",
    )

    assert len(landscape.weak_matches) == 1
    assert landscape.weak_matches[0].risk_id == "r1"
    assert landscape.weak_matches[0].distance == 0.75


def test_build_risk_landscape_framework_coverage():
    from risk_landscaper.stages.build_landscape import build_risk_landscape

    mappings = [
        PolicyRiskMapping(
            policy_concept="Policy A",
            matched_risks=[
                RiskMatch(risk_id="atlas-fraud", risk_name="Fraud",
                          relevance="primary", justification="test"),
                RiskMatch(risk_id="nist-data-privacy", risk_name="Data Privacy",
                          relevance="supporting", justification="test"),
            ],
        ),
    ]
    risk_details_cache = {
        "atlas-fraud": {"id": "atlas-fraud", "name": "Fraud", "description": ""},
        "nist-data-privacy": {"id": "nist-data-privacy", "name": "Data Privacy", "description": ""},
    }

    landscape = build_risk_landscape(
        mappings=mappings,
        risk_details_cache=risk_details_cache,
        model="test-model",
        run_slug="test",
        timestamp="2026-04-14T12:00:00Z",
    )

    assert "IBM Risk Atlas" in landscape.framework_coverage
    assert "NIST AI RMF" in landscape.framework_coverage


def test_build_risk_landscape_with_policy_source():
    from risk_landscaper.stages.build_landscape import build_risk_landscape

    policy_profile = PolicyProfile(
        organization=Stakeholder(name="South West Bank"),
        domain="banking",
        policies=[],
    )
    landscape = build_risk_landscape(
        mappings=[],
        risk_details_cache={},
        model="test-model",
        run_slug="test",
        timestamp="2026-04-14T12:00:00Z",
        policy_profile=policy_profile,
    )

    assert landscape.policy_source is not None
    assert landscape.policy_source.organization == "South West Bank"
    assert landscape.policy_source.domain == "banking"


def test_build_risk_landscape_empty_inputs():
    from risk_landscaper.stages.build_landscape import build_risk_landscape

    landscape = build_risk_landscape(
        mappings=[],
        risk_details_cache={},
        model="test-model",
        run_slug="test",
        timestamp="2026-04-14T12:00:00Z",
    )

    assert landscape.risks == []
    assert landscape.policy_mappings == []
    assert landscape.framework_coverage == {}


def test_build_risk_landscape_with_coverage_gaps():
    from risk_landscaper.stages.build_landscape import build_risk_landscape
    from risk_landscaper.models import CoverageGap

    gaps = [
        CoverageGap(
            policy_concept="Multi-agent collusion",
            concept_definition="AI agents coordinating to bypass controls",
            gap_type="novel",
            confidence=0.82,
            nearest_risks=[{"id": "atlas-dangerous-use", "name": "Dangerous use", "distance": 0.75}],
            reasoning="No existing risk covers multi-agent coordination failures",
        ),
    ]

    landscape = build_risk_landscape(
        mappings=[],
        risk_details_cache={},
        coverage_gaps=gaps,
        model="test-model",
        run_slug="test",
        timestamp="2026-04-16T12:00:00Z",
    )

    assert len(landscape.coverage_gaps) == 1
    assert landscape.coverage_gaps[0].gap_type == "novel"
    assert landscape.coverage_gaps[0].policy_concept == "Multi-agent collusion"


def test_build_risk_landscape_empty_coverage_gaps():
    from risk_landscaper.stages.build_landscape import build_risk_landscape

    landscape = build_risk_landscape(
        mappings=[],
        risk_details_cache={},
        model="test-model",
        run_slug="test",
        timestamp="2026-04-16T12:00:00Z",
    )

    assert landscape.coverage_gaps == []
