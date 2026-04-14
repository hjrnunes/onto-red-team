"""Tests for the tracking module."""

import subprocess
from unittest.mock import MagicMock, patch

from refiner.tracking import (
    _collect_artifacts,
    _flatten_metrics,
    _get_git_context,
    read_run_id,
    write_run_id,
)


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


def test_collect_artifacts_whitelists(tmp_path):
    # Create whitelisted files
    (tmp_path / "swb-taxonomy.yaml").write_text("x")
    (tmp_path / "swb-evaluation.json").write_text("x")
    (tmp_path / "swb-evaluation.html").write_text("x")
    (tmp_path / "swb-dataset.jsonl").write_text("x")
    (tmp_path / "swb-adversarial-prompts.jsonl").write_text("x")
    (tmp_path / "swb-run-report.yaml").write_text("x")
    (tmp_path / "swb-policy-document.json").write_text("x")
    (tmp_path / "swb-curie-map.json").write_text("x")
    (tmp_path / "swb-provenance.jsonl").write_text("x")
    (tmp_path / "swb-risk-landscape.yaml").write_text("x")
    (tmp_path / "assessment.md").write_text("x")
    # Create files that should be excluded
    (tmp_path / ".mlflow-run-id").write_text("abc123")
    (tmp_path / "random-file.txt").write_text("x")

    files, dirs = _collect_artifacts(tmp_path)
    names = {f.name for f in files}
    assert "swb-taxonomy.yaml" in names
    assert "swb-evaluation.json" in names
    assert "swb-evaluation.html" in names
    assert "swb-dataset.jsonl" in names
    assert "swb-adversarial-prompts.jsonl" in names
    assert "swb-run-report.yaml" in names
    assert "swb-policy-document.json" in names
    assert "swb-curie-map.json" in names
    assert "swb-provenance.jsonl" in names
    assert "swb-risk-landscape.yaml" in names
    assert "assessment.md" in names
    assert ".mlflow-run-id" not in names
    assert "random-file.txt" not in names
    assert dirs == []


def test_collect_artifacts_includes_debug_dir(tmp_path):
    debug_dir = tmp_path / "debug"
    debug_dir.mkdir()
    (debug_dir / "01-classify.json").write_text("x")

    files, dirs = _collect_artifacts(tmp_path)
    assert dirs == [debug_dir]


def test_collect_artifacts_empty_dir(tmp_path):
    files, dirs = _collect_artifacts(tmp_path)
    assert files == []
    assert dirs == []


def test_write_and_read_run_id(tmp_path):
    write_run_id(tmp_path, "abc-123-def")
    assert read_run_id(tmp_path) == "abc-123-def"


def test_read_run_id_missing(tmp_path):
    assert read_run_id(tmp_path) is None


def test_extract_params():
    from refiner.tracking import _extract_params

    evaluation = {
        "run": {"model": "gemma2-9b", "policy_set": "swb.json"},
        "stage_quality": {
            "identify_domains": {"selected_domains": ["FIBO", "CCO"]},
        },
    }
    with patch("refiner.tracking._get_git_context", return_value=("abc123", True)):
        params = _extract_params(evaluation)
    assert params["model"] == "gemma2-9b"
    assert params["policy_set"] == "swb.json"
    assert params["selected_domains"] == "FIBO,CCO"
    assert params["git_sha"] == "abc123"
    assert params["git_dirty"] == "True"


def test_extract_params_no_domains():
    from refiner.tracking import _extract_params

    evaluation = {"run": {"model": "test", "policy_set": "test.json"}}
    with patch("refiner.tracking._get_git_context", return_value=("unknown", False)):
        params = _extract_params(evaluation)
    assert params["selected_domains"] == ""


def test_extract_tags_with_description():
    from refiner.tracking import _extract_tags

    evaluation = {
        "run": {"timestamp": "2026-04-02T10:00:00Z", "stages_completed": ["identify_domains", "map_risks"]},
    }
    tags = _extract_tags(evaluation, description="added sibling fallback")
    assert tags["description"] == "added sibling fallback"
    assert tags["timestamp"] == "2026-04-02T10:00:00Z"
    assert tags["stages_completed"] == "identify_domains,map_risks"


def test_extract_tags_no_description():
    from refiner.tracking import _extract_tags

    evaluation = {"run": {"timestamp": "2026-04-02T10:00:00Z", "stages_completed": []}}
    tags = _extract_tags(evaluation, description=None)
    assert "description" not in tags


def test_log_run_to_mlflow_new_run(tmp_path):
    # Create minimal evaluation file and artifacts
    evaluation = {
        "run": {"model": "test-model", "policy_set": "test.json",
                "timestamp": "2026-04-02T10:00:00Z", "stages_completed": ["identify_domains"]},
        "coverage": {"risk_framework": {"total_matched": 5}},
    }
    (tmp_path / "test-evaluation.json").write_text("{}")
    (tmp_path / "test-taxonomy.yaml").write_text("x")

    mock_mlflow = MagicMock()
    mock_mlflow.active_run.return_value = MagicMock()
    mock_mlflow.active_run.return_value.info.run_id = "run-123"

    with patch.dict("sys.modules", {"mlflow": mock_mlflow}):
        from refiner.tracking import log_run_to_mlflow
        with patch("refiner.tracking._get_git_context", return_value=("sha123", False)):
            run_id = log_run_to_mlflow(evaluation, tmp_path, "http://localhost:5000")

    assert run_id == "run-123"
    mock_mlflow.set_tracking_uri.assert_called_once_with("http://localhost:5000")
    mock_mlflow.set_experiment.assert_called_once_with("test")
    mock_mlflow.log_params.assert_called_once()
    mock_mlflow.set_tags.assert_called_once()
    mock_mlflow.log_metrics.assert_called_once()
    # Should have logged 2 artifacts (evaluation.json + taxonomy.yaml)
    assert mock_mlflow.log_artifact.call_count == 2
    mock_mlflow.end_run.assert_called_once()


def test_log_run_to_mlflow_reopens_existing_run(tmp_path):
    """When .mlflow-run-id exists, reopen that run instead of creating new."""
    import json

    evaluation = {
        "run": {"model": "test", "policy_set": "swb.json",
                "timestamp": "2026-04-02T10:00:00Z", "stages_completed": []},
    }
    write_run_id(tmp_path, "existing-run-456")
    (tmp_path / "swb-evaluation.json").write_text(json.dumps(evaluation))

    mock_mlflow = MagicMock()
    mock_mlflow.active_run.return_value = MagicMock()
    mock_mlflow.active_run.return_value.info.run_id = "existing-run-456"

    with patch.dict("sys.modules", {"mlflow": mock_mlflow}):
        from refiner.tracking import log_run_to_mlflow
        with patch("refiner.tracking._get_git_context", return_value=("sha", False)):
            run_id = log_run_to_mlflow(
                evaluation, tmp_path, "http://localhost:5000",
                run_id="existing-run-456",
            )

    assert run_id == "existing-run-456"
    mock_mlflow.start_run.assert_called_once_with(run_id="existing-run-456")
    # Params should NOT be re-logged when reopening an existing run
    mock_mlflow.log_params.assert_not_called()


def test_full_flow_evaluate_then_track(tmp_path):
    """Simulate: evaluate writes JSON, then track reads it and logs to MLflow."""
    import json

    evaluation = {
        "run": {"model": "gemma2", "policy_set": "generic.json",
                "timestamp": "2026-04-02T12:00:00Z",
                "stages_completed": ["identify_domains", "map_risks"]},
        "coverage": {"risk_framework": {"total_matched": 8}},
        "prompt_metrics": {
            "lexical_diversity": 0.55,
            "mean_prompt_length": 42.0,
            "domain_term_hit_rate": 0.4,
            "red_flag_count": 1,
            "per_policy": [{"policy_concept": "fraud", "count": 5}],
        },
    }
    eval_path = tmp_path / "generic-evaluation.json"
    eval_path.write_text(json.dumps(evaluation))

    mock_mlflow = MagicMock()
    mock_mlflow.active_run.return_value = MagicMock()
    mock_mlflow.active_run.return_value.info.run_id = "new-run-789"

    with patch.dict("sys.modules", {"mlflow": mock_mlflow}):
        from refiner.tracking import log_run_to_mlflow
        with patch("refiner.tracking._get_git_context", return_value=("sha", False)):
            run_id = log_run_to_mlflow(evaluation, tmp_path, "http://localhost:5000")

    assert run_id == "new-run-789"
    mock_mlflow.set_experiment.assert_called_once_with("generic")
    # Verify metrics were logged
    logged_metrics = mock_mlflow.log_metrics.call_args[0][0]
    assert logged_metrics["coverage.total_risks_matched"] == 8
    assert logged_metrics["prompt.lexical_diversity"] == 0.55
    # Verify artifact logged
    mock_mlflow.log_artifact.assert_called_once()
    assert "generic-evaluation.json" in str(mock_mlflow.log_artifact.call_args)
