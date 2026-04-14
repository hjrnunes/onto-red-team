"""Tests for report.py — Stage 3: advisory report generation."""
from pathlib import Path

import pytest


def _make_analysis():
    """Same analysis fixture as test_configure.py."""
    return {
        "client": "test",
        "domain": "finance",
        "source": {"source_type": "scenario", "scenario": "healthcare_chat.json"},
        "risks": [
            {
                "risk_id": "atlas-jailbreaking",
                "risk_name": "Jailbreaking",
                "policy_concept": "Security",
                "alternative_framings": [
                    {"risk_id": "atlas-prompt-injection", "taxonomy": "ibm-risk-atlas", "mapping_type": "related"}
                ],
                "attack_dimensions": [
                    {"cco_class": "Person", "role": "attacker", "term_count": 5, "terms": []}
                ],
                "coverage": {
                    "probes": [
                        {"probe_id": "dan.DanInTheWild", "platform": "garak",
                         "mapping_source": "garak_tags", "description": "", "garak_tier": "OF_CONCERN"},
                    ],
                    "guardrails": [
                        {"guardrail_id": "nemo-jailbreak-heuristics", "detector_name": "jailbreak_detection_heuristics",
                         "platform": "nemo", "mapping_source": "platform_docs", "description": ""},
                    ],
                    "benchmarks": [],
                    "gaps": {"has_probes": True, "has_guardrails": True,
                             "has_benchmarks": False, "uncovered_dimensions": ["Person"]},
                },
            },
            {
                "risk_id": "atlas-novel",
                "risk_name": "Novel Risk",
                "policy_concept": "Custom",
                "alternative_framings": [],
                "attack_dimensions": [
                    {"cco_class": "Organization", "role": "target", "term_count": 3, "terms": []}
                ],
                "coverage": {
                    "probes": [],
                    "guardrails": [],
                    "benchmarks": [],
                    "gaps": {"has_probes": False, "has_guardrails": False,
                             "has_benchmarks": False, "uncovered_dimensions": ["Organization"]},
                },
            },
        ],
        "summary": {
            "total_risks": 2, "amplified_risks": 1,
            "risks_with_probes": 1, "risks_with_guardrails": 1, "risks_with_benchmarks": 0,
            "fully_covered": 1, "partial_gaps": 0, "no_coverage": 1,
        },
    }


class TestReport:
    def test_generates_markdown(self, tmp_path):
        from report import generate_report

        analysis = _make_analysis()
        generate_report(analysis, tmp_path)
        report_path = tmp_path / "advisory-report.md"
        assert report_path.exists()

    def test_report_includes_header(self, tmp_path):
        from report import generate_report

        analysis = _make_analysis()
        generate_report(analysis, tmp_path)
        content = (tmp_path / "advisory-report.md").read_text()
        assert "test" in content.lower() or "Advisory Report" in content

    def test_report_includes_coverage_matrix(self, tmp_path):
        from report import generate_report

        analysis = _make_analysis()
        generate_report(analysis, tmp_path)
        content = (tmp_path / "advisory-report.md").read_text()
        assert "Jailbreaking" in content
        assert "Novel Risk" in content

    def test_report_includes_gap_analysis(self, tmp_path):
        from report import generate_report

        analysis = _make_analysis()
        generate_report(analysis, tmp_path)
        content = (tmp_path / "advisory-report.md").read_text()
        assert "Gap" in content or "gap" in content
        assert "Novel Risk" in content

    def test_report_includes_summary_numbers(self, tmp_path):
        from report import generate_report

        analysis = _make_analysis()
        generate_report(analysis, tmp_path)
        content = (tmp_path / "advisory-report.md").read_text()
        assert "2" in content  # total risks
        assert "1" in content  # fully covered
