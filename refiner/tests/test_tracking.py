"""Tests for the tracking module."""

import subprocess
from unittest.mock import patch

from refiner.tracking import _flatten_metrics, _get_git_context


def test_get_git_context_returns_sha_and_dirty():
    sha, dirty = _get_git_context()
    # We're in a git repo, so sha should be a 40-char hex string
    assert len(sha) == 40
    assert all(c in "0123456789abcdef" for c in sha)
    assert isinstance(dirty, bool)


def test_get_git_context_fallback_on_error():
    with patch("subprocess.check_output", side_effect=FileNotFoundError):
        sha, dirty = _get_git_context()
    assert sha == "unknown"
    assert dirty is False


def test_flatten_metrics_full_evaluation():
    evaluation = {
        "coverage": {
            "risk_framework": {"total_matched": 12},
            "single_value_axis_dominance": {"single_value_rate": 0.45},
            "enumeration_domain_mismatch": {"mismatch_rate": 0.05},
            "sibling_relevance": {"sibling_mean_score": 2.1, "subclass_mean_score": 2.8},
            "cross_mapping": {"risks_with_cross_mappings": 8, "risks_without": 2},
        },
        "generation_metrics": {
            "axis_diversity": {"overall_mean": 0.75},
            "enumeration_concentration": {"top_k_share": 0.35},
        },
        "prompt_metrics": {
            "lexical_diversity": 0.62,
            "mean_prompt_length": 45.3,
            "domain_term_hit_rate": 0.48,
            "red_flag_count": 2,
            "policy_coverage_balance": {"normalized_entropy": 0.85},
            "jargon_leak_rate": {"jargon_rate": 0.12},
            "axis_fidelity": {"mean_fidelity": 0.7},
            "named_entity_utilization": {"utilization_rate": 0.55},
            "semantic_diversity": {"mean_pairwise_distance": 0.68},
        },
        "judge_evaluation": {
            "aggregates": {
                "subtlety": {"mean": 3.5},
                "plausibility": {"mean": 4.0},
                "domain_grounding": {"mean": 3.2},
                "policy_relevance": {"mean": 3.8},
            },
        },
    }
    metrics = _flatten_metrics(evaluation)
    assert metrics["coverage.total_risks_matched"] == 12
    assert metrics["coverage.single_value_axis_rate"] == 0.45
    assert metrics["coverage.enum_domain_mismatch_rate"] == 0.05
    assert metrics["coverage.sibling_mean_score"] == 2.1
    assert metrics["coverage.subclass_mean_score"] == 2.8
    assert metrics["coverage.cross_mapping_utilization"] == 0.8  # 8 / (8+2)
    assert metrics["generation.axis_diversity"] == 0.75
    assert metrics["generation.enum_concentration_top5"] == 0.35
    assert metrics["prompt.lexical_diversity"] == 0.62
    assert metrics["prompt.mean_length"] == 45.3
    assert metrics["prompt.domain_term_hit_rate"] == 0.48
    assert metrics["prompt.red_flag_count"] == 2
    assert metrics["prompt.coverage_balance"] == 0.85
    assert metrics["prompt.jargon_leak_rate"] == 0.12
    assert metrics["prompt.axis_fidelity"] == 0.7
    assert metrics["prompt.entity_utilization"] == 0.55
    assert metrics["prompt.semantic_diversity"] == 0.68
    assert metrics["judge.subtlety"] == 3.5
    assert metrics["judge.plausibility"] == 4.0
    assert metrics["judge.domain_grounding"] == 3.2
    assert metrics["judge.policy_relevance"] == 3.8


def test_flatten_metrics_minimal_evaluation():
    """Only run info, no coverage/generation/prompt/judge sections."""
    evaluation = {"run": {"model": "test"}}
    metrics = _flatten_metrics(evaluation)
    assert metrics == {}


def test_flatten_metrics_partial_coverage_no_mismatch():
    """coverage present but no enumeration_domain_mismatch (partial run)."""
    evaluation = {
        "coverage": {
            "risk_framework": {"total_matched": 5},
        },
    }
    metrics = _flatten_metrics(evaluation)
    assert metrics["coverage.total_risks_matched"] == 5
    assert "coverage.enum_domain_mismatch_rate" not in metrics


def test_flatten_metrics_cross_mapping_zero_division():
    evaluation = {
        "coverage": {
            "cross_mapping": {"risks_with_cross_mappings": 0, "risks_without": 0},
        },
    }
    metrics = _flatten_metrics(evaluation)
    assert "coverage.cross_mapping_utilization" not in metrics
