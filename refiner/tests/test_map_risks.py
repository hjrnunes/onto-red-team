import logging
from refiner.models import (
    PolicyClassification,
    PolicyRiskMapping,
    RiskMatch,
)
from refiner.stages.map_risks import map_risks, _RiskSelection


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
            RiskMatch(risk_id="atlas-fraud", risk_name="Fraud", relevance="primary", justification="j"),
        ],
    )
    mappings, details, seen_ids, related = map_risks(classifications, mock_client, mock_config, mock_risk_handlers)
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
    # LLM hallucinates a risk_id that doesn't exist
    mock_client.chat.completions.create.return_value = _RiskSelection(
        matched_risks=[
            RiskMatch(risk_id="atlas-fraud", risk_name="Fraud", relevance="primary", justification="j"),
            RiskMatch(risk_id="hallucinated-id", risk_name="Fake", relevance="supporting", justification="j"),
        ],
    )
    mappings, details, seen_ids, related = map_risks(classifications, mock_client, mock_config, mock_risk_handlers)
    # Hallucinated ID should be filtered out
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
        matched_risks=[RiskMatch(risk_id="atlas-fraud", risk_name="Fraud", relevance="primary", justification="j")],
    )
    _, details, _, _ = map_risks(classifications, mock_client, mock_config, mock_risk_handlers)
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
        matched_risks=[RiskMatch(risk_id="atlas-fraud", risk_name="Fraud", relevance="primary", justification="j")],
    )
    _, _, seen_ids, _ = map_risks(classifications, mock_client, mock_config, mock_risk_handlers)
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
        matched_risks=[RiskMatch(risk_id="atlas-fraud", risk_name="Fraud", relevance="primary", justification="j")],
    )
    _, _, _, related_risks = map_risks(classifications, mock_client, mock_config, mock_risk_handlers)
    assert "atlas-fraud" in related_risks
    assert len(related_risks["atlas-fraud"]) == 2
    assert related_risks["atlas-fraud"][0]["id"] == "owasp-fraud"


def test_map_risks_empty_classifications(mock_client, mock_config, mock_risk_handlers):
    mappings, details, seen_ids, related = map_risks([], mock_client, mock_config, mock_risk_handlers)
    assert mappings == []
    assert details == {}
    assert seen_ids == set()
    assert related == {}
