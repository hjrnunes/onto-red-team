"""Tests for enriched policy models: BoundaryExample, NamedEntity, PolicyDocument."""

from refiner.models import (
    BoundaryExample,
    NamedEntity,
    Policy,
    PolicyDocument,
)


def test_boundary_example_construction():
    be = BoundaryExample(
        prohibited="Share customer SSNs",
        acceptable="Confirm last 4 digits of SSN on file",
    )
    assert be.prohibited == "Share customer SSNs"
    assert be.acceptable == "Confirm last 4 digits of SSN on file"


def test_named_entity_construction():
    ne = NamedEntity(name="Jenny Carlson", role="CEO")
    assert ne.name == "Jenny Carlson"
    assert ne.role == "CEO"


def test_policy_backward_compat_no_enrichments():
    """Existing 2-field Policy dicts must still work (new fields default to empty)."""
    p = Policy(policy_concept="Fraud", concept_definition="Prompts about fraud")
    assert p.policy_concept == "Fraud"
    assert p.concept_definition == "Prompts about fraud"
    assert p.boundary_examples == []
    assert p.acceptable_uses == []
    assert p.risk_controls == []
    assert p.human_involvement is None


def test_policy_with_enrichments():
    p = Policy(
        policy_concept="Data Leakage",
        concept_definition="Disclosure of confidential data",
        boundary_examples=[
            BoundaryExample(
                prohibited="Reveal customer account numbers",
                acceptable="Discuss account types in general terms",
            )
        ],
        acceptable_uses=["General financial education"],
        risk_controls=["PII filter applied to all outputs"],
        human_involvement="Human review required for account queries",
    )
    assert len(p.boundary_examples) == 1
    assert p.boundary_examples[0].prohibited == "Reveal customer account numbers"
    assert p.acceptable_uses == ["General financial education"]
    assert p.risk_controls == ["PII filter applied to all outputs"]
    assert p.human_involvement == "Human review required for account queries"


def test_policy_document_defaults():
    doc = PolicyDocument()
    assert doc.airo_version == "0.2"
    assert doc.organization is None
    assert doc.domain is None
    assert doc.purpose == []
    assert doc.ai_systems == []
    assert doc.ai_users == []
    assert doc.ai_subjects == []
    assert doc.governing_regulations == []
    assert doc.named_entities == []
    assert doc.policies == []


def test_policy_document_roundtrip():
    """Construct from dict, serialize back, and verify equality."""
    data = {
        "airo_version": "0.2",
        "organization": "South West Bank",
        "domain": "banking",
        "purpose": ["Customer support chatbot"],
        "ai_systems": ["LLM-powered assistant"],
        "ai_users": ["Bank employees"],
        "ai_subjects": ["Bank customers"],
        "governing_regulations": ["GDPR", "PCI-DSS"],
        "named_entities": [
            {"name": "Jenny Carlson", "role": "CEO"},
            {"name": "CreditAlpha", "role": "Credit card product"},
        ],
        "policies": [
            {
                "policy_concept": "Fraud",
                "concept_definition": "Prompts about fraud",
            },
            {
                "policy_concept": "Data Leakage",
                "concept_definition": "Disclosure of confidential data",
                "boundary_examples": [
                    {
                        "prohibited": "Reveal account numbers",
                        "acceptable": "Discuss account types",
                    }
                ],
                "acceptable_uses": ["General info"],
                "risk_controls": ["PII filter"],
                "human_involvement": "Required for sensitive queries",
            },
        ],
    }
    doc = PolicyDocument(**data)
    assert doc.organization.name == "South West Bank"
    assert doc.domain == "banking"
    assert len(doc.named_entities) == 2
    assert doc.named_entities[0].name == "Jenny Carlson"
    assert len(doc.policies) == 2
    # First policy: minimal (backward compat)
    assert doc.policies[0].boundary_examples == []
    assert doc.policies[0].human_involvement is None
    # Second policy: enriched
    assert len(doc.policies[1].boundary_examples) == 1
    assert doc.policies[1].risk_controls == ["PII filter"]

    # Round-trip: model_dump should produce equivalent dict
    dumped = doc.model_dump()
    assert dumped["organization"]["name"] == data["organization"]
    assert len(dumped["named_entities"]) == 2
    assert len(dumped["policies"]) == 2
