import logging
from refiner.models import (
    PolicyClassification,
    PolicyRiskMapping,
)
from refiner.stages.map_risks import map_risks, _RiskSelection, _SlimRiskMatch


def _make_classification(concept="Fraud", policy_type="A"):
    return PolicyClassification(
        policy_concept=concept,
        concept_definition=f"Prompts about {concept.lower()}",
        policy_type=policy_type,
        justification="test",
    )


def test_map_risks_calls_search_and_details(mock_client, mock_config, mock_risk_handlers):
    classifications = [_make_classification()]
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
    mappings, details, seen_ids, related, _ = map_risks(classifications, mock_client, mock_config, mock_risk_handlers)
    assert len(mappings) == 1
    assert mappings[0].matched_risks[0].risk_id == "atlas-fraud"
    assert mappings[0].policy_concept == "Fraud"
    assert mappings[0].policy_type == "A"
    mock_risk_handlers["search_risks"].assert_called_once()
    mock_risk_handlers["get_risk_details"].assert_called_once_with("atlas-fraud")


def test_map_risks_filters_hallucinated_risk_ids(mock_client, mock_config, mock_risk_handlers):
    classifications = [_make_classification()]
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
    mappings, details, seen_ids, related, _ = map_risks(classifications, mock_client, mock_config, mock_risk_handlers)
    # Invalid index should be filtered out
    assert len(mappings[0].matched_risks) == 1
    assert mappings[0].matched_risks[0].risk_id == "atlas-fraud"


def test_map_risks_returns_risk_details_cache(mock_client, mock_config, mock_risk_handlers):
    classifications = [_make_classification()]
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
    _, details, _, _, _ = map_risks(classifications, mock_client, mock_config, mock_risk_handlers)
    assert "atlas-fraud" in details
    assert details["atlas-fraud"]["description"] == "Fraud risk"


def test_map_risks_seen_ids_includes_related(mock_client, mock_config, mock_risk_handlers):
    classifications = [_make_classification()]
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
    _, _, seen_ids, _, _ = map_risks(classifications, mock_client, mock_config, mock_risk_handlers)
    assert "atlas-fraud" in seen_ids
    assert "owasp-fraud" in seen_ids
    assert "nist-fraud" in seen_ids


def test_map_risks_returns_related_risks(mock_client, mock_config, mock_risk_handlers):
    classifications = [_make_classification()]
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
    _, _, _, related_risks, _ = map_risks(classifications, mock_client, mock_config, mock_risk_handlers)
    assert "atlas-fraud" in related_risks
    assert len(related_risks["atlas-fraud"]) == 2
    assert related_risks["atlas-fraud"][0]["id"] == "owasp-fraud"


def test_map_risks_populates_match_distance(mock_client, mock_config, mock_risk_handlers):
    classifications = [_make_classification()]
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
    mappings, _, _, _, _ = map_risks(classifications, mock_client, mock_config, mock_risk_handlers)
    assert mappings[0].matched_risks[0].match_distance == 0.25


def test_map_risks_warns_on_weak_match(mock_client, mock_config, mock_risk_handlers, caplog):
    classifications = [_make_classification()]
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
        mappings, _, _, _, _ = map_risks(classifications, mock_client, mock_config, mock_risk_handlers)
    assert mappings[0].matched_risks[0].match_distance == 0.65
    assert any("Weak match" in msg for msg in caplog.messages)


def test_map_risks_empty_classifications(mock_client, mock_config, mock_risk_handlers):
    mappings, details, seen_ids, related, risk_actions = map_risks([], mock_client, mock_config, mock_risk_handlers)
    assert mappings == []
    assert details == {}
    assert seen_ids == set()
    assert related == {}
    assert risk_actions == {}


def test_map_risks_emits_weak_match(mock_client, mock_config, mock_risk_handlers):
    """When a match distance > 0.6, emit a weak_match event."""
    from refiner.models import RunReport
    classifications = [_make_classification()]
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
    mappings, _, _, _, _ = map_risks(classifications, mock_client, mock_config, mock_risk_handlers, report=report)
    weak = [e for e in report.events if e["event"] == "weak_match"]
    assert len(weak) == 1
    assert weak[0]["risk_id"] == "atlas-fraud"
    assert weak[0]["distance"] == 0.65


def test_map_risks_emits_invalid_risk_index(mock_client, mock_config, mock_risk_handlers):
    """When LLM returns an out-of-range index, emit invalid_risk_index."""
    from refiner.models import RunReport
    classifications = [_make_classification()]
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
    mappings, _, _, _, _ = map_risks(classifications, mock_client, mock_config, mock_risk_handlers, report=report)
    invalid = [e for e in report.events if e["event"] == "invalid_risk_index"]
    assert len(invalid) == 1
    assert invalid[0]["raw_index"] == 99


def test_map_risks_emits_match_count(mock_client, mock_config, mock_risk_handlers):
    """Emit match_count per policy concept."""
    from refiner.models import RunReport
    classifications = [_make_classification()]
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
    mappings, _, _, _, _ = map_risks(classifications, mock_client, mock_config, mock_risk_handlers, report=report)
    counts = [e for e in report.events if e["event"] == "match_count"]
    assert len(counts) == 1
    assert counts[0]["policy_concept"] == "Fraud"
    assert counts[0]["count"] == 1


def test_map_risks_no_report_works(mock_client, mock_config, mock_risk_handlers):
    """map_risks works without report param (backward compat)."""
    classifications = [_make_classification()]
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
    mappings, _, _, _, _ = map_risks(classifications, mock_client, mock_config, mock_risk_handlers)
    assert len(mappings) == 1


def test_map_risks_returns_risk_actions(mock_client, mock_config, mock_risk_handlers):
    """map_risks collects action descriptions from get_related_actions."""
    classifications = [_make_classification()]
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
    mappings, details, seen_ids, related, risk_actions = map_risks(
        classifications, mock_client, mock_config, mock_risk_handlers,
    )
    assert "atlas-fraud" in risk_actions
    assert len(risk_actions["atlas-fraud"]) == 2
    assert "Monitor financial transactions for anomalies" in risk_actions["atlas-fraud"]


def test_map_risks_actions_empty_when_none(mock_client, mock_config, mock_risk_handlers):
    """When get_related_actions returns empty, risk_actions has empty list."""
    classifications = [_make_classification()]
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
    _, _, _, _, risk_actions = map_risks(
        classifications, mock_client, mock_config, mock_risk_handlers,
    )
    assert risk_actions.get("atlas-fraud") == []


def test_map_risks_actions_skips_empty_descriptions(mock_client, mock_config, mock_risk_handlers):
    """Actions without descriptions are not included."""
    classifications = [_make_classification()]
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
    _, _, _, _, risk_actions = map_risks(
        classifications, mock_client, mock_config, mock_risk_handlers,
    )
    assert risk_actions["atlas-fraud"] == ["Real description"]
