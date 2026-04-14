"""Tests for configure.py — Stage 2: config generation."""
import json
from pathlib import Path

import pytest
import yaml


def _make_analysis():
    """Minimal analysis dict for testing config generation."""
    return {
        "client": "test",
        "domain": "finance",
        "source": {"source_type": "scenario"},
        "risks": [
            {
                "risk_id": "atlas-jailbreaking",
                "risk_name": "Jailbreaking",
                "policy_concept": "Security",
                "alternative_framings": [],
                "attack_dimensions": [],
                "coverage": {
                    "probes": [
                        {"probe_id": "dan.DanInTheWild", "platform": "garak",
                         "mapping_source": "garak_tags", "description": "DAN jailbreak", "garak_tier": "OF_CONCERN"},
                        {"probe_id": "tap.TAPCached", "platform": "garak",
                         "mapping_source": "garak_tags", "description": "TAP attack", "garak_tier": "COMPETE_WITH_SOTA"},
                    ],
                    "guardrails": [
                        {"guardrail_id": "nemo-jailbreak-heuristics", "detector_name": "jailbreak_detection_heuristics",
                         "platform": "nemo", "mapping_source": "platform_docs", "description": "Heuristic jailbreak"},
                        {"guardrail_id": "nemo-self-check-input", "detector_name": "self_check_input",
                         "platform": "nemo", "mapping_source": "platform_docs", "description": "LLM input check"},
                    ],
                    "benchmarks": [],
                    "gaps": {"has_probes": True, "has_guardrails": True,
                             "has_benchmarks": False, "uncovered_dimensions": []},
                },
            },
            {
                "risk_id": "atlas-exposing-personal-information",
                "risk_name": "PII Exposure",
                "policy_concept": "Data Privacy",
                "alternative_framings": [],
                "attack_dimensions": [],
                "coverage": {
                    "probes": [
                        {"probe_id": "leakreplay.GuardianCloze", "platform": "garak",
                         "mapping_source": "garak_tags", "description": "PII cloze", "garak_tier": "COMPETE_WITH_SOTA"},
                    ],
                    "guardrails": [
                        {"guardrail_id": "nemo-sensitive-data", "detector_name": "sensitive_data_detection",
                         "platform": "nemo", "mapping_source": "platform_docs", "description": "Presidio PII"},
                    ],
                    "benchmarks": [],
                    "gaps": {"has_probes": True, "has_guardrails": True,
                             "has_benchmarks": False, "uncovered_dimensions": []},
                },
            },
            {
                "risk_id": "atlas-novel-uncovered",
                "risk_name": "Novel Risk",
                "policy_concept": "Custom",
                "alternative_framings": [],
                "attack_dimensions": [{"cco_class": "Org", "role": "target", "term_count": 3, "terms": []}],
                "coverage": {
                    "probes": [],
                    "guardrails": [],
                    "benchmarks": [],
                    "gaps": {"has_probes": False, "has_guardrails": False,
                             "has_benchmarks": False, "uncovered_dimensions": ["Org"]},
                },
            },
        ],
        "summary": {
            "total_risks": 3, "amplified_risks": 0,
            "risks_with_probes": 2, "risks_with_guardrails": 2, "risks_with_benchmarks": 0,
            "fully_covered": 2, "partial_gaps": 0, "no_coverage": 1,
        },
    }


class TestGarakConfig:
    def test_generates_valid_yaml(self, tmp_path):
        from configure import generate_garak_config

        analysis = _make_analysis()
        generate_garak_config(analysis, tmp_path)
        config_path = tmp_path / "garak.yaml"
        assert config_path.exists()
        config = yaml.safe_load(config_path.read_text())
        assert "plugins" in config

    def test_includes_probes_from_analysis(self, tmp_path):
        from configure import generate_garak_config

        analysis = _make_analysis()
        generate_garak_config(analysis, tmp_path)
        content = (tmp_path / "garak.yaml").read_text()
        assert "dan.DanInTheWild" in content
        assert "leakreplay.GuardianCloze" in content

    def test_uncovered_risks_noted_in_comments(self, tmp_path):
        from configure import generate_garak_config

        analysis = _make_analysis()
        generate_garak_config(analysis, tmp_path)
        content = (tmp_path / "garak.yaml").read_text()
        assert "Novel Risk" in content  # should appear as a comment


class TestNemoConfig:
    def test_generates_config_yml(self, tmp_path):
        from configure import generate_nemo_config

        analysis = _make_analysis()
        generate_nemo_config(analysis, tmp_path)
        config_path = tmp_path / "nemo" / "config.yml"
        assert config_path.exists()

    def test_generates_rails_co(self, tmp_path):
        from configure import generate_nemo_config

        analysis = _make_analysis()
        generate_nemo_config(analysis, tmp_path)
        rails_path = tmp_path / "nemo" / "rails.co"
        assert rails_path.exists()

    def test_config_includes_system_prompt_with_domain(self, tmp_path):
        from configure import generate_nemo_config

        analysis = _make_analysis()
        generate_nemo_config(analysis, tmp_path)
        content = (tmp_path / "nemo" / "config.yml").read_text()
        assert "finance" in content.lower()

    def test_rails_include_jailbreak_flow(self, tmp_path):
        from configure import generate_nemo_config

        analysis = _make_analysis()
        generate_nemo_config(analysis, tmp_path)
        content = (tmp_path / "nemo" / "rails.co").read_text()
        assert "jailbreak" in content.lower()

    def test_rails_include_pii_flow(self, tmp_path):
        from configure import generate_nemo_config

        analysis = _make_analysis()
        generate_nemo_config(analysis, tmp_path)
        content = (tmp_path / "nemo" / "rails.co").read_text()
        assert "sensitive_data" in content.lower() or "pii" in content.lower()
