import pytest
from refiner.models import (
    Policy, RiskMatch, PolicyRiskMapping,
    VariationAxis, RiskVariationAxes, AxisEnumeration, DomainContextAxis, DomainContextProfile,
)

def test_policy_creation():
    p = Policy(policy_concept="Fraud", concept_definition="Prompts about fraud")
    assert p.policy_concept == "Fraud"

def test_risk_match_valid_relevance():
    for r in ("primary", "supporting", "tangential"):
        rm = RiskMatch(risk_id="r1", risk_name="Risk", relevance=r, justification="j")
        assert rm.relevance == r

def test_policy_risk_mapping():
    prm = PolicyRiskMapping(policy_concept="Fraud", matched_risks=[])
    assert prm.matched_risks == []

def test_variation_axis():
    va = VariationAxis(cco_class_uri="http://example.org/Person", cco_class_label="Person", roles=["agent"], rationale="Actors who commit fraud")
    assert va.roles == ["agent"]

def test_risk_variation_axes():
    rva = RiskVariationAxes(risk_id="r1", risk_name="Fraud", policy_concept="Fraud", axes=[])
    assert rva.axes == []

def test_axis_enumeration_valid_relevance():
    for r in ("high", "medium", "low"):
        ae = AxisEnumeration(class_uri="http://example.org/C", class_label="Class", source_ontology="CCO", relevance=r)
        assert ae.relevance == r

def test_domain_context_profile():
    dcp = DomainContextProfile(
        risk_id="r1", risk_name="Fraud", policy_concept="Fraud",
        axes=[DomainContextAxis(cco_class_uri="http://example.org/Person", cco_class_label="Person", roles=["agent"], enumerations=[])],
    )
    assert len(dcp.axes) == 1


def test_sampled_axis_creation():
    from refiner.models import SampledAxis
    sa = SampledAxis(
        cco_class_uri="http://example.org/Person",
        cco_class_label="Person",
        roles=["agent"],
        sampled_uri="http://example.org/Manager",
        sampled_label="Manager",
        source_ontology="FIBO",
        relevance="high",
    )
    assert sa.sampled_label == "Manager"
    assert sa.roles == ["agent"]


def test_sampled_axis_rejects_invalid_relevance():
    from refiner.models import SampledAxis
    import pytest
    with pytest.raises(Exception):
        SampledAxis(
            cco_class_uri="http://example.org/Person",
            cco_class_label="Person",
            roles=["agent"],
            sampled_uri="http://example.org/Manager",
            sampled_label="Manager",
            source_ontology="FIBO",
            relevance="critical",
        )


def test_run_report_creation():
    from refiner.models import RunReport
    report = RunReport(model="test-model", policy_set="test.json", timestamp="2026-04-01T00:00:00Z")
    assert report.model == "test-model"
    assert report.stages_completed == []
    assert report.events == []


def test_run_report_append_event():
    from refiner.models import RunReport
    report = RunReport(model="m", policy_set="p", timestamp="t")
    report.events.append({"stage": "identify_domains", "event": "selected_domains", "domains": ["CCO"]})
    assert len(report.events) == 1
    assert report.events[0]["stage"] == "identify_domains"


def test_run_report_to_dict():
    from refiner.models import RunReport
    report = RunReport(model="m", policy_set="p.json", timestamp="t")
    report.stages_completed.append("identify_domains")
    report.events.append({"stage": "identify_domains", "event": "selected_domains", "domains": ["CCO"]})
    d = report.to_dict()
    assert d["model"] == "m"
    assert d["policy_set"] == "p.json"
    assert d["stages_completed"] == ["identify_domains"]
    assert len(d["events"]) == 1
