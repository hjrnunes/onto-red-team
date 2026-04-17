# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml"]
# ///
"""Pipeline battery runner — executes refiner + redteam across policy × model matrix."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yaml

_print_lock = threading.Lock()


def _ts() -> str:
    """Return a short elapsed-time or clock stamp for log lines."""
    return time.strftime("%H:%M:%S")


def _progress(msg: str) -> None:
    """Thread-safe progress print."""
    with _print_lock:
        print(f"[{_ts()}] {msg}", flush=True)


def _fmt_elapsed(seconds: float) -> str:
    """Format elapsed seconds as e.g. '2m 34s' or '5s'."""
    m, s = divmod(int(seconds), 60)
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


_REQUIRED_KEYS = [
    "policy_dir",
    "runs_dir",
    "nexus_base_dir",
    "ontoquery_chroma_dir",
    "nexus_chroma_dir",
    "samples_per_risk",
    "policies",
    "models",
]

_PATH_KEYS = ["policy_dir", "runs_dir", "nexus_base_dir", "ontoquery_chroma_dir", "nexus_chroma_dir"]


def load_config(config_path: Path) -> dict:
    with open(config_path) as f:
        raw = yaml.safe_load(f)
    missing = [k for k in _REQUIRED_KEYS if k not in raw]
    if missing:
        print(f"Error: missing config keys: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)
    raw.setdefault("tracking_uri", "")
    root = config_path.parent
    for key in _PATH_KEYS:
        p = Path(raw[key])
        if not p.is_absolute():
            p = root / p
        raw[key] = p
    return raw


def resolve_policy_file(
        policy: str, policy_dir: Path, *, run_dir: Path, prefer_enriched: bool
) -> Path:
    if prefer_enriched:
        policy_doc = run_dir / f"{policy}-policy-document.json"
        if policy_doc.exists():
            return policy_doc
        enriched = run_dir / f"{policy}-enriched.json"
        if enriched.exists():
            return enriched
    for ext in ("json", "md"):
        candidate = policy_dir / f"{policy}.{ext}"
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"No policy file found for '{policy}' in {policy_dir}")


def build_ingest_cmd(
        *, policy_file: Path, run_dir: Path, policy: str, model_name: str, model_url: str, api_key: str
) -> tuple[list[str], str]:
    cmd = [
        "uv", "run", "refiner", "ingest", str(policy_file),
        "--output", str(run_dir / f"{policy}-policy-document.json"),
        "--base-url", model_url,
        "--model", model_name,
    ]
    if api_key:
        cmd.extend(["--api-key", api_key])
    return cmd, "refiner"


def build_refine_cmd(
        *,
        input_file: Path,
        run_dir: Path,
        model_name: str,
        model_url: str,
        api_key: str,
        nexus_base_dir: Path,
        onto_chroma: Path,
        nexus_chroma: Path,
        tracking_uri: str,
        tags: list[str],
        max_concurrent: int = 1,
) -> tuple[list[str], str]:
    cmd = [
        "uv", "run", "refiner", "run", str(input_file),
        "--output", str(run_dir),
        "--debug", str(run_dir / "debug"),
        "--base-url", model_url,
        "--model", model_name,
    ]
    if api_key:
        cmd.extend(["--api-key", api_key])
    cmd.extend([
        "--nexus-base-dir", str(nexus_base_dir),
        "--ontoquery-chroma-dir", str(onto_chroma),
        "--nexus-chroma-dir", str(nexus_chroma),
    ])
    if max_concurrent > 1:
        cmd.extend(["--max-concurrent", str(max_concurrent)])
    if tracking_uri:
        cmd.extend(["--track", "--tracking-uri", tracking_uri])
    for tag in tags:
        cmd.extend(["--tag", tag])
    return cmd, "refiner"


def build_emit_cmd(
    *, run_dir: Path, policy_file: Path, samples_per_risk: int,
    policy: str,
    technique_weights: dict[str, float] | None = None,
    emit_mode: str | None = None,
    benign_weights: dict[str, float] | None = None,
) -> tuple[list[str], str]:
    if emit_mode == "paired":
        output_file = f"{policy}-dataset-redteam.jsonl"
    elif emit_mode == "utility":
        output_file = f"{policy}-dataset-utility.jsonl"
    else:
        output_file = f"{policy}-dataset.jsonl"
    cmd = [
        "uv", "run", "refiner", "emit", str(run_dir),
        "--policies", str(policy_file),
        "--samples-per-risk", str(samples_per_risk),
        "--output", str(run_dir / output_file),
    ]
    if emit_mode:
        cmd.extend(["--mode", emit_mode])
    if technique_weights:
        import json as _json
        cmd.extend(["--technique-weights", _json.dumps(technique_weights)])
    if benign_weights:
        import json as _json
        cmd.extend(["--benign-weights", _json.dumps(benign_weights)])
    return cmd, "refiner"


def build_generate_cmd(
        *, run_dir: Path, policy: str, model_name: str, model_url: str, api_key: str,
        emit_mode: str | None = None,
) -> tuple[list[str], str]:
    if emit_mode == "paired":
        dataset_file = f"{policy}-dataset-redteam.jsonl"
    elif emit_mode == "utility":
        dataset_file = f"{policy}-dataset-utility.jsonl"
    else:
        dataset_file = f"{policy}-dataset.jsonl"
    cmd = [
        "uv", "run", "redteam", str(run_dir / dataset_file),
        "--model", f"hosted_vllm/{model_name}",
        "--api-base", model_url,
    ]
    if api_key:
        cmd.extend(["--api-key", api_key])
    cmd.extend(["--concurrency", "5", "--output", str(run_dir / f"{policy}-adversarial-prompts.jsonl")])
    return cmd, "redteam"


def build_evaluate_cmd(
        *, run_dir: Path, policy: str, policy_file: Path, tracking_uri: str, tags: list[str],
        judge_cfg: dict | None = None,
        emit_mode: str | None = None,
) -> tuple[list[str], str]:
    emit_file = f"{policy}-dataset.jsonl"
    if emit_mode == "paired":
        emit_file = f"{policy}-dataset-redteam.jsonl"
    elif emit_mode == "utility":
        emit_file = f"{policy}-dataset-utility.jsonl"
    cmd = [
        "uv", "run", "refiner", "evaluate", str(run_dir),
        "--emit", str(run_dir / emit_file),
        "--adversarial", str(run_dir / f"{policy}-adversarial-prompts.jsonl"),
        "--policies", str(policy_file),
    ]
    if emit_mode:
        cmd.extend(["--mode", emit_mode])
    if judge_cfg and judge_cfg.get("enabled"):
        cmd.append("--judge")
        if judge_cfg.get("model"):
            cmd.extend(["--judge-model", judge_cfg["model"]])
        if judge_cfg.get("base_url"):
            cmd.extend(["--judge-base-url", judge_cfg["base_url"]])
        if judge_cfg.get("api_key"):
            cmd.extend(["--judge-api-key", judge_cfg["api_key"]])
        if judge_cfg.get("sample"):
            cmd.extend(["--judge-sample", str(judge_cfg["sample"])])
    if tracking_uri:
        cmd.extend(["--track", "--tracking-uri", tracking_uri])
    for tag in tags:
        cmd.extend(["--tag", tag])
    return cmd, "refiner"


def build_combined_report_cmd(*, run_dir: Path, repo_root: Path) -> tuple[list[str], str]:
    return [
        "uv", "run", str(repo_root / "scripts" / "build_combined_report.py"),
        str(run_dir),
    ], "."


def _log_tail(log_path: Path, n: int = 10) -> str:
    try:
        lines = log_path.read_text().splitlines()
        return "\n".join(f"  | {l}" for l in lines[-n:])
    except OSError:
        return ""


def _run_stage(
        cmd: list[str], cwd: str, *, dry_run: bool, repo_root: Path, log_file=None,
) -> None:
    full_cwd = repo_root / cwd
    if dry_run:
        print(f"  [{cwd}] {' '.join(cmd)}")
        return
    subprocess.run(cmd, cwd=full_cwd, check=True, stdout=log_file, stderr=subprocess.STDOUT)


def run_model(
        *,
        model_name: str,
        model_url: str,
        run_name: str,
        policies: list[str],
        cfg: dict,
        api_key: str,
        tags: list[str],
        skip_ingest: bool,
        skip_refine: bool,
        skip_generate: bool,
        dry_run: bool,
        repo_root: Path,
        log_path: Path | None = None,
) -> dict[str, str]:
    results: dict[str, str] = {}

    tmp_onto = tmp_nexus = None
    if not skip_refine and not dry_run:
        tmp_onto = Path(tempfile.mkdtemp())
        tmp_nexus = Path(tempfile.mkdtemp())
        if cfg["ontoquery_chroma_dir"].exists():
            shutil.copytree(cfg["ontoquery_chroma_dir"], tmp_onto, dirs_exist_ok=True)
        if cfg["nexus_chroma_dir"].exists():
            shutil.copytree(cfg["nexus_chroma_dir"], tmp_nexus, dirs_exist_ok=True)

    log_fh = open(log_path, "w") if log_path and not dry_run else None
    total_policies = len(policies)
    try:
        for pi, policy in enumerate(policies, 1):
            _progress(f"{model_name} ▸ policy {pi}/{total_policies}: {policy}")
            run_dir = cfg["runs_dir"] / f"{policy}-{run_name}"
            run_dir.mkdir(parents=True, exist_ok=True)
            t0 = time.monotonic()
            try:
                _run_policy(
                    policy=policy,
                    run_dir=run_dir,
                    model_name=model_name,
                    model_url=model_url,
                    cfg=cfg,
                    api_key=api_key,
                    tags=tags,
                    skip_ingest=skip_ingest,
                    skip_refine=skip_refine,
                    skip_generate=skip_generate,
                    dry_run=dry_run,
                    repo_root=repo_root,
                    tmp_onto=tmp_onto if tmp_onto else cfg["ontoquery_chroma_dir"],
                    tmp_nexus=tmp_nexus if tmp_nexus else cfg["nexus_chroma_dir"],
                    log_file=log_fh,
                )
                elapsed = time.monotonic() - t0
                _progress(f"{model_name}/{policy} ✓ done ({_fmt_elapsed(elapsed)})")
                results[policy] = "OK"
            except subprocess.CalledProcessError as e:
                elapsed = time.monotonic() - t0
                # Flush log so we can read the tail
                if log_fh:
                    log_fh.flush()
                tail = _log_tail(log_path, 10) if log_path else ""
                msg = f"{model_name}/{policy} ✗ FAILED (exit {e.returncode}, {_fmt_elapsed(elapsed)})"
                if tail:
                    msg += f"\n  --- last lines of {log_path.name} ---\n{tail}"
                _progress(msg)
                if log_fh:
                    log_fh.write(msg + "\n")
                results[policy] = "FAIL"
            except Exception as e:
                elapsed = time.monotonic() - t0
                msg = f"{model_name}/{policy} ✗ FAILED: {e} ({_fmt_elapsed(elapsed)})"
                _progress(msg)
                if log_fh:
                    log_fh.write(msg + "\n")
                results[policy] = "FAIL"
    finally:
        if log_fh:
            log_fh.close()
        if tmp_onto:
            shutil.rmtree(tmp_onto, ignore_errors=True)
        if tmp_nexus:
            shutil.rmtree(tmp_nexus, ignore_errors=True)

    return results


def _run_policy(
        *,
        policy: str,
        run_dir: Path,
        model_name: str,
        model_url: str,
        cfg: dict,
        api_key: str,
        tags: list[str],
        skip_ingest: bool,
        skip_refine: bool,
        skip_generate: bool,
        dry_run: bool,
        repo_root: Path,
        tmp_onto: Path,
        tmp_nexus: Path,
        log_file=None,
) -> None:
    policy_dir = cfg["policy_dir"]
    stage_kw = dict(dry_run=dry_run, repo_root=repo_root, log_file=log_file)
    prefix = f"{model_name}/{policy}"

    # Build list of active stages for numbering
    stages: list[str] = []
    if not skip_ingest:
        stages.append("ingest")
    if not skip_refine:
        stages.append("refine")
    stages.append("emit")
    if not skip_generate:
        stages.append("generate")
        stages.append("evaluate")
    stages.append("report")
    total_stages = len(stages)
    stage_idx = 0

    def _stage_msg(name: str) -> str:
        nonlocal stage_idx
        stage_idx += 1
        return f"{prefix} ▸ {name} [{stage_idx}/{total_stages}]"

    if not skip_ingest:
        _progress(_stage_msg("ingest"))
        raw_file = resolve_policy_file(policy, policy_dir, run_dir=run_dir, prefer_enriched=False)
        cmd, cwd = build_ingest_cmd(
            policy_file=raw_file, run_dir=run_dir, policy=policy,
            model_name=model_name, model_url=model_url, api_key=api_key,
        )
        _run_stage(cmd, cwd, **stage_kw)

    if not skip_refine:
        _progress(_stage_msg("refine"))
        input_file = resolve_policy_file(policy, policy_dir, run_dir=run_dir, prefer_enriched=True)
        cmd, cwd = build_refine_cmd(
            input_file=input_file, run_dir=run_dir, model_name=model_name,
            model_url=model_url, api_key=api_key, nexus_base_dir=cfg["nexus_base_dir"],
            onto_chroma=tmp_onto, nexus_chroma=tmp_nexus,
            tracking_uri=cfg["tracking_uri"], tags=tags,
            max_concurrent=cfg.get("max_concurrent", 1),
        )
        _run_stage(cmd, cwd, **stage_kw)

    _progress(_stage_msg("emit"))
    policy_file = resolve_policy_file(policy, policy_dir, run_dir=run_dir, prefer_enriched=True)
    cmd, cwd = build_emit_cmd(
        run_dir=run_dir, policy_file=policy_file, samples_per_risk=cfg["samples_per_risk"],
        policy=policy, technique_weights=cfg.get("technique_weights"),
        emit_mode=cfg.get("emit_mode"),
        benign_weights=cfg.get("benign_weights"),
    )
    _run_stage(cmd, cwd, **stage_kw)

    if not skip_generate:
        _progress(_stage_msg("generate"))
        cmd, cwd = build_generate_cmd(
            run_dir=run_dir, policy=policy, model_name=model_name,
            model_url=model_url, api_key=api_key,
            emit_mode=cfg.get("emit_mode"),
        )
        _run_stage(cmd, cwd, **stage_kw)

    if not skip_generate:
        _progress(_stage_msg("evaluate"))
        policy_file = resolve_policy_file(policy, policy_dir, run_dir=run_dir, prefer_enriched=True)
        cmd, cwd = build_evaluate_cmd(
            run_dir=run_dir, policy=policy, policy_file=policy_file,
            tracking_uri=cfg["tracking_uri"], tags=tags,
            judge_cfg=cfg.get("judge"),
            emit_mode=cfg.get("emit_mode"),
        )
        _run_stage(cmd, cwd, **stage_kw)

    _progress(_stage_msg("report"))
    cmd, cwd = build_combined_report_cmd(run_dir=run_dir, repo_root=repo_root)
    _run_stage(cmd, cwd, **stage_kw)


def format_summary_table(results: dict[str, dict[str, str]], policies: list[str]) -> str:
    models = list(results.keys())
    col_widths = [max(len(m), 4) for m in models]
    policy_col = max(len(p) for p in policies) if policies else 8

    header = " " * (policy_col + 2) + "  ".join(m.rjust(w) for m, w in zip(models, col_widths))
    lines = [header]
    for policy in policies:
        cells = []
        for model, width in zip(models, col_widths):
            status = results.get(model, {}).get(policy, "—")
            cells.append(status.rjust(width))
        lines.append(f"{policy.ljust(policy_col)}  {'  '.join(cells)}")
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run pipeline battery across policies × models")
    p.add_argument("run_name", help="Name suffix for this battery run")
    p.add_argument("--config", default="battery.yaml", help="Config file (default: battery.yaml)")
    p.add_argument("--policy", action="append", dest="policies", help="Run only this policy (repeatable)")
    p.add_argument("--model", action="append", dest="models", help="Run only this model (repeatable)")
    p.add_argument("--skip-ingest", action="store_true", help="Skip the ingest stage")
    p.add_argument("--skip-refine", action="store_true", help="Skip the refine stage")
    p.add_argument("--skip-generate", action="store_true", help="Skip generate + evaluate stages")
    p.add_argument("--tags", action="append", default=[], help="Run tags (repeatable)")
    p.add_argument("--dry-run", action="store_true", help="Print commands without executing")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config_path = Path(args.config).resolve()
    cfg = load_config(config_path)
    repo_root = config_path.parent

    os.environ["MLFLOW_TRACKING_INSECURE_TLS"] = "true"
    api_key = os.environ.get("REFINER_API_KEY", "")

    policies = args.policies or cfg["policies"]
    model_filter = args.models
    models = cfg["models"]
    if model_filter:
        unknown = set(model_filter) - set(models)
        if unknown:
            print(f"Error: unknown model(s): {', '.join(unknown)}", file=sys.stderr)
            return 1
        models = {m: models[m] for m in model_filter}

    unknown_policies = set(policies) - set(cfg["policies"])
    if unknown_policies:
        print(f"Warning: policies not in config: {', '.join(unknown_policies)}", file=sys.stderr)

    cfg["runs_dir"].mkdir(parents=True, exist_ok=True)

    all_results: dict[str, dict[str, str]] = {}

    total_models = len(models)
    _progress(f"Battery: {total_models} model(s) × {len(policies)} policy(ies)")

    def _worker(model_name: str, model_url: str) -> tuple[str, dict[str, str], float]:
        run_name = f"{model_name}-{args.run_name}"
        log_path = cfg["runs_dir"] / f"{run_name}.log"
        _progress(f"=== Starting {model_name} (log: {log_path}) ===")
        t0 = time.monotonic()
        results = run_model(
            model_name=model_name,
            model_url=model_url,
            run_name=run_name,
            policies=policies,
            cfg=cfg,
            api_key=api_key,
            tags=args.tags,
            skip_ingest=args.skip_ingest,
            skip_refine=args.skip_refine,
            skip_generate=args.skip_generate,
            dry_run=args.dry_run,
            repo_root=repo_root,
            log_path=log_path,
        )
        return model_name, results, time.monotonic() - t0

    models_done = 0
    with ThreadPoolExecutor(max_workers=len(models)) as pool:
        futures = {pool.submit(_worker, name, url): name for name, url in models.items()}
        for future in as_completed(futures):
            model_name = futures[future]
            models_done += 1
            try:
                name, results, elapsed = future.result()
                all_results[name] = results
                failed = any(v == "FAIL" for v in results.values())
                status = "✗ FAILED" if failed else "✓ done"
                _progress(f"=== {name} {status} ({_fmt_elapsed(elapsed)}) [{models_done}/{total_models} models] ===")
            except Exception as e:
                _progress(f"=== {model_name} ✗ FAILED: {e} [{models_done}/{total_models} models] ===")
                all_results[model_name] = {p: "FAIL" for p in policies}

    print()
    print(format_summary_table(all_results, policies))
    print()

    any_failed = any(v == "FAIL" for r in all_results.values() for v in r.values())
    if any_failed:
        print("Some runs failed.")
        return 1
    print("All runs complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
