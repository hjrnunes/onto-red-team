import pytest
from unittest.mock import patch, MagicMock
from refiner.models import (
    Policy,
    PolicyRiskMapping,
    RiskMatch,
    RiskDetail,
    RiskVariationAxes,
    VariationAxis,
    DomainContext,
    PolicyDomainContext,
    RiskGrounding,
    DomainContextAxis,
    RiskLandscape,
    RunReport,
)
from refiner.pipeline import PipelineState, run_pipeline


def test_pipeline_requires_landscape(mock_client, mock_config, mock_risk_handlers, mock_onto_handlers):
    """Pipeline raises ValueError if no landscape provided."""
    policies = [Policy(policy_concept="Fraud", concept_definition="About fraud")]
    with pytest.raises(ValueError, match="No pre-built landscape"):
        run_pipeline(policies, mock_client, mock_config, mock_risk_handlers, mock_onto_handlers)


def test_pipeline_threads_state(mock_client, mock_config, mock_risk_handlers, mock_onto_handlers):
    policies = [Policy(policy_concept="Fraud", concept_definition="About fraud")]
    report = RunReport(model="test-model", policy_set="test.json", timestamp="2026-04-01T00:00:00Z")

    landscape = RiskLandscape(
        model="test-model",
        selected_domains=["CCO", "Commons", "FIBO"],
        risks=[
            RiskDetail(
                risk_id="r1", risk_name="R1",
                risk_description="d", risk_concern="c",
                related_actions=[],
                cross_mappings=[{"id": "r2", "mapping_type": "close"}],
            ),
        ],
        policy_mappings=[
            PolicyRiskMapping(
                policy_concept="Fraud",
                matched_risks=[RiskMatch(risk_id="r1", risk_name="R1", relevance="primary", justification="j")],
            ),
        ],
    )
    anchor_axes = [
        RiskVariationAxes(
            risk_id="r1", risk_name="R1", policy_concept="Fraud",
            axes=[VariationAxis(cco_class_uri="http://ex/P", cco_class_label="P", rationale="r")],
        ),
    ]
    anchor_vocab = {"r1": {"stakeholders": [{"concept": "eu-aiact:AISubject", "label": "AI Subject"}]}}
    anchor_result = (anchor_axes, anchor_vocab)
    context_result = DomainContext(
        model="test-model",
        policy_contexts=[
            PolicyDomainContext(
                policy_concept="Fraud",
                risk_groundings=[
                    RiskGrounding(
                        risk_id="r1",
                        axes=[DomainContextAxis(
                            cco_class_uri="http://ex/P", cco_class_label="P",
                            enumerations=[],
                        )],
                    ),
                ],
            ),
        ],
    )

    fake_uris = {"http://cso#DangerousInformation", "http://cso#Weapons"}

    with patch("refiner.pipeline.anchor", return_value=anchor_result) as m_anchor, \
         patch("refiner.pipeline.contextualize", return_value=context_result) as m_ctx, \
         patch("refiner.pipeline.build_generic_safety_uris", return_value=fake_uris) as m_build:

        state = run_pipeline(
            policies, mock_client, mock_config, mock_risk_handlers, mock_onto_handlers,
            report=report, run_slug="test-policy", landscape=landscape,
        )

        assert state.selected_domains == ["CCO", "Commons", "FIBO"]
        assert state.risk_landscape is landscape
        assert state.variation_axes == anchor_axes
        assert state.vocabulary_contexts == anchor_vocab
        assert state.domain_context == context_result
        assert state.report == report
        assert report.stages_completed == ["anchor", "contextualize"]

        m_build.assert_called_once_with(mock_onto_handlers)


def test_pipeline_sets_generic_safety_uris_for_domain_specific(mock_client, mock_config, mock_risk_handlers, mock_onto_handlers):
    """When domain-specific ontologies in landscape, build_generic_safety_uris is called."""
    policies = [Policy(policy_concept="Fraud", concept_definition="About fraud")]
    landscape = RiskLandscape(
        model="test-model",
        selected_domains=["CCO", "Commons", "D3FEND", "CSO", "FIBO"],
        risks=[], policy_mappings=[],
    )

    with patch("refiner.pipeline.anchor", return_value=([], {})), \
         patch("refiner.pipeline.contextualize", return_value=DomainContext(model="m")), \
         patch("refiner.pipeline.build_generic_safety_uris") as m_build:

        run_pipeline(
            policies, mock_client, mock_config, mock_risk_handlers, mock_onto_handlers,
            landscape=landscape, until="anchor",
        )

        m_build.assert_called_once_with(mock_onto_handlers)


def test_pipeline_no_generic_safety_uris_for_generic_only(mock_client, mock_config, mock_risk_handlers, mock_onto_handlers):
    """When only always-included domains in landscape, build_generic_safety_uris is not called."""
    policies = [Policy(policy_concept="Safety", concept_definition="About safety")]
    landscape = RiskLandscape(
        model="test-model",
        selected_domains=["CCO", "Commons", "D3FEND", "CSO"],
        risks=[], policy_mappings=[],
    )

    with patch("refiner.pipeline.anchor", return_value=([], {})), \
         patch("refiner.pipeline.contextualize", return_value=DomainContext(model="m")), \
         patch("refiner.pipeline.build_generic_safety_uris") as m_build:

        run_pipeline(
            policies, mock_client, mock_config, mock_risk_handlers, mock_onto_handlers,
            landscape=landscape, until="anchor",
        )

        m_build.assert_not_called()


def test_pipeline_state_has_risk_landscape():
    from refiner.pipeline import PipelineState
    from refiner.models import RiskLandscape
    state = PipelineState(policies=[])
    assert state.risk_landscape is None
    state.risk_landscape = RiskLandscape(model="test")
    assert state.risk_landscape.model == "test"


def test_pipeline_state_extracts_risk_details_from_landscape():
    from refiner.pipeline import PipelineState
    from refiner.models import (
        RiskLandscape, RiskDetail,
        PolicyRiskMapping, RiskMatch,
    )

    landscape = RiskLandscape(
        risks=[
            RiskDetail(
                risk_id="r1", risk_name="Risk One",
                risk_description="desc", risk_concern="concern",
                related_actions=["act1"],
                cross_mappings=[{"id": "x1", "mapping_type": "broad"}],
            ),
        ],
        policy_mappings=[
            PolicyRiskMapping(
                policy_concept="P1",
                matched_risks=[
                    RiskMatch(risk_id="r1", risk_name="Risk One",
                              relevance="primary", justification="j"),
                ],
            ),
        ],
    )

    state = PipelineState(policies=[], risk_landscape=landscape)

    # Old-style access should still work via landscape
    assert state.risk_mappings_resolved is not None
    assert len(state.risk_mappings_resolved) == 1
    assert state.risk_details_resolved["r1"]["name"] == "Risk One"
    assert state.risk_actions_resolved["r1"] == ["act1"]
    assert state.related_risks_resolved["r1"] == [{"id": "x1", "mapping_type": "broad"}]
