import logging
from refiner.models import (
    Policy,
    PolicyRiskMapping,
    RunReport,
    CoverageGap,
    PolicyDecomposition,
)
from refiner.stages.map_risks import map_risks, _RiskSelection, _SlimRiskMatch, _GapClassification


def _make_policy(concept="Fraud"):
    return Policy(
        policy_concept=concept,
        concept_definition=f"Prompts about {concept.lower()}",
    )


def test_map_risks_calls_search_and_details(mock_client, mock_config, mock_risk_handlers):
    classifications = [_make_policy()]
    mock_risk_handlers["search_risks"].return_value = [
        {"id": "atlas-fraud", "name": "Fraud", "description": "Fraud risk", "distance": 0.2},
    ]
    mock_risk_handlers["get_risk_details"].return_value = {
        "id": "atlas-fraud",
        "name": "Fraud",
        "description": "Fraud risk",
        "concern": "Financial loss",
        "risk_type": "output",
        "taxonomy": "ibm-risk-atlas",
    }
    mock_risk_handlers["get_related_risks"].return_value = []
    mock_client.chat.completions.create.return_value = _RiskSelection(
        matched_risks=[
            _SlimRiskMatch(risk_index=1, risk_name="Fraud", relevance="primary", justification="j"),
        ],
    )
    mappings, details, seen_ids, related, _, _ = map_risks(classifications, mock_client, mock_config, mock_risk_handlers)
    assert len(mappings) == 1
    assert mappings[0].matched_risks[0].risk_id == "atlas-fraud"
    assert mappings[0].policy_concept == "Fraud"
    mock_risk_handlers["search_risks"].assert_called_once()
    mock_risk_handlers["get_risk_details"].assert_called_once_with("atlas-fraud")


def test_map_risks_filters_hallucinated_risk_ids(mock_client, mock_config, mock_risk_handlers):
    classifications = [_make_policy()]
    mock_risk_handlers["search_risks"].return_value = [
        {"id": "atlas-fraud", "name": "Fraud", "description": "Fraud risk", "distance": 0.2},
    ]
    mock_risk_handlers["get_risk_details"].side_effect = lambda rid: (
        {"id": "atlas-fraud", "name": "Fraud", "description": "d", "concern": "c",
         "risk_type": "output", "taxonomy": "ibm-risk-atlas"}
        if rid == "atlas-fraud" else None
    )
    mock_risk_handlers["get_related_risks"].return_value = []
    # LLM returns an invalid index
    mock_client.chat.completions.create.return_value = _RiskSelection(
        matched_risks=[
            _SlimRiskMatch(risk_index=1, risk_name="Fraud", relevance="primary", justification="j"),
            _SlimRiskMatch(risk_index=99, risk_name="Fake", relevance="supporting", justification="j"),
        ],
    )
    mappings, details, seen_ids, related, _, _ = map_risks(classifications, mock_client, mock_config, mock_risk_handlers)
    # Invalid index should be filtered out
    assert len(mappings[0].matched_risks) == 1
    assert mappings[0].matched_risks[0].risk_id == "atlas-fraud"


def test_map_risks_returns_risk_details_cache(mock_client, mock_config, mock_risk_handlers):
    classifications = [_make_policy()]
    risk_detail = {
        "id": "atlas-fraud", "name": "Fraud", "description": "Fraud risk",
        "concern": "Financial loss", "risk_type": "output", "taxonomy": "ibm-risk-atlas",
    }
    mock_risk_handlers["search_risks"].return_value = [
        {"id": "atlas-fraud", "name": "Fraud", "description": "Fraud risk", "distance": 0.2},
    ]
    mock_risk_handlers["get_risk_details"].return_value = risk_detail
    mock_risk_handlers["get_related_risks"].return_value = []
    mock_client.chat.completions.create.return_value = _RiskSelection(
        matched_risks=[_SlimRiskMatch(risk_index=1, risk_name="Fraud", relevance="primary", justification="j")],
    )
    _, details, _, _, _, _ = map_risks(classifications, mock_client, mock_config, mock_risk_handlers)
    assert "atlas-fraud" in details
    assert details["atlas-fraud"]["description"] == "Fraud risk"


def test_map_risks_seen_ids_includes_related(mock_client, mock_config, mock_risk_handlers):
    classifications = [_make_policy()]
    mock_risk_handlers["search_risks"].return_value = [
        {"id": "atlas-fraud", "name": "Fraud", "description": "Fraud risk", "distance": 0.2},
    ]
    mock_risk_handlers["get_risk_details"].return_value = {
        "id": "atlas-fraud", "name": "Fraud", "description": "d", "concern": "c",
        "risk_type": "output", "taxonomy": "ibm-risk-atlas",
    }
    mock_risk_handlers["get_related_risks"].return_value = [
        {"id": "owasp-fraud", "mapping_type": "close"},
        {"id": "nist-fraud", "mapping_type": "related"},
    ]
    mock_client.chat.completions.create.return_value = _RiskSelection(
        matched_risks=[_SlimRiskMatch(risk_index=1, risk_name="Fraud", relevance="primary", justification="j")],
    )
    _, _, seen_ids, _, _, _ = map_risks(classifications, mock_client, mock_config, mock_risk_handlers)
    assert "atlas-fraud" in seen_ids
    assert "owasp-fraud" in seen_ids
    assert "nist-fraud" in seen_ids


def test_map_risks_returns_related_risks(mock_client, mock_config, mock_risk_handlers):
    classifications = [_make_policy()]
    mock_risk_handlers["search_risks"].return_value = [
        {"id": "atlas-fraud", "name": "Fraud", "description": "Fraud risk", "distance": 0.2},
    ]
    mock_risk_handlers["get_risk_details"].return_value = {
        "id": "atlas-fraud", "name": "Fraud", "description": "d", "concern": "c",
        "risk_type": "output", "taxonomy": "ibm-risk-atlas",
    }
    related = [
        {"id": "owasp-fraud", "mapping_type": "close"},
        {"id": "nist-fraud", "mapping_type": "related"},
    ]
    mock_risk_handlers["get_related_risks"].return_value = related
    mock_client.chat.completions.create.return_value = _RiskSelection(
        matched_risks=[_SlimRiskMatch(risk_index=1, risk_name="Fraud", relevance="primary", justification="j")],
    )
    _, _, _, related_risks, _, _ = map_risks(classifications, mock_client, mock_config, mock_risk_handlers)
    assert "atlas-fraud" in related_risks
    assert len(related_risks["atlas-fraud"]) == 2
    assert related_risks["atlas-fraud"][0]["id"] == "owasp-fraud"


def test_map_risks_populates_match_distance(mock_client, mock_config, mock_risk_handlers):
    classifications = [_make_policy()]
    mock_risk_handlers["search_risks"].return_value = [
        {"id": "atlas-fraud", "name": "Fraud", "description": "Fraud risk", "distance": 0.25},
    ]
    mock_risk_handlers["get_risk_details"].return_value = {
        "id": "atlas-fraud", "name": "Fraud", "description": "d", "concern": "c",
        "risk_type": "output", "taxonomy": "ibm-risk-atlas",
    }
    mock_risk_handlers["get_related_risks"].return_value = []
    mock_client.chat.completions.create.return_value = _RiskSelection(
        matched_risks=[_SlimRiskMatch(risk_index=1, risk_name="Fraud", relevance="primary", justification="j")],
    )
    mappings, _, _, _, _, _ = map_risks(classifications, mock_client, mock_config, mock_risk_handlers)
    assert mappings[0].matched_risks[0].match_distance == 0.25


def test_map_risks_warns_on_weak_match(mock_client, mock_config, mock_risk_handlers, caplog):
    classifications = [_make_policy()]
    mock_risk_handlers["search_risks"].return_value = [
        {"id": "atlas-fraud", "name": "Fraud", "description": "Fraud risk", "distance": 0.65},
    ]
    mock_risk_handlers["get_risk_details"].return_value = {
        "id": "atlas-fraud", "name": "Fraud", "description": "d", "concern": "c",
        "risk_type": "output", "taxonomy": "ibm-risk-atlas",
    }
    mock_risk_handlers["get_related_risks"].return_value = []
    mock_client.chat.completions.create.return_value = _RiskSelection(
        matched_risks=[_SlimRiskMatch(risk_index=1, risk_name="Fraud", relevance="primary", justification="j")],
    )
    with caplog.at_level(logging.WARNING):
        mappings, _, _, _, _, _ = map_risks(classifications, mock_client, mock_config, mock_risk_handlers)
    assert mappings[0].matched_risks[0].match_distance == 0.65
    assert any("Weak match" in msg for msg in caplog.messages)


def test_map_risks_empty_classifications(mock_client, mock_config, mock_risk_handlers):
    mappings, details, seen_ids, related, risk_actions, coverage_gaps = map_risks([], mock_client, mock_config, mock_risk_handlers)
    assert mappings == []
    assert details == {}
    assert seen_ids == set()
    assert related == {}
    assert risk_actions == {}
    assert coverage_gaps == []


def test_map_risks_emits_weak_match(mock_client, mock_config, mock_risk_handlers):
    """When a match distance > 0.6, emit a weak_match event."""
    from refiner.models import RunReport
    classifications = [_make_policy()]
    mock_risk_handlers["search_risks"].return_value = [
        {"id": "atlas-fraud", "name": "Fraud", "description": "Fraud risk", "distance": 0.65},
    ]
    mock_risk_handlers["get_risk_details"].return_value = {
        "id": "atlas-fraud", "name": "Fraud", "description": "d", "concern": "c",
        "risk_type": "output", "taxonomy": "ibm-risk-atlas",
    }
    mock_risk_handlers["get_related_risks"].return_value = []
    mock_client.chat.completions.create.return_value = _RiskSelection(
        matched_risks=[_SlimRiskMatch(risk_index=1, risk_name="Fraud", relevance="primary", justification="j")],
    )
    report = RunReport(model="m", policy_set="p", timestamp="t")
    mappings, _, _, _, _, _ = map_risks(classifications, mock_client, mock_config, mock_risk_handlers, report=report)
    weak = [e for e in report.events if e["event"] == "weak_match"]
    assert len(weak) == 1
    assert weak[0]["risk_id"] == "atlas-fraud"
    assert weak[0]["distance"] == 0.65


def test_map_risks_emits_invalid_risk_index(mock_client, mock_config, mock_risk_handlers):
    """When LLM returns an out-of-range index, emit invalid_risk_index."""
    from refiner.models import RunReport
    classifications = [_make_policy()]
    mock_risk_handlers["search_risks"].return_value = [
        {"id": "atlas-fraud", "name": "Fraud", "description": "Fraud risk", "distance": 0.2},
    ]
    mock_risk_handlers["get_risk_details"].return_value = {
        "id": "atlas-fraud", "name": "Fraud", "description": "d", "concern": "c",
        "risk_type": "output", "taxonomy": "ibm-risk-atlas",
    }
    mock_risk_handlers["get_related_risks"].return_value = []
    mock_client.chat.completions.create.return_value = _RiskSelection(
        matched_risks=[
            _SlimRiskMatch(risk_index=1, risk_name="Fraud", relevance="primary", justification="j"),
            _SlimRiskMatch(risk_index=99, risk_name="Fake", relevance="supporting", justification="j"),
        ],
    )
    report = RunReport(model="m", policy_set="p", timestamp="t")
    mappings, _, _, _, _, _ = map_risks(classifications, mock_client, mock_config, mock_risk_handlers, report=report)
    invalid = [e for e in report.events if e["event"] == "invalid_risk_index"]
    assert len(invalid) == 1
    assert invalid[0]["raw_index"] == 99


def test_map_risks_emits_match_count(mock_client, mock_config, mock_risk_handlers):
    """Emit match_count per policy concept."""
    from refiner.models import RunReport
    classifications = [_make_policy()]
    mock_risk_handlers["search_risks"].return_value = [
        {"id": "atlas-fraud", "name": "Fraud", "description": "Fraud risk", "distance": 0.2},
    ]
    mock_risk_handlers["get_risk_details"].return_value = {
        "id": "atlas-fraud", "name": "Fraud", "description": "d", "concern": "c",
        "risk_type": "output", "taxonomy": "ibm-risk-atlas",
    }
    mock_risk_handlers["get_related_risks"].return_value = []
    mock_client.chat.completions.create.return_value = _RiskSelection(
        matched_risks=[_SlimRiskMatch(risk_index=1, risk_name="Fraud", relevance="primary", justification="j")],
    )
    report = RunReport(model="m", policy_set="p", timestamp="t")
    mappings, _, _, _, _, _ = map_risks(classifications, mock_client, mock_config, mock_risk_handlers, report=report)
    counts = [e for e in report.events if e["event"] == "match_count"]
    assert len(counts) == 1
    assert counts[0]["policy_concept"] == "Fraud"
    assert counts[0]["count"] == 1


def test_map_risks_no_report_works(mock_client, mock_config, mock_risk_handlers):
    """map_risks works without report param (backward compat)."""
    classifications = [_make_policy()]
    mock_risk_handlers["search_risks"].return_value = [
        {"id": "atlas-fraud", "name": "Fraud", "description": "d", "distance": 0.2},
    ]
    mock_risk_handlers["get_risk_details"].return_value = {
        "id": "atlas-fraud", "name": "Fraud", "description": "d", "concern": "c",
        "risk_type": "output", "taxonomy": "ibm-risk-atlas",
    }
    mock_risk_handlers["get_related_risks"].return_value = []
    mock_client.chat.completions.create.return_value = _RiskSelection(
        matched_risks=[_SlimRiskMatch(risk_index=1, risk_name="Fraud", relevance="primary", justification="j")],
    )
    mappings, _, _, _, _, _ = map_risks(classifications, mock_client, mock_config, mock_risk_handlers)
    assert len(mappings) == 1


def test_map_risks_returns_risk_actions(mock_client, mock_config, mock_risk_handlers):
    """map_risks collects action descriptions from get_related_actions."""
    classifications = [_make_policy()]
    mock_risk_handlers["search_risks"].return_value = [
        {"id": "atlas-fraud", "name": "Fraud", "description": "Fraud risk", "distance": 0.2},
    ]
    mock_risk_handlers["get_risk_details"].return_value = {
        "id": "atlas-fraud", "name": "Fraud", "description": "d", "concern": "c",
        "risk_type": "output", "taxonomy": "ibm-risk-atlas",
    }
    mock_risk_handlers["get_related_risks"].return_value = []
    mock_risk_handlers["get_related_actions"].return_value = [
        {"id": "action-1", "name": "Monitor transactions", "description": "Monitor financial transactions for anomalies"},
        {"id": "action-2", "name": "Verify identity", "description": "Verify user identity before sensitive operations"},
    ]
    mock_client.chat.completions.create.return_value = _RiskSelection(
        matched_risks=[_SlimRiskMatch(risk_index=1, risk_name="Fraud", relevance="primary", justification="j")],
    )
    mappings, details, seen_ids, related, risk_actions, _ = map_risks(
        classifications, mock_client, mock_config, mock_risk_handlers,
    )
    assert "atlas-fraud" in risk_actions
    assert len(risk_actions["atlas-fraud"]) == 2
    assert "Monitor financial transactions for anomalies" in risk_actions["atlas-fraud"]


def test_map_risks_actions_empty_when_none(mock_client, mock_config, mock_risk_handlers):
    """When get_related_actions returns empty, risk_actions has empty list."""
    classifications = [_make_policy()]
    mock_risk_handlers["search_risks"].return_value = [
        {"id": "atlas-fraud", "name": "Fraud", "description": "d", "distance": 0.2},
    ]
    mock_risk_handlers["get_risk_details"].return_value = {
        "id": "atlas-fraud", "name": "Fraud", "description": "d", "concern": "c",
        "risk_type": "output", "taxonomy": "ibm-risk-atlas",
    }
    mock_risk_handlers["get_related_risks"].return_value = []
    mock_risk_handlers["get_related_actions"].return_value = []
    mock_client.chat.completions.create.return_value = _RiskSelection(
        matched_risks=[_SlimRiskMatch(risk_index=1, risk_name="Fraud", relevance="primary", justification="j")],
    )
    _, _, _, _, risk_actions, _ = map_risks(
        classifications, mock_client, mock_config, mock_risk_handlers,
    )
    assert risk_actions.get("atlas-fraud") == []


def test_map_risks_actions_skips_empty_descriptions(mock_client, mock_config, mock_risk_handlers):
    """Actions without descriptions are not included."""
    classifications = [_make_policy()]
    mock_risk_handlers["search_risks"].return_value = [
        {"id": "atlas-fraud", "name": "Fraud", "description": "d", "distance": 0.2},
    ]
    mock_risk_handlers["get_risk_details"].return_value = {
        "id": "atlas-fraud", "name": "Fraud", "description": "d", "concern": "c",
        "risk_type": "output", "taxonomy": "ibm-risk-atlas",
    }
    mock_risk_handlers["get_related_risks"].return_value = []
    mock_risk_handlers["get_related_actions"].return_value = [
        {"id": "action-1", "name": "No desc", "description": ""},
        {"id": "action-2", "name": "Has desc", "description": "Real description"},
    ]
    mock_client.chat.completions.create.return_value = _RiskSelection(
        matched_risks=[_SlimRiskMatch(risk_index=1, risk_name="Fraud", relevance="primary", justification="j")],
    )
    _, _, _, _, risk_actions, _ = map_risks(
        classifications, mock_client, mock_config, mock_risk_handlers,
    )
    assert risk_actions["atlas-fraud"] == ["Real description"]


from refiner.stages.map_risks import compute_gap_score


def test_gap_score_all_distant_no_primary():
    """High distance + no primary match + decomposition = high gap score."""
    from refiner.models import PolicyDecomposition
    score = compute_gap_score(
        min_distance=0.7,
        primary_count=0,
        has_decomposition=True,
    )
    # 0.45*0.7 + 0.35*1.0 + 0.20*1.0 = 0.315 + 0.35 + 0.20 = 0.865
    assert abs(score - 0.865) < 0.01


def test_gap_score_close_match_with_primary():
    """Low distance + primary match = low gap score."""
    score = compute_gap_score(
        min_distance=0.15,
        primary_count=2,
        has_decomposition=True,
    )
    # 0.45*0.15 + 0.35*0.0 + 0.20*1.0 = 0.0675 + 0 + 0.20 = 0.2675
    assert score < 0.4


def test_gap_score_no_decomposition_still_works():
    """Without decomposition, the score degrades gracefully (lower ceiling)."""
    score = compute_gap_score(
        min_distance=0.8,
        primary_count=0,
        has_decomposition=False,
    )
    # 0.45*0.8 + 0.35*1.0 + 0.20*0.0 = 0.36 + 0.35 + 0 = 0.71
    assert abs(score - 0.71) < 0.01


def test_gap_score_moderate_distance_tangential_only():
    """Moderate distance, no primary but has matches = moderate score."""
    score = compute_gap_score(
        min_distance=0.5,
        primary_count=0,
        has_decomposition=True,
    )
    # 0.45*0.5 + 0.35*1.0 + 0.20*1.0 = 0.225 + 0.35 + 0.20 = 0.775
    assert 0.7 < score < 0.85


from refiner.stages.map_risks import characterize_gap, _GapClassification, GAP_TYPE_WEIGHTS


def test_characterize_gap_novel(mock_client, mock_config):
    mock_client.chat.completions.create.return_value = _GapClassification(
        gap_type="novel",
        reasoning="No existing risk covers multi-agent collusion",
    )
    result = characterize_gap(
        policy_concept="Multi-agent collusion",
        concept_definition="Multiple AI agents coordinating to bypass safety controls",
        nearest_candidates=[
            {"name": "Dangerous use", "description": "Dangerous capabilities", "distance": 0.72},
        ],
        client=mock_client,
        config=mock_config,
    )
    assert result.gap_type == "novel"
    assert "multi-agent" in result.reasoning.lower() or "collusion" in result.reasoning.lower() or "No existing" in result.reasoning


def test_characterize_gap_compositional_downweighted(mock_client, mock_config):
    mock_client.chat.completions.create.return_value = _GapClassification(
        gap_type="compositional",
        reasoning="Combination of bias and hiring discrimination",
    )
    result = characterize_gap(
        policy_concept="Automated hiring discrimination",
        concept_definition="AI hiring tools that discriminate via training data bias",
        nearest_candidates=[
            {"name": "Bias", "description": "Model bias", "distance": 0.55},
            {"name": "Discrimination", "description": "Discrimination in outputs", "distance": 0.58},
        ],
        client=mock_client,
        config=mock_config,
    )
    assert result.gap_type == "compositional"


def test_gap_type_weights():
    assert GAP_TYPE_WEIGHTS["compositional"] == 0.6
    assert GAP_TYPE_WEIGHTS["novel"] == 1.0
    assert GAP_TYPE_WEIGHTS["domain_specialization"] == 1.0


def test_map_risks_detects_coverage_gap(mock_client, mock_config, mock_risk_handlers):
    """When all candidates are distant and LLM returns no primary, detect a gap."""
    pol = Policy(
        policy_concept="Multi-agent collusion",
        concept_definition="Multiple AI agents coordinating to bypass safety controls",
        decomposition=PolicyDecomposition(agent="AI agents", activity="coordinate", entity="safety controls"),
    )
    mock_risk_handlers["search_risks"].return_value = [
        {"id": "atlas-dangerous-use", "name": "Dangerous use", "description": "Dangerous capabilities", "distance": 0.75},
    ]
    mock_risk_handlers["get_risk_details"].return_value = {
        "id": "atlas-dangerous-use", "name": "Dangerous use", "description": "Dangerous capabilities",
        "concern": "Misuse risk", "risk_type": "output", "taxonomy": "ibm-risk-atlas",
    }
    mock_risk_handlers["get_related_risks"].return_value = []
    mock_risk_handlers["get_related_actions"].return_value = []

    # First LLM call: risk mapping — returns only tangential
    # Second LLM call: gap characterization — returns novel
    mock_client.chat.completions.create.side_effect = [
        _RiskSelection(
            matched_risks=[_SlimRiskMatch(risk_index=1, risk_name="Dangerous use", relevance="tangential", justification="j")],
        ),
        _GapClassification(gap_type="novel", reasoning="Multi-agent collusion is a new failure mode"),
    ]

    report = RunReport(model="m", policy_set="p", timestamp="t")
    mappings, _, _, _, _, coverage_gaps = map_risks([pol], mock_client, mock_config, mock_risk_handlers, report=report)

    assert len(coverage_gaps) == 1
    assert coverage_gaps[0].gap_type == "novel"
    assert coverage_gaps[0].policy_concept == "Multi-agent collusion"
    assert coverage_gaps[0].confidence > 0.6
    assert len(coverage_gaps[0].nearest_risks) > 0
    assert coverage_gaps[0].decomposition is not None

    gap_events = [e for e in report.events if e["event"] == "coverage_gap"]
    assert len(gap_events) == 1
    assert gap_events[0]["gap_type"] == "novel"


def test_map_risks_no_gap_on_strong_match(mock_client, mock_config, mock_risk_handlers):
    """When there's a close primary match, no gap is detected."""
    pol = _make_policy()
    mock_risk_handlers["search_risks"].return_value = [
        {"id": "atlas-fraud", "name": "Fraud", "description": "Fraud risk", "distance": 0.15},
    ]
    mock_risk_handlers["get_risk_details"].return_value = {
        "id": "atlas-fraud", "name": "Fraud", "description": "Fraud risk",
        "concern": "Financial loss", "risk_type": "output", "taxonomy": "ibm-risk-atlas",
    }
    mock_risk_handlers["get_related_risks"].return_value = []
    mock_risk_handlers["get_related_actions"].return_value = []
    mock_client.chat.completions.create.return_value = _RiskSelection(
        matched_risks=[_SlimRiskMatch(risk_index=1, risk_name="Fraud", relevance="primary", justification="j")],
    )

    mappings, _, _, _, _, coverage_gaps = map_risks([pol], mock_client, mock_config, mock_risk_handlers)
    assert len(coverage_gaps) == 0


def test_map_risks_compositional_gap_downweighted(mock_client, mock_config, mock_risk_handlers):
    """Compositional gaps get a 0.6x confidence discount."""
    pol = Policy(
        policy_concept="Automated hiring discrimination",
        concept_definition="AI hiring tools that discriminate via training data bias",
        decomposition=PolicyDecomposition(agent="AI hiring tools", activity="discriminate", entity="job candidates"),
    )
    mock_risk_handlers["search_risks"].return_value = [
        {"id": "atlas-bias", "name": "Bias", "description": "Model bias", "distance": 0.68},
        {"id": "atlas-discrimination", "name": "Discrimination", "description": "Outputs that discriminate", "distance": 0.70},
    ]
    mock_risk_handlers["get_risk_details"].side_effect = lambda rid: {
        "id": rid, "name": rid.replace("atlas-", "").title(), "description": "desc",
        "concern": "concern", "risk_type": "output", "taxonomy": "ibm-risk-atlas",
    }
    mock_risk_handlers["get_related_risks"].return_value = []
    mock_risk_handlers["get_related_actions"].return_value = []

    mock_client.chat.completions.create.side_effect = [
        _RiskSelection(matched_risks=[]),
        _GapClassification(gap_type="compositional", reasoning="Combination of bias and discrimination"),
    ]

    mappings, _, _, _, _, coverage_gaps = map_risks([pol], mock_client, mock_config, mock_risk_handlers)
    assert len(coverage_gaps) == 1
    assert coverage_gaps[0].gap_type == "compositional"
    # Compositional gaps get 0.6x weight, so confidence should be noticeably lower than raw gap_score
    assert coverage_gaps[0].confidence < 0.6


def test_map_risks_empty_returns_six_tuple(mock_client, mock_config, mock_risk_handlers):
    """Empty input returns six-element tuple with empty coverage_gaps."""
    mappings, details, seen_ids, related, risk_actions, coverage_gaps = map_risks(
        [], mock_client, mock_config, mock_risk_handlers,
    )
    assert coverage_gaps == []
