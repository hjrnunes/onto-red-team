# Advisory System Prototype — Design Spec

**Date:** 2026-04-14
**Status:** Draft
**Location:** `prototypes/advisory/`

---

## Purpose

A concept prototype demonstrating the advisory reasoning chain: given a client's risk profile (from the refiner), query AIROO for matching operational tools (probes, guardrails, benchmarks), compute coverage and gaps, generate actionable Garak and NeMo Guardrails configurations, and render an SA-facing advisory report.

This is explicitly experimental — it lives in `prototypes/`, not a production subproject. The goal is to prove the advisory system's core value proposition: traceable, ontology-grounded recommendations that surface gaps no manual review would find.

## What This Is Not

- Not a conversational agent (that's the long-term vision)
- Not an MCP server (would over-engineer the prototype)
- Not a production recommendation system (rules are simple and illustrative)
- Does not execute Garak scans or NeMo guardrails (generates configs, not results)
- No LLM calls — pure data transformation and template rendering

---

## Architecture

Three staged scripts, each reading the previous stage's output:

```
Input (refiner run dir OR canned scenario)
  │
  ▼
Stage 1: analyze.py
  │  Read refiner output → extract risk IDs
  │  → query AIROO for probes, guardrails, benchmarks
  │  → compute coverage matrix → identify gaps
  │  → write analysis.json
  ▼
Stage 2: configure.py
  │  Read analysis.json
  │  → generate garak.yaml (probes from AIROO mappings)
  │  → compose NeMo config.yml + rails.co (layered, cost-ordered)
  │  → domain-scoped system prompt from policy concepts
  ▼
Stage 3: report.py
  │  Read analysis.json + configs
  │  → render advisory-report.md
  │  → coverage matrix, gap analysis, recommendations
  │  → inline lineage citations
  ▼
Output: analysis.json, garak.yaml, nemo/, advisory-report.md
```

A thin `advise.py` wrapper chains all three stages.

### Dependencies

| Dependency | How consumed | Purpose |
|---|---|---|
| AIROO | Path dependency (import `ontology.query.OntologyQuery`) | Risk → probe/guardrail/benchmark lookups |
| Atlas Nexus | Via AIROO (optional dep) | Cross-taxonomy risk mappings |
| Refiner output | File reads (JSON/YAML) | Risk IDs, domain context, attack surface |
| Jinja2 | Template rendering | Config and report generation |
| PyYAML | Data serialization | YAML config output |

**Environment:** Separate `.venv` in `prototypes/advisory/` via its own `pyproject.toml`. Does not share venvs with refiner, ontoquery, or nexus-mcp.

---

## Input

### Primary: Refiner Run Directory

The prototype reads three artifacts from a refiner run:

1. **Taxonomy** (`<client>-taxonomy.json`) — risk IDs, policy concepts, cross-mappings
2. **Domain context** (`<client>-domain-context.json`) — variation axes, enumerations
3. **Attack surface profile** (`<client>-attack-surface.yaml`) — restructured layers (if present)

Plus the source **policy file** (for policy concept names and domain identification).

### Fallback: Canned Scenario

A pre-populated JSON file in `scenarios/` that mimics the structure Stage 1 would extract from a real refiner run. Includes enough risks and dimensions to exercise all stages.

```json
{
  "client": "healthcare-demo",
  "domain": "healthcare",
  "risks": [
    {
      "risk_id": "atlas-harmful-output",
      "risk_name": "Harmful Output",
      "policy_concept": "Clinical Safety",
      "policy_type": "A",
      "alternative_framings": [
        {"risk_id": "nist-dangerous-violent-or-hateful-content", "taxonomy": "nist-ai-rmf", "mapping_type": "close"}
      ],
      "attack_dimensions": [
        {"cco_class": "Person", "role": "Patient or clinician", "terms": ["Patient", "Nurse", "Physician"]},
        {"cco_class": "ClinicalProcedure", "role": "Medical procedure discussed", "terms": ["Surgery", "Prescription", "Diagnosis"]}
      ]
    }
  ]
}
```

Stages 2 and 3 cannot distinguish between real and canned input.

---

## Stage 1: Analysis (`analyze.py`)

### Input
- Refiner run directory (or canned scenario)
- Policy file (optional, for domain identification)

### Process
1. Parse refiner taxonomy output → extract risk entries with IDs, policy concepts, cross-mappings
2. Parse domain context → extract attack dimensions and enumerations per risk
3. Parse attack surface profile (if present) → extract alternative framings
4. For each risk ID, query AIROO:
   - `get_probes_for_risk(risk_id)` → matching Garak probes
   - `get_guardrails_for_risk(risk_id)` → matching NeMo/Granite Guardian/FMS guardrails
   - `get_evals_for_risk(risk_id)` → matching evaluation benchmarks
   - If no direct match, try `get_dimension_for_risk(risk_id)` → dimension-level rollup
5. For amplified risks (alternative framings), repeat AIROO lookups
6. Compute coverage matrix:
   - Per risk: has_probes, has_guardrails, has_benchmarks
   - Per attack dimension: is any probe specifically targeting this semantic axis?
   - Gap classification: fully_covered, partial_gap, no_coverage
7. Compute summary statistics

### Output: `analysis.json`

```json
{
  "client": "swb",
  "domain": "finance",
  "source": {
    "run_dir": "runs/swb-phi4-20260414",
    "policy_file": "policy_examples/swb.json",
    "source_type": "refiner_run"
  },
  "risks": [
    {
      "risk_id": "atlas-fraud-assistance",
      "risk_name": "Fraud Assistance",
      "policy_concept": "Fraud",
      "policy_type": "A",
      "alternative_framings": [
        {"risk_id": "atlas-social-engineering", "taxonomy": "ibm-risk-atlas", "mapping_type": "close"}
      ],
      "attack_dimensions": [
        {"cco_class": "Person", "role": "Who performs fraudulent action", "term_count": 12}
      ],
      "coverage": {
        "probes": [
          {"probe_id": "dan.DanInTheWild", "platform": "garak", "mapping_source": "garak_tags"}
        ],
        "guardrails": [
          {"guardrail_id": "nemo-self_check_input", "platform": "nemo", "mapping_source": "platform_docs"}
        ],
        "benchmarks": [
          {"benchmark_id": "truthfulqa_mc2", "platform": "lm-eval-harness", "mapping_source": "benchmark_scope"}
        ],
        "gaps": {
          "has_probes": true,
          "has_guardrails": true,
          "has_benchmarks": true,
          "uncovered_dimensions": ["InformationBearingArtifact"]
        }
      }
    }
  ],
  "summary": {
    "total_risks": 12,
    "amplified_risks": 28,
    "risks_with_probes": 10,
    "risks_with_guardrails": 9,
    "risks_with_benchmarks": 8,
    "fully_covered": 7,
    "partial_gaps": 3,
    "no_coverage": 2
  }
}
```

### AIROO Query Strategy

Risk IDs from the refiner use Atlas Nexus identifiers (e.g., `atlas-fraud-assistance`). AIROO maps risks at the dimension level (5 dimensions, each with a primary risk and related risks). The lookup strategy:

1. Direct match: `get_probes_for_risk(risk_id)` — checks if the risk is primary or related in any dimension
2. Dimension rollup: `get_dimension_for_risk(risk_id)` → `get_probes_for_dimension(dim_id)` — if no direct match, use dimension-level tools
3. Cross-taxonomy: for amplified risks, try the mapped risk ID (e.g., `nist-confabulation` instead of `atlas-hallucination`)
4. No match: record as a gap

---

## Stage 2: Config Generation (`configure.py`)

### Input
- `analysis.json` from Stage 1

### Garak Config (`garak.yaml`)

Generated from a Jinja2 template. For each risk in the analysis:
- Look up matched probes from `coverage.probes`
- Deduplicate (same probe can appear for multiple risks)
- Group by AIROO dimension with comments showing risk → probe lineage
- Add detector config (MulticlassJudge with Granite Guardian)
- Environment variable placeholders for target endpoint and API key

Risks with no probes appear as YAML comments flagging the gap.

Template structure follows the rh-summit-demos `garak.yaml` format:
- `plugins.generators` — target model endpoint (env vars)
- `plugins.probes` — probe list grouped by dimension
- `plugins.detectors` — judge model config
- `eval_threshold`, `generations` — scan parameters

### NeMo Guardrails Config

Two files generated from Jinja2 templates:

**`config.yml`** — Model connections and rail ordering:
- `models` section: main LLM + guard models (added conditionally based on which risks are present)
- `instructions` section: system prompt generated from policy concepts and domain
- `rails.input.flows` and `rails.output.flows`: ordered flow references

**`rails.co`** — Colang flow definitions:
- One flow per selected guardrail
- Refuse messages per guardrail type
- Comments with lineage (risk ID → AIROO mapping → guardrail)

### Composition Rules

| Rule | Rationale |
|---|---|
| Heuristic detectors before model-based | Cheaper, faster — fail fast on obvious attacks |
| Input rails before output rails | Block bad inputs before they reach the model |
| PII detection always on if domain involves personal data | Domain-aware default |
| System prompt scoped to client domain + policy concepts | From refiner output |
| Only emit flows for guardrails AIROO maps to identified risks | No speculative rails |
| HAP guard model only added if harmful_content risks present | Avoid unnecessary model loading |

### Guardrail Selection Logic

For risks mapping to multiple guardrails on the same platform (e.g., both `nemo-self_check_input` and `nemo-content_safety` for jailbreak), prefer:
1. Dedicated detectors over general-purpose (e.g., `nemo-jailbreak_detection_heuristics` over `nemo-self_check_input` for jailbreak)
2. Heuristic/rule-based over model-based (cheaper, no extra model needed)
3. Include both if they cover different aspects (input vs output)

---

## Stage 3: Report Generation (`report.py`)

### Input
- `analysis.json` from Stage 1
- Generated config files from Stage 2

### Output: `advisory-report.md`

Rendered from a Jinja2 template with the following sections:

#### Header
- Client name, domain, generation date
- Source (refiner run dir or canned scenario)

#### Executive Summary
- Headline numbers: risks identified, amplified, covered, gaps
- One-sentence verdict

#### Coverage Matrix
Table with one row per risk:
- Risk name, source policy, probe count, guardrail count, benchmark count, status (Covered / Partial Gap / Gap)

#### Gap Analysis

Three subsections:

**Uncovered Risks** — Risks with no AIROO probes or guardrails. Each entry includes:
- Risk name and ID
- How many attack dimensions the refiner identified (to show the gap's severity)
- Recommendation (custom rail, Granite Guardian fine-tune, manual review)

**Partial Gaps** — Risks with some but not complete coverage. Each entry includes:
- What's covered and what's missing
- Domain-specific context from the refiner (e.g., "8 financial instrument terms that could trigger domain-specific confabulation")
- Recommendation

**Uncovered Attack Dimensions** — Attack dimensions from the refiner that no probe specifically targets, even when the parent risk has generic coverage. Includes term counts from domain ontology enumerations.

#### Generated Configurations
- Summary of Garak config (probe count, dimensions covered)
- Summary of NeMo config (rail count, input vs output, guard models needed)
- Lineage per probe group and rail

#### Lineage
Explanation of how each recommendation traces back through:
- Policy concept → refiner risk ID → Atlas Nexus cross-mapping
- AIROO dimension → specific probe/guardrail with mapping_source
- Refiner attack dimension → CCO class → domain ontology terms

---

## Project Structure

```
prototypes/
  advisory/
    pyproject.toml              # uv project
    advise.py                   # Wrapper: chains all stages
    analyze.py                  # Stage 1: coverage analysis
    configure.py                # Stage 2: config generation
    report.py                   # Stage 3: report rendering
    templates/
      garak.yaml.j2             # Garak config template
      nemo_config.yml.j2        # NeMo config.yml template
      nemo_rails.co.j2          # NeMo rails.co template
      report.md.j2              # Advisory report template
    scenarios/
      healthcare_chat.json      # Canned fallback scenario
    README.md                   # Usage and purpose
```

## CLI Interface

```bash
cd prototypes/advisory

# Full pipeline from refiner run
uv run python advise.py ../../runs/swb-phi4-20260414 \
  --policy ../../policy_examples/swb.json \
  --output /tmp/advisory-swb

# Full pipeline from canned scenario
uv run python advise.py --scenario scenarios/healthcare_chat.json \
  --output /tmp/advisory-healthcare

# Individual stages
uv run python analyze.py ../../runs/swb-phi4-20260414 \
  --policy ../../policy_examples/swb.json \
  --output /tmp/advisory-swb

uv run python configure.py /tmp/advisory-swb/analysis.json \
  --output /tmp/advisory-swb

uv run python report.py /tmp/advisory-swb \
  --output /tmp/advisory-swb
```

## Output Directory

```
/tmp/advisory-swb/
  analysis.json                 # Stage 1: coverage analysis
  garak.yaml                    # Stage 2: Garak scan config
  nemo/
    config.yml                  # Stage 2: NeMo guardrails config
    rails.co                    # Stage 2: NeMo Colang flows
  advisory-report.md            # Stage 3: SA-facing report
```

---

## Provenance

Lightweight lineage, not full PROV-O. Each recommendation carries inline citations:

- **`mapping_source`** on every probe/guardrail/benchmark reference — traces to AIROO's `garak_tags`, `platform_docs`, `benchmark_scope`, or `manual_review`
- **Risk lineage** in the report — policy concept → refiner risk ID → Atlas Nexus cross-mapping chain
- **Domain context lineage** — CCO class URI → role description → domain ontology terms

If the prototype graduates from `prototypes/` to a real subproject, these references are the natural formalization points for PROV-O records.

---

## What's Explicitly Out of Scope

- Garak execution (config generation only)
- NeMo Guardrails execution (config generation only)
- Model recommendations (the model catalog doesn't exist yet)
- Conversational agent interface (long-term vision, not this prototype)
- PROV-O provenance graph (lightweight lineage instead)
- Production guardrail composition logic (simple rules for the prototype)
- Granite Guardian config generation (AIROO maps it, but no config format to target)
- FMS regex detector config generation (same — mapped but no config artifact)
