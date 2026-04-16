from unittest.mock import patch, MagicMock
from refiner.models import (
    Policy,
    PolicyRiskMapping,
    RiskMatch,
    RiskVariationAxes,
    VariationAxis,
    DomainContext,
    PolicyDomainContext,
    RiskGrounding,
    DomainContextAxis,
    RunReport,
)
from refiner.pipeline import PipelineState, run_pipeline


def test_pipeline_threads_state(mock_client, mock_config, mock_risk_handlers, mock_onto_handlers):
    policies = [Policy(policy_concept="Fraud", concept_definition="About fraud")]
    report = RunReport(model="test-model", policy_set="test.json", timestamp="2026-04-01T00:00:00Z")

    domains_result = ["CCO", "Commons", "FIBO"]
    map_result = (
        [PolicyRiskMapping(
            policy_concept="Fraud",
            matched_risks=[RiskMatch(risk_id="r1", risk_name="R1", relevance="primary", justification="j")],
        )],
        {"r1": {"id": "r1", "name": "R1", "description": "d", "concern": "c"}},
        {"r1"},
        {"r1": [{"id": "r2", "mapping_type": "close"}]},
        {},
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

    # Mock build_generic_safety_uris to return expected URIs for FIBO domain-specific run
    fake_uris = {"http://cso#DangerousInformation", "http://cso#Weapons"}

    with patch("refiner.pipeline.identify_domains", return_value=domains_result) as m_domains, \
         patch("refiner.pipeline.map_risks", return_value=map_result) as m_map, \
         patch("refiner.pipeline.anchor", return_value=anchor_result) as m_anchor, \
         patch("refiner.pipeline.contextualize", return_value=context_result) as m_ctx, \
         patch("refiner.pipeline.build_generic_safety_uris", return_value=fake_uris) as m_build:

        state = run_pipeline(policies, mock_client, mock_config, mock_risk_handlers, mock_onto_handlers, report=report, run_slug="test-policy")

        assert state.selected_domains == domains_result
        assert state.risk_mappings == map_result[0]
        assert state.risk_details == map_result[1]
        assert state.related_risks == map_result[3]
        assert state.risk_actions == map_result[4]
        assert state.variation_axes == anchor_axes
        assert state.vocabulary_contexts == anchor_vocab
        assert state.domain_context == context_result
        assert isinstance(state.domain_context, DomainContext)
        assert len(state.domain_context.policy_contexts) == 1
        assert state.domain_context.policy_contexts[0].policy_concept == "Fraud"
        assert state.domain_context.policy_contexts[0].risk_groundings[0].risk_id == "r1"
        assert state.report == report
        assert report.stages_completed == ["identify_domains", "map_risks", "anchor", "contextualize"]

        # Verify stage calls received correct inputs
        m_domains.assert_called_once_with(policies, mock_client, mock_config, report=report)
        m_map.assert_called_once_with(policies, mock_client, mock_config, mock_risk_handlers, report=report)
        # FIBO is domain-specific, so generic_safety_uris should be passed
        m_anchor.assert_called_once_with(
            map_result[0], map_result[1], mock_client, mock_config, mock_onto_handlers,
            selected_domains=domains_result,
            risk_actions=map_result[4],
            related_risks=map_result[3],
            nexus_handlers=mock_risk_handlers,
            layer1_mappings=None,
            layer2_mappings=None,
            report=report,
            generic_safety_uris=fake_uris,
            policies=policies,
            bfo_fallbacks=None,
        )
        m_ctx.assert_called_once_with(
            anchor_axes, mock_client, mock_config, mock_onto_handlers,
            selected_domains=domains_result,
            risk_details=map_result[1],
            report=report,
            policies=policies,
            vocabulary_contexts=anchor_vocab,
            run_slug="test-policy",
            timestamp="2026-04-01T00:00:00Z",
            risk_landscape=state.risk_landscape,
        )


def test_pipeline_until_identify_domains(mock_client, mock_config, mock_risk_handlers, mock_onto_handlers):
    policies = [Policy(policy_concept="Fraud", concept_definition="About fraud")]
    domains_result = ["CCO", "Commons", "FIBO"]

    with patch("refiner.pipeline.identify_domains", return_value=domains_result), \
         patch("refiner.pipeline.map_risks") as m_map:

        state = run_pipeline(
            policies, mock_client, mock_config, mock_risk_handlers, mock_onto_handlers,
            until="identify_domains",
        )

        assert state.selected_domains == domains_result
        assert state.risk_mappings is None
        m_map.assert_not_called()


def test_pipeline_sets_generic_safety_uris_for_domain_specific(mock_client, mock_config, mock_risk_handlers, mock_onto_handlers):
    """When domain-specific ontologies selected, build_generic_safety_uris is called."""
    policies = [Policy(policy_concept="Fraud", concept_definition="About fraud")]
    # FIBO is domain-specific (not in ALWAYS_INCLUDED)
    domains_result = ["CCO", "Commons", "D3FEND", "CSO", "FIBO"]

    fake_descendants = [
        {"uri": "http://cso#Weapons", "label": "Weapons", "depth": 1},
        {"uri": "http://cso#Arson", "label": "Arson", "depth": 2},
    ]
    mock_onto_handlers["get_subclasses"] = MagicMock(return_value=fake_descendants)

    with patch("refiner.pipeline.identify_domains", return_value=domains_result), \
         patch("refiner.pipeline.map_risks") as m_map, \
         patch("refiner.pipeline.build_generic_safety_uris") as m_build:

        run_pipeline(
            policies, mock_client, mock_config, mock_risk_handlers, mock_onto_handlers,
            until="identify_domains",
        )

        # build_generic_safety_uris should be called with onto_handlers
        m_build.assert_called_once_with(mock_onto_handlers)


def test_pipeline_no_generic_safety_uris_for_generic_only(mock_client, mock_config, mock_risk_handlers, mock_onto_handlers):
    """When only always-included domains selected, build_generic_safety_uris is not called."""
    policies = [Policy(policy_concept="Safety", concept_definition="About safety")]
    # Only always-included domains — no domain-specific selection
    domains_result = ["CCO", "Commons", "D3FEND", "CSO"]

    with patch("refiner.pipeline.identify_domains", return_value=domains_result), \
         patch("refiner.pipeline.map_risks") as m_map, \
         patch("refiner.pipeline.build_generic_safety_uris") as m_build:

        run_pipeline(
            policies, mock_client, mock_config, mock_risk_handlers, mock_onto_handlers,
            until="identify_domains",
        )

        # build_generic_safety_uris should NOT be called (no domain-specific domains)
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
