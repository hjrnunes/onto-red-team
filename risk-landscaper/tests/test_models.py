from risk_landscaper.models import (
    Policy, PolicyProfile, PolicyDecomposition, BoundaryExample,
    Stakeholder, AiSystem, RiskMatch, PolicyRiskMapping,
    RiskDetail, RiskLandscape, CoverageGap, RunReport,
)


def test_policy_profile_round_trip():
    profile = PolicyProfile(
        organization=Stakeholder(name="Acme Corp"),
        domain="finance",
        policies=[Policy(policy_concept="Fraud", concept_definition="Do not assist with fraud")],
    )
    data = profile.model_dump()
    restored = PolicyProfile(**data)
    assert restored.organization.name == "Acme Corp"
    assert len(restored.policies) == 1


def test_policy_profile_coerce_organization_string():
    profile = PolicyProfile(organization="Acme Corp")
    assert profile.organization.name == "Acme Corp"


def test_policy_profile_migrate_governed_systems():
    data = {"governed_systems": [{"name": "ChatBot"}], "policies": []}
    profile = PolicyProfile(**data)
    assert len(profile.ai_systems) == 1
    assert profile.ai_systems[0].name == "ChatBot"


def test_risk_landscape_serialization():
    landscape = RiskLandscape(
        model="test-model",
        risks=[RiskDetail(risk_id="atlas-1", risk_name="Test Risk", risk_framework="IBM Risk Atlas")],
        policy_mappings=[PolicyRiskMapping(
            policy_concept="Fraud",
            matched_risks=[RiskMatch(risk_id="atlas-1", risk_name="Test Risk", relevance="primary", justification="Direct match")],
        )],
    )
    data = landscape.model_dump()
    assert data["risks"][0]["risk_id"] == "atlas-1"
    restored = RiskLandscape(**data)
    assert len(restored.risks) == 1


def test_coverage_gap_creation():
    gap = CoverageGap(
        policy_concept="Novel Risk", concept_definition="Something new",
        gap_type="novel", confidence=0.85,
        nearest_risks=[{"id": "atlas-1", "name": "Similar", "distance": 0.7}],
        reasoning="No existing risk covers this",
    )
    assert gap.gap_type == "novel"
    assert gap.confidence == 0.85


def test_run_report_to_dict():
    report = RunReport(model="test", policy_set="test.json", timestamp="2026-01-01")
    report.stages_completed.append("ingest")
    d = report.to_dict()
    assert d["stages_completed"] == ["ingest"]
