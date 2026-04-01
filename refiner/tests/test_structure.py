import pytest
from refiner.models import (
    Policy,
    PolicyClassification,
    PolicyRiskMapping,
    RiskMatch,
    CrossMapping,
    DomainContextProfile,
    DomainContextAxis,
    AxisEnumeration,
)
from refiner.stages.structure import structure, slugify


def test_slugify():
    assert slugify("Executive Compensation") == "executive-compensation"
    assert slugify("Debt Repayment Negotiation") == "debt-repayment-negotiation"
    assert slugify("Fraud") == "fraud"
    assert slugify("Security & Malware") == "security-malware"


def _make_state_data():
    classifications = [
        PolicyClassification(
            policy_concept="Fraud", concept_definition="About fraud",
            policy_type="A", justification="Safety",
        ),
        PolicyClassification(
            policy_concept="Executive Compensation", concept_definition="About exec pay",
            policy_type="B", justification="Confidentiality",
        ),
    ]
    risk_mappings = [
        PolicyRiskMapping(
            policy_concept="Fraud", policy_type="A",
            matched_risks=[
                RiskMatch(risk_id="atlas-fraud", risk_name="Fraud", relevance="primary", justification="j"),
            ],
            cross_mappings=[
                CrossMapping(
                    source_risk_id="atlas-fraud", target_risk_id="owasp-fraud",
                    target_risk_name="OWASP Fraud", target_taxonomy="owasp",
                    mapping_type="close",
                ),
            ],
        ),
        PolicyRiskMapping(
            policy_concept="Executive Compensation", policy_type="B",
            matched_risks=[
                RiskMatch(risk_id="atlas-data-disclosure", risk_name="Data Disclosure", relevance="primary", justification="j"),
            ],
            cross_mappings=[],
        ),
    ]
    domain_context = [
        DomainContextProfile(
            risk_id="atlas-fraud", risk_name="Fraud", policy_concept="Fraud",
            axes=[
                DomainContextAxis(
                    cco_class_uri="http://example.org/Person", cco_class_label="Person", role="agent",
                    enumerations=[
                        AxisEnumeration(class_uri="http://example.org/Employee", class_label="Employee", source_ontology="CCO", relevance="high"),
                    ],
                ),
            ],
        ),
    ]
    return classifications, risk_mappings, domain_context


def test_structure_taxonomy_has_correct_id():
    classifications, risk_mappings, domain_context = _make_state_data()
    taxonomy, profiles = structure("swb", classifications, risk_mappings, domain_context)
    assert taxonomy["taxonomies"][0]["id"] == "client-swb"
    assert taxonomy["taxonomies"][0]["type"] == "RiskTaxonomy"


def test_structure_creates_groups_per_policy_type():
    classifications, risk_mappings, domain_context = _make_state_data()
    taxonomy, _ = structure("swb", classifications, risk_mappings, domain_context)
    group_ids = {g["id"] for g in taxonomy["groups"]}
    assert "client-swb-safety" in group_ids  # type A
    assert "client-swb-confidentiality" in group_ids  # type B
    assert "client-swb-scope-regulatory" not in group_ids  # no type C policies
    assert "client-swb-routing" not in group_ids  # no type D policies


def test_structure_entries_have_correct_isPartOf():
    classifications, risk_mappings, domain_context = _make_state_data()
    taxonomy, _ = structure("swb", classifications, risk_mappings, domain_context)
    entries = taxonomy["entries"]
    fraud_entry = next(e for e in entries if "fraud" in e["id"])
    assert fraud_entry["isPartOf"] == "client-swb-safety"
    disclosure_entry = next(e for e in entries if "data-disclosure" in e["id"])
    assert disclosure_entry["isPartOf"] == "client-swb-confidentiality"


def test_structure_entries_have_cross_mappings():
    classifications, risk_mappings, domain_context = _make_state_data()
    taxonomy, _ = structure("swb", classifications, risk_mappings, domain_context)
    fraud_entry = next(e for e in taxonomy["entries"] if "fraud" in e["id"])
    assert "owasp-fraud" in fraud_entry.get("close_mappings", [])


def test_structure_filters_invalid_cross_mapping_targets():
    classifications, risk_mappings, domain_context = _make_state_data()
    # Only "owasp-fraud" is in the valid set; any other target would be filtered
    taxonomy, _ = structure("swb", classifications, risk_mappings, domain_context,
                            valid_risk_ids={"owasp-fraud"})
    fraud_entry = next(e for e in taxonomy["entries"] if "fraud" in e["id"])
    assert "owasp-fraud" in fraud_entry.get("close_mappings", [])


def test_structure_warns_on_unknown_cross_mapping_targets():
    classifications, risk_mappings, domain_context = _make_state_data()
    # Empty valid set means all cross-mappings are filtered
    taxonomy, _ = structure("swb", classifications, risk_mappings, domain_context,
                            valid_risk_ids=set())
    fraud_entry = next(e for e in taxonomy["entries"] if "fraud" in e["id"])
    assert "close_mappings" not in fraud_entry


def test_structure_no_validation_when_valid_ids_none():
    """When valid_risk_ids is None, all cross-mappings pass through (backwards compat)."""
    classifications, risk_mappings, domain_context = _make_state_data()
    taxonomy, _ = structure("swb", classifications, risk_mappings, domain_context,
                            valid_risk_ids=None)
    fraud_entry = next(e for e in taxonomy["entries"] if "fraud" in e["id"])
    assert "owasp-fraud" in fraud_entry.get("close_mappings", [])


def test_structure_profiles_output():
    classifications, risk_mappings, domain_context = _make_state_data()
    _, profiles = structure("swb", classifications, risk_mappings, domain_context)
    assert len(profiles["profiles"]) == 1
    assert profiles["profiles"][0]["risk_id"] == "atlas-fraud"
