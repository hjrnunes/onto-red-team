# Advisory System Prototype

Concept prototype demonstrating the advisory reasoning chain:
refiner output → AIROO coverage queries → Garak/NeMo config generation → SA-facing report.

## Setup

```bash
cd prototypes/advisory
uv sync --extra airoo
```

Requires AIROO at `../../trustyai-explainability/ai-risk-operational-ontology` (adjust path in `pyproject.toml` if needed).

## Usage

### From a refiner run

```bash
uv run python advise.py ../../runs/swb-mistral-small-3-1-24b-g10 \
  --policy ../../policy_examples/swb.json \
  --output /tmp/advisory-swb
```

### From a canned scenario (no refiner run needed)

```bash
uv run python advise.py --scenario scenarios/healthcare_chat.json \
  --output /tmp/advisory-healthcare
```

### Individual stages

```bash
# Stage 1: Coverage analysis
uv run python analyze.py ../../runs/swb-mistral-small-3-1-24b-g10 \
  --policy ../../policy_examples/swb.json \
  --output /tmp/advisory-swb

# Stage 2: Config generation
uv run python configure.py /tmp/advisory-swb/analysis.json \
  --output /tmp/advisory-swb

# Stage 3: Report
uv run python report.py /tmp/advisory-swb
```

## Output

```
/tmp/advisory-swb/
  analysis.json           # Coverage analysis (machine-readable)
  garak.yaml              # Garak scan configuration
  nemo/
    config.yml            # NeMo Guardrails configuration
    rails.co              # NeMo Colang flow definitions
  advisory-report.md      # SA-facing advisory report
```

## Tests

```bash
uv run pytest tests/ -v
```

## What this does NOT do

- Execute Garak scans (generates config only)
- Execute NeMo Guardrails (generates config only)
- Recommend specific models (model catalog doesn't exist yet)
- Make LLM calls (pure data transformation)
