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
)
from refiner.pipeline import PipelineState, run_pipeline


def test_pipeline_threads_state(mock_client, mock_config, mock_risk_handlers, mock_onto_handlers):
    policies = [Policy(policy_concept="Fraud", concept_definition="About fraud")]

    classify_result = [
        PolicyClassification(
            policy_concept="Fraud", concept_definition="About fraud",
            policy_type="A", justification="j",
        ),
    ]
    map_result = (
        [PolicyRiskMapping(
            policy_concept="Fraud", policy_type="A",
            matched_risks=[RiskMatch(risk_id="r1", risk_name="R1", relevance="primary", justification="j")],
            cross_mappings=[],
        )],
        {"r1": {"id": "r1", "name": "R1", "description": "d", "concern": "c"}},
    )
    anchor_result = [
        RiskVariationAxes(
            risk_id="r1", risk_name="R1", policy_concept="Fraud",
            axes=[VariationAxis(cco_class_uri="http://ex/P", cco_class_label="P", role="agent", rationale="r")],
        ),
    ]
    context_result = [
        DomainContextProfile(
            risk_id="r1", risk_name="R1", policy_concept="Fraud",
            axes=[DomainContextAxis(cco_class_uri="http://ex/P", cco_class_label="P", role="agent", enumerations=[])],
        ),
    ]

    with patch("refiner.pipeline.classify", return_value=classify_result) as m_classify, \
         patch("refiner.pipeline.map_risks", return_value=map_result) as m_map, \
         patch("refiner.pipeline.anchor", return_value=anchor_result) as m_anchor, \
         patch("refiner.pipeline.contextualize", return_value=context_result) as m_ctx:

        state = run_pipeline(policies, mock_client, mock_config, mock_risk_handlers, mock_onto_handlers)

        assert state.classifications == classify_result
        assert state.risk_mappings == map_result[0]
        assert state.risk_details == map_result[1]
        assert state.variation_axes == anchor_result
        assert state.domain_context == context_result

        # Verify stage calls received correct inputs
        m_classify.assert_called_once_with(policies, mock_client, mock_config)
        m_map.assert_called_once_with(classify_result, mock_client, mock_config, mock_risk_handlers)
        m_anchor.assert_called_once_with(
            map_result[0], map_result[1], mock_client, mock_config, mock_onto_handlers
        )
        m_ctx.assert_called_once_with(anchor_result, mock_client, mock_config, mock_onto_handlers)


def test_pipeline_until_classify(mock_client, mock_config, mock_risk_handlers, mock_onto_handlers):
    policies = [Policy(policy_concept="Fraud", concept_definition="About fraud")]
    classify_result = [
        PolicyClassification(
            policy_concept="Fraud", concept_definition="About fraud",
            policy_type="A", justification="j",
        ),
    ]

    with patch("refiner.pipeline.classify", return_value=classify_result), \
         patch("refiner.pipeline.map_risks") as m_map:

        state = run_pipeline(
            policies, mock_client, mock_config, mock_risk_handlers, mock_onto_handlers,
            until="classify",
        )

        assert state.classifications is not None
        assert state.risk_mappings is None
        m_map.assert_not_called()
