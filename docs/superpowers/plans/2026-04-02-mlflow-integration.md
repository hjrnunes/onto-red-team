# MLflow Integration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate the refiner evaluation framework with MLflow for cross-run comparison (metrics) and experiment lifecycle tracking (params, artifacts, LLM call traces).

**Architecture:** A `tracking.py` module handles all MLflow interactions (params, metrics, artifacts, run linking via `.mlflow-run-id`). `debug.py` gets a dual-write extension to create MLflow trace spans alongside JSON files. The CLI gains `--track` flags on `run`/`evaluate` and a new `track` command for backfilling. MLflow is an optional dependency — everything works without it.

**Tech Stack:** mlflow>=2.14 (optional), typer (CLI), subprocess (git context)

**Spec:** `docs/superpowers/specs/2026-04-02-mlflow-integration-design.md`

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `refiner/pyproject.toml` | Modify | Add `mlflow>=2.14` as optional `[tracking]` dependency |
| `refiner/src/refiner/tracking.py` | Create | Core MLflow logic: git context, metric flattening, artifact upload, run linking |
| `refiner/src/refiner/debug.py` | Modify | Add MLflow trace span creation alongside existing JSON file writes |
| `refiner/src/refiner/cli.py` | Modify | Add `--track`/`--tracking-uri`/`--description` to `run` and `evaluate`; add `track` command |
| `refiner/tests/test_tracking.py` | Create | Tests for `tracking.py` (metric flattening, git context, artifact whitelisting, run linking) |
| `refiner/tests/test_debug_tracing.py` | Create | Tests for `debug.py` MLflow dual-write behavior |

---

### Task 1: Add MLflow optional dependency

**Files:**
- Modify: `refiner/pyproject.toml`

- [ ] **Step 1: Add optional dependency group**

In `refiner/pyproject.toml`, add after the `[dependency-groups]` section:

```toml
[project.optional-dependencies]
tracking = ["mlflow>=2.14"]
```

- [ ] **Step 2: Install with tracking extra**

Run: `cd refiner && uv pip install -e ".[tracking]"`
Expected: mlflow installed successfully

- [ ] **Step 3: Verify mlflow is importable**

Run: `cd refiner && uv run python -c "import mlflow; print(mlflow.__version__)"`
Expected: Version >= 2.14 printed

- [ ] **Step 4: Verify existing tests still pass**

Run: `cd refiner && uv run pytest tests/ -x -q`
Expected: All 221+ tests pass

- [ ] **Step 5: Commit**

```bash
git add refiner/pyproject.toml
git commit -m "build(refiner): add mlflow as optional tracking dependency"
```

---

### Task 2: Create tracking module — git context and metric flattening

**Files:**
- Create: `refiner/src/refiner/tracking.py`
- Create: `refiner/tests/test_tracking.py`

- [ ] **Step 1: Write tests for `_get_git_context()`**

Create `refiner/tests/test_tracking.py`:

```python
import subprocess
from unittest.mock import patch

from refiner.tracking import _get_git_context


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
```

- [ ] **Step 2: Write tests for `_flatten_metrics()`**

Append to `refiner/tests/test_tracking.py`:

```python
from refiner.tracking import _flatten_metrics


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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd refiner && uv run pytest tests/test_tracking.py -v`
Expected: FAIL — `tracking` module doesn't exist yet

- [ ] **Step 4: Implement `_get_git_context()` and `_flatten_metrics()`**

Create `refiner/src/refiner/tracking.py`:

```python
"""MLflow tracking integration for the refiner pipeline."""

import subprocess
from pathlib import Path


def _get_git_context() -> tuple[str, bool]:
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL
        ).decode().strip()
        dirty = bool(subprocess.check_output(
            ["git", "status", "--porcelain"], stderr=subprocess.DEVNULL
        ).decode().strip())
        return sha, dirty
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown", False


def _flatten_metrics(evaluation: dict) -> dict[str, float]:
    metrics: dict[str, float] = {}

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

    gen = evaluation.get("generation_metrics", {})
    if ad := gen.get("axis_diversity"):
        metrics["generation.axis_diversity"] = ad["overall_mean"]
    if ec := gen.get("enumeration_concentration"):
        metrics["generation.enum_concentration_top5"] = ec["top_k_share"]

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

    if je := evaluation.get("judge_evaluation", {}).get("aggregates"):
        for dim in ("subtlety", "plausibility", "domain_grounding", "policy_relevance"):
            if dim_data := je.get(dim):
                metrics[f"judge.{dim}"] = dim_data["mean"]

    return metrics
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd refiner && uv run pytest tests/test_tracking.py -v`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add refiner/src/refiner/tracking.py refiner/tests/test_tracking.py
git commit -m "feat(refiner): add tracking module with git context and metric flattening"
```

---

### Task 3: Tracking module — artifact whitelisting and run linking

**Files:**
- Modify: `refiner/src/refiner/tracking.py`
- Modify: `refiner/tests/test_tracking.py`

- [ ] **Step 1: Write tests for `_collect_artifacts()` and run ID file helpers**

Append to `refiner/tests/test_tracking.py`:

```python
from refiner.tracking import _collect_artifacts, read_run_id, write_run_id


def test_collect_artifacts_whitelists(tmp_path):
    # Create whitelisted files
    (tmp_path / "swb-taxonomy.yaml").write_text("x")
    (tmp_path / "swb-evaluation.json").write_text("x")
    (tmp_path / "swb-evaluation.html").write_text("x")
    (tmp_path / "dataset.jsonl").write_text("x")
    (tmp_path / "adversarial_prompts.jsonl").write_text("x")
    (tmp_path / "assessment.md").write_text("x")
    # Create files that should be excluded
    (tmp_path / ".mlflow-run-id").write_text("abc123")
    (tmp_path / "random-file.txt").write_text("x")

    files, dirs = _collect_artifacts(tmp_path)
    names = {f.name for f in files}
    assert "swb-taxonomy.yaml" in names
    assert "swb-evaluation.json" in names
    assert "swb-evaluation.html" in names
    assert "dataset.jsonl" in names
    assert "adversarial_prompts.jsonl" in names
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd refiner && uv run pytest tests/test_tracking.py::test_collect_artifacts_whitelists -v`
Expected: FAIL — functions not defined

- [ ] **Step 3: Implement `_collect_artifacts()`, `read_run_id()`, `write_run_id()`**

Add to `refiner/src/refiner/tracking.py`:

```python
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


def _collect_artifacts(output_dir: Path) -> tuple[list[Path], list[Path]]:
    files = []
    for pattern in _ARTIFACT_PATTERNS:
        files.extend(output_dir.glob(pattern))
    dirs = []
    debug_dir = output_dir / "debug"
    if debug_dir.is_dir():
        dirs.append(debug_dir)
    return files, dirs


def write_run_id(output_dir: Path, run_id: str) -> None:
    (output_dir / _RUN_ID_FILE).write_text(run_id)


def read_run_id(output_dir: Path) -> str | None:
    path = output_dir / _RUN_ID_FILE
    if path.exists():
        return path.read_text().strip()
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd refiner && uv run pytest tests/test_tracking.py -v`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add refiner/src/refiner/tracking.py refiner/tests/test_tracking.py
git commit -m "feat(refiner): add artifact collection and run ID linking to tracking module"
```

---

### Task 4: Tracking module — `log_run_to_mlflow()` with MLflow calls

**Files:**
- Modify: `refiner/src/refiner/tracking.py`
- Modify: `refiner/tests/test_tracking.py`

- [ ] **Step 1: Write tests for `_extract_params()` and `_extract_tags()`**

Append to `refiner/tests/test_tracking.py`:

```python
from unittest.mock import patch
from refiner.tracking import _extract_params, _extract_tags


def test_extract_params():
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
    evaluation = {"run": {"model": "test", "policy_set": "test.json"}}
    with patch("refiner.tracking._get_git_context", return_value=("unknown", False)):
        params = _extract_params(evaluation)
    assert params["selected_domains"] == ""


def test_extract_tags_with_description():
    evaluation = {
        "run": {"timestamp": "2026-04-02T10:00:00Z", "stages_completed": ["classify", "map_risks"]},
    }
    tags = _extract_tags(evaluation, description="added sibling fallback")
    assert tags["description"] == "added sibling fallback"
    assert tags["timestamp"] == "2026-04-02T10:00:00Z"
    assert tags["stages_completed"] == "classify,map_risks"


def test_extract_tags_no_description():
    evaluation = {"run": {"timestamp": "2026-04-02T10:00:00Z", "stages_completed": []}}
    tags = _extract_tags(evaluation, description=None)
    assert "description" not in tags
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd refiner && uv run pytest tests/test_tracking.py::test_extract_params -v`
Expected: FAIL

- [ ] **Step 3: Implement `_extract_params()` and `_extract_tags()`**

Add to `refiner/src/refiner/tracking.py`:

```python
def _extract_params(evaluation: dict) -> dict[str, str]:
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
    run = evaluation.get("run", {})
    tags: dict[str, str] = {
        "timestamp": run.get("timestamp", "unknown"),
        "stages_completed": ",".join(run.get("stages_completed", [])),
    }
    if description:
        tags["description"] = description
    return tags
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd refiner && uv run pytest tests/test_tracking.py -v`
Expected: All tests pass

- [ ] **Step 5: Write test for `log_run_to_mlflow()` (mocked MLflow)**

Append to `refiner/tests/test_tracking.py`:

```python
from unittest.mock import MagicMock, call


def test_log_run_to_mlflow_new_run(tmp_path):
    # Create minimal evaluation file and artifacts
    evaluation = {
        "run": {"model": "test-model", "policy_set": "test.json",
                "timestamp": "2026-04-02T10:00:00Z", "stages_completed": ["classify"]},
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
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd refiner && uv run pytest tests/test_tracking.py::test_log_run_to_mlflow_new_run -v`
Expected: FAIL

- [ ] **Step 7: Implement `log_run_to_mlflow()`**

Add to `refiner/src/refiner/tracking.py`:

```python
def _experiment_name(policy_set: str) -> str:
    return policy_set.removesuffix(".json")


def log_run_to_mlflow(
    evaluation: dict,
    output_dir: Path,
    tracking_uri: str,
    description: str | None = None,
    run_id: str | None = None,
) -> str:
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
```

- [ ] **Step 8: Run all tracking tests**

Run: `cd refiner && uv run pytest tests/test_tracking.py -v`
Expected: All tests pass

- [ ] **Step 9: Commit**

```bash
git add refiner/src/refiner/tracking.py refiner/tests/test_tracking.py
git commit -m "feat(refiner): add log_run_to_mlflow with params, metrics, artifacts"
```

---

### Task 5: Dual-write tracing in `debug.py`

**Files:**
- Modify: `refiner/src/refiner/debug.py`
- Create: `refiner/tests/test_debug_tracing.py`

- [ ] **Step 1: Write tests for MLflow span creation**

Create `refiner/tests/test_debug_tracing.py`:

```python
from unittest.mock import MagicMock, patch
from refiner.debug import configure, log_call


def test_log_call_creates_span_when_mlflow_active(tmp_path):
    configure(tmp_path)
    mock_mlflow = MagicMock()
    mock_mlflow.active_run.return_value = MagicMock()
    mock_span = MagicMock()
    mock_mlflow.start_span.return_value = mock_span

    with patch.dict("sys.modules", {"mlflow": mock_mlflow}):
        log_call("classify", [{"role": "user", "content": "test"}], "response")

    mock_mlflow.start_span.assert_called_once_with(name="classify")
    mock_span.set_inputs.assert_called_once()
    mock_span.set_outputs.assert_called_once()
    mock_span.end.assert_called_once()


def test_log_call_span_name_includes_slug(tmp_path):
    configure(tmp_path)
    mock_mlflow = MagicMock()
    mock_mlflow.active_run.return_value = MagicMock()
    mock_span = MagicMock()
    mock_mlflow.start_span.return_value = mock_span

    with patch.dict("sys.modules", {"mlflow": mock_mlflow}):
        log_call(
            "map_risks", [{"role": "user", "content": "test"}], "response",
            context={"policy_concept": "Illegal Activity"},
        )

    mock_mlflow.start_span.assert_called_once_with(name="map_risks-illegal-activity")


def test_log_call_sets_attributes_from_context(tmp_path):
    configure(tmp_path)
    mock_mlflow = MagicMock()
    mock_mlflow.active_run.return_value = MagicMock()
    mock_span = MagicMock()
    mock_mlflow.start_span.return_value = mock_span
    ctx = {"policy_concept": "Fraud", "num_candidates": 5}

    with patch.dict("sys.modules", {"mlflow": mock_mlflow}):
        log_call("anchor", [{"role": "user", "content": "test"}], "response", context=ctx)

    mock_span.set_attributes.assert_called_once_with(ctx)


def test_log_call_no_span_when_mlflow_inactive(tmp_path):
    configure(tmp_path)
    mock_mlflow = MagicMock()
    mock_mlflow.active_run.return_value = None

    with patch.dict("sys.modules", {"mlflow": mock_mlflow}):
        log_call("classify", [{"role": "user", "content": "test"}], "response")

    mock_mlflow.start_span.assert_not_called()


def test_log_call_no_span_when_mlflow_not_installed(tmp_path):
    configure(tmp_path)
    # Ensure mlflow is not importable
    with patch.dict("sys.modules", {"mlflow": None}):
        # Should not raise — graceful fallback
        log_call("classify", [{"role": "user", "content": "test"}], "response")

    # Verify JSON file was still written
    files = list(tmp_path.glob("*.json"))
    assert len(files) >= 1


def test_log_call_json_still_written_with_mlflow(tmp_path):
    """Dual-write: JSON file AND span both created."""
    configure(tmp_path)
    mock_mlflow = MagicMock()
    mock_mlflow.active_run.return_value = MagicMock()
    mock_mlflow.start_span.return_value = MagicMock()

    with patch.dict("sys.modules", {"mlflow": mock_mlflow}):
        log_call("classify", [{"role": "user", "content": "test"}], "response")

    files = list(tmp_path.glob("*.json"))
    assert len(files) >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd refiner && uv run pytest tests/test_debug_tracing.py -v`
Expected: FAIL — `log_call` doesn't create spans yet

- [ ] **Step 3: Modify `debug.py` to add MLflow tracing**

In `refiner/src/refiner/debug.py`, refactor `log_call` to extract slug earlier and add the MLflow span block. The full function becomes:

```python
def log_call(
    stage: str,
    messages: list[dict],
    response,
    *,
    context: dict | None = None,
) -> None:
    global _call_counter
    _call_counter += 1

    # Build slug from context (reused for JSON filename and span name)
    slug = ""
    if context:
        for key in ("policy_concept", "risk_name", "risk_id"):
            if key in context:
                slug = "-" + context[key].lower().replace(" ", "-")[:40]
                break

    # Extract response data
    if hasattr(response, "model_dump"):
        response_data = response.model_dump()
    elif isinstance(response, list):
        response_data = [r.model_dump() if hasattr(r, "model_dump") else r for r in response]
    else:
        response_data = str(response)

    # JSON file (existing behavior)
    if _debug_dir is not None:
        entry = {
            "call_number": _call_counter,
            "stage": stage,
            "messages": messages,
            "response": response_data,
        }
        if context:
            entry["context"] = context

        filename = f"{_call_counter:02d}-{stage}{slug}.json"
        path = _debug_dir / filename
        path.write_text(json.dumps(entry, indent=2, default=str))
        logger.debug("Debug log written to %s", path)

    # MLflow tracing (conditional)
    try:
        import mlflow
        if mlflow.active_run():
            span = mlflow.start_span(name=f"{stage}{slug}")
            span.set_inputs({"messages": messages})
            span.set_outputs({"response": response_data})
            if context:
                span.set_attributes(context)
            span.end()
    except ImportError:
        pass
    except Exception:
        logger.debug("MLflow span creation failed", exc_info=True)
```

**Key changes from original:**
- Slug extraction moved before the `if _debug_dir` block (was inside it)
- `response_data` extraction moved before the `if _debug_dir` block (was inside it)
- MLflow tracing block added at the end
- The early `if _debug_dir is None: return` is removed — tracing should work even without debug dir

- [ ] **Step 4: Run tracing tests to verify they pass**

Run: `cd refiner && uv run pytest tests/test_debug_tracing.py -v`
Expected: All tests pass

- [ ] **Step 5: Run ALL existing tests to verify no regressions**

Run: `cd refiner && uv run pytest tests/ -x -q`
Expected: All 221+ tests pass (existing debug behavior unchanged)

- [ ] **Step 6: Commit**

```bash
git add refiner/src/refiner/debug.py refiner/tests/test_debug_tracing.py
git commit -m "feat(refiner): add MLflow trace spans to debug.log_call dual-write"
```

---

### Task 6: CLI — `--track` flag on `refiner evaluate`

**Files:**
- Modify: `refiner/src/refiner/cli.py`

- [ ] **Step 1: Add `--track`, `--tracking-uri`, `--description` flags to `evaluate` command**

In `refiner/src/refiner/cli.py`, add three new parameters to the `evaluate` function signature (after `output`):

```python
    track: bool = typer.Option(False, "--track", help="Log evaluation to MLflow"),
    tracking_uri: str = typer.Option(None, "--tracking-uri", envvar="MLFLOW_TRACKING_URI", help="MLflow tracking server URI"),
    description: str = typer.Option(None, "--description", help="Human-readable description for this run"),
```

- [ ] **Step 2: Add tracking logic at end of `evaluate` command**

After the HTML report is written (after `typer.echo(f"HTML report written to {html_path}")`), add:

```python
    if track:
        try:
            from refiner.tracking import log_run_to_mlflow, read_run_id, write_run_id
        except ImportError:
            typer.echo("Error: MLflow is required for --track. Install with: uv pip install -e \".[tracking]\"", err=True)
            raise typer.Exit(1)

        if not tracking_uri:
            typer.echo("Error: --tracking-uri or MLFLOW_TRACKING_URI is required for --track", err=True)
            raise typer.Exit(1)

        existing_run_id = read_run_id(output_dir)
        run_id = log_run_to_mlflow(
            evaluation, output_dir, tracking_uri,
            description=description, run_id=existing_run_id,
        )
        if not existing_run_id:
            write_run_id(output_dir, run_id)
        typer.echo(f"Logged to MLflow: run {run_id}")
```

- [ ] **Step 3: Verify existing tests still pass**

Run: `cd refiner && uv run pytest tests/ -x -q`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add refiner/src/refiner/cli.py
git commit -m "feat(refiner): add --track flag to refiner evaluate for MLflow logging"
```

---

### Task 7: CLI — `--track` flag on `refiner run`

**Files:**
- Modify: `refiner/src/refiner/cli.py`

- [ ] **Step 1: Add `--track`, `--tracking-uri`, `--description` flags to `run` command**

In `refiner/src/refiner/cli.py`, add three new parameters to the `run` function signature (after `nexus_chroma_dir`):

```python
    track: bool = typer.Option(False, "--track", help="Enable MLflow tracking + tracing"),
    tracking_uri: str = typer.Option(None, "--tracking-uri", envvar="MLFLOW_TRACKING_URI", help="MLflow tracking server URI"),
    description: str = typer.Option(None, "--description", help="Human-readable description for this run"),
```

- [ ] **Step 2: Add MLflow run lifecycle around pipeline execution**

In the `run` command, after `out.mkdir(parents=True, exist_ok=True)` and before `client_slug = policy_json.stem`, add the MLflow setup. Then wrap the pipeline + output section in try/finally. The tracking block is:

```python
    mlflow_active = False
    if track:
        try:
            import mlflow
            from refiner.tracking import _get_git_context, write_run_id
        except ImportError:
            typer.echo("Error: MLflow is required for --track. Install with: uv pip install -e \".[tracking]\"", err=True)
            raise typer.Exit(1)

        if not tracking_uri:
            typer.echo("Error: --tracking-uri or MLFLOW_TRACKING_URI is required for --track", err=True)
            raise typer.Exit(1)

        mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_experiment(policy_json.stem)
        mlflow.start_run()
        mlflow_active = True

        git_sha, git_dirty = _get_git_context()
        mlflow.log_params({
            "model": config.model,
            "policy_set": policy_json.name,
            "git_sha": git_sha,
            "git_dirty": str(git_dirty),
        })
        if description:
            mlflow.set_tag("description", description)

        write_run_id(out, mlflow.active_run().info.run_id)

    try:
        # ... existing pipeline + output code (indented inside try) ...
        pass  # placeholder — the existing code goes here
    except Exception:
        if mlflow_active:
            import mlflow
            mlflow.end_run(status="FAILED")
        raise
    else:
        if mlflow_active:
            import mlflow
            # Log output artifacts
            from refiner.tracking import _collect_artifacts
            files, dirs = _collect_artifacts(out)
            for f in files:
                mlflow.log_artifact(str(f))
            for d in dirs:
                mlflow.log_artifacts(str(d), artifact_path=d.name)
            run_id = mlflow.active_run().info.run_id
            mlflow.end_run()
            typer.echo(f"Logged to MLflow: run {run_id}")
```

Note: The existing pipeline code (from `client_slug = policy_json.stem` through the end of the output section) moves inside the `try` block. This is a structural change — be careful to preserve all existing logic.

- [ ] **Step 3: Verify existing tests still pass**

Run: `cd refiner && uv run pytest tests/ -x -q`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add refiner/src/refiner/cli.py
git commit -m "feat(refiner): add --track flag to refiner run for MLflow tracing"
```

---

### Task 8: CLI — `refiner track` backfill command

**Files:**
- Modify: `refiner/src/refiner/cli.py`

- [ ] **Step 1: Add `track` command**

In `refiner/src/refiner/cli.py`, add a new command:

```python
@app.command()
def track(
    output_dir: Path = typer.Argument(..., help="Directory with evaluation outputs to track"),
    tracking_uri: str = typer.Option(None, "--tracking-uri", envvar="MLFLOW_TRACKING_URI", help="MLflow tracking server URI"),
    description: str = typer.Option(None, "--description", help="Human-readable description for this run"),
):
    """Retroactively log an existing evaluation to MLflow."""
    if not output_dir.is_dir():
        typer.echo(f"Error: {output_dir} is not a directory", err=True)
        raise typer.Exit(1)

    try:
        from refiner.tracking import log_run_to_mlflow, read_run_id, write_run_id
    except ImportError:
        typer.echo("Error: MLflow is required. Install with: uv pip install -e \".[tracking]\"", err=True)
        raise typer.Exit(1)

    if not tracking_uri:
        typer.echo("Error: --tracking-uri or MLFLOW_TRACKING_URI is required", err=True)
        raise typer.Exit(1)

    from refiner.evaluate import _discover_file
    eval_path = _discover_file(output_dir, "*-evaluation.json")
    if not eval_path:
        typer.echo(f"Error: no *-evaluation.json found in {output_dir}", err=True)
        raise typer.Exit(1)

    evaluation = json.loads(eval_path.read_text())
    existing_run_id = read_run_id(output_dir)

    run_id = log_run_to_mlflow(
        evaluation, output_dir, tracking_uri,
        description=description, run_id=existing_run_id,
    )
    if not existing_run_id:
        write_run_id(output_dir, run_id)
    typer.echo(f"Logged to MLflow: run {run_id}")
```

- [ ] **Step 2: Verify the command appears in help**

Run: `cd refiner && uv run refiner --help`
Expected: `track` command listed alongside `run`, `emit`, `evaluate`, `ingest`

- [ ] **Step 3: Verify existing tests still pass**

Run: `cd refiner && uv run pytest tests/ -x -q`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add refiner/src/refiner/cli.py
git commit -m "feat(refiner): add refiner track command for retroactive MLflow logging"
```

---

### Task 9: Integration smoke test

**Files:**
- Modify: `refiner/tests/test_tracking.py`

- [ ] **Step 1: Write integration test with mocked MLflow**

Append to `refiner/tests/test_tracking.py`:

```python
import json


def test_log_run_to_mlflow_reopens_existing_run(tmp_path):
    """When .mlflow-run-id exists, reopen that run instead of creating new."""
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
    evaluation = {
        "run": {"model": "gemma2", "policy_set": "generic.json",
                "timestamp": "2026-04-02T12:00:00Z",
                "stages_completed": ["classify", "map_risks"]},
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
```

- [ ] **Step 2: Run all tests**

Run: `cd refiner && uv run pytest tests/test_tracking.py tests/test_debug_tracing.py -v`
Expected: All tests pass

- [ ] **Step 3: Run full test suite for regressions**

Run: `cd refiner && uv run pytest tests/ -x -q`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add refiner/tests/test_tracking.py
git commit -m "test(refiner): add integration smoke tests for MLflow tracking flow"
```
