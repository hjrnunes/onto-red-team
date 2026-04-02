from unittest.mock import patch, MagicMock
from refiner.models import (
    Policy,
    PolicyClassification,
    PolicyRiskMapping,
    RiskMatch,
    RiskVariationAxes,
    VariationAxis,
    DomainContextProfile,
    DomainContextAxis,
    RunReport,
)
from refiner.pipeline import PipelineState, run_pipeline


def test_pipeline_threads_state(mock_client, mock_config, mock_risk_handlers, mock_onto_handlers):
    policies = [Policy(policy_concept="Fraud", concept_definition="About fraud")]
    report = RunReport(model="test-model", policy_set="test.json", timestamp="2026-04-01T00:00:00Z")

    classify_result = [
        PolicyClassification(
            policy_concept="Fraud", concept_definition="About fraud",
            policy_type="A", justification="j",
        ),
    ]
    domains_result = ["CCO", "Commons", "FIBO"]
    map_result = (
        [PolicyRiskMapping(
            policy_concept="Fraud", policy_type="A",
            matched_risks=[RiskMatch(risk_id="r1", risk_name="R1", relevance="primary", justification="j")],
        )],
        {"r1": {"id": "r1", "name": "R1", "description": "d", "concern": "c"}},
        {"r1"},
        {"r1": [{"id": "r2", "mapping_type": "close"}]},
        {},
    )
    anchor_result = [
        RiskVariationAxes(
            risk_id="r1", risk_name="R1", policy_concept="Fraud",
            axes=[VariationAxis(cco_class_uri="http://ex/P", cco_class_label="P", roles=["agent"], rationale="r")],
        ),
    ]
    context_result = [
        DomainContextProfile(
            risk_id="r1", risk_name="R1", policy_concept="Fraud",
            axes=[DomainContextAxis(cco_class_uri="http://ex/P", cco_class_label="P", roles=["agent"], enumerations=[])],
        ),
    ]

    with patch("refiner.pipeline.classify", return_value=classify_result) as m_classify, \
         patch("refiner.pipeline.identify_domains", return_value=domains_result) as m_domains, \
         patch("refiner.pipeline.map_risks", return_value=map_result) as m_map, \
         patch("refiner.pipeline.anchor", return_value=anchor_result) as m_anchor, \
         patch("refiner.pipeline.contextualize", return_value=context_result) as m_ctx:

        state = run_pipeline(policies, mock_client, mock_config, mock_risk_handlers, mock_onto_handlers, report=report)

        assert state.classifications == classify_result
        assert state.selected_domains == domains_result
        assert state.risk_mappings == map_result[0]
        assert state.risk_details == map_result[1]
        assert state.related_risks == map_result[3]
        assert state.risk_actions == map_result[4]
        assert state.variation_axes == anchor_result
        assert state.domain_context == context_result
        assert state.report == report
        assert report.stages_completed == ["classify", "identify_domains", "map_risks", "anchor", "contextualize"]

        # Verify stage calls received correct inputs
        m_classify.assert_called_once_with(policies, mock_client, mock_config, report=report)
        m_domains.assert_called_once_with(classify_result, mock_client, mock_config, report=report)
        m_map.assert_called_once_with(classify_result, mock_client, mock_config, mock_risk_handlers, report=report)
        m_anchor.assert_called_once_with(
            map_result[0], map_result[1], mock_client, mock_config, mock_onto_handlers,
            selected_domains=domains_result,
            risk_actions=map_result[4],
            related_risks=map_result[3],
            report=report,
        )
        m_ctx.assert_called_once_with(
            anchor_result, mock_client, mock_config, mock_onto_handlers,
            selected_domains=domains_result,
            risk_details=map_result[1],
            report=report,
        )


def test_pipeline_until_classify(mock_client, mock_config, mock_risk_handlers, mock_onto_handlers):
    policies = [Policy(policy_concept="Fraud", concept_definition="About fraud")]
    classify_result = [
        PolicyClassification(
            policy_concept="Fraud", concept_definition="About fraud",
            policy_type="A", justification="j",
        ),
    ]

    with patch("refiner.pipeline.classify", return_value=classify_result), \
         patch("refiner.pipeline.identify_domains") as m_domains:

        state = run_pipeline(
            policies, mock_client, mock_config, mock_risk_handlers, mock_onto_handlers,
            until="classify",
        )

        assert state.classifications is not None
        assert state.selected_domains is None
        m_domains.assert_not_called()


def test_pipeline_until_identify_domains(mock_client, mock_config, mock_risk_handlers, mock_onto_handlers):
    policies = [Policy(policy_concept="Fraud", concept_definition="About fraud")]
    classify_result = [
        PolicyClassification(
            policy_concept="Fraud", concept_definition="About fraud",
            policy_type="A", justification="j",
        ),
    ]
    domains_result = ["CCO", "Commons", "FIBO"]

    with patch("refiner.pipeline.classify", return_value=classify_result), \
         patch("refiner.pipeline.identify_domains", return_value=domains_result), \
         patch("refiner.pipeline.map_risks") as m_map:

        state = run_pipeline(
            policies, mock_client, mock_config, mock_risk_handlers, mock_onto_handlers,
            until="identify_domains",
        )

        assert state.selected_domains == domains_result
        assert state.risk_mappings is None
        m_map.assert_not_called()
