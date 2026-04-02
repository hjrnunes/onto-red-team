# MLflow Integration Design

## Purpose

Integrate the refiner evaluation framework with MLflow for two goals:

1. **Cross-run comparison** — compare evaluation metrics across runs with different models, prompt templates, pipeline logic, and ontology configurations side-by-side in MLflow's UI.
2. **Experiment lifecycle** — track the full pipeline execution (run → emit → evaluate) as a single MLflow run with parameters, metrics, artifacts, and LLM call traces.

## Scope

- MLflow tracking wraps `refiner run` (for tracing) and `refiner evaluate` (for metrics/artifacts).
- A standalone `refiner track` command enables retroactive logging of existing runs.
- `refiner ingest` is excluded — it's a preprocessing step that produces a `PolicyDocument`; its outputs feed into `refiner run` where tracking begins. Adding tracing to ingest can be revisited if ingestion quality becomes a comparison axis.
- Prompt Registry is excluded — git SHA + tracing adequately covers prompt template versioning for the current workflow.

## Architecture

### Components

```
refiner/src/refiner/
  tracking.py    # NEW — core MLflow logging logic
  debug.py       # MODIFIED — dual-write: JSON file + MLflow trace span
  cli.py         # MODIFIED — --track, --tracking-uri, --description flags; new track command
  pyproject.toml # MODIFIED — mlflow optional dependency
```

### Data Flow

```
refiner run --track
  ├── mlflow.start_run() → creates MLflow run, writes .mlflow-run-id
  ├── pipeline executes → debug.log_call() creates trace spans per LLM call
  └── logs output artifacts (taxonomy, domain context, report YAML)

refiner evaluate --track
  ├── reads .mlflow-run-id → reopens existing run (or creates new)
  ├── computes all metrics
  └── logs flattened metrics + evaluation artifacts (JSON, HTML, adversarial JSONL, etc.)

refiner track <output-dir>
  ├── reads *-evaluation.json
  ├── reads .mlflow-run-id → reopens existing run (or creates new)
  └── logs params + metrics + artifacts (no traces — those require live execution)
```

## Tracking Module (`tracking.py`)

Single main function:

```python
def log_run_to_mlflow(
    evaluation: dict,
    output_dir: Path,
    tracking_uri: str,
    description: str | None = None,
) -> str:  # returns MLflow run ID
```

Responsibilities:
- Derive experiment name from `evaluation["run"]["policy_set"]` (strip `.json` suffix).
- Create or get experiment via `mlflow.set_experiment()`.
- Capture git context by shelling out to `git rev-parse HEAD` and `git status --porcelain`.
- Open (or reopen) an MLflow run, log params/metrics/artifacts, return the run ID.

### Run Linking

`refiner run --track` writes a `.mlflow-run-id` file (containing the MLflow run ID) to the output directory. When `refiner evaluate --track` or `refiner track` finds this file, it reopens the same run to append metrics and artifacts. If the file doesn't exist, a new run is created.

This ensures traces (from `run`) and metrics (from `evaluate`) live together on the same MLflow run.

### Git Context

Captured at tracking time inside `tracking.py`, with graceful fallback if git is unavailable:

```python
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
```

Logged as MLflow parameters. Captures the code state (prompt templates, pipeline logic, filtering rules) that produced the evaluation.

## What Gets Logged

### Parameters

| Parameter | Source |
|---|---|
| `model` | `evaluation["run"]["model"]` |
| `policy_set` | `evaluation["run"]["policy_set"]` |
| `selected_domains` | Stage quality → `identify_domains.selected_domains` (comma-joined; `""` if absent on partial runs) |
| `git_sha` | `git rev-parse HEAD` |
| `git_dirty` | `bool(git status --porcelain)` |

### Tags

| Tag | Source |
|---|---|
| `description` | `--description` flag (optional human note) |
| `timestamp` | `evaluation["run"]["timestamp"]` |
| `stages_completed` | Comma-joined list from evaluation |

### Metrics

Flattened scalar values for MLflow's comparison UI. Dot-separated names for grouping.

**Coverage:**

| Metric | Source |
|---|---|
| `coverage.total_risks_matched` | `coverage.risk_framework.total_matched` |
| `coverage.single_value_axis_rate` | `coverage.single_value_axis_dominance.single_value_rate` |
| `coverage.enum_domain_mismatch_rate` | `coverage.enumeration_domain_mismatch.mismatch_rate` |
| `coverage.sibling_mean_score` | `coverage.sibling_relevance.sibling_mean_score` |
| `coverage.subclass_mean_score` | `coverage.sibling_relevance.subclass_mean_score` |
| `coverage.cross_mapping_utilization` | Derived in `tracking.py`: `risks_with_cross_mappings / (risks_with + risks_without)` from `coverage.cross_mapping` |

**Generation:**

| Metric | Source |
|---|---|
| `generation.axis_diversity` | `generation_metrics.axis_diversity.overall_mean` |
| `generation.enum_concentration_top5` | `generation_metrics.enumeration_concentration.top_k_share` |

**Prompt quality:**

| Metric | Source |
|---|---|
| `prompt.lexical_diversity` | `prompt_metrics.lexical_diversity` |
| `prompt.mean_length` | `prompt_metrics.mean_prompt_length` |
| `prompt.domain_term_hit_rate` | `prompt_metrics.domain_term_hit_rate` |
| `prompt.red_flag_count` | `prompt_metrics.red_flag_count` |
| `prompt.coverage_balance` | `prompt_metrics.policy_coverage_balance.normalized_entropy` |
| `prompt.jargon_leak_rate` | `prompt_metrics.jargon_leak_rate.jargon_rate` |
| `prompt.axis_fidelity` | `prompt_metrics.axis_fidelity.mean_fidelity` |
| `prompt.entity_utilization` | `prompt_metrics.named_entity_utilization.utilization_rate` |
| `prompt.semantic_diversity` | `prompt_metrics.semantic_diversity.mean_pairwise_distance` |

**Judge (logged only when present):**

| Metric | Source |
|---|---|
| `judge.subtlety` | `judge_evaluation.aggregates.subtlety.mean` |
| `judge.plausibility` | `judge_evaluation.aggregates.plausibility.mean` |
| `judge.domain_grounding` | `judge_evaluation.aggregates.domain_grounding.mean` |
| `judge.policy_relevance` | `judge_evaluation.aggregates.policy_relevance.mean` |

Per-risk and per-policy breakdowns are not logged as metrics — they remain in the artifact files (evaluation JSON, HTML report).

### Conditional Metrics

Several metrics are only present when specific inputs were provided to `refiner evaluate`:

| Metric | Condition |
|---|---|
| `prompt.*` (all) | Requires `--adversarial` |
| `prompt.entity_utilization` | Requires `--adversarial` AND `--policies` |
| `coverage.enum_domain_mismatch_rate` | Requires `selected_domains` in stage quality (not present on partial runs) |
| `generation.*` (all) | Requires `--emit` |
| `judge.*` (all) | Requires `--judge` |

`tracking.py` uses `.get()` with guards — absent metrics are simply not logged. MLflow handles sparse metrics gracefully in comparison views.

### Artifacts

All files present in the output directory are uploaded:

| Artifact | Method |
|---|---|
| `*-taxonomy.yaml` | `mlflow.log_artifact()` |
| `*-domain-context.yaml` | `mlflow.log_artifact()` |
| `*-report.yaml` | `mlflow.log_artifact()` |
| `*-evaluation.json` | `mlflow.log_artifact()` |
| `*-evaluation.html` | `mlflow.log_artifact()` |
| `dataset.jsonl` | `mlflow.log_artifact()` |
| `adversarial_prompts.jsonl` | `mlflow.log_artifact()` |
| `adversarial_prompts.html` | `mlflow.log_artifact()` |
| `assessment.md` | `mlflow.log_artifact()` |
| `debug/` | `mlflow.log_artifacts(debug_dir, artifact_path="debug")` |

Artifact upload uses a whitelist of the glob patterns listed above. Internal files (`.mlflow-run-id`) and stale files from prior runs are excluded.

## Tracing via `debug.log_call()`

`debug.py` is modified to dual-write: JSON file (existing behavior) + MLflow trace span (new, when active).

```python
def log_call(stage, messages, response, *, context=None):
    global _call_counter
    _call_counter += 1

    # Build slug from context (reused for both JSON filename and span name)
    slug = ""
    if context:
        for key in ("policy_concept", "risk_name", "risk_id"):
            if key in context:
                slug = "-" + context[key].lower().replace(" ", "-")[:40]
                break

    # ... existing JSON file logic using slug (unchanged) ...

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
```

### Span Naming

Reuses the existing slug logic from debug file naming. Examples:
- `classify` (no context → no slug)
- `identify_domains` (no context → no slug)
- `map_risks-illegal-activity`
- `anchor-executive-compensation`
- `contextualize-data-leakage-via-llm`

This produces a readable timeline in MLflow's trace UI: you see the pipeline as a sequence of named LLM calls with full prompt/response payloads.

**Note:** Span duration reflects only the logging overhead, not the actual LLM call duration. The `log_call()` function runs after the LLM call completes. Adding actual timing would require wrapping the `client.chat.completions.create()` call, which contradicts the "no stage code changes" principle. The trace value here is the full prompt/response payloads, not latency measurement.

### No Stage Code Changes

Every LLM stage already calls `debug.log_call()`. Tracing is automatic — zero modifications to `classify.py`, `map_risks.py`, `anchor.py`, `contextualize.py`, or `identify_domains.py`.

### Import Guard

The `import mlflow` is inside the function, guarded by `try/except ImportError`. When mlflow is not installed, the existing JSON-file behavior is unaffected.

## CLI Integration

### `refiner run` — modified

New flags:

| Flag | Envvar | Default | Description |
|---|---|---|---|
| `--track` | — | `False` | Enable MLflow tracking + tracing |
| `--tracking-uri` | `MLFLOW_TRACKING_URI` | — | MLflow server URL |
| `--description` | — | `None` | Human note for the run |

Behavior when `--track` is passed:
1. Validate mlflow is importable (fail fast with install instructions).
2. `mlflow.set_tracking_uri(tracking_uri)`.
3. `mlflow.set_experiment(policy_json.stem)`.
4. `mlflow.start_run()` — log params (model, policy_set, git_sha, git_dirty), tag description.
5. Write `output_dir / .mlflow-run-id` containing the run ID (written early so evaluate can find it even if the pipeline crashes).
6. Pipeline executes inside `try/finally`. `debug.log_call()` creates trace spans.
7. On success: log output artifacts, `mlflow.end_run()`.
8. On failure: `mlflow.end_run(status="FAILED")`. The `.mlflow-run-id` remains so `evaluate --track` can later append metrics to the failed run if the outputs were partially written.

### `refiner evaluate` — modified

New flags:

| Flag | Envvar | Default | Description |
|---|---|---|---|
| `--track` | — | `False` | Log evaluation to MLflow |
| `--tracking-uri` | `MLFLOW_TRACKING_URI` | — | MLflow server URL |
| `--description` | — | `None` | Human note (only used if creating a new run) |

Behavior when `--track` is passed:
1. Run evaluation as normal (all metrics computed).
2. Check for `.mlflow-run-id` in output_dir:
   - **Found:** reopen that run via `mlflow.start_run(run_id=...)`.
   - **Not found:** create new run (standalone evaluate).
3. Call `log_run_to_mlflow()` — logs flattened metrics + artifacts.

### `refiner track` — new command

```
refiner track <output-dir> [--tracking-uri URI] [--description TEXT]
```

Reads `*-evaluation.json` from the output directory. Checks for `.mlflow-run-id`:
- **Found:** reopens and appends metrics + artifacts.
- **Not found:** creates a new run.

This is the backfill command for retroactively tracking existing runs in `runs/`.

### Shared Defaults

`--tracking-uri` falls back to the `MLFLOW_TRACKING_URI` envvar across all three commands. Set once in the shell:

```bash
export MLFLOW_TRACKING_URI=https://mlflow.taxonomy-refiner.orb.local
```

## Experiment Organization

One MLflow experiment per policy set. The experiment name is derived from the policy JSON filename stem:

| Policy file | Experiment name |
|---|---|
| `swb.json` | `swb` |
| `generic.json` | `generic` |
| `aramco.json` | `aramco` |

Runs within an experiment vary by model, git SHA (code/prompt changes), and configuration. Cross-run comparison answers: "did this change make prompts better for this policy set?"

Filtering by model or other dimensions uses MLflow's parameter/tag filtering in the runs table.

## Dependency Management

MLflow is an optional dependency:

```toml
[project.optional-dependencies]
tracking = ["mlflow>=2.14"]
```

- MLflow 2.14+ required (tracing API stabilization).
- Install with `uv pip install -e ".[tracking]"`.
- Without it, all existing functionality works unchanged.
- `tracking.py` is only imported when `--track` is used.
- `debug.py` uses `try/except ImportError` — silent no-op when mlflow is absent.

Runtime guard on `--track` flags:

```
Error: MLflow is required for --track. Install with: uv pip install -e ".[tracking]"
```

## Decisions

| Decision | Rationale |
|---|---|
| Evaluate-only boundary for metrics | Re-evaluation is cheap; don't force pipeline re-runs to track |
| `refiner run --track` for tracing | Tracing requires live instrumentation; `debug.log_call()` is the natural hook point |
| Same MLflow run for run + evaluate | Traces and metrics belong together; `.mlflow-run-id` links them |
| Git SHA as primary change tracker | Prompt templates and pipeline logic are code; git tracks them precisely |
| `--description` for human notes | Git SHA is precise but not readable; description adds "what I changed" context |
| Prompt Registry excluded | Git SHA + tracing captures prompt changes; registry adds complexity for a single-developer project with 5 tightly-coupled prompt templates |
| Optional dependency | MLflow is heavy; shouldn't be required for users who don't need tracking |
| No per-risk/per-policy metrics in MLflow | Too many dimensions; these stay in artifact files (evaluation JSON, HTML report) |
