"""Tests for ingest report data builder and confidence signals."""

import json

from refiner.ingest_report import build_report_data
from refiner.models import (
    BoundaryExample,
    GovernedSystem,
    Policy,
    PolicyDecomposition,
    PolicyDocument,
    RegulatoryReference,
    RunReport,
    Stakeholder,
)


def _make_meta(**overrides):
    base = {
        "model": "test-model",
        "source_document": "test.md",
        "timestamp": "2026-01-01T00:00:00Z",
        "input_format": "markdown",
        "passes_completed": ["context", "policies", "enrichment"],
    }
    base.update(overrides)
    return base


def _make_report(**overrides):
    base = {"model": "test-model", "policy_set": "test", "timestamp": "2026-01-01T00:00:00Z"}
    base.update(overrides)
    return RunReport(**base)


def _full_doc():
    """PolicyDocument with all fields populated — expect all green."""
    return PolicyDocument(
        organization=Stakeholder(name="Acme Corp"),
        domain="finance",
        purpose=["chatbot"],
        governed_systems=[GovernedSystem(name="ChatGPT")],
        stakeholders=[
            Stakeholder(name="staff", roles=["airo:AIUser"]),
            Stakeholder(name="customers", roles=["airo:AISubject"]),
            Stakeholder(name="DPO", roles=["data protection"]),
        ],
        regulations=[
            RegulatoryReference(name="GDPR", jurisdiction="EU", reference="https://gdpr.eu")
        ],
        policies=[
            Policy(
                policy_concept="Data Privacy",
                concept_definition="No PII disclosure",
                boundary_examples=[
                    BoundaryExample(prohibited="Share SSN", acceptable="Confirm last 4")
                ],
                acceptable_uses=["General info"],
                risk_controls=["PII filter"],
                human_involvement="Required",
                decomposition=PolicyDecomposition(
                    agent="staff", activity="disclose", entity="PII"
                ),
            )
        ],
    )


def test_context_confidence_all_green():
    doc = _full_doc()
    data = build_report_data(doc, _make_report(), _make_meta())
    ctx = data["confidence"]["context"]
    assert ctx["organization"] == "green"
    assert ctx["domain"] == "green"
    assert ctx["purpose"] == "green"
    assert ctx["governed_systems"] == "green"
    assert ctx["stakeholders"] == "green"
    assert ctx["regulations"] == "green"


def test_context_confidence_missing_fields():
    doc = PolicyDocument()
    data = build_report_data(doc, _make_report(), _make_meta())
    ctx = data["confidence"]["context"]
    assert ctx["organization"] == "red"
    assert ctx["domain"] == "red"
    assert ctx["purpose"] == "red"
    assert ctx["governed_systems"] == "red"
    assert ctx["stakeholders"] == "red"
    assert ctx["regulations"] == "red"


def test_context_confidence_regulations_amber():
    """Regulations present but missing jurisdiction/reference → amber."""
    doc = PolicyDocument(
        organization=Stakeholder(name="Acme"),
        domain="finance",
        purpose=["chatbot"],
        governed_systems=[GovernedSystem(name="ChatGPT")],
        stakeholders=[Stakeholder(name="staff", roles=["airo:AIUser"])],
        regulations=[RegulatoryReference(name="GDPR")],
    )
    data = build_report_data(doc, _make_report(), _make_meta())
    assert data["confidence"]["context"]["regulations"] == "amber"


def test_context_confidence_stakeholders_amber():
    """Stakeholders present but none with governance roles → amber."""
    doc = PolicyDocument(
        organization=Stakeholder(name="Acme"),
        domain="finance",
        purpose=["chatbot"],
        governed_systems=[GovernedSystem(name="ChatGPT")],
        stakeholders=[
            Stakeholder(name="staff", roles=["airo:AIUser"]),
            Stakeholder(name="patients", roles=["airo:AISubject"]),
        ],
        regulations=[
            RegulatoryReference(name="GDPR", jurisdiction="EU", reference="https://gdpr.eu")
        ],
    )
    data = build_report_data(doc, _make_report(), _make_meta())
    assert data["confidence"]["context"]["stakeholders"] == "amber"


def test_policy_confidence_all_green():
    doc = _full_doc()
    data = build_report_data(doc, _make_report(), _make_meta())
    pc = data["confidence"]["policies"][0]
    assert pc["policy_concept"] == "Data Privacy"
    assert pc["boundary_examples"] == "green"
    assert pc["acceptable_uses"] == "green"
    assert pc["risk_controls"] == "green"
    assert pc["human_involvement"] == "green"
    assert pc["decomposition"] == "green"


def test_policy_confidence_minimal():
    """Policy with only concept + definition — everything red/amber."""
    doc = PolicyDocument(
        policies=[
            Policy(policy_concept="Fraud", concept_definition="About fraud")
        ]
    )
    data = build_report_data(doc, _make_report(), _make_meta())
    pc = data["confidence"]["policies"][0]
    assert pc["boundary_examples"] == "red"
    assert pc["acceptable_uses"] == "amber"
    assert pc["risk_controls"] == "amber"
    assert pc["human_involvement"] == "amber"
    assert pc["decomposition"] == "red"


def test_policy_confidence_partial_decomposition():
    """Decomposition with only 1 of 3 fields → amber."""
    doc = PolicyDocument(
        policies=[
            Policy(
                policy_concept="Test",
                concept_definition="Test",
                decomposition=PolicyDecomposition(agent="clinician"),
            )
        ]
    )
    data = build_report_data(doc, _make_report(), _make_meta())
    assert data["confidence"]["policies"][0]["decomposition"] == "amber"


def test_summary_counts():
    doc = PolicyDocument(
        policies=[
            Policy(
                policy_concept="P1",
                concept_definition="D1",
                boundary_examples=[
                    BoundaryExample(prohibited="x", acceptable="y"),
                    BoundaryExample(prohibited="a", acceptable="b"),
                ],
            ),
            Policy(policy_concept="P2", concept_definition="D2"),
        ]
    )
    data = build_report_data(doc, _make_report(), _make_meta())
    summary = data["confidence"]["summary"]
    assert summary["policies_total"] == 2
    assert summary["policies_enriched"] == 1
    assert summary["boundary_pairs_total"] == 2
    assert summary["policies_with_zero_pairs"] == 1


def test_summary_weak_inferences():
    report = _make_report()
    report.events.append({
        "stage": "ingest",
        "event": "context_weak_inference",
        "missing_fields": ["organization", "domain"],
    })
    doc = PolicyDocument()
    data = build_report_data(doc, report, _make_meta())
    assert data["confidence"]["summary"]["weak_inferences"] == ["organization", "domain"]


def test_meta_passthrough():
    meta = _make_meta(model="gemma-4", source_document="rdash.md")
    doc = PolicyDocument()
    data = build_report_data(doc, _make_report(), meta)
    assert data["meta"]["model"] == "gemma-4"
    assert data["meta"]["source_document"] == "rdash.md"


def test_document_included():
    doc = _full_doc()
    data = build_report_data(doc, _make_report(), _make_meta())
    assert data["document"]["domain"] == "finance"
    assert len(data["document"]["policies"]) == 1


from refiner.ingest_report import group_stakeholders


def test_group_stakeholders_full():
    """Stakeholders are grouped by Lewis et al. categories."""
    doc = PolicyDocument(
        organization=Stakeholder(name="RDaSH"),
        stakeholders=[
            Stakeholder(name="staff", roles=["airo:AIUser"]),
            Stakeholder(name="volunteers", roles=["airo:AIUser"]),
            Stakeholder(name="patients", roles=["airo:AISubject"]),
            Stakeholder(name="DPO", roles=["data protection"]),
            Stakeholder(name="Caldicott Guardian", roles=["patient info oversight"]),
        ],
    )
    groups = group_stakeholders(doc)
    assert groups["organisation"] == {"name": "RDaSH"}
    assert len(groups["users"]) == 2
    assert groups["users"][0]["name"] == "staff"
    assert len(groups["subjects"]) == 1
    assert groups["subjects"][0]["name"] == "patients"
    assert len(groups["governance"]) == 2
    assert groups["governance"][0]["name"] == "DPO"


def test_group_stakeholders_empty():
    doc = PolicyDocument()
    groups = group_stakeholders(doc)
    assert groups["organisation"] is None
    assert groups["users"] == []
    assert groups["subjects"] == []
    assert groups["governance"] == []


def test_group_stakeholders_mixed_roles():
    """Stakeholder with both airo:AIUser and governance role goes to governance."""
    doc = PolicyDocument(
        stakeholders=[
            Stakeholder(name="Admin", roles=["airo:AIUser", "system admin"]),
        ],
    )
    groups = group_stakeholders(doc)
    assert len(groups["governance"]) == 1
    assert groups["users"] == []


def test_report_data_includes_stakeholder_groups():
    doc = _full_doc()
    data = build_report_data(doc, _make_report(), _make_meta())
    groups = data["stakeholder_groups"]
    assert groups["organisation"]["name"] == "Acme Corp"
    assert len(groups["users"]) == 1
    assert len(groups["subjects"]) == 1
    assert len(groups["governance"]) == 1
