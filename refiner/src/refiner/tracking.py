"""MLflow tracking integration for the refiner pipeline."""

import subprocess
from pathlib import Path

_ARTIFACT_PATTERNS = [
    "*-taxonomy.yaml",
    "*-domain-context.yaml",
    "*-report.yaml",
    "*-evaluation.json",
    "*-evaluation.html",
    "dataset.jsonl",
    "adversarial_prompts.jsonl",
    "adversarial_prompts.html",
    "assessment.md",
]

_RUN_ID_FILE = ".mlflow-run-id"


def _get_git_context() -> tuple[str, bool]:
    """Get git commit SHA and dirty status.

    Returns:
        Tuple of (commit_sha, is_dirty). Returns ("unknown", False) on error.
    """
    try:
        sha = (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL
            )
            .decode()
            .strip()
        )
        dirty = bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"], stderr=subprocess.DEVNULL
            )
            .decode()
            .strip()
        )
        return sha, dirty
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown", False


def _flatten_metrics(evaluation: dict) -> dict[str, float]:
    """Flatten nested evaluation metrics into MLflow-compatible flat dict.

    Args:
        evaluation: Nested evaluation dict from run_evaluation()

    Returns:
        Flat dict with dot-separated keys (e.g., "coverage.total_risks_matched")
    """
    metrics: dict[str, float] = {}

    # Coverage metrics
    cov = evaluation.get("coverage", {})
    if rf := cov.get("risk_framework"):
        metrics["coverage.total_risks_matched"] = rf["total_matched"]
    if svad := cov.get("single_value_axis_dominance"):
        metrics["coverage.single_value_axis_rate"] = svad["single_value_rate"]
    if edm := cov.get("enumeration_domain_mismatch"):
        metrics["coverage.enum_domain_mismatch_rate"] = edm["mismatch_rate"]
    if sr := cov.get("sibling_relevance"):
        metrics["coverage.sibling_mean_score"] = sr["sibling_mean_score"]
        metrics["coverage.subclass_mean_score"] = sr["subclass_mean_score"]
    if cm := cov.get("cross_mapping"):
        total = cm["risks_with_cross_mappings"] + cm["risks_without"]
        if total > 0:
            metrics["coverage.cross_mapping_utilization"] = round(
                cm["risks_with_cross_mappings"] / total, 3
            )

    # Generation metrics
    gen = evaluation.get("generation_metrics", {})
    if ad := gen.get("axis_diversity"):
        metrics["generation.axis_diversity"] = ad["overall_mean"]
    if ec := gen.get("enumeration_concentration"):
        metrics["generation.enum_concentration_top5"] = ec["top_k_share"]

    # Prompt metrics
    pm = evaluation.get("prompt_metrics", {})
    if "lexical_diversity" in pm:
        metrics["prompt.lexical_diversity"] = pm["lexical_diversity"]
    if "mean_prompt_length" in pm:
        metrics["prompt.mean_length"] = pm["mean_prompt_length"]
    if "domain_term_hit_rate" in pm:
        metrics["prompt.domain_term_hit_rate"] = pm["domain_term_hit_rate"]
    if "red_flag_count" in pm:
        metrics["prompt.red_flag_count"] = pm["red_flag_count"]
    if pcb := pm.get("policy_coverage_balance"):
        metrics["prompt.coverage_balance"] = pcb["normalized_entropy"]
    if jlr := pm.get("jargon_leak_rate"):
        metrics["prompt.jargon_leak_rate"] = jlr["jargon_rate"]
    if af := pm.get("axis_fidelity"):
        metrics["prompt.axis_fidelity"] = af["mean_fidelity"]
    if neu := pm.get("named_entity_utilization"):
        metrics["prompt.entity_utilization"] = neu["utilization_rate"]
    if sd := pm.get("semantic_diversity"):
        metrics["prompt.semantic_diversity"] = sd["mean_pairwise_distance"]

    # Judge evaluation metrics
    if je := evaluation.get("judge_evaluation", {}).get("aggregates"):
        for dim in ("subtlety", "plausibility", "domain_grounding", "policy_relevance"):
            if dim_data := je.get(dim):
                metrics[f"judge.{dim}"] = dim_data["mean"]

    return metrics


def _collect_artifacts(output_dir: Path) -> tuple[list[Path], list[Path]]:
    """Collect whitelisted artifact files and directories for MLflow upload.

    Args:
        output_dir: Pipeline output directory

    Returns:
        Tuple of (files, dirs) where files are individual artifact files
        and dirs are directories to upload recursively (e.g., debug/)
    """
    files = []
    for pattern in _ARTIFACT_PATTERNS:
        files.extend(output_dir.glob(pattern))
    dirs = []
    debug_dir = output_dir / "debug"
    if debug_dir.is_dir():
        dirs.append(debug_dir)
    return files, dirs


def write_run_id(output_dir: Path, run_id: str) -> None:
    """Write MLflow run ID to output directory for linking.

    Args:
        output_dir: Pipeline output directory
        run_id: MLflow run ID
    """
    (output_dir / _RUN_ID_FILE).write_text(run_id)


def read_run_id(output_dir: Path) -> str | None:
    """Read MLflow run ID from output directory if present.

    Args:
        output_dir: Pipeline output directory

    Returns:
        MLflow run ID or None if not found
    """
    path = output_dir / _RUN_ID_FILE
    if path.exists():
        return path.read_text().strip()
    return None


def _extract_params(evaluation: dict) -> dict[str, str]:
    """Extract MLflow parameters from evaluation dict.

    Args:
        evaluation: Evaluation dict from run_evaluation()

    Returns:
        Dict of string parameters (model, policy_set, selected_domains, git_sha, git_dirty)
    """
    run = evaluation.get("run", {})
    git_sha, git_dirty = _get_git_context()
    domains = (
        evaluation.get("stage_quality", {})
        .get("identify_domains", {})
        .get("selected_domains", [])
    )
    return {
        "model": run.get("model", "unknown"),
        "policy_set": run.get("policy_set", "unknown"),
        "selected_domains": ",".join(domains),
        "git_sha": git_sha,
        "git_dirty": str(git_dirty),
    }


def _extract_tags(evaluation: dict, description: str | None) -> dict[str, str]:
    """Extract MLflow tags from evaluation dict.

    Args:
        evaluation: Evaluation dict from run_evaluation()
        description: Optional run description

    Returns:
        Dict of string tags (timestamp, stages_completed, description)
    """
    run = evaluation.get("run", {})
    tags: dict[str, str] = {
        "timestamp": run.get("timestamp", "unknown"),
        "stages_completed": ",".join(run.get("stages_completed", [])),
    }
    if description:
        tags["description"] = description
    return tags


def _experiment_name(policy_set: str) -> str:
    """Derive experiment name from policy set filename.

    Args:
        policy_set: Policy set filename (e.g., "swb.json")

    Returns:
        Experiment name (e.g., "swb")
    """
    return policy_set.removesuffix(".json")


def log_run_to_mlflow(
    evaluation: dict,
    output_dir: Path,
    tracking_uri: str,
    description: str | None = None,
    run_id: str | None = None,
) -> str:
    """Log pipeline run to MLflow with params, metrics, and artifacts.

    Args:
        evaluation: Evaluation dict from run_evaluation()
        output_dir: Pipeline output directory
        tracking_uri: MLflow tracking server URI
        description: Optional run description (logged as tag)
        run_id: Optional existing run ID to append to (for incremental updates)

    Returns:
        MLflow run ID (new or existing)

    Raises:
        ImportError: If mlflow is not installed
    """
    import mlflow

    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(_experiment_name(evaluation.get("run", {}).get("policy_set", "unknown")))

    if run_id:
        mlflow.start_run(run_id=run_id)
    else:
        mlflow.start_run()

    try:
        if not run_id:
            params = _extract_params(evaluation)
            mlflow.log_params(params)

        tags = _extract_tags(evaluation, description)
        mlflow.set_tags(tags)

        metrics = _flatten_metrics(evaluation)
        if metrics:
            mlflow.log_metrics(metrics)

        files, dirs = _collect_artifacts(output_dir)
        for f in files:
            mlflow.log_artifact(str(f))
        for d in dirs:
            mlflow.log_artifacts(str(d), artifact_path=d.name)

        current_run_id = mlflow.active_run().info.run_id
        mlflow.end_run()
        return current_run_id
    except Exception:
        mlflow.end_run(status="FAILED")
        raise
