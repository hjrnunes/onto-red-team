"""Tests for the SSSOM-based anchor stage (v2 redesign)."""
import pytest
from unittest.mock import MagicMock
from refiner.models import PolicyRiskMapping, RiskMatch, RiskVariationAxes
from refiner.ontology_seeds import SSSOMIndex, SSSOMMapping
from refiner.stages.anchor import anchor, _AnchorResponse, _SlimAxis


@pytest.fixture
def mock_config():
    from refiner.llm import LLMConfig
    return LLMConfig(base_url="http://localhost:8000/v1", model="test-model")


@pytest.fixture
def mock_client():
    client = MagicMock()
    return client


@pytest.fixture
def mock_onto_handlers():
    return {
        "search_classes": MagicMock(return_value=[]),
        "search_domains": MagicMock(return_value={}),
        "get_class_definition": MagicMock(side_effect=lambda uri: {
            "uri": uri, "label": uri.split("/")[-1].split("#")[-1],
            "definition": f"Definition of {uri.split('/')[-1]}",
            "superclasses": [],
        }),
        "get_subclasses": MagicMock(return_value=[]),
        "get_superclasses": MagicMock(return_value=[]),
        "get_siblings": MagicMock(return_value=[]),
        "get_properties": MagicMock(return_value=[]),
        "explore_class": MagicMock(return_value=None),
        "get_restrictions": MagicMock(return_value=[]),
        "get_disjoint_classes": MagicMock(return_value=[]),
        "get_equivalent_axioms": MagicMock(return_value=[]),
    }


@pytest.fixture
def mock_nexus_handlers():
    return {
        "get_risk_details": MagicMock(return_value={"group": "ibm-risk-atlas-privacy"}),
        "get_related_risks": MagicMock(return_value=[]),
        "get_related_actions": MagicMock(return_value=[]),
        "get_risk_group": MagicMock(return_value={"id": "ibm-risk-atlas-privacy", "name": "Privacy"}),
    }


@pytest.fixture
def layer1():
    return SSSOMIndex([
        SSSOMMapping("ibm-risk-atlas-privacy", "Privacy", "skos:relatedMatch",
                     "pd:Biometric", "Biometric", "semapv:ManualMappingCuration", 0.90),
        SSSOMMapping("ibm-risk-atlas-privacy", "Privacy", "skos:relatedMatch",
                     "eu-aiact:AISubject", "AI Subject", "semapv:ManualMappingCuration", 0.95),
    ])


@pytest.fixture
def layer2():
    return SSSOMIndex([
        SSSOMMapping("pd:Biometric", "Biometric", "skos:broadMatch",
                     "http://example.org/BiometricId", "Biometric Identifier",
                     "semapv:ManualMappingCuration", 0.85),
        SSSOMMapping("eu-aiact:AISubject", "AI Subject", "skos:relatedMatch",
                     "http://example.org/Person", "Person",
                     "semapv:ManualMappingCuration", 0.90),
    ])


@pytest.fixture
def sample_mapping():
    return PolicyRiskMapping(
        policy_concept="Do not disclose biometric data",
        matched_risks=[RiskMatch(
            risk_id="atlas-biometric-exposure",
            risk_name="Biometric exposure",
            relevance="primary",
            justification="Direct match",
        )],
    )


@pytest.fixture
def sample_risk_details():
    return {
        "atlas-biometric-exposure": {
            "id": "atlas-biometric-exposure",
            "name": "Biometric exposure",
            "description": "Risk of biometric data being exposed",
            "concern": "Biometric identifiers leaked",
            "group": "ibm-risk-atlas-privacy",
        }
    }


def test_anchor_uses_sssom_seeds(
    mock_client, mock_config, mock_onto_handlers, mock_nexus_handlers,
    layer1, layer2, sample_mapping, sample_risk_details
):
    """Anchor should resolve seeds via two-layer SSSOM and call navigate_from_seeds."""
    mock_onto_handlers["get_subclasses"].return_value = [
        {"uri": "http://example.org/FacialPrint", "label": "Facial Print", "depth": 1}
    ]
    mock_client.chat.completions.create.return_value = _AnchorResponse(axes=[
        _SlimAxis(class_id="C1", class_label="Facial Print", rationale="relevant")
    ])
    result, vocab_contexts = anchor(
        risk_mappings=[sample_mapping],
        risk_details=sample_risk_details,
        client=mock_client,
        config=mock_config,
        onto_handlers=mock_onto_handlers,
        nexus_handlers=mock_nexus_handlers,
        layer1_mappings=layer1,
        layer2_mappings=layer2,
    )
    assert len(result) == 1
    assert len(result[0].axes) >= 1
    assert "atlas-biometric-exposure" in vocab_contexts


def test_anchor_caches_by_risk_id(
    mock_client, mock_config, mock_onto_handlers, mock_nexus_handlers,
    layer1, layer2, sample_risk_details
):
    """Same risk from two policies should use cache."""
    mock_client.chat.completions.create.return_value = _AnchorResponse(axes=[])

    mapping1 = PolicyRiskMapping(
        policy_concept="Policy A",
        matched_risks=[RiskMatch(risk_id="atlas-biometric-exposure", risk_name="Bio",
                                 relevance="primary", justification="test")],
    )
    mapping2 = PolicyRiskMapping(
        policy_concept="Policy B",
        matched_risks=[RiskMatch(risk_id="atlas-biometric-exposure", risk_name="Bio",
                                 relevance="primary", justification="test")],
    )
    result, vocab_contexts = anchor(
        risk_mappings=[mapping1, mapping2],
        risk_details=sample_risk_details,
        client=mock_client,
        config=mock_config,
        onto_handlers=mock_onto_handlers,
        nexus_handlers=mock_nexus_handlers,
        layer1_mappings=layer1,
        layer2_mappings=layer2,
    )
    assert len(result) == 2
    # LLM should only be called once (second is cached)
    assert mock_client.chat.completions.create.call_count == 1
