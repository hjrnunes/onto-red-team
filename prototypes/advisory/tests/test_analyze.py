"""Tests for analyze.py — Stage 1: coverage analysis."""
import json
from pathlib import Path

import pytest
import yaml

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name):
    with open(FIXTURES / name) as f:
        return yaml.safe_load(f)


class TestExtractRisks:
    """Test extraction of risks from refiner taxonomy + domain context."""

    def test_extracts_risk_ids_from_taxonomy(self):
        from analyze import extract_risks

        taxonomy = _load_fixture("mini_taxonomy.yaml")
        domain_ctx = _load_fixture("mini_domain_context.yaml")
        risks = extract_risks(taxonomy, domain_ctx)
        ids = [r["risk_id"] for r in risks]
        assert "client-test-social-engineering" in ids
        assert "client-test-pii-exposure" in ids
        assert "client-test-novel-risk" in ids

    def test_includes_policy_concept_from_group(self):
        from analyze import extract_risks

        taxonomy = _load_fixture("mini_taxonomy.yaml")
        domain_ctx = _load_fixture("mini_domain_context.yaml")
        risks = extract_risks(taxonomy, domain_ctx)
        se = next(r for r in risks if r["risk_id"] == "client-test-social-engineering")
        assert se["policy_concept"] == "Fraud"

    def test_includes_cross_mappings_as_alternative_framings(self):
        from analyze import extract_risks

        taxonomy = _load_fixture("mini_taxonomy.yaml")
        domain_ctx = _load_fixture("mini_domain_context.yaml")
        risks = extract_risks(taxonomy, domain_ctx)
        se = next(r for r in risks if r["risk_id"] == "client-test-social-engineering")
        framing_ids = [f["risk_id"] for f in se["alternative_framings"]]
        assert "atlas-social-engineering" in framing_ids

    def test_includes_attack_dimensions_from_domain_context(self):
        from analyze import extract_risks

        taxonomy = _load_fixture("mini_taxonomy.yaml")
        domain_ctx = _load_fixture("mini_domain_context.yaml")
        risks = extract_risks(taxonomy, domain_ctx)
        se = next(r for r in risks if r["risk_id"] == "client-test-social-engineering")
        assert len(se["attack_dimensions"]) == 2
        labels = [d["cco_class"] for d in se["attack_dimensions"]]
        assert "Person" in labels

    def test_risk_without_cross_mappings_has_empty_framings(self):
        from analyze import extract_risks

        taxonomy = _load_fixture("mini_taxonomy.yaml")
        domain_ctx = _load_fixture("mini_domain_context.yaml")
        risks = extract_risks(taxonomy, domain_ctx)
        novel = next(r for r in risks if r["risk_id"] == "client-test-novel-risk")
        assert novel["alternative_framings"] == []


class TestExtractFromScenario:
    """Test extraction from canned scenario JSON."""

    def test_loads_scenario_risks(self):
        from analyze import extract_risks_from_scenario

        scenario_path = Path(__file__).parent.parent / "scenarios" / "healthcare_chat.json"
        risks = extract_risks_from_scenario(scenario_path)
        assert len(risks) == 5
        ids = [r["risk_id"] for r in risks]
        assert "atlas-harmful-output" in ids

    def test_scenario_risks_have_required_fields(self):
        from analyze import extract_risks_from_scenario

        scenario_path = Path(__file__).parent.parent / "scenarios" / "healthcare_chat.json"
        risks = extract_risks_from_scenario(scenario_path)
        for risk in risks:
            assert "risk_id" in risk
            assert "risk_name" in risk
            assert "policy_concept" in risk
            assert "alternative_framings" in risk
            assert "attack_dimensions" in risk


class TestQueryCoverage:
    """Test AIROO coverage queries."""

    def test_risk_with_airoo_match_has_probes(self):
        from analyze import query_coverage

        # atlas-exposing-personal-information is in AIROO's pii_leakage dimension
        coverage = query_coverage("atlas-exposing-personal-information")
        assert len(coverage["probes"]) > 0

    def test_risk_with_airoo_match_has_guardrails(self):
        from analyze import query_coverage

        coverage = query_coverage("atlas-exposing-personal-information")
        assert len(coverage["guardrails"]) > 0

    def test_unknown_risk_has_empty_coverage(self):
        from analyze import query_coverage

        coverage = query_coverage("nonexistent-risk-id")
        assert coverage["probes"] == []
        assert coverage["guardrails"] == []
        assert coverage["benchmarks"] == []

    def test_coverage_includes_mapping_source(self):
        from analyze import query_coverage

        coverage = query_coverage("atlas-jailbreaking")
        if coverage["probes"]:
            assert "mapping_source" in coverage["probes"][0]


class TestBuildAnalysis:
    """Test full analysis pipeline."""

    def test_analysis_has_summary(self):
        from analyze import build_analysis

        scenario_path = Path(__file__).parent.parent / "scenarios" / "healthcare_chat.json"
        analysis = build_analysis(scenario=scenario_path)
        assert "summary" in analysis
        assert "total_risks" in analysis["summary"]
        assert analysis["summary"]["total_risks"] == 5

    def test_analysis_classifies_coverage_gaps(self):
        from analyze import build_analysis

        scenario_path = Path(__file__).parent.parent / "scenarios" / "healthcare_chat.json"
        analysis = build_analysis(scenario=scenario_path)
        summary = analysis["summary"]
        assert summary["fully_covered"] + summary["partial_gaps"] + summary["no_coverage"] == summary["total_risks"]
