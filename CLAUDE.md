# Taxonomy Refiner

Transforms client content policies into standards-aligned risk taxonomies with structured domain context, for red-team
prompt generation against LLM deployments. Built on the AI Atlas Nexus knowledge graph (600+ risks, 10 frameworks).

## Documentation

Detailed docs in `docs/`:

- `docs/architecture.md` — data flow, key concepts, three-layer ontology stack
- `docs/refiner.md` — pipeline stages, CLI, config, emit, evaluation, MLflow tracking
- `docs/ontoquery.md` — ontology query CLI + MCP server
- `docs/nexus-mcp.md` — risk knowledge graph MCP server
- `docs/ontologies.md` — ontology foundation, domain table, bridges, axiom extraction
- `docs/redteam.md` — adversarial prompt generation

Design specs and plans in `docs/superpowers/specs/` and `docs/superpowers/plans/`.

## Directory Structure

```
ontoquery/          # Ontology CLI + MCP server (rdflib, pyoxigraph, chromadb)
nexus-mcp/          # AI Atlas Nexus MCP server (chromadb, ai-atlas-nexus)
refiner/            # LLM pipeline + emit + evaluate (instructor, openai)
redteam/            # Adversarial prompt generation (sdg_hub)
ontologies/         # Ontology files (CCO, Commons, FIBO, OBO, D3FEND, CSO, bridges)
policy_examples/    # Sample policies: swb.json, generic.json, aramco.json
runs/               # Pipeline outputs (gitignored)
```

Each subproject is a separate uv project with its own `pyproject.toml` and `.venv`.

## Running

```bash
# Index ontologies (required before pipeline)
just index-ontologies

# Full battery: all policies × all models (parallel by model)
uv run scripts/run_battery.py my-run

# Single policy + model
uv run scripts/run_battery.py my-run --policy swb --model phi-4

# Skip stages (regen workflow: skip ingest + refine)
uv run scripts/run_battery.py my-run --skip-ingest --skip-refine

# Dry run (print commands without executing)
uv run scripts/run_battery.py my-run --dry-run

# Individual steps (without battery script)
cd refiner
uv run refiner run ../policy_examples/swb.json --output /tmp/out
uv run refiner emit /tmp/out --policies ../policy_examples/swb.json --samples-per-risk 10
uv run refiner evaluate /tmp/out --policies ../policy_examples/swb.json
```

Config: `battery.yaml` (policies, models, paths, settings).

## Testing

```bash
cd ontoquery && uv run pytest    # ~139 tests
cd nexus-mcp && uv run pytest    # ~19 tests
cd refiner && uv run pytest      # ~313 tests
```

## Code Conventions

### Pydantic Models for LLM Calls

- Private `_`-prefixed models (e.g. `_SlimRiskMatch`) — only fields the LLM must reason about
- NO docstrings on these models — Instructor embeds them in JSON schema, confusing small models
- Known metadata stitched back programmatically after LLM response

### MCP Server Pattern

- `create_tool_handlers()` returns dict of callables — enables testing without MCP transport
- Lazy-singleton `_get_handlers()` loads heavy state on first call
- Refiner pipeline calls handler dicts directly (no MCP transport)

### Backend Protocol

- `GraphBackend` (`typing.Protocol`) abstracts oxigraph (default) and rdflib (fallback)
- Factory: `create_index_backend()` for indexing, `load_backend()` for runtime
- Extended with `get_restrictions()`, `get_disjoint_classes()`, `get_equivalent_axioms()`

### Pipeline Patterns

- Ground-truth cross-mappings from knowledge graph, never LLM-generated
- Domain filtering: always-included (CCO, Commons, D3FEND, CSO) + selectable (FIBO, OBO, IOF)
- Per-domain ChromaDB collections with merge strategies (weighted/grouped)
- Sibling fallback when `get_subclasses()` returns empty (leaf nodes)
- BFO/CCO/Commons role derivation via `_CATEGORY_ROLES` (29 entries)
- `RunReport` events with `report=None` default + `if report:` guards (backward compat)
- Restriction/equivalence expansion capped at 3 additional candidates
- Disjointness validation guarded by `onto_handlers.get()` for backward compat

### URI Namespace Mapping

- Canonical: `derive_domain(uri)` in `ontoquery/index.py`
- Refiner delegates: `derive_source_ontology(uri)` in `identify_domains.py`

## Environment

| Variable               | Purpose                     |
|------------------------|-----------------------------|
| `REFINER_BASE_URL`     | LLM endpoint                |
| `REFINER_MODEL`        | Model name                  |
| `REFINER_API_KEY`      | API key                     |
| `NEXUS_BASE_DIR`       | Path to ai-atlas-nexus repo |
| `ONTOQUERY_CHROMA_DIR` | ontoquery ChromaDB path     |
| `NEXUS_CHROMA_DIR`     | nexus-mcp ChromaDB path     |
| `MLFLOW_TRACKING_URI`  | MLflow server URL           |

## Related Projects

- **AI Atlas Nexus**: `/Users/hjrnunes/workspace/redhat/ibm/ai-atlas-nexus` — schema, knowledge graph, mappings
- **CCO source**: `/Users/hjrnunes/workspace/sandbox/CommonCoreOntologies`

## Runs assessemnt

Produce an assessment.md inside each run's folder (check previous runs for format). 
There is also a script you can use: assess_run.py 
Do a global assessment in the end.
