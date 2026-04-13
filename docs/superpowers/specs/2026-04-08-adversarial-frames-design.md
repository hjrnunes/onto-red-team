# Adversarial Technique Frames Design Spec

## Overview

Introduces 5 adversarial technique frames to diversify the emit stage's prompt generation beyond the single pretexting strategy used in g8.x battery runs. Each frame provides soft LLM guidance (descriptions + examples, not hard templates) and ontology-grounded slot labels for BFO categories. Frame distribution is configurable.

## Motivation

Analysis of 3,000+ generated prompts from the g8.x battery revealed all use the same adversarial strategy: professional pretexting (adopting a plausible professional identity to make requests seem routine). Cross-validation against external datasets confirmed this is one technique family among many:

- **Galtea** (26K prompts): Predominantly direct requests, not pretexting
- **TUD-ARTS** (282 prompts, 6 attack techniques): Covers narrative distancing, analytical reframing, authority exploitation, and comparative benchmarking — none of which our system generated

The g8.4 assessment also showed that scenario block formatting has massive impact on axis fidelity (garbled prefix fix: +0.15 fidelity in worst runs). This confirms the generation LLM is very sensitive to how scenario context is presented, making meaningful slot labels and technique guidance high-leverage improvements.

## Data Flow

```
frames.py: FRAMES registry (5 frames)
                  ↓
emit.py: select_frame(weights) → frame per sample
                  ↓
emit.py: build_prompt(frame=frame) → slot labels + technique block in user message
                  ↓
dataset.jsonl: "technique" + "technique_description" fields per row
                  ↓
evaluate.py: compute_technique_diversity() → entropy metrics
```

Frames only affect the emit stage. Upstream stages (classify, identify_domains, map_risks, anchor, contextualize, structure) remain unchanged.

## Frame Definitions

| Frame | Strategy | Risk Affinities |
|-------|----------|-----------------|
| `pretexting` | Professional identity + social engineering pretext | fraud, social engineering, impersonation, phishing |
| `narrative_framing` | Fiction, case study, historical account as distance | disinformation, propaganda, manipulation, deception |
| `analytical_reframing` | Research/analysis positioning | bias, fairness, discrimination, privacy, data |
| `delegated_authority` | Urgency + chain of command pressure | compliance, governance, regulatory, safety |
| `comparative_benchmark` | Harmful content as test data / calibration input | toxicity, hate speech, profanity, content moderation |

Each frame contains:

```python
@dataclass(frozen=True)
class AdversarialFrame:
    name: str                       # e.g. "pretexting"
    description: str                # paragraph for LLM context
    examples: list[str]             # 1-2 short example prompts
    slot_labels: dict[str, str]     # bfo_category → human-readable slot label
    risk_affinities: list[str]      # keywords for soft weight boost
```

### Slot Labels

Each frame maps BFO categories to frame-specific descriptive labels:

| BFO Category | pretexting | narrative_framing | analytical_reframing | delegated_authority | comparative_benchmark |
|--------------|-----------|-------------------|---------------------|--------------------|-----------------------|
| Role | professional role | character role | researcher role | delegated role | evaluator role |
| Agent | requesting party | narrator | research subject | authority figure | benchmark source |
| InformationContentEntity | information target | narrative subject | data source | compliance document | test content |
| Act | professional activity | plot event | analytical method | urgent action | benchmark procedure |
| MaterialEntity | professional tool | story prop | research material | enforcement tool | test material |
| Process | business process | narrative arc | analytical process | escalation process | evaluation process |
| Site | workplace | story setting | research setting | jurisdictional area | test environment |
| Facility | professional facility | narrative location | research facility | authority facility | testing facility |

When `bfo_category` is empty (currently ~78% of axes), no slot label is applied — the technique description paragraph provides primary guidance. As upstream `bfo_category` coverage improves, slot labels become more effective automatically.

## Frame Selection

```python
def select_frame(
    weights: dict[str, float],
    risk_name: str = "",
    risk_description: str = "",
) -> AdversarialFrame
```

Selection uses weighted random choice with affinity boosting:
1. Start with user-configured weights (default: uniform 1.0 across all 5 frames)
2. For each frame, check if any of its `risk_affinities` keywords appear in `risk_name` or `risk_description`
3. If matched, multiply that frame's weight by `_AFFINITY_BOOST` (2.0)
4. Select using `random.choices()` with adjusted weights
5. Fallback: if all weights are zero, return `pretexting`

This creates soft coupling between risk semantics and technique selection without hardcoding.

## Prompt Modifications

### With frame (new behavior)

Scenario lines use slot labels when `bfo_category` is non-empty:
```
- professional role: Financial Analyst (a type of Person)
```

When `bfo_category` is empty, falls back to plain label:
```
- Financial Analyst (a type of Person)
```

A technique guidance block is inserted between scenario and policy blocks:
```
Adversarial technique: The requester adopts a plausible professional identity...

Examples of effective prompts in this style:
- "As a compliance officer reviewing our quarterly reports..."
```

### Without frame (backward compat)

When `frame=None`, `build_prompt()` produces identical output to the pre-frames implementation.

## Output Dataset Extensions

Each row in `dataset.jsonl` gains two fields:

| Field | Type | Example |
|-------|------|---------|
| `technique` | str | `"narrative_framing"` |
| `technique_description` | str | `"The prompt wraps the request in a fictional scenario..."` |

## Configuration

### CLI

```bash
refiner emit <run-dir> --policies <policy> --samples-per-risk 10 \
  --technique-weights '{"pretexting": 2, "analytical_reframing": 1}'
```

### battery.yaml

```yaml
# Adversarial technique frame weights for emit stage.
# Default: uniform distribution across all 5 frames.
# technique_weights:
#   pretexting: 0.35
#   narrative_framing: 0.15
#   analytical_reframing: 0.25
#   delegated_authority: 0.15
#   comparative_benchmark: 0.10
```

### run_battery.py

Reads optional `technique_weights` from `battery.yaml`, serializes as JSON, and passes via `--technique-weights` CLI flag.

## Evaluation Metrics

### In compute_generation_metrics()

`technique_distribution`: count of each technique in emit rows. Backward-compatible: rows without `"technique"` default to `"pretexting"`.

### compute_technique_diversity(rows)

Standalone function returning:

| Metric | Description |
|--------|-------------|
| `technique_counts` | `{technique_name: count}` |
| `technique_entropy` | Shannon entropy (bits) |
| `technique_normalized_entropy` | Entropy / max_entropy, range [0, 1] |
| `per_risk_technique_count` | `{risk_id: unique_technique_count}` |

## Pre-existing Bug Fix

`bfo_category` was never propagated from `DomainContextAxis` to `SampledAxis` in `sample_axes()` despite both models having the field. Fixed by adding `bfo_category=axis.bfo_category` to the SampledAxis constructor.

## Files Modified

| File | Action |
|------|--------|
| `refiner/src/refiner/frames.py` | Create — frame definitions, selection, slot labels |
| `refiner/src/refiner/emit.py` | Modify — bfo_category fix, frame in build_prompt, technique_weights in emit |
| `refiner/src/refiner/evaluate.py` | Modify — technique diversity metrics |
| `refiner/src/refiner/cli.py` | Modify — `--technique-weights` option |
| `scripts/run_battery.py` | Modify — thread technique_weights from config |
| `battery.yaml` | Modify — add commented technique_weights |
| `refiner/tests/test_frames.py` | Create — 13 tests |
| `refiner/tests/test_emit.py` | Extend — 9 new tests |
| `refiner/tests/test_evaluate.py` | Extend — 6 new tests |

## Verification

1. `cd refiner && uv run pytest` — all tests pass (318 → 346)
2. `refiner emit` with `--technique-weights` produces varied `"technique"` values in output JSONL
3. `refiner evaluate` reports technique_distribution in generation_metrics
4. Small battery run confirms technique distribution matches configured weights
