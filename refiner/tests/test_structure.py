import pytest
from refiner.models import (
    Policy,
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
    risk_mappings = [
        PolicyRiskMapping(
            policy_concept="Fraud",
            matched_risks=[
                RiskMatch(risk_id="atlas-fraud", risk_name="Fraud", relevance="primary", justification="j"),
            ],
        ),
        PolicyRiskMapping(
            policy_concept="Executive Compensation",
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
    return risk_mappings, related_risks, domain_context


def test_structure_taxonomy_has_correct_id():
    risk_mappings, related_risks, domain_context = _make_state_data()
    taxonomy, profiles = structure("swb", risk_mappings, domain_context,
                                   related_risks=related_risks)
    assert taxonomy["taxonomies"][0]["id"] == "client-swb"
    assert taxonomy["taxonomies"][0]["type"] == "RiskTaxonomy"


def test_structure_creates_groups_per_policy_concept():
    risk_mappings, related_risks, domain_context = _make_state_data()
    taxonomy, _ = structure("swb", risk_mappings, domain_context,
                            related_risks=related_risks)
    group_names = {g["name"] for g in taxonomy["groups"]}
    assert "Fraud" in group_names
    assert "Executive Compensation" in group_names


def test_structure_entries_have_correct_isPartOf():
    risk_mappings, related_risks, domain_context = _make_state_data()
    taxonomy, _ = structure("swb", risk_mappings, domain_context,
                            related_risks=related_risks)
    entries = taxonomy["entries"]
    fraud_entry = next(e for e in entries if "fraud" in e["id"])
    assert fraud_entry["isPartOf"] == "client-swb-fraud"
    disclosure_entry = next(e for e in entries if "data-disclosure" in e["id"])
    assert disclosure_entry["isPartOf"] == "client-swb-executive-compensation"


def test_structure_entries_have_cross_mappings():
    risk_mappings, related_risks, domain_context = _make_state_data()
    taxonomy, _ = structure("swb", risk_mappings, domain_context,
                            related_risks=related_risks)
    fraud_entry = next(e for e in taxonomy["entries"] if "fraud" in e["id"])
    assert "owasp-fraud" in fraud_entry.get("close_mappings", [])


def test_structure_filters_invalid_cross_mapping_targets():
    risk_mappings, related_risks, domain_context = _make_state_data()
    # Only "owasp-fraud" is in the valid set; any other target would be filtered
    taxonomy, _ = structure("swb", risk_mappings, domain_context,
                            related_risks=related_risks,
                            valid_risk_ids={"owasp-fraud"})
    fraud_entry = next(e for e in taxonomy["entries"] if "fraud" in e["id"])
    assert "owasp-fraud" in fraud_entry.get("close_mappings", [])


def test_structure_warns_on_unknown_cross_mapping_targets():
    risk_mappings, related_risks, domain_context = _make_state_data()
    # Empty valid set means all cross-mappings are filtered
    taxonomy, _ = structure("swb", risk_mappings, domain_context,
                            related_risks=related_risks,
                            valid_risk_ids=set())
    fraud_entry = next(e for e in taxonomy["entries"] if "fraud" in e["id"])
    assert "close_mappings" not in fraud_entry


def test_structure_no_cross_mappings_when_related_risks_none():
    """When related_risks is None, no cross-mappings are added."""
    risk_mappings, _, domain_context = _make_state_data()
    taxonomy, _ = structure("swb", risk_mappings, domain_context,
                            related_risks=None)
    fraud_entry = next(e for e in taxonomy["entries"] if "fraud" in e["id"])
    assert "close_mappings" not in fraud_entry


def test_structure_profiles_output():
    risk_mappings, related_risks, domain_context = _make_state_data()
    _, profiles = structure("swb", risk_mappings, domain_context,
                            related_risks=related_risks)
    assert len(profiles["profiles"]) == 1
    assert profiles["profiles"][0]["risk_id"] == "atlas-fraud"


def test_structure_deduplicates_entries_by_id():
    """Same risk matched from two policies should produce one entry with merged mappings."""
    risk_mappings = [
        PolicyRiskMapping(
            policy_concept="Fraud",
            matched_risks=[RiskMatch(risk_id="atlas-fraud", risk_name="Fraud", relevance="primary", justification="j")],
        ),
        PolicyRiskMapping(
            policy_concept="AML",
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
    taxonomy, _ = structure("test", risk_mappings, domain_context,
                            related_risks=related_risks)
    fraud_entries = [e for e in taxonomy["entries"] if "fraud" in e["id"]]
    assert len(fraud_entries) == 1
    entry = fraud_entries[0]
    assert "owasp-fraud" in entry.get("close_mappings", [])
    assert "nist-fraud" in entry.get("related_mappings", [])


def test_structure_emits_cross_mapping_filtered():
    """When cross-mapping target is not in valid_risk_ids, emit cross_mapping_filtered."""
    risk_mappings, related_risks, domain_context = _make_state_data()
    report = RunReport(model="m", policy_set="p", timestamp="t")
    # Empty valid set — all cross-mappings should be filtered
    taxonomy, _ = structure("swb", risk_mappings, domain_context,
                            related_risks=related_risks, valid_risk_ids=set(), report=report)
    filtered = [e for e in report.events if e["event"] == "cross_mapping_filtered"]
    assert len(filtered) >= 1
    assert filtered[0]["target_id"] == "owasp-fraud"


def test_structure_no_report_works():
    """structure works without report param (backward compat)."""
    risk_mappings, related_risks, domain_context = _make_state_data()
    taxonomy, profiles = structure("swb", risk_mappings, domain_context,
                                    related_risks=related_risks)
    assert len(taxonomy["entries"]) > 0


def test_structure_includes_domain_context_summary():
    """Taxonomy entries include domain_context_summary from matching profiles."""
    risk_mappings, related_risks, domain_context = _make_state_data()
    taxonomy, _ = structure("swb", risk_mappings, domain_context,
                            related_risks=related_risks)
    fraud_entry = next(e for e in taxonomy["entries"] if "fraud" in e["id"])
    assert "domain_context_summary" in fraud_entry
    summary = fraud_entry["domain_context_summary"]
    assert summary["axis_count"] == 1
    assert summary["enumeration_count"] == 1
    assert "CCO" in summary["source_ontologies"]
    assert len(summary["axes"]) == 1
    assert summary["axes"][0]["class"] == "Person"


def test_structure_no_summary_when_no_matching_profile():
    """Entries without matching domain context profiles have no summary."""
    risk_mappings, related_risks, domain_context = _make_state_data()
    taxonomy, _ = structure("swb", risk_mappings, domain_context,
                            related_risks=related_risks)
    disclosure_entry = next(e for e in taxonomy["entries"] if "data-disclosure" in e["id"])
    # No domain context profile for atlas-data-disclosure in _make_state_data
    assert "domain_context_summary" not in disclosure_entry


def test_structure_summary_with_multiple_axes():
    """Summary correctly aggregates across multiple axes."""
    risk_mappings = [
        PolicyRiskMapping(
            policy_concept="Fraud",
            matched_risks=[RiskMatch(risk_id="atlas-fraud", risk_name="Fraud", relevance="primary", justification="j")],
        ),
    ]
    domain_context = [
        DomainContextProfile(
            risk_id="atlas-fraud", risk_name="Fraud", policy_concept="Fraud",
            axes=[
                DomainContextAxis(
                    cco_class_uri="http://example.org/Person", cco_class_label="Person", roles=["agent"],
                    enumerations=[
                        AxisEnumeration(class_uri="http://example.org/E1", class_label="E1", source_ontology="CCO", relevance="high"),
                        AxisEnumeration(class_uri="http://example.org/E2", class_label="E2", source_ontology="CCO", relevance="medium"),
                    ],
                ),
                DomainContextAxis(
                    cco_class_uri="http://example.org/Instrument", cco_class_label="Instrument", roles=["instrument"],
                    enumerations=[
                        AxisEnumeration(class_uri="http://example.org/E3", class_label="E3", source_ontology="FIBO", relevance="high"),
                    ],
                ),
            ],
        ),
    ]
    taxonomy, _ = structure("swb", risk_mappings, domain_context)
    fraud_entry = next(e for e in taxonomy["entries"] if "fraud" in e["id"])
    summary = fraud_entry["domain_context_summary"]
    assert summary["axis_count"] == 2
    assert summary["enumeration_count"] == 3
    assert sorted(summary["source_ontologies"]) == ["CCO", "FIBO"]
