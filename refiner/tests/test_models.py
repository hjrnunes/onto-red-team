import pytest
from refiner.models import (
    Policy, PolicyClassification, RiskMatch, PolicyRiskMapping,
    VariationAxis, RiskVariationAxes, AxisEnumeration, DomainContextAxis, DomainContextProfile,
)

def test_policy_creation():
    p = Policy(policy_concept="Fraud", concept_definition="Prompts about fraud")
    assert p.policy_concept == "Fraud"

def test_policy_classification_valid_types():
    for t in ("A", "B", "C", "D"):
        pc = PolicyClassification(policy_concept="X", concept_definition="Y", policy_type=t, justification="reason")
        assert pc.policy_type == t

def test_policy_classification_invalid_type():
    with pytest.raises(Exception):
        PolicyClassification(policy_concept="X", concept_definition="Y", policy_type="Z", justification="reason")

def test_risk_match_valid_relevance():
    for r in ("primary", "supporting", "tangential"):
        rm = RiskMatch(risk_id="r1", risk_name="Risk", relevance=r, justification="j")
        assert rm.relevance == r

def test_policy_risk_mapping():
    prm = PolicyRiskMapping(policy_concept="Fraud", policy_type="A", matched_risks=[])
    assert prm.matched_risks == []

def test_variation_axis():
    va = VariationAxis(cco_class_uri="http://example.org/Person", cco_class_label="Person", role="agent", rationale="Actors who commit fraud")
    assert va.role == "agent"

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
        axes=[DomainContextAxis(cco_class_uri="http://example.org/Person", cco_class_label="Person", role="agent", enumerations=[])],
    )
    assert len(dcp.axes) == 1


def test_sampled_axis_creation():
    from refiner.models import SampledAxis
    sa = SampledAxis(
        cco_class_uri="http://example.org/Person",
        cco_class_label="Person",
        role="agent",
        sampled_uri="http://example.org/Manager",
        sampled_label="Manager",
        source_ontology="FIBO",
        relevance="high",
    )
    assert sa.sampled_label == "Manager"
    assert sa.role == "agent"


def test_sampled_axis_rejects_invalid_relevance():
    from refiner.models import SampledAxis
    import pytest
    with pytest.raises(Exception):
        SampledAxis(
            cco_class_uri="http://example.org/Person",
            cco_class_label="Person",
            role="agent",
            sampled_uri="http://example.org/Manager",
            sampled_label="Manager",
            source_ontology="FIBO",
            relevance="critical",
        )
