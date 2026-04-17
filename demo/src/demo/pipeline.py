"""End-to-end ORT demo pipeline: policy + model → ART report.

Orchestrates the full flow by shelling out to the refiner and redteam
sub-project CLIs, then running the demo stages in-process.

Usage::

    demo run --policy ../policy_examples/rdash-nhs.json \\
             --model mistral-small-3-1-24b \\
             --model-url https://model-serving.example.com/v1 \\
             --config configs/garak.yaml

Importable for notebooks::

    from demo.pipeline import run_pipeline
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent


# ---------------------------------------------------------------------------
# Sub-project runners (shell out like run_battery.py)
# ---------------------------------------------------------------------------


def _run_cmd(cmd: list[str], cwd: Path, *, label: str, dry_run: bool = False) -> None:
    print(f"  [{label}] {' '.join(cmd)}")
    if dry_run:
        return
    result = subprocess.run(cmd, cwd=cwd, check=True)


def run_refiner_ingest(
    policy_path: Path,
    output_path: Path,
    *,
    model: str,
    model_url: str,
    api_key: str | None = None,
    dry_run: bool = False,
) -> None:
    """Run ``refiner ingest`` to enrich a raw policy into PolicyProfile."""
    cmd = [
        "uv", "run", "refiner", "ingest", str(policy_path),
        "--output", str(output_path),
        "--base-url", model_url,
        "--model", model,
    ]
    if api_key:
        cmd.extend(["--api-key", api_key])
    _run_cmd(cmd, REPO_ROOT / "refiner", label="refiner ingest", dry_run=dry_run)


def run_refiner(
    policy_path: Path,
    run_dir: Path,
    *,
    model: str,
    model_url: str,
    api_key: str | None = None,
    nexus_base_dir: Path | None = None,
    ontoquery_chroma_dir: Path | None = None,
    nexus_chroma_dir: Path | None = None,
    dry_run: bool = False,
) -> None:
    """Run ``refiner run`` — the core pipeline (identify_domains → contextualize)."""
    nexus = nexus_base_dir or REPO_ROOT / "ontologies" / "ai-atlas-nexus"
    onto_chroma = ontoquery_chroma_dir or REPO_ROOT / "ontoquery" / ".chroma"
    nexus_chroma = nexus_chroma_dir or REPO_ROOT / "nexus-mcp" / ".chroma"

    cmd = [
        "uv", "run", "refiner", "run", str(policy_path),
        "--output", str(run_dir),
        "--debug", str(run_dir / "debug"),
        "--base-url", model_url,
        "--model", model,
        "--nexus-base-dir", str(nexus),
        "--ontoquery-chroma-dir", str(onto_chroma),
        "--nexus-chroma-dir", str(nexus_chroma),
    ]
    if api_key:
        cmd.extend(["--api-key", api_key])
    _run_cmd(cmd, REPO_ROOT / "refiner", label="refiner run", dry_run=dry_run)


def run_emit(
    run_dir: Path,
    policy_path: Path,
    *,
    samples_per_risk: int = 15,
    slug: str | None = None,
    dry_run: bool = False,
) -> Path:
    """Run ``refiner emit`` — produce dataset JSONL from domain context."""
    output_name = f"{slug}-dataset.jsonl" if slug else "dataset.jsonl"
    output_path = run_dir / output_name
    cmd = [
        "uv", "run", "refiner", "emit", str(run_dir),
        "--policies", str(policy_path),
        "--samples-per-risk", str(samples_per_risk),
        "--output", str(output_path),
    ]
    _run_cmd(cmd, REPO_ROOT / "refiner", label="refiner emit", dry_run=dry_run)
    return output_path


def run_redteam(
    dataset_path: Path,
    output_path: Path,
    *,
    model: str,
    model_url: str,
    api_key: str | None = None,
    concurrency: int = 5,
    dry_run: bool = False,
) -> None:
    """Run ``redteam`` — generate adversarial prompts from dataset."""
    cmd = [
        "uv", "run", "redteam", str(dataset_path),
        "--model", f"hosted_vllm/{model}",
        "--api-base", model_url,
        "--concurrency", str(concurrency),
        "--output", str(output_path),
    ]
    if api_key:
        cmd.extend(["--api-key", api_key])
    _run_cmd(cmd, REPO_ROOT / "redteam", label="redteam", dry_run=dry_run)


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------


def _derive_slug(policy_path: Path) -> str:
    return policy_path.stem


def run_pipeline(
    policy_path: Path,
    model: str,
    model_url: str,
    *,
    garak_config: Path | None = None,
    output_dir: Path | None = None,
    api_key: str | None = None,
    samples_per_risk: int = 15,
    utility_samples: int = 5,
    seed: int | None = None,
    concurrency: int = 5,
    nexus_base_dir: Path | None = None,
    ontoquery_chroma_dir: Path | None = None,
    nexus_chroma_dir: Path | None = None,
    skip_ingest: bool = False,
    skip_scan: bool = False,
    skip_utility: bool = False,
    dry_run: bool = False,
) -> Path:
    """Run the full demo pipeline: policy + model → ART report.

    Returns the output directory path.
    """
    slug = _derive_slug(policy_path)
    policy_path = policy_path.resolve()
    if output_dir is None:
        output_dir = Path("demo_runs") / f"{slug}-{model}"
    output_dir = output_dir.resolve()

    refiner_dir = output_dir / "refiner"
    refiner_dir.mkdir(parents=True, exist_ok=True)

    api_key = api_key or os.environ.get("REFINER_API_KEY", "")

    # ---- Stage 1: Ingest (optional) ----
    if not skip_ingest:
        print()
        print("=" * 60)
        print("STAGE 1: Ingest policy")
        print("=" * 60)
        enriched_policy = refiner_dir / f"{slug}-policy-document.json"
        run_refiner_ingest(
            policy_path, enriched_policy,
            model=model, model_url=model_url, api_key=api_key,
            dry_run=dry_run,
        )
        refiner_policy = enriched_policy
    else:
        refiner_policy = policy_path

    # ---- Stage 2: Refiner pipeline ----
    print()
    print("=" * 60)
    print("STAGE 2: Run refiner pipeline")
    print("=" * 60)
    run_refiner(
        refiner_policy, refiner_dir,
        model=model, model_url=model_url, api_key=api_key,
        nexus_base_dir=nexus_base_dir,
        ontoquery_chroma_dir=ontoquery_chroma_dir,
        nexus_chroma_dir=nexus_chroma_dir,
        dry_run=dry_run,
    )

    # ---- Stage 3: Emit dataset ----
    print()
    print("=" * 60)
    print("STAGE 3: Emit dataset")
    print("=" * 60)
    dataset_path = run_emit(
        refiner_dir, refiner_policy,
        samples_per_risk=samples_per_risk, slug=slug,
        dry_run=dry_run,
    )

    # ---- Stage 4: Generate adversarial prompts ----
    print()
    print("=" * 60)
    print("STAGE 4: Generate adversarial prompts")
    print("=" * 60)
    adversarial_path = refiner_dir / f"{slug}-adversarial-prompts.jsonl"
    run_redteam(
        dataset_path, adversarial_path,
        model=model, model_url=model_url, api_key=api_key,
        concurrency=concurrency,
        dry_run=dry_run,
    )

    # ---- Stage 5: Prepare ORT data ----
    print()
    print("=" * 60)
    print("STAGE 5: Prepare ORT data + garak CAS")
    print("=" * 60)
    from demo.prepare import prepare
    if not dry_run:
        prepare(refiner_dir, output_dir)

    # ---- Stage 6: Utility prompts (optional) ----
    if not skip_utility:
        print()
        print("=" * 60)
        print("STAGE 6: Generate utility prompts")
        print("=" * 60)
        from demo.utility import utility
        if not dry_run:
            utility(
                refiner_dir, output_dir,
                samples_per_risk=utility_samples,
                seed=seed,
            )

    # ---- Stage 7: Garak scan (optional) ----
    if not skip_scan:
        if garak_config is None:
            print("\nWarning: no --config provided, skipping garak scan", file=sys.stderr)
        else:
            print()
            print("=" * 60)
            print("STAGE 7: Run garak scan")
            print("=" * 60)
            from demo.scan import run_garak
            if not dry_run:
                report = run_garak(garak_config.resolve(), output_dir)
                if report:
                    print(f"Garak report: {report}")

    # ---- Stage 8: ART report ----
    print()
    print("=" * 60)
    print("STAGE 8: Build ART report")
    print("=" * 60)
    from demo.report import render_report
    if not dry_run:
        try:
            html = render_report(output_dir, refiner_dir)
            report_html = output_dir / "report.html"
            with open(report_html, "w") as f:
                f.write(html)
            print(f"Report written to {report_html}")
        except FileNotFoundError as e:
            print(f"Skipping report (missing data): {e}", file=sys.stderr)

    print()
    print("=" * 60)
    print(f"Pipeline complete. Outputs in {output_dir}")
    print("=" * 60)

    return output_dir
