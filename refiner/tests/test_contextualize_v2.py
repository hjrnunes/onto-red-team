"""Tests for the policy-driven contextualize stage (v2 redesign)."""
import pytest
from unittest.mock import MagicMock
from refiner.models import (
    RiskVariationAxes, VariationAxis, DomainContextDocument
)
from refiner.stages.contextualize import contextualize, _Variation, _ContextResponse


@pytest.fixture
def mock_config():
    from refiner.llm import LLMConfig
    return LLMConfig(base_url="http://localhost:8000/v1", model="test-model")


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def mock_onto_handlers():
    return {
        "get_subclasses": MagicMock(return_value=[]),
        "get_class_definition": MagicMock(return_value=None),
        "get_siblings": MagicMock(return_value=[]),
        "get_restrictions": MagicMock(return_value=[]),
    }


@pytest.fixture
def sample_axes():
    return [RiskVariationAxes(
        risk_id="atlas-bio",
        risk_name="Biometric exposure",
        policy_concept="Do not disclose biometric data",
        axes=[VariationAxis(
            cco_class_uri="http://example.org/BiometricId",
            cco_class_label="Biometric Identifier",
            bfo_category="InformationContentEntity",
            vocabulary_concept="pd:Biometric",
            vocabulary_label="Biometric",
            rationale="Biometric data at risk",
        )],
    )]


@pytest.fixture
def sample_risk_details():
    return {
        "atlas-bio": {
            "description": "Risk of biometric data exposure",
            "concern": "Biometric identifiers leaked",
        }
    }


@pytest.fixture
def sample_policies():
    from refiner.models import Policy
    return [Policy(
        policy_concept="Do not disclose biometric data",
        concept_definition="Biometric identifiers must not be revealed",
        boundary_examples=[],
        acceptable_uses=["aggregate statistical reporting"],
        risk_controls=["biometric data masking"],
    )]


def test_generates_variations(
    mock_client, mock_config, mock_onto_handlers,
    sample_axes, sample_risk_details, sample_policies
):
    mock_client.chat.completions.create.return_value = _ContextResponse(
        variations=[
            _Variation(instance="Facial recognition template leaked", relevance="high"),
            _Variation(instance="Fingerprint hash exposed in logs", relevance="high"),
        ]
    )
    result = contextualize(
        sample_axes, mock_client, mock_config, mock_onto_handlers,
        risk_details=sample_risk_details,
        policies=sample_policies,
    )
    assert isinstance(result, DomainContextDocument)
    assert len(result.policy_contexts) == 1
    assert result.policy_contexts[0].policy_concept == "Do not disclose biometric data"
    assert len(result.policy_contexts[0].risk_groundings) == 1
    grounding = result.policy_contexts[0].risk_groundings[0]
    assert grounding.risk_id == "atlas-bio"
    assert len(grounding.axes[0].enumerations) == 2
    assert grounding.axes[0].enumerations[0].provenance == "generated"


def test_caches_by_risk_id(
    mock_client, mock_config, mock_onto_handlers,
    sample_risk_details, sample_policies
):
    mock_client.chat.completions.create.return_value = _ContextResponse(
        variations=[_Variation(instance="Test", relevance="high")]
    )
    axes = [
        RiskVariationAxes(
            risk_id="atlas-bio", risk_name="Bio", policy_concept="Policy A",
            axes=[VariationAxis(
                cco_class_uri="http://example.org/X", cco_class_label="X",
                rationale="test",
            )],
        ),
        RiskVariationAxes(
            risk_id="atlas-bio", risk_name="Bio", policy_concept="Policy B",
            axes=[VariationAxis(
                cco_class_uri="http://example.org/X", cco_class_label="X",
                rationale="test",
            )],
        ),
    ]
    result = contextualize(
        axes, mock_client, mock_config, mock_onto_handlers,
        risk_details=sample_risk_details,
        policies=sample_policies,
    )
    # Two policy concepts -> two PolicyDomainContext entries
    assert len(result.policy_contexts) == 2
    # But only one LLM call (cache hit on second)
    assert mock_client.chat.completions.create.call_count == 1
    # Both share the same risk grounding axes
    axes_a = result.policy_contexts[0].risk_groundings[0].axes
    axes_b = result.policy_contexts[1].risk_groundings[0].axes
    assert axes_a == axes_b


def test_risks_populated_from_risk_details(
    mock_client, mock_config, mock_onto_handlers,
    sample_axes, sample_risk_details, sample_policies
):
    mock_client.chat.completions.create.return_value = _ContextResponse(
        variations=[_Variation(instance="Test", relevance="high")]
    )
    result = contextualize(
        sample_axes, mock_client, mock_config, mock_onto_handlers,
        risk_details=sample_risk_details,
        policies=sample_policies,
    )
    assert len(result.risks) == 1
    assert result.risks[0].risk_id == "atlas-bio"
    assert result.risks[0].risk_name == "Biometric exposure"
    assert result.risks[0].risk_description == "Risk of biometric data exposure"
    assert result.risks[0].risk_concern == "Biometric identifiers leaked"


def test_includes_vocabulary_context_in_prompt(
    mock_client, mock_config, mock_onto_handlers,
    sample_axes, sample_risk_details, sample_policies
):
    mock_client.chat.completions.create.return_value = _ContextResponse(variations=[])
    contextualize(
        sample_axes, mock_client, mock_config, mock_onto_handlers,
        risk_details=sample_risk_details,
        policies=sample_policies,
        vocabulary_contexts={"atlas-bio": {
            "stakeholders": [{"concept_id": "eu-aiact:AISubject", "label": "AI Subject", "confidence": 0.9}],
            "data_sensitivity": [{"concept_id": "pd:Biometric", "label": "Biometric", "confidence": 0.9}],
            "rights": [], "justifications": [], "sector_purposes": [],
            "risk_concepts": [], "prohibited_practices": [],
        }},
    )
    call_args = mock_client.chat.completions.create.call_args
    user_msg = [m for m in call_args.kwargs.get("messages", []) if m["role"] == "user"][0]
    assert "Biometric" in user_msg["content"]
    assert "AI Subject" in user_msg["content"]


def test_empty_axes_returns_grounding_with_empty_axes(
    mock_client, mock_config, mock_onto_handlers
):
    axes = [RiskVariationAxes(
        risk_id="atlas-bio", risk_name="Bio", policy_concept="Policy",
        axes=[],
    )]
    result = contextualize(
        axes, mock_client, mock_config, mock_onto_handlers,
    )
    assert isinstance(result, DomainContextDocument)
    assert len(result.policy_contexts) == 1
    assert result.policy_contexts[0].risk_groundings[0].axes == []
    assert mock_client.chat.completions.create.call_count == 0


def test_empty_input_returns_empty_document(
    mock_client, mock_config, mock_onto_handlers
):
    result = contextualize(
        [], mock_client, mock_config, mock_onto_handlers,
    )
    assert isinstance(result, DomainContextDocument)
    assert result.policy_contexts == []
    assert result.risks == []


def test_contextualize_accepts_risk_landscape(mock_client, mock_config, mock_onto_handlers):
    from refiner.models import (
        RiskLandscape, RiskDetail, PolicyRiskMapping, RiskMatch,
        RiskVariationAxes, VariationAxis,
    )
    from refiner.stages.contextualize import contextualize

    landscape = RiskLandscape(
        model="test-model",
        run_slug="test",
        timestamp="2026-04-14T12:00:00Z",
        selected_domains=["CCO", "Commons"],
        risks=[
            RiskDetail(
                risk_id="r1", risk_name="Risk One",
                risk_description="desc", risk_concern="concern",
            ),
        ],
    )

    axes = [
        RiskVariationAxes(
            risk_id="r1",
            risk_name="Risk One",
            policy_concept="Policy A",
            axes=[
                VariationAxis(
                    cco_class_uri="http://example.org/Class1",
                    cco_class_label="Class One",
                    rationale="test",
                ),
            ],
        ),
    ]

    mock_onto_handlers["get_subclasses"].return_value = []

    from unittest.mock import MagicMock
    from pydantic import BaseModel
    from typing import Literal

    class _MockVariation(BaseModel):
        instance: str
        relevance: Literal["high", "medium", "low"]

    class _MockResponse(BaseModel):
        variations: list[_MockVariation]

    mock_client.chat.completions.create.return_value = _MockResponse(
        variations=[_MockVariation(instance="test instance", relevance="high")]
    )

    result = contextualize(
        variation_axes=axes,
        client=mock_client,
        config=mock_config,
        onto_handlers=mock_onto_handlers,
        risk_landscape=landscape,
    )

    assert result.selected_domains == ["CCO", "Commons"]
    assert result.run_slug == "test"
