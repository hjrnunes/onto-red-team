# Battery Script Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the justfile's bash-heavy pipeline orchestration with a Python script + YAML config for running all policy × model combinations.

**Architecture:** A standalone Python script (`scripts/run_battery.py`) reads `battery.yaml` for config, constructs CLI commands for each pipeline stage, and runs models in parallel via `ThreadPoolExecutor`. Each stage is a subprocess call to `uv run refiner ...` or `uv run redteam ...`.

**Tech Stack:** Python 3.12+ stdlib (argparse, subprocess, concurrent.futures, tempfile, shutil, pathlib), PyYAML (PEP 723 inline metadata)

**Spec:** `docs/superpowers/specs/2026-04-03-battery-script-design.md`

---

## File Structure

| File | Responsibility |
|------|---------------|
| `scripts/run_battery.py` | Main script: config loading, policy resolution, command building, parallel orchestration, CLI |
| `scripts/tests/test_battery.py` | Tests for all pure functions (config, resolution, command building, summary) |
| `battery.yaml` | Config: paths, settings, policies, models |
| `justfile` | Reduced to `index-ontologies`, `ingest-doc`, `battery` alias |

---

### Task 1: Config Loading

**Files:**
- Create: `scripts/tests/test_battery.py`
- Create: `scripts/run_battery.py`

- [ ] **Step 1: Write the failing test for config loading**

```python
# scripts/tests/test_battery.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from run_battery import load_config


def test_load_config_resolves_relative_paths(tmp_path):
    cfg_file = tmp_path / "battery.yaml"
    cfg_file.write_text(
        """\
policy_dir: policy_examples
runs_dir: runs
nexus_base_dir: /absolute/path
ontoquery_chroma_dir: ontoquery/.chroma
nexus_chroma_dir: nexus-mcp/.chroma
samples_per_risk: 15
tracking_uri: https://mlflow.example.com
policies:
  - swb
  - generic
models:
  phi-4: http://localhost:1234/v1
"""
    )
    cfg = load_config(cfg_file)
    assert cfg["policy_dir"] == tmp_path / "policy_examples"
    assert cfg["runs_dir"] == tmp_path / "runs"
    assert cfg["nexus_base_dir"] == Path("/absolute/path")
    assert cfg["ontoquery_chroma_dir"] == tmp_path / "ontoquery/.chroma"
    assert cfg["nexus_chroma_dir"] == tmp_path / "nexus-mcp/.chroma"
    assert cfg["samples_per_risk"] == 15
    assert cfg["tracking_uri"] == "https://mlflow.example.com"
    assert cfg["policies"] == ["swb", "generic"]
    assert cfg["models"] == {"phi-4": "http://localhost:1234/v1"}


def test_load_config_missing_required_field(tmp_path):
    cfg_file = tmp_path / "battery.yaml"
    cfg_file.write_text("policies:\n  - swb\n")
    try:
        load_config(cfg_file)
        assert False, "Should have raised"
    except SystemExit:
        pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with pyyaml --with pytest pytest scripts/tests/test_battery.py -v`
Expected: FAIL — `ModuleNotFoundError` or `ImportError`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/run_battery.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --with pyyaml --with pytest pytest scripts/tests/test_battery.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/run_battery.py scripts/tests/test_battery.py
git commit -m "feat(battery): add config loading with path resolution"
```

---

### Task 2: Policy File Resolution

**Files:**
- Modify: `scripts/tests/test_battery.py`
- Modify: `scripts/run_battery.py`

- [ ] **Step 1: Write failing tests for policy resolution**

Append to `scripts/tests/test_battery.py`:

```python
from run_battery import resolve_policy_file


def test_resolve_raw_policy_json(tmp_path):
    policy_dir = tmp_path / "policies"
    policy_dir.mkdir()
    (policy_dir / "swb.json").write_text("{}")
    result = resolve_policy_file("swb", policy_dir, run_dir=tmp_path / "run", prefer_enriched=False)
    assert result == policy_dir / "swb.json"


def test_resolve_raw_policy_md(tmp_path):
    policy_dir = tmp_path / "policies"
    policy_dir.mkdir()
    (policy_dir / "rdash.md").write_text("# Policy")
    result = resolve_policy_file("rdash", policy_dir, run_dir=tmp_path / "run", prefer_enriched=False)
    assert result == policy_dir / "rdash.md"


def test_resolve_prefers_enriched(tmp_path):
    policy_dir = tmp_path / "policies"
    policy_dir.mkdir()
    (policy_dir / "swb.json").write_text("{}")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    enriched = run_dir / "swb-enriched.json"
    enriched.write_text("{}")
    result = resolve_policy_file("swb", policy_dir, run_dir=run_dir, prefer_enriched=True)
    assert result == enriched


def test_resolve_falls_back_to_raw_when_no_enriched(tmp_path):
    policy_dir = tmp_path / "policies"
    policy_dir.mkdir()
    (policy_dir / "swb.json").write_text("{}")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    result = resolve_policy_file("swb", policy_dir, run_dir=run_dir, prefer_enriched=True)
    assert result == policy_dir / "swb.json"


def test_resolve_missing_policy_raises(tmp_path):
    policy_dir = tmp_path / "policies"
    policy_dir.mkdir()
    try:
        resolve_policy_file("missing", policy_dir, run_dir=tmp_path / "run", prefer_enriched=False)
        assert False, "Should have raised"
    except FileNotFoundError:
        pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with pyyaml --with pytest pytest scripts/tests/test_battery.py::test_resolve_raw_policy_json -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Write implementation**

Add to `scripts/run_battery.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --with pyyaml --with pytest pytest scripts/tests/test_battery.py -v -k resolve`
Expected: All 5 resolve tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/run_battery.py scripts/tests/test_battery.py
git commit -m "feat(battery): add policy file resolution logic"
```

---

### Task 3: Command Builders

**Files:**
- Modify: `scripts/tests/test_battery.py`
- Modify: `scripts/run_battery.py`

- [ ] **Step 1: Write failing tests for command builders**

Append to `scripts/tests/test_battery.py`:

```python
from run_battery import build_ingest_cmd, build_refine_cmd, build_emit_cmd, build_generate_cmd, build_evaluate_cmd


def test_build_ingest_cmd():
    cmd, cwd = build_ingest_cmd(
        policy_file=Path("/p/swb.json"),
        run_dir=Path("/runs/swb-phi4-v1"),
        policy="swb",
        model_name="phi-4",
        model_url="http://localhost/v1",
        api_key="secret",
    )
    assert cwd == "refiner"
    assert cmd[:4] == ["uv", "run", "refiner", "ingest"]
    assert "/p/swb.json" in cmd
    assert "--output" in cmd
    assert "--api-key" in cmd
    assert "secret" in cmd


def test_build_refine_cmd():
    cmd, cwd = build_refine_cmd(
        input_file=Path("/runs/swb-phi4-v1/swb-enriched.json"),
        run_dir=Path("/runs/swb-phi4-v1"),
        model_name="phi-4",
        model_url="http://localhost/v1",
        api_key="secret",
        nexus_base_dir=Path("/nexus"),
        onto_chroma=Path("/tmp/onto"),
        nexus_chroma=Path("/tmp/nexus"),
        tracking_uri="https://mlflow.example.com",
        tags=["exp1", "exp2"],
    )
    assert cwd == "refiner"
    assert cmd[:4] == ["uv", "run", "refiner", "run"]
    assert "--track" in cmd
    assert cmd[cmd.index("--tag") + 1] == "exp1"
    # two --tag flags
    tag_indices = [i for i, x in enumerate(cmd) if x == "--tag"]
    assert len(tag_indices) == 2


def test_build_refine_cmd_no_tags():
    cmd, _ = build_refine_cmd(
        input_file=Path("/in.json"),
        run_dir=Path("/runs/x"),
        model_name="m",
        model_url="http://u",
        api_key="k",
        nexus_base_dir=Path("/n"),
        onto_chroma=Path("/o"),
        nexus_chroma=Path("/c"),
        tracking_uri="https://t",
        tags=[],
    )
    assert "--tag" not in cmd


def test_build_emit_cmd():
    cmd, cwd = build_emit_cmd(
        run_dir=Path("/runs/swb-phi4-v1"),
        policy_file=Path("/p/swb.json"),
        samples_per_risk=15,
    )
    assert cwd == "refiner"
    assert "15" in cmd


def test_build_generate_cmd_with_key():
    cmd, cwd = build_generate_cmd(
        run_dir=Path("/runs/swb-phi4-v1"),
        model_name="phi-4",
        model_url="http://localhost/v1",
        api_key="secret",
    )
    assert cwd == "redteam"
    assert "--api-key" in cmd
    assert "secret" in cmd
    assert "hosted_vllm/phi-4" in cmd


def test_build_generate_cmd_no_key():
    cmd, _ = build_generate_cmd(
        run_dir=Path("/runs/swb-phi4-v1"),
        model_name="phi-4",
        model_url="http://localhost/v1",
        api_key="",
    )
    assert "--api-key" not in cmd


def test_build_evaluate_cmd():
    cmd, cwd = build_evaluate_cmd(
        run_dir=Path("/runs/swb-phi4-v1"),
        policy_file=Path("/p/swb.json"),
        tracking_uri="https://mlflow.example.com",
        tags=["exp1"],
    )
    assert cwd == "refiner"
    assert "--adversarial" in cmd
    assert "--track" in cmd
    assert cmd[cmd.index("--tag") + 1] == "exp1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --with pyyaml --with pytest pytest scripts/tests/test_battery.py -v -k build`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Write implementation**

Add to `scripts/run_battery.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --with pyyaml --with pytest pytest scripts/tests/test_battery.py -v -k build`
Expected: All 7 build tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/run_battery.py scripts/tests/test_battery.py
git commit -m "feat(battery): add command builders for all pipeline stages"
```

---

### Task 4: Per-Model Runner

**Files:**
- Modify: `scripts/tests/test_battery.py`
- Modify: `scripts/run_battery.py`

- [ ] **Step 1: Write failing test for run_model**

Append to `scripts/tests/test_battery.py`:

```python
from unittest.mock import patch, MagicMock
from run_battery import run_model


def test_run_model_dry_run(tmp_path, capsys):
    policy_dir = tmp_path / "policies"
    policy_dir.mkdir()
    (policy_dir / "swb.json").write_text("{}")
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    onto = tmp_path / "onto"
    onto.mkdir()
    nexus = tmp_path / "nexus"
    nexus.mkdir()

    cfg = {
        "policy_dir": policy_dir,
        "runs_dir": runs_dir,
        "nexus_base_dir": Path("/nexus"),
        "ontoquery_chroma_dir": onto,
        "nexus_chroma_dir": nexus,
        "samples_per_risk": 15,
        "tracking_uri": "https://mlflow.example.com",
    }
    results = run_model(
        model_name="phi-4",
        model_url="http://localhost/v1",
        run_name="v1",
        policies=["swb"],
        cfg=cfg,
        api_key="secret",
        tags=[],
        skip_ingest=True,
        skip_refine=False,
        skip_generate=True,
        dry_run=True,
        repo_root=tmp_path,
    )
    assert results == {"swb": "OK"}
    out = capsys.readouterr().out
    assert "refiner" in out  # printed command includes cwd


def test_run_model_calls_subprocess(tmp_path):
    policy_dir = tmp_path / "policies"
    policy_dir.mkdir()
    (policy_dir / "swb.json").write_text("{}")
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    onto = tmp_path / "onto"
    onto.mkdir()
    nexus = tmp_path / "nexus"
    nexus.mkdir()

    cfg = {
        "policy_dir": policy_dir,
        "runs_dir": runs_dir,
        "nexus_base_dir": Path("/nexus"),
        "ontoquery_chroma_dir": onto,
        "nexus_chroma_dir": nexus,
        "samples_per_risk": 15,
        "tracking_uri": "https://mlflow.example.com",
    }
    mock_run = MagicMock()
    with patch("run_battery.subprocess.run", mock_run):
        results = run_model(
            model_name="phi-4",
            model_url="http://localhost/v1",
            run_name="v1",
            policies=["swb"],
            cfg=cfg,
            api_key="secret",
            tags=[],
            skip_ingest=True,
            skip_refine=True,
            skip_generate=True,
            dry_run=False,
            repo_root=tmp_path,
        )
    assert results == {"swb": "OK"}
    # Only emit runs (ingest, refine, generate all skipped)
    assert mock_run.call_count == 1
    call_args = mock_run.call_args
    assert "emit" in call_args[0][0]


def test_run_model_records_failure(tmp_path):
    policy_dir = tmp_path / "policies"
    policy_dir.mkdir()
    (policy_dir / "swb.json").write_text("{}")
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    onto = tmp_path / "onto"
    onto.mkdir()
    nexus = tmp_path / "nexus"
    nexus.mkdir()

    cfg = {
        "policy_dir": policy_dir,
        "runs_dir": runs_dir,
        "nexus_base_dir": Path("/nexus"),
        "ontoquery_chroma_dir": onto,
        "nexus_chroma_dir": nexus,
        "samples_per_risk": 15,
        "tracking_uri": "https://mlflow.example.com",
    }
    with patch("run_battery.subprocess.run", side_effect=Exception("boom")):
        results = run_model(
            model_name="phi-4",
            model_url="http://localhost/v1",
            run_name="v1",
            policies=["swb"],
            cfg=cfg,
            api_key="",
            tags=[],
            skip_ingest=True,
            skip_refine=True,
            skip_generate=True,
            dry_run=False,
            repo_root=tmp_path,
        )
    assert results["swb"] == "FAIL"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with pyyaml --with pytest pytest scripts/tests/test_battery.py::test_run_model_dry_run -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Write implementation**

Add to `scripts/run_battery.py`:

```python
import os
import subprocess
import shutil
import tempfile


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

    # Snapshot ChromaDB dirs for this model (reused across policies)
    tmp_onto = tmp_nexus = None
    if not skip_refine and not dry_run:
        tmp_onto = Path(tempfile.mkdtemp())
        tmp_nexus = Path(tempfile.mkdtemp())
        shutil.copytree(cfg["ontoquery_chroma_dir"], tmp_onto, dirs_exist_ok=True)
        shutil.copytree(cfg["nexus_chroma_dir"], tmp_nexus, dirs_exist_ok=True)

    log_fh = open(log_path, "w") if log_path and not dry_run else None
    try:
        for policy in policies:
            run_dir = cfg["runs_dir"] / f"{policy}-{run_name}"
            run_dir.mkdir(parents=True, exist_ok=True)
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
                results[policy] = "OK"
            except Exception as e:
                msg = f"  FAILED: {policy}/{model_name}: {e}"
                print(msg)
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

    # 1. Ingest
    if not skip_ingest:
        raw_file = resolve_policy_file(policy, policy_dir, run_dir=run_dir, prefer_enriched=False)
        cmd, cwd = build_ingest_cmd(
            policy_file=raw_file, run_dir=run_dir, policy=policy,
            model_name=model_name, model_url=model_url, api_key=api_key,
        )
        _run_stage(cmd, cwd, **stage_kw)

    # 2. Refine
    if not skip_refine:
        input_file = resolve_policy_file(policy, policy_dir, run_dir=run_dir, prefer_enriched=True)
        cmd, cwd = build_refine_cmd(
            input_file=input_file, run_dir=run_dir, model_name=model_name,
            model_url=model_url, api_key=api_key, nexus_base_dir=cfg["nexus_base_dir"],
            onto_chroma=tmp_onto, nexus_chroma=tmp_nexus,
            tracking_uri=cfg["tracking_uri"], tags=tags,
        )
        _run_stage(cmd, cwd, **stage_kw)

    # 3. Emit
    policy_file = resolve_policy_file(policy, policy_dir, run_dir=run_dir, prefer_enriched=True)
    cmd, cwd = build_emit_cmd(
        run_dir=run_dir, policy_file=policy_file, samples_per_risk=cfg["samples_per_risk"],
    )
    _run_stage(cmd, cwd, **stage_kw)

    # 4. Generate
    if not skip_generate:
        cmd, cwd = build_generate_cmd(
            run_dir=run_dir, model_name=model_name, model_url=model_url, api_key=api_key,
        )
        _run_stage(cmd, cwd, **stage_kw)

    # 5. Evaluate (skipped when generate is skipped)
    if not skip_generate:
        policy_file = resolve_policy_file(policy, policy_dir, run_dir=run_dir, prefer_enriched=True)
        cmd, cwd = build_evaluate_cmd(
            run_dir=run_dir, policy_file=policy_file,
            tracking_uri=cfg["tracking_uri"], tags=tags,
        )
        _run_stage(cmd, cwd, **stage_kw)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --with pyyaml --with pytest pytest scripts/tests/test_battery.py -v -k run_model`
Expected: Both `test_run_model_dry_run` and `test_run_model_records_failure` PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/run_battery.py scripts/tests/test_battery.py
git commit -m "feat(battery): add per-model runner with ChromaDB snapshots"
```

---

### Task 5: Summary Table

**Files:**
- Modify: `scripts/tests/test_battery.py`
- Modify: `scripts/run_battery.py`

- [ ] **Step 1: Write failing test for summary table**

Append to `scripts/tests/test_battery.py`:

```python
from run_battery import format_summary_table


def test_format_summary_table():
    results = {
        "phi-4": {"swb": "OK", "generic": "OK"},
        "gemma": {"swb": "FAIL", "generic": "OK"},
    }
    table = format_summary_table(results, ["swb", "generic"])
    assert "phi-4" in table
    assert "gemma" in table
    assert "FAIL" in table
    assert "OK" in table
    lines = table.strip().split("\n")
    assert len(lines) == 3  # header + 2 policies


def test_format_summary_table_single():
    results = {"m1": {"p1": "OK"}}
    table = format_summary_table(results, ["p1"])
    assert "OK" in table
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with pyyaml --with pytest pytest scripts/tests/test_battery.py::test_format_summary_table -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Write implementation**

Add to `scripts/run_battery.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --with pyyaml --with pytest pytest scripts/tests/test_battery.py -v -k summary`
Expected: Both summary tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/run_battery.py scripts/tests/test_battery.py
git commit -m "feat(battery): add summary table formatter"
```

---

### Task 6: CLI + Parallel Orchestrator

**Files:**
- Modify: `scripts/run_battery.py`

- [ ] **Step 1: Write the CLI parser and main function**

Add to `scripts/run_battery.py`:

```python
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed


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

    def _worker(model_name: str, model_url: str) -> tuple[str, dict[str, str]]:
        run_name = f"{model_name}-{args.run_name}"
        log_path = cfg["runs_dir"] / f"{run_name}.log"
        print(f"=== Starting {model_name} (log: {log_path}) ===")
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
        return model_name, results

    with ThreadPoolExecutor(max_workers=len(models)) as pool:
        futures = {pool.submit(_worker, name, url): name for name, url in models.items()}
        for future in as_completed(futures):
            model_name = futures[future]
            try:
                name, results = future.result()
                all_results[name] = results
                failed = any(v == "FAIL" for v in results.values())
                status = "FAILED" if failed else "done"
                print(f"=== {name} {status} ===")
            except Exception as e:
                print(f"=== {model_name} FAILED: {e} ===")
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
```

- [ ] **Step 2: Test the CLI parses correctly**

Append to `scripts/tests/test_battery.py`:

```python
from run_battery import parse_args


def test_parse_args_minimal():
    args = parse_args(["my-run"])
    assert args.run_name == "my-run"
    assert args.policies is None
    assert args.models is None
    assert not args.skip_ingest
    assert not args.dry_run


def test_parse_args_full():
    args = parse_args([
        "v1", "--config", "custom.yaml",
        "--policy", "swb", "--policy", "generic",
        "--model", "phi-4",
        "--skip-ingest", "--skip-generate",
        "--tags", "exp1", "--tags", "exp2",
        "--dry-run",
    ])
    assert args.run_name == "v1"
    assert args.config == "custom.yaml"
    assert args.policies == ["swb", "generic"]
    assert args.models == ["phi-4"]
    assert args.skip_ingest
    assert args.skip_generate
    assert args.tags == ["exp1", "exp2"]
    assert args.dry_run
```

- [ ] **Step 3: Run all tests**

Run: `uv run --with pyyaml --with pytest pytest scripts/tests/test_battery.py -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add scripts/run_battery.py scripts/tests/test_battery.py
git commit -m "feat(battery): add CLI parser and parallel orchestrator"
```

---

### Task 7: Config File + Justfile Replacement

**Files:**
- Create: `battery.yaml`
- Modify: `justfile`

- [ ] **Step 1: Create battery.yaml**

```yaml
# battery.yaml — pipeline battery configuration
policy_dir: policy_examples
runs_dir: runs
nexus_base_dir: /Users/hjrnunes/workspace/redhat/ibm/ai-atlas-nexus
ontoquery_chroma_dir: ontoquery/.chroma
nexus_chroma_dir: nexus-mcp/.chroma

samples_per_risk: 15
tracking_uri: https://mlflow.taxonomy-refiner.orb.local

policies:
  - swb
  - generic
  - aramco
  - healthcare
  - rdash-nhs

models:
  phi-4: https://phi-4-model-serving.apps.rosa.hnunes-421.0o92.p3.openshiftapps.com/v1
  gemma-2-9b-it-abliterated: https://gemma-2-9b-it-abliterated-model-serving.apps.rosa.u1q6z7t9c5c9x9t.262f.p3.openshiftapps.com/v1
  gemma-3-12b-it: https://gemma-3-12b-it-model-serving.apps.rosa.u1q6z7t9c5c9x9t.262f.p3.openshiftapps.com/v1
  mistral-small-3-1-24b: https://mistral-small-3-1-24b-model-serving.apps.rosa.hnunes-421.0o92.p3.openshiftapps.com/v1
  gemma-4-e4b-it: http://localhost:1234/v1
```

- [ ] **Step 2: Replace justfile contents**

```just
# Taxonomy Refiner — utility recipes
# Battery runs: uv run scripts/run_battery.py <run-name> [options]

# Index all ontologies into ontoquery ChromaDB (CCO + Commons + FIBO + OBO + D3FEND + CSO + bridges)
index-ontologies:
    cd ontoquery && uv run ontoquery index \
        ../ontologies/CommonCoreOntologies/src/cco-modules/ \
        ../ontologies/commons/ \
        ../ontologies/fibo/ \
        ../ontologies/obo/ \
        ../ontologies/d3fend-ontology/src/ontology/d3fend-protege.ttl \
        ../ontologies/cso/ \
        ../ontologies/bridges/

# Ingest an arbitrary document (standalone utility)
ingest-doc input model_name model_url output="":
    cd refiner && uv run refiner ingest {{ input }} \
        {{ if output != "" { "--output " + output } else { "" } }} \
        --base-url {{ model_url }} \
        --model {{ model_name }} \
        --api-key {{ env("REFINER_API_KEY", "none") }}

# Run pipeline battery (delegates to Python)
battery *args:
    uv run scripts/run_battery.py {{args}}
```

- [ ] **Step 3: Verify dry-run produces correct output**

Run: `uv run scripts/run_battery.py test-run --policy swb --model phi-4 --skip-ingest --skip-generate --dry-run`

Expected: prints the refine and emit commands with correct paths and arguments, no subprocess execution.

- [ ] **Step 4: Commit**

```bash
git add battery.yaml justfile
git commit -m "feat(battery): add battery.yaml config, slim down justfile"
```

---

### Task 8: Cleanup

**Files:**
- Possibly delete: `models.json` (superseded by `battery.yaml`)

- [ ] **Step 1: Check if models.json is referenced anywhere else**

Run: `grep -r "models.json" --include="*.py" --include="*.md" --include="*.yaml" .`

If only referenced in `CLAUDE.md` and docs, it can be removed.

- [ ] **Step 2: Update CLAUDE.md**

Update the "Running" section to reference `battery.yaml` and the new script instead of `models.json` and justfile recipes. Update the `just run-all` references.

- [ ] **Step 3: Run all tests one final time**

Run: `uv run --with pyyaml --with pytest pytest scripts/tests/test_battery.py -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore(battery): remove models.json, update docs"
```
