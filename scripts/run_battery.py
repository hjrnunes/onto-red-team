# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml"]
# ///
"""Pipeline battery runner — executes refiner + redteam across policy × model matrix."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

_REQUIRED_KEYS = [
    "policy_dir",
    "runs_dir",
    "nexus_base_dir",
    "ontoquery_chroma_dir",
    "nexus_chroma_dir",
    "samples_per_risk",
    "tracking_uri",
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
    return [
        "uv", "run", "refiner", "ingest", str(policy_file),
        "--output", str(run_dir / f"{policy}-enriched.json"),
        "--base-url", model_url,
        "--model", model_name,
        "--api-key", api_key,
    ], "refiner"


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
) -> tuple[list[str], str]:
    cmd = [
        "uv", "run", "refiner", "run", str(input_file),
        "--output", str(run_dir),
        "--debug", str(run_dir / "debug"),
        "--base-url", model_url,
        "--model", model_name,
        "--api-key", api_key,
        "--nexus-base-dir", str(nexus_base_dir),
        "--ontoquery-chroma-dir", str(onto_chroma),
        "--nexus-chroma-dir", str(nexus_chroma),
        "--track",
        "--tracking-uri", tracking_uri,
    ]
    for tag in tags:
        cmd.extend(["--tag", tag])
    return cmd, "refiner"


def build_emit_cmd(*, run_dir: Path, policy_file: Path, samples_per_risk: int) -> tuple[list[str], str]:
    return [
        "uv", "run", "refiner", "emit", str(run_dir),
        "--policies", str(policy_file),
        "--samples-per-risk", str(samples_per_risk),
        "--output", str(run_dir / "dataset.jsonl"),
    ], "refiner"


def build_generate_cmd(
    *, run_dir: Path, model_name: str, model_url: str, api_key: str
) -> tuple[list[str], str]:
    cmd = [
        "uv", "run", "redteam", str(run_dir / "dataset.jsonl"),
        "--model", f"hosted_vllm/{model_name}",
        "--api-base", model_url,
    ]
    if api_key:
        cmd.extend(["--api-key", api_key])
    cmd.extend(["--concurrency", "5", "--output", str(run_dir / "adversarial_prompts.jsonl")])
    return cmd, "redteam"


def build_evaluate_cmd(
    *, run_dir: Path, policy_file: Path, tracking_uri: str, tags: list[str]
) -> tuple[list[str], str]:
    cmd = [
        "uv", "run", "refiner", "evaluate", str(run_dir),
        "--emit", str(run_dir / "dataset.jsonl"),
        "--adversarial", str(run_dir / "adversarial_prompts.jsonl"),
        "--policies", str(policy_file),
        "--track",
        "--tracking-uri", tracking_uri,
    ]
    for tag in tags:
        cmd.extend(["--tag", tag])
    return cmd, "refiner"
