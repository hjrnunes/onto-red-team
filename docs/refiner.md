# Refiner Pipeline

6-stage LLM pipeline that transforms client policies into taxonomy YAML + domain context profiles.

## Stack

- **Instructor** + OpenAI SDK (`instructor.Mode.JSON`) for structured LLM output
- Self-hosted models via OpenAI-compatible endpoints (vLLM, TGI, llama.cpp)
- Tested with Gemma 2 9B IT Abliterated on OpenShift vLLM

## Stages

1. **Classify** (`classify.py`) — A/B/C/D policy type classification
2. **Identify Domains** (`identify_domains.py`) — LLM selects relevant domain ontologies (FIBO/OBO/IOF)
3. **Map Risks** (`map_risks.py`) — semantic search + LLM ranking of candidate risks; collects ground-truth
   cross-mappings from knowledge graph
4. **Anchor** (`anchor.py`) — variation axis identification; ontology search filtered by selected domains;
   restriction/equivalence expansion discovers related candidates
5. **Contextualize** (`contextualize.py`) — domain context profiles from subclasses (with sibling fallback for leaf
   nodes); disjointness validation filters conflicting enumerations
6. **Structure** (`structure.py`) — deterministic LinkML-conformant YAML assembly with ground-truth cross-mappings

5 LLM stages + 1 deterministic (structure). Python does retrieval, LLM does reasoning.

## Key Design Patterns

- **Slim response models:** Private `_`-prefixed Pydantic models without docstrings for LLM calls. Known metadata
  stitched back programmatically. No docstrings — Instructor embeds them in JSON schema, confusing small models.
- **Ground-truth cross-mappings:** `get_related_risks()` from knowledge graph, not LLM-generated. Eliminates
  hallucinated cross-mapping IDs.
- **Domain filtering:** `identify_domains` selects ontologies; `anchor` filters search results by URI namespace. CCO,
  Commons, D3FEND, CSO are always-included; FIBO/OBO/IOF are selectable.
- **Per-domain search:** Per-domain ChromaDB collections prevent CSO (plain English) from crowding out OBO/D3FEND
  (technical). Merge strategies (weighted/grouped) control candidate distribution. Dual threshold
  (raw distance ceiling + z-score) rejects poor candidates. CSO DangerousInformation branch (18
  physical harm classes) auto-filtered in domain-specific runs via `build_generic_safety_uris()`.
- **Sibling fallback:** `contextualize` falls back to `get_siblings()` when leaf node. Each `AxisEnumeration` carries
  `provenance` field (`"subclass"` or `"sibling"`).
- **Programmatic retrieval:** Python calls `create_tool_handlers()` dicts from ontoquery + nexus-mcp (no MCP transport).
- **Restriction/equivalence expansion:** `expand_candidates()` follows OWL restrictions and equivalence axioms to
  discover structurally related classes (capped at 3 additional, domain-filtered).
- **Disjointness validation:** Greedy filter removes classes declared `owl:disjointWith` each other (keeps
  higher-relevance in conflict pair).
- **BFO/CCO/Commons role derivation:** `derive_roles()` walks superclass chain looking for known category URIs ->
  semantic roles. `_CATEGORY_ROLES` dict (29 entries). Falls back to LLM-assigned role when no known URI found.
- **Sequential indices for risk matching:** LLM sees numbered candidates, returns index. Post-processing maps back
  to actual IDs.
- **Risk-level memoization:** anchor and contextualize cache results by `risk_id`.
- **Per-call debug logging:** `--debug <dir>` writes JSON per LLM call. When `--track` active, also creates MLflow
  trace spans (dual-write).

## Pipeline Events

Each stage emits structured events to a `RunReport` dataclass (17 event types). Report written as `*-report.yaml`.

## Source Layout

```
refiner/src/refiner/
  cli.py          # Typer CLI: run, emit, evaluate, track
  pipeline.py     # Stage sequencing, state threading
  emit.py         # Domain context -> sdg_hub-ready JSONL (pure Python)
  evaluate.py     # Post-hoc metrics, coverage, quality analysis
  tracking.py     # MLflow integration
  judge.py        # Judge-model evaluation (4-dimension rubric)
  debug.py        # Per-call debug logging + MLflow trace spans
  models.py       # 11 Pydantic models + RunReport dataclass
  llm.py          # Instructor + OpenAI client setup, LLMConfig
  stages/         # classify, identify_domains, map_risks, anchor, contextualize, structure
```

## CLI

```bash
cd refiner

# Full pipeline
uv run refiner run ../policy_examples/swb.json --output /tmp/out --debug /tmp/debug

# Partial run (stop after stage)
uv run refiner run ../policy_examples/swb.json --until identify_domains

# Emit dataset (cheap, re-runnable with different params)
uv run refiner emit /tmp/out --policies ../policy_examples/swb.json --samples-per-risk 10

# Evaluate
uv run refiner evaluate /tmp/out --policies ../policy_examples/swb.json
uv run refiner evaluate /tmp/out --emit /tmp/dataset.jsonl --adversarial /tmp/adv.jsonl
uv run refiner evaluate /tmp/out --adversarial /tmp/adv.jsonl --judge --judge-sample 20

# MLflow tracking (requires: uv sync --extra tracking)
uv run refiner run ../policy_examples/swb.json --output /tmp/out --track --tracking-uri $MLFLOW_TRACKING_URI
uv run refiner evaluate /tmp/out --track --tracking-uri $MLFLOW_TRACKING_URI
uv run refiner track /tmp/out --tracking-uri $MLFLOW_TRACKING_URI  # backfill
```

## Configuration

| Env var                | Purpose                     |
|------------------------|-----------------------------|
| `REFINER_BASE_URL`     | LLM endpoint URL            |
| `REFINER_MODEL`        | Model name                  |
| `REFINER_API_KEY`      | API key                     |
| `NEXUS_BASE_DIR`       | Path to ai-atlas-nexus repo |
| `ONTOQUERY_CHROMA_DIR` | Path to ontoquery ChromaDB  |
| `NEXUS_CHROMA_DIR`     | Path to nexus-mcp ChromaDB  |
| `MLFLOW_TRACKING_URI`  | MLflow server URL           |

## Emit Dataset

Pure Python command (`refiner emit`) that transforms domain context profiles into sdg_hub-ready JSONL. No LLM calls.
Re-runnable with different sampling parameters without re-running the pipeline.

- **Relevance-weighted sampling:** high=3, medium=2, low=1, normalized per axis
- **Scenario-first prompts:** Domain context defines the world; harm emerges naturally
- **Full ontology traceability:** `sampled_axes` column carries provenance through the full chain
- **SampledAxis model:** `cco_class_uri`, `cco_class_label`, `role`, `sampled_uri`, `sampled_label`, `source_ontology`,
  `relevance`

Output columns: `generation_prompt`, `policy_concept`, `concept_definition`, `risk_id`, `risk_name`, `sampled_axes`.

## Evaluation Framework

Post-hoc evaluation via `refiner evaluate`. Two components:

### Pipeline Events (during execution)

17 event types across 6 stages, emitted to `RunReport`. Each stage accepts `report=None` (backward compatible).

### Coverage Metrics

- `compute_risk_framework_coverage` — maps risk IDs to frameworks by prefix convention
- `compute_policy_coverage` — per-policy risk/axis/enumeration counts
- `compute_ontological_coverage` — unique axis classes, unique enumeration URIs, breakdown by ontology
- `compute_cross_mapping_coverage` — cross-mapping utilization
- `compute_single_value_axis_dominance` — axes with <=1 enumeration (predicts prompt repetition)
- `compute_enumeration_domain_mismatch` — enumerations from wrong ontology
- `compute_disjoint_filter_rate` — risks where disjointness removed conflicts
- `compute_restriction_discovery_rate` — risks where expansion found additional candidates

### Proxy Quality Metrics

- `compute_generation_metrics` — axis diversity, role/relevance distribution, dedup saturation
- `compute_enumeration_concentration` — top-k share of sampled values
- `compute_adversarial_metrics` — lexical diversity, prompt length, domain terms, red-flag patterns
- `compute_policy_coverage_balance` — Shannon entropy of prompt distribution
- `compute_jargon_leak_rate` — ontology naming patterns leaked into prompts
- `compute_axis_fidelity` — axis labels present in prompt text
- `compute_named_entity_utilization` — policy proper nouns in prompts
- `compute_weak_match_impact` — weak-match vs strong-match prompt comparison
- `compute_semantic_diversity` — TF-IDF cosine pairwise distance
- `compute_sibling_relevance` — subclass vs sibling enumeration relevance

### Judge-Model Evaluation

`judge.py` — Instructor-based LLM scoring on 4 dimensions (1-5 scale): subtlety, plausibility, domain_grounding,
policy_relevance. CLI flags: `--judge`, `--judge-model`, `--judge-base-url`, `--judge-sample`.

## MLflow Tracking

Optional integration (`uv sync --extra tracking`). Wraps `refiner run` (tracing) and `refiner evaluate` (metrics).

- **Run linking:** `.mlflow-run-id` file links run + evaluate to same MLflow run
- **Experiment org:** One experiment per policy set (swb, generic, aramco)
- **Params:** model, policy_set, selected_domains, git_sha, git_dirty
- **Metrics:** 22 flattened scalars (coverage.*, generation.*, prompt.*, judge.*)
- **Artifacts:** Whitelisted pipeline outputs
- **Traces:** One span per LLM call with full prompt/response payloads

## Run Assessment

`refiner/tools/assess_run.py` extracts structured data from a run directory for qualitative analysis. Each run gets
an `assessment.md` with best/worst examples, systematic issues, distribution stats, and root cause analysis.
