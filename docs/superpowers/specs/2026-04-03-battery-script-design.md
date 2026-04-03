# Battery Script — Design Spec

**Date:** 2026-04-03
**Status:** Draft

## Problem

The justfile has grown complex with bash-heavy orchestration for running the pipeline across all policies and models. The `run-all` recipe uses bash arrays for PID tracking, wait loops, log routing, and duplicated policy-file resolution logic across every recipe. This is hard to read, test, and extend.

## Solution

Port all pipeline orchestration to a standalone Python script (`scripts/run_battery.py`) with a YAML config file (`battery.yaml`). The justfile is reduced to `index-ontologies`, `ingest-doc`, and a thin `battery` alias.

## Script Location

`scripts/run_battery.py` — invoked as `uv run scripts/run_battery.py <run-name> [options]` or via `just battery <run-name> [options]`.

No packaging — standalone script using PEP 723 inline metadata for dependencies:

```python
# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml"]
# ///
```

## Config File

`battery.yaml` at the repo root. All paths, settings, policies, and models in one place:

```yaml
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

- Paths can be absolute or relative to the repo root.
- `REFINER_API_KEY` is read from the environment (not stored in the config file).
- `models.json` is superseded by the `models` section in `battery.yaml`.

## CLI Interface

```
uv run scripts/run_battery.py <run-name> [options]

Positional:
  run-name              Name suffix for this battery run

Options:
  --config PATH         Config file (default: battery.yaml)
  --policy NAME         Run only this policy (repeatable; default: all from config)
  --model NAME          Run only this model (repeatable; default: all from config)
  --skip-ingest         Skip the ingest stage
  --skip-refine         Skip the refine stage (for regen workflows)
  --skip-generate       Skip the redteam generation stage (also skips evaluate)
  --tags TAG            Run tags forwarded to refiner (repeatable)
  --dry-run             Print commands that would be executed, don't run them
```

## Parallelism

- One subprocess per model, all models in parallel.
- Within each model, policies run sequentially.
- Each model's combined stdout/stderr goes to `<runs_dir>/<model>-<run>.log`.
- Console output shows a progress line per model start/completion (e.g. `=== Starting phi-4 ===`, `=== phi-4 done ===`).

This matches the current justfile behavior. The rationale: each model endpoint is independent, but ChromaDB locks and endpoint rate limits make per-policy parallelism unnecessary. Uses `ThreadPoolExecutor` since the work is I/O-bound (waiting for child processes).

## Pipeline Stages

For each (policy, model) combination, the following stages run in order:

### 1. Ingest (skipped with `--skip-ingest`)

```
cd refiner && uv run refiner ingest <policy-file> \
    --output <run-dir>/<policy>-enriched.json \
    --base-url <model-url> \
    --model <model-name> \
    --api-key <api-key>
```

### 2. Refine (skipped with `--skip-refine`)

```
cd refiner && uv run refiner run <input-file> \
    --output <run-dir> \
    --debug <run-dir>/debug \
    --base-url <model-url> \
    --model <model-name> \
    --api-key <api-key> \
    --nexus-base-dir <nexus-base-dir> \
    --ontoquery-chroma-dir <tmp-onto-snapshot> \
    --nexus-chroma-dir <tmp-nexus-snapshot> \
    --track \
    --tracking-uri <tracking-uri> \
    [--tag TAG ...]
```

ChromaDB directories are snapshotted to per-model temp dirs before the model's policy loop begins and reused across all policies for that model. This is safe because the refine stage is read-only against ChromaDB — it queries but never writes. Temp dirs are cleaned up on completion (success or failure).

### 3. Emit

```
cd refiner && uv run refiner emit <run-dir> \
    --policies <policy-file> \
    --samples-per-risk <n> \
    --output <run-dir>/dataset.jsonl
```

### 4. Generate (skipped with `--skip-generate`)

```
cd redteam && uv run redteam <run-dir>/dataset.jsonl \
    --model hosted_vllm/<model-name> \
    --api-base <model-url> \
    [--api-key <api-key>] \
    --concurrency 5 \
    --output <run-dir>/adversarial_prompts.jsonl
```

`--api-key` is omitted when `REFINER_API_KEY` is unset or empty (the redteam CLI falls back to `OPENAI_API_KEY` from environment).

### 5. Evaluate (skipped when `--skip-generate` is set)

```
cd refiner && uv run refiner evaluate <run-dir> \
    --emit <run-dir>/dataset.jsonl \
    --adversarial <run-dir>/adversarial_prompts.jsonl \
    --policies <policy-file> \
    --track \
    --tracking-uri <tracking-uri> \
    [--tag TAG ...]
```

Evaluate depends on adversarial prompts from the generate stage. When `--skip-generate` is used, evaluate is also skipped since `adversarial_prompts.jsonl` won't exist.

## Policy File Resolution

Shared logic used by all stages:

1. If enriched file exists at `<run-dir>/<policy>-enriched.json`, use it (for stages after ingest).
2. Else look for `<policy_dir>/<policy>.json`.
3. Else look for `<policy_dir>/<policy>.md`.
4. Else raise an error.

For ingest, always use the raw policy file (step 2/3). For refine/emit/evaluate, prefer enriched (step 1).

## Output Structure

Unchanged from current layout:

```
runs/
  <policy>-<model>-<run>/
    <policy>-enriched.json
    debug/
    dataset.jsonl
    adversarial_prompts.jsonl
    ...
  <model>-<run>.log          # per-model log
```

## Error Handling

- If a stage fails for a policy, remaining stages for that policy are skipped.
- The model continues to the next policy.
- A summary table is printed at the end showing pass/fail per (policy, model):
  ```
                phi-4    gemma-2-9b    gemma-3-12b
  swb            OK        OK          FAIL
  generic        OK        FAIL        OK
  ```
- Exit code 1 if any combination failed.

## Dry Run

`--dry-run` prints each command that would be executed, with the working directory, without running anything. Useful for verifying config and argument construction.

## Justfile After Port

```just
# Index all ontologies into ontoquery ChromaDB
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

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `REFINER_API_KEY` | API key passed to ingest/refine/generate stages. Omitted from generate command when unset/empty. |
| `MLFLOW_TRACKING_INSECURE_TLS` | Set to `true` automatically by the script |

`REFINER_RUN_TAGS` (used by the old justfile) is superseded by the `--tags` CLI flag.

All other configuration comes from `battery.yaml`. `--config` defaults to `battery.yaml` relative to CWD (expected to be the repo root).

## Dependencies

The script uses only:
- Python stdlib (`argparse`, `subprocess`, `pathlib`, `tempfile`, `shutil`, `os`, `concurrent.futures`)
- `pyyaml` (for config parsing — declared via PEP 723 inline metadata, resolved automatically by `uv run`)
