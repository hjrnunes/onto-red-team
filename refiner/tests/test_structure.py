import pytest
from refiner.models import (
    Policy,
    PolicyClassification,
    PolicyRiskMapping,
    RiskMatch,
    DomainContextProfile,
    DomainContextAxis,
    AxisEnumeration,
    RunReport,
)
from refiner.stages.structure import structure, slugify


def test_slugify():
    assert slugify("Executive Compensation") == "executive-compensation"
    assert slugify("Debt Repayment Negotiation") == "debt-repayment-negotiation"
    assert slugify("Fraud") == "fraud"
    assert slugify("Disclosure - Financial") == "disclosure-financial"
    assert slugify("A -- B") == "a-b"
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
        ),
        PolicyRiskMapping(
            policy_concept="Executive Compensation", policy_type="B",
            matched_risks=[
                RiskMatch(risk_id="atlas-data-disclosure", risk_name="Data Disclosure", relevance="primary", justification="j"),
            ],
        ),
    ]
    related_risks = {
        "atlas-fraud": [
            {"id": "owasp-fraud", "mapping_type": "close"},
        ],
    }
    domain_context = [
        DomainContextProfile(
            risk_id="atlas-fraud", risk_name="Fraud", policy_concept="Fraud",
            axes=[
                DomainContextAxis(
                    cco_class_uri="http://example.org/Person", cco_class_label="Person", roles=["agent"],
                    enumerations=[
                        AxisEnumeration(class_uri="http://example.org/Employee", class_label="Employee", source_ontology="CCO", relevance="high"),
                    ],
                ),
            ],
        ),
    ]
    return classifications, risk_mappings, related_risks, domain_context


def test_structure_taxonomy_has_correct_id():
    classifications, risk_mappings, related_risks, domain_context = _make_state_data()
    taxonomy, profiles = structure("swb", classifications, risk_mappings, domain_context,
                                   related_risks=related_risks)
    assert taxonomy["taxonomies"][0]["id"] == "client-swb"
    assert taxonomy["taxonomies"][0]["type"] == "RiskTaxonomy"


def test_structure_creates_groups_per_policy_type():
    classifications, risk_mappings, related_risks, domain_context = _make_state_data()
    taxonomy, _ = structure("swb", classifications, risk_mappings, domain_context,
                            related_risks=related_risks)
    group_ids = {g["id"] for g in taxonomy["groups"]}
    assert "client-swb-safety" in group_ids  # type A
    assert "client-swb-confidentiality" in group_ids  # type B
    assert "client-swb-scope-regulatory" not in group_ids  # no type C policies
    assert "client-swb-routing" not in group_ids  # no type D policies


def test_structure_entries_have_correct_isPartOf():
    classifications, risk_mappings, related_risks, domain_context = _make_state_data()
    taxonomy, _ = structure("swb", classifications, risk_mappings, domain_context,
                            related_risks=related_risks)
    entries = taxonomy["entries"]
    fraud_entry = next(e for e in entries if "fraud" in e["id"])
    assert fraud_entry["isPartOf"] == "client-swb-safety"
    disclosure_entry = next(e for e in entries if "data-disclosure" in e["id"])
    assert disclosure_entry["isPartOf"] == "client-swb-confidentiality"


def test_structure_entries_have_cross_mappings():
    classifications, risk_mappings, related_risks, domain_context = _make_state_data()
    taxonomy, _ = structure("swb", classifications, risk_mappings, domain_context,
                            related_risks=related_risks)
    fraud_entry = next(e for e in taxonomy["entries"] if "fraud" in e["id"])
    assert "owasp-fraud" in fraud_entry.get("close_mappings", [])


def test_structure_filters_invalid_cross_mapping_targets():
    classifications, risk_mappings, related_risks, domain_context = _make_state_data()
    # Only "owasp-fraud" is in the valid set; any other target would be filtered
    taxonomy, _ = structure("swb", classifications, risk_mappings, domain_context,
                            related_risks=related_risks,
                            valid_risk_ids={"owasp-fraud"})
    fraud_entry = next(e for e in taxonomy["entries"] if "fraud" in e["id"])
    assert "owasp-fraud" in fraud_entry.get("close_mappings", [])


def test_structure_warns_on_unknown_cross_mapping_targets():
    classifications, risk_mappings, related_risks, domain_context = _make_state_data()
    # Empty valid set means all cross-mappings are filtered
    taxonomy, _ = structure("swb", classifications, risk_mappings, domain_context,
                            related_risks=related_risks,
                            valid_risk_ids=set())
    fraud_entry = next(e for e in taxonomy["entries"] if "fraud" in e["id"])
    assert "close_mappings" not in fraud_entry


def test_structure_no_cross_mappings_when_related_risks_none():
    """When related_risks is None, no cross-mappings are added."""
    classifications, risk_mappings, _, domain_context = _make_state_data()
    taxonomy, _ = structure("swb", classifications, risk_mappings, domain_context,
                            related_risks=None)
    fraud_entry = next(e for e in taxonomy["entries"] if "fraud" in e["id"])
    assert "close_mappings" not in fraud_entry


def test_structure_profiles_output():
    classifications, risk_mappings, related_risks, domain_context = _make_state_data()
    _, profiles = structure("swb", classifications, risk_mappings, domain_context,
                            related_risks=related_risks)
    assert len(profiles["profiles"]) == 1
    assert profiles["profiles"][0]["risk_id"] == "atlas-fraud"


def test_structure_deduplicates_entries_by_id():
    """Same risk matched from two policies should produce one entry with merged mappings."""
    classifications = [
        PolicyClassification(policy_concept="Fraud", concept_definition="d", policy_type="A", justification="j"),
        PolicyClassification(policy_concept="AML", concept_definition="d", policy_type="A", justification="j"),
    ]
    risk_mappings = [
        PolicyRiskMapping(
            policy_concept="Fraud", policy_type="A",
            matched_risks=[RiskMatch(risk_id="atlas-fraud", risk_name="Fraud", relevance="primary", justification="j")],
        ),
        PolicyRiskMapping(
            policy_concept="AML", policy_type="A",
            matched_risks=[RiskMatch(risk_id="atlas-fraud", risk_name="Fraud", relevance="supporting", justification="j")],
        ),
    ]
    related_risks = {
        "atlas-fraud": [
            {"id": "owasp-fraud", "mapping_type": "close"},
            {"id": "nist-fraud", "mapping_type": "related"},
        ],
    }
    domain_context = []
    taxonomy, _ = structure("test", classifications, risk_mappings, domain_context,
                            related_risks=related_risks)
    fraud_entries = [e for e in taxonomy["entries"] if "fraud" in e["id"]]
    assert len(fraud_entries) == 1
    entry = fraud_entries[0]
    assert "owasp-fraud" in entry.get("close_mappings", [])
    assert "nist-fraud" in entry.get("related_mappings", [])


def test_structure_emits_cross_mapping_filtered():
    """When cross-mapping target is not in valid_risk_ids, emit cross_mapping_filtered."""
    classifications, risk_mappings, related_risks, domain_context = _make_state_data()
    report = RunReport(model="m", policy_set="p", timestamp="t")
    # Empty valid set — all cross-mappings should be filtered
    taxonomy, _ = structure("swb", classifications, risk_mappings, domain_context,
                            related_risks=related_risks, valid_risk_ids=set(), report=report)
    filtered = [e for e in report.events if e["event"] == "cross_mapping_filtered"]
    assert len(filtered) >= 1
    assert filtered[0]["target_id"] == "owasp-fraud"


def test_structure_no_report_works():
    """structure works without report param (backward compat)."""
    classifications, risk_mappings, related_risks, domain_context = _make_state_data()
    taxonomy, profiles = structure("swb", classifications, risk_mappings, domain_context,
                                    related_risks=related_risks)
    assert len(taxonomy["entries"]) > 0
