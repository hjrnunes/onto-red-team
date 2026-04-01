import logging
from refiner.models import (
    PolicyRiskMapping,
    RiskMatch,
    RiskVariationAxes,
    VariationAxis,
)
from refiner.stages.anchor import anchor, _AnchorResponse


def _make_mapping():
    return PolicyRiskMapping(
        policy_concept="Fraud",
        policy_type="A",
        matched_risks=[
            RiskMatch(risk_id="atlas-fraud", risk_name="Fraud", relevance="primary", justification="j"),
        ],
    )


def _make_risk_details():
    return {
        "atlas-fraud": {
            "id": "atlas-fraud",
            "name": "Fraud",
            "description": "Fraudulent activities targeting financial systems",
            "concern": "Financial loss and trust erosion",
        }
    }


def test_anchor_searches_ontology(mock_client, mock_config, mock_onto_handlers):
    mappings = [_make_mapping()]
    risk_details = _make_risk_details()
    mock_onto_handlers["search_classes"].return_value = [
        {"uri": "http://example.org/Person", "label": "Person", "definition": "A human.", "distance": 0.3},
    ]
    mock_onto_handlers["get_class_definition"].return_value = {
        "uri": "http://example.org/Person", "label": "Person", "definition": "A human.",
        "superclasses": [],
    }
    mock_onto_handlers["get_siblings"].return_value = []
    mock_client.chat.completions.create.return_value = _AnchorResponse(
        axes=[
            VariationAxis(
                cco_class_uri="http://example.org/Person",
                cco_class_label="Person",
                role="agent",
                rationale="Person committing fraud",
            ),
        ],
    )
    result = anchor(mappings, risk_details, mock_client, mock_config, mock_onto_handlers)
    assert len(result) == 1
    assert result[0].axes[0].cco_class_uri == "http://example.org/Person"
    assert result[0].risk_id == "atlas-fraud"
    assert result[0].policy_concept == "Fraud"
    mock_onto_handlers["search_classes"].assert_called_once()


def test_anchor_filters_invalid_uris(mock_client, mock_config, mock_onto_handlers):
    mappings = [_make_mapping()]
    risk_details = _make_risk_details()
    mock_onto_handlers["search_classes"].return_value = [
        {"uri": "http://example.org/Person", "label": "Person", "definition": "A human.", "distance": 0.3},
    ]
    mock_onto_handlers["get_class_definition"].side_effect = lambda uri: (
        {"uri": uri, "label": "Person", "definition": "A human.", "superclasses": []}
        if uri == "http://example.org/Person" else None
    )
    mock_onto_handlers["get_siblings"].return_value = []
    # LLM returns a valid and an invalid URI
    mock_client.chat.completions.create.return_value = _AnchorResponse(
        axes=[
            VariationAxis(cco_class_uri="http://example.org/Person", cco_class_label="Person", role="agent", rationale="r"),
            VariationAxis(cco_class_uri="http://example.org/Fake", cco_class_label="Fake", role="object", rationale="r"),
        ],
    )
    result = anchor(mappings, risk_details, mock_client, mock_config, mock_onto_handlers)
    assert len(result[0].axes) == 1
    assert result[0].axes[0].cco_class_uri == "http://example.org/Person"


def test_anchor_filters_candidates_by_domain(mock_client, mock_config, mock_onto_handlers):
    """When selected_domains is set, candidates from other domains are excluded."""
    mappings = [_make_mapping()]
    risk_details = _make_risk_details()
    # Search returns candidates from FIBO and OBO
    mock_onto_handlers["search_classes"].return_value = [
        {"uri": "http://purl.obolibrary.org/obo/MAXO_0000943", "label": "deep brain stimulation", "distance": 0.1},
        {"uri": "https://spec.edmcouncil.org/fibo/ontology/FND/Foo/Bar", "label": "Bar", "distance": 0.2},
        {"uri": "http://purl.obolibrary.org/obo/MONDO_123", "label": "some disease", "distance": 0.3},
    ]
    mock_onto_handlers["get_class_definition"].return_value = {
        "uri": "https://spec.edmcouncil.org/fibo/ontology/FND/Foo/Bar",
        "label": "Bar", "definition": "A bar.", "superclasses": [],
    }
    mock_onto_handlers["get_siblings"].return_value = []
    mock_client.chat.completions.create.return_value = _AnchorResponse(
        axes=[
            VariationAxis(
                cco_class_uri="https://spec.edmcouncil.org/fibo/ontology/FND/Foo/Bar",
                cco_class_label="Bar", role="object", rationale="r",
            ),
        ],
    )
    # Only FIBO and CCO selected — OBO candidates should be filtered out
    result = anchor(mappings, risk_details, mock_client, mock_config, mock_onto_handlers,
                    selected_domains=["CCO", "Commons", "FIBO"])
    assert len(result) == 1
    # The search was called with top_k=10 (extra headroom for filtering)
    mock_onto_handlers["search_classes"].assert_called_once()
    call_kwargs = mock_onto_handlers["search_classes"].call_args
    assert call_kwargs[1]["top_k"] == 10


def test_anchor_empty_mappings(mock_client, mock_config, mock_onto_handlers):
    result = anchor([], {}, mock_client, mock_config, mock_onto_handlers)
    assert result == []
