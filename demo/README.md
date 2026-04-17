# ORT Demo

Self-contained Online Red Teaming demo pipeline. Takes a policy file and a model endpoint, runs the full ORT pipeline (refiner → emit → redteam → garak → ART report).

## Setup

```bash
cd demo
uv sync                          # core deps (pyyaml, jinja2)
uv sync --extra scan             # + garak for vulnerability scanning
```

Requires the refiner, redteam, and ontoquery sub-projects to be set up (indexed ontologies, ChromaDB populated).

## Quick Start

```bash
# Full pipeline: policy + model → ART report
demo run \
  --policy ../policy_examples/rdash-nhs.json \
  --model mistral-small-3-1-24b \
  --model-url https://model-serving.example.com/v1 \
  --config configs/garak.yaml

# Dry run (prints all commands without executing)
demo run \
  --policy ../policy_examples/rdash-nhs.json \
  --model mistral-small-3-1-24b \
  --model-url https://model-serving.example.com/v1 \
  --dry-run

# Skip garak scan (build datasets + report shell only)
demo run ... --skip-scan
```

Set `REFINER_API_KEY` and `OPENAICOMPATIBLE_API_KEY` env vars as needed.

## Pipeline Stages

| # | Stage | Tool | What |
|---|-------|------|------|
| 1 | Ingest | `refiner ingest` | Raw policy → enriched PolicyProfile |
| 2 | Refine | `refiner run` | PolicyProfile → domain context, risk landscape, taxonomy |
| 3 | Emit | `refiner emit` | Domain context → dataset JSONL (sampled axes, techniques) |
| 4 | Generate | `redteam` | Dataset → adversarial prompts via LLM |
| 5 | Prepare | in-process | Refiner artifacts → ORT intent mapping + garak CAS format |
| 6 | Utility | in-process | Generate blue-team/utility prompts for over-refusal testing |
| 7 | Scan | garak | Run EarlyStopHarness probe funnel against target model |
| 8 | Report | in-process | Build interactive HTML dashboard (PatternFly + Vega-Lite) |

Stages 1–4 shell out to the refiner/redteam CLIs. Stages 5–8 run in-process.

## Individual Stage Commands

Each stage can also be run independently (e.g. from an existing refiner run):

```bash
# Prepare ORT data from a refiner run
demo prepare --run-dir ../runs/gen18/rdash-nhs-gemma-4-26b-a4b-it-g18

# Generate utility/blue-team prompts
demo utility --run-dir ../runs/gen18/rdash-nhs-gemma-4-26b-a4b-it-g18 \
             --demo-dir demo_runs/rdash-nhs

# Run garak scan
demo scan --demo-dir demo_runs/rdash-nhs --config configs/garak.yaml

# Build ART report
demo report --demo-dir demo_runs/rdash-nhs \
            --run-dir ../runs/gen18/rdash-nhs-gemma-4-26b-a4b-it-g18
```

## Output Structure

```
demo_runs/<policy>-<model>/
├── refiner/                    # Refiner run artifacts
│   ├── *-domain-context.yaml
│   ├── *-policy-document.json
│   ├── *-adversarial-prompts.jsonl
│   └── debug/
├── intent_mapping.json         # S-number → risk metadata + cross-mappings
├── stubs.jsonl                 # Red-team stubs with IDs
├── utility_stubs.jsonl         # Blue-team stubs
├── data/cas/                   # Garak CAS (red-team)
│   ├── trait_typology.json
│   └── intent_stubs/*.json
├── data/cas_utility/           # Garak CAS (utility)
├── garak_runs/                 # Garak results
│   └── garak.<uuid>.report.jsonl
└── report.html                 # ORT-enriched ART report
```

## Garak Configuration

Copy and edit `configs/garak.yaml` for your setup. Key sections:

- **Target model** — endpoint for the model under test
- **Judge model** — MulticlassJudge for classifying responses (complied/rejected/alternative/other)
- **Probes** — EarlyStopHarness funnel: SPO → SPO+augmentation → Translation → TAP
- **Language providers** — Helsinki-NLP models for translation probes

## Notebook Usage

All modules expose importable functions:

```python
from pathlib import Path
from demo.pipeline import run_pipeline

# Full pipeline in one call
run_pipeline(
    Path("../policy_examples/rdash-nhs.json"),
    "mistral-small-3-1-24b",
    "https://model-serving.example.com/v1",
    garak_config=Path("configs/garak.yaml"),
)
```

Or stage by stage:

```python
from demo.prepare import prepare, build_intent_mapping, build_stubs
from demo.utility import generate_utility_stubs, utility
from demo.scan import run_garak
from demo.report import render_report

run_dir = Path("demo_runs/rdash-nhs/refiner")
demo_dir = Path("demo_runs/rdash-nhs")

prepare(run_dir, demo_dir)
utility(run_dir, demo_dir, samples_per_risk=5)
run_garak(Path("configs/garak.yaml"), demo_dir)
html = render_report(demo_dir, run_dir)
Path("demo_runs/rdash-nhs/report.html").write_text(html)
```
