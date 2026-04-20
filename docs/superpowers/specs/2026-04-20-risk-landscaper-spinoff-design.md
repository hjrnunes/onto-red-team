# Risk Landscaper Spin-off Design

Spin off the ontology-independent pipeline stages (ingest, domain detection, map_risks, build_landscape) into a standalone sub-project called `risk-landscaper`.

## Motivation

The ORT pipeline's core value -- policy-driven, risk-grounded, multi-framework adversarial prompt generation -- does not depend on the three-layer ontology stack (BFO/CCO/Domain). The ontology stack powers anchor and contextualize (dimensional sampling), but the upstream stages that transform client policies into a risk landscape are independently valuable and deployable.

Separating these stages:
- Enables deployment without ontoquery, ChromaDB ontology indexing, or SSSOM bridges
- Simplifies the pitch: "policy-driven risk identification against 600+ risks across 10 frameworks"
- Makes refiner a focused ontology-enrichment layer that consumes a pre-built risk landscape

See: Obsidian note "ORT Pipeline Without Ontologies" for the full analysis.

## Approach: Move & Decouple

Move the stage code from refiner into risk-landscaper. Refiner does NOT depend on risk-landscaper. The two projects communicate exclusively through a `risk-landscape.yaml` artifact. Each project owns its own Pydantic models; no shared Python types.

## Project Structure

```
risk-landscaper/
  pyproject.toml
  src/
    risk_landscaper/
      __init__.py
      cli.py
      models.py
      llm.py
      nexus_adapter.py
      stages/
        __init__.py
        ingest.py
        detect_domain.py
        map_risks.py
        build_landscape.py
  tests/
    test_ingest.py
    test_detect_domain.py
    test_map_risks.py
    test_build_landscape.py
```

Location: sibling directory in the taxonomy-refiner monorepo, alongside `refiner/`, `ontoquery/`, `nexus-mcp/`.

## Dependencies

```toml
[project]
name = "risk-landscaper"
dependencies = [
    "instructor>=1.0",
    "openai>=1.0",
    "pydantic>=2.0",
    "typer>=0.12",
    "pyyaml>=6.0",
    "nexus-mcp",
]

[tool.uv.sources]
nexus-mcp = { path = "../nexus-mcp", editable = true }
```

No `ontoquery` dependency.

## CLI

Single entry point:

```bash
risk-landscaper run <policy-file> --output <dir>
```

Runs four stages sequentially:

| Stage | Input | Output | LLM Calls |
|---|---|---|---|
| ingest | policy document (markdown/JSON) | PolicyProfile | 3 (context, policies, enrichment) |
| detect_domain | PolicyProfile | domain label | 0-1 (skipped if domain already set) |
| map_risks | policies + nexus handlers | risk mappings | 1-2 per policy |
| build_landscape | risk mappings + details | RiskLandscape | 0 (pure data) |

Output files written to `--output` directory:
- `policy-profile.json` -- enriched policy profile
- `risk-landscape.yaml` -- primary artifact (consumed by refiner)
- `run-report.json` -- token usage, timing, stage events

CLI flags:
- `--base-url`, `--model`, `--api-key` (or env vars `REFINER_BASE_URL`, `REFINER_MODEL`, `REFINER_API_KEY`)
- `--skip-enrichment` -- skip ingest enrichment pass
- `--max-concurrent N` -- parallel LLM calls within map_risks
- `--input-format markdown|json_array` -- auto-detected if not specified

## Stages

### ingest

Moved from `refiner/src/refiner/stages/ingest.py` (471 lines). Converts policy documents into enriched `PolicyProfile` objects via three LLM passes:

1. Extract context (organization, domain, purpose, stakeholders, regulations)
2. Extract policies (policy_concept + concept_definition pairs)
3. Enrich policies (boundary examples, acceptable uses, risk controls, decomposition)

No external subproject dependencies. Pure LLM extraction.

### detect_domain (new)

Replaces `identify_domains` (which selected ontology vocabularies FIBO/OBO/IOF). Simplified to detect the policy's domain as a plain label from a fixed menu: `healthcare`, `financial_services`, `energy`, `government`, `legal`, `manufacturing`, `technology`, `education`, `general`.

If `PolicyProfile.domain` is already populated from ingest, validates/normalizes it and skips the LLM call. Otherwise, one LLM call against the policies list.

Output stored in `RiskLandscape.selected_domains` as a single-element list.

~20-30 lines of stage code.

### map_risks

Moved from `refiner/src/refiner/stages/map_risks.py` (424 lines). Maps policies to AI risks via nexus-mcp semantic search.

Key behaviors preserved:
- Perspective-based query expansion (base + deployer + regulator viewpoints)
- LLM risk matching with relevance classification (primary/supporting/tangential)
- Coverage gap detection and characterization
- Concurrent processing via ThreadPoolExecutor

Requires `risk_handlers` dict from nexus-mcp: `search_risks`, `get_risk_details`, `get_related_risks`, `get_related_actions`.

### build_landscape

Moved from `refiner/src/refiner/stages/build_landscape.py` (109 lines). Pure data transformation:
- Deduplicates risks across policies
- Detects frameworks from risk ID prefixes
- Classifies weak matches (distance > threshold)
- Assembles the `RiskLandscape` artifact

No LLM calls, no external dependencies.

## Models

risk-landscaper defines its own Pydantic models, copied from refiner's `models.py`:

**Policy models:** `PolicyProfile`, `Policy`, `PolicyDecomposition`, `BoundaryExample`, `Stakeholder`, `AiSystem`, `RegulatoryReference`

**Risk mapping models:** `RiskMatch`, `PolicyRiskMapping`, `CoverageGap`

**Landscape models:** `RiskDetail`, `WeakMatch`, `RiskLandscape`, `PolicySourceRef`, `KnowledgeBaseRef`

**Infrastructure:** `LLMConfig`, `TokenTracker`, `RunReport` (from `llm.py`)

**Also moved:** `nexus_adapter.py` (nexus-format detection + risk-to-policy projection)

## Data Contract

The `risk-landscape.yaml` file is the sole interface between risk-landscaper and refiner. Schema versioned via `RiskLandscape.version` (currently `"0.1"`). If either side changes the YAML structure, bump the version.

## Refiner Modifications

### New flag: `refiner run --landscape <path>`

When `--landscape` is provided:
1. Skip `identify_domains`, `map_risks`, `build_landscape`
2. Load and deserialize the YAML into refiner's own `RiskLandscape` model
3. Populate `PipelineState` via existing `_resolved` properties (`risk_mappings_resolved`, `risk_details_resolved`, `risk_actions_resolved`, `related_risks_resolved`)
4. Continue with `anchor` -> `contextualize` as normal

Also needs the original `PolicyProfile` for anchor/contextualize -- reads from `--policies` flag (already exists).

### Code removed from refiner

- `stages/ingest.py`, `stages/identify_domains.py`, `stages/map_risks.py`, `stages/build_landscape.py`
- Corresponding tests (~58 tests)
- `ingest` CLI sub-command
- `map-risks` standalone CLI sub-command
- First half of `run_pipeline()` (identify_domains -> map_risks -> build_landscape)

### Code kept in refiner

- All models in `models.py` (refiner still needs `RiskLandscape` for deserialization)
- `nexus_adapter.py` removed (moved to risk-landscaper; refiner no longer handles raw policy ingestion)

## Battery Script Changes

`scripts/run_battery.py` updated to call risk-landscaper first, then refiner:

```python
# Stage 1: risk-landscaper
risk-landscaper run <policy> --output <run-dir> --model <model> --base-url <url>

# Stage 2: refiner (anchor + contextualize)
refiner run --landscape <run-dir>/risk-landscape.yaml --policies <policy> --output <run-dir>

# Stage 3: emit (unchanged)
refiner emit <run-dir> --policies <policy>

# Stage 4: evaluate (unchanged)
refiner evaluate <run-dir> --policies <policy>
```

Existing `--skip-ingest` and `--skip-refine` flags map naturally: `--skip-ingest` skips the risk-landscaper call, `--skip-refine` skips the refiner call.

## Test Migration

~58 tests move from `refiner/tests/` to `risk-landscaper/tests/`:
- `test_ingest.py` (15 tests)
- `test_map_risks.py` (35 tests)
- `test_build_landscape.py` (8 tests)
- New `test_detect_domain.py` for the simplified domain detection

Tests updated to import from `risk_landscaper.*` instead of `refiner.*`.
