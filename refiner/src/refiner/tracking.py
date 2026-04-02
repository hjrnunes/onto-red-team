"""MLflow tracking integration for the refiner pipeline."""

import subprocess
from pathlib import Path


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
