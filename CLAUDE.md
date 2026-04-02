# Taxonomy Refiner

Tooling to transform client content policies into standards-aligned risk taxonomies with structured domain context, for red-team prompt generation against LLM deployments.

## Project Context

This project builds on the **AI Atlas Nexus** ontology and knowledge graph (`/Users/hjrnunes/workspace/redhat/ibm/ai-atlas-nexus`), which integrates 10 AI risk frameworks with 600+ unique risk entries and cross-taxonomy mappings (IBM Risk Atlas, NIST AI RMF, OWASP Top 10 for LLMs, AIR 2024, MIT AI Risk Repository, AILuminate, Credo, AIUC-1, CSIRO).

## Design Notes (Obsidian)

Detailed design thinking lives in Obsidian vault notes:

- **AI Atlas Nexus - Client Policy Taxonomies** — Methodology for classifying, enriching, cross-mapping, and gap-analysing client policies. Policy type classification (A: Safety, B: Confidentiality, C: Scope/Regulatory, D: Routing). Output formats (taxonomy YAML, SSSOM TSV mappings, gap reports).
- **AI Atlas Nexus - Ontology Overview** — Schema modules, core entities (RiskTaxonomy, RiskGroup, Risk, Action, RiskControl), relationships, and the 10 integrated risk frameworks.
- **AI Atlas Nexus - Domain Context Generation** — Three-layer ontology stack (CCO -> Domain Ontology -> Client Instances) for generating diverse, semantically grounded prompts. CCO classes as variation axes, domain ontology enumerations, runtime parsing, industry profiles. Aramco walkthrough showing multi-ontology coverage gaps. LLM querying strategy (semantic search + traversal tools via MCP servers).
- **AI Atlas Nexus - Industrial Ontology Portal Survey** — Comprehensive survey of ~136 ontologies on industryportal.enit.fr. Tiered by CCO alignment: Tier 1 (ROMAIN, SIMPM import CCO directly), Tier 2 (IOF family, MSDL, IAO, PMDCO etc. are BFO-aligned), Tier 3 (UNSPSC, EMMO, SCOR, NORIA-O etc. useful but not BFO-aligned). Documents gaps (no finance, healthcare, telecom, oil & gas on portal).
- **AI Atlas Nexus - Domain Ontology Selection** — Ontology selection for 5 priority verticals (Financial Services, Healthcare, Telecom, Insurance, Government). OMG Commons as bridge hub between CCO/IOF and FIBO. Per-domain ontology stacks with class counts, formats, licenses, BFO alignment, bridge strategies. Healthcare easiest (all BFO-native), Insurance hardest (no existing ontology). Key finds: DPV EU AI Act extension for government, NORIA-O+UCO for telecom, FIBO via Commons bridge for finance.

## Directory Structure

```
ontoquery/                 # Ontology MCP server + CLI
  pyproject.toml           # uv project: rdflib, pyoxigraph, chromadb, typer, mcp[cli]
  src/ontoquery/
    cli.py                 # Typer CLI: index, search, navigate commands
    backend.py             # GraphBackend Protocol + OxigraphBackend + RdflibBackend
                           # Factory functions: create_index_backend(), load_backend()
    graph.py               # rdflib graph utilities (used by RdflibBackend)
                           # Includes: get_siblings, get_subclasses_recursive, get_class_definition
    index.py               # ChromaDB indexing and semantic search (OntologyIndex class)
                           # Includes: search_raw() for single-query MCP tool use
    mcp_server.py          # MCP server with 7 tools (FastMCP, stdio transport)
                           # Tools: search_classes, get_class_definition, get_subclasses,
                           # get_superclasses, get_siblings, get_properties, explore_class
                           # Entry point: ontoquery-mcp
  tests/                   # 103 tests (pytest)
  .chroma/                 # Runtime: ChromaDB + oxigraph/ RocksDB store (gitignored)

nexus-mcp/                 # AI Atlas Nexus MCP server
  pyproject.toml           # uv project: mcp[cli], chromadb, ai-atlas-nexus (git dep)
  src/nexus_mcp/
    risk_index.py          # ChromaDB semantic index over risk descriptions (~600 entries)
    server.py              # MCP server with 8 tools (FastMCP, stdio transport)
                           # Tools: search_risks, get_risk_details, get_related_risks,
                           # get_related_actions, list_taxonomies, list_risk_groups,
                           # explore_risk, gap_analysis
                           # Entry point: nexus-mcp
  tests/                   # 19 tests (pytest)
  .chroma/                 # Runtime: ChromaDB persistent store (gitignored)

ontologies/
  CommonCoreOntologies/    # CCO — mid-level ontology (BFO-based, ISO standard)
                           # Provides structural constraints and semantic definitions
                           # Key modules: AgentOntology.ttl, ArtifactOntology.ttl,
                           # InformationEntityOntology.ttl
                           # src/cco-modules/ has the .ttl files
  ontology/                # IOF (Industrial Ontology Foundry) — built on BFO+CCO
                           # Manufacturing, supply chain, maintenance domain ontology
  commons/                 # OMG Commons (22 modules, .rdf) — bridge hub between
                           # IOF/BFO and FIBO ecosystems
  fibo/                    # FIBO Q4 2025 (297 .rdf files across 10 domains)
                           # Financial services domain ontology
  obo/                     # OBO Foundry healthcare ontologies (.owl)
                           # ogms, mondo-base, hp-base, uberon-base, maxo, oae
  d3fend-ontology/         # MITRE D3FEND v1.3.0 — cybersecurity countermeasures (OWL 2 DL)
                           # 4,366 classes: OffensiveTechnique (849), DigitalArtifact (896),
                           # Weakness/CWE (943), DefensiveTechnique (272)
                           # ATT&CK Enterprise/Mobile/ICS + ATLAS (AI) + SPARTA (space)
                           # Has CCO mapping: DigitalArtifact → CCO InformationBearingArtifact
                           # src/ontology/d3fend-protege.ttl is the main file
  cso/                     # Content Safety Ontology (CSO) — ~195 classes
                           # 9 harm categories: Violence, Hate/Discrimination, Self-Harm,
                           # Sexual Exploitation, Sexual Content, Fraud/Deception,
                           # Dangerous Information, Intellectual Property, Privacy Violation
                           # Standalone (not BFO-aligned), rdfs:comment for definitions
                           # Namespace: http://taxonomy-refiner.io/ontologies/cso#
  dron-base.owl            # Drug Ontology — excluded from obo/ (770k classes,
                           # only 72 with definitions, too large for ChromaDB)

refiner/                   # LLM pipeline: policy → taxonomy + domain context
  pyproject.toml           # uv project: instructor, openai, pydantic, typer, pyyaml
                           # Optional: mlflow>=2.14 under [tracking] extra
  src/refiner/
    cli.py                 # Typer CLI: `refiner run`, `refiner emit`, `refiner evaluate`, `refiner track`
    pipeline.py            # Pipeline orchestration: stage sequencing, state threading
    emit.py                # Emit dataset: domain context → sdg_hub-ready JSONL (pure Python)
    evaluate.py            # Post-hoc evaluation: metrics, coverage, quality analysis
    tracking.py            # MLflow integration: params, metrics, artifacts, run linking
    judge.py               # Judge-model evaluation: 4-dimension rubric scoring (LLM)
    debug.py               # Per-call debug logging + MLflow trace spans (dual-write)
    models.py              # 11 Pydantic models + RunReport dataclass for stage I/O
    llm.py                 # Instructor + OpenAI client setup, LLMConfig
    stages/
      classify.py          # Stage 1: Policy type classification (A/B/C/D)
      identify_domains.py  # Stage 2: LLM selects relevant domain ontologies
                           # Also contains derive_source_ontology() used by anchor + contextualize
      map_risks.py         # Stage 3: Policy→risk mapping + ground-truth cross-mappings
      anchor.py            # Stage 4: Variation axis identification (with domain filtering)
      contextualize.py     # Stage 5: Domain context profiles (with sibling fallback)
      structure.py         # Stage 6: LinkML-conformant YAML assembly (deterministic)
  tests/                   # 245 tests (pytest)
  tools/
    assess_run.py          # Run assessment data extraction (see Run Assessment below)

redteam/                   # Adversarial prompt generation via sdg_hub
  pyproject.toml           # uv project: sdg_hub, pandas, nest_asyncio
  src/redteam/
    generate.py            # CLI: load emit dataset, run sdg_hub flow, save results
                           # Builds HTML explorer automatically after generation
                           # Entry point: redteam
  flows/
    flow.yaml              # Companion sdg_hub flow (3 blocks: LLMChat, Extractor, JSONParser)
  tools/
    build_explorer.py      # Build HTML explorer from JSON/JSONL output
    explorer_template.html # Alpine.js + Tailwind template for browsing results

policy_examples/
  swb.json                 # South West Bank — banking domain, 6 policies
                           # Mix of safety, confidentiality, regulatory, routing
                           # Named entities: Jenny Carlson (CEO), Mark Warden (CFO),
                           # Ursula Berger (CTO), CreditAlpha (credit card product)
  generic.json             # Generic safety policies — 8 policies
                           # All Type A (safety): illegal activity, hate speech,
                           # malware, violence, fraud, sexually explicit,
                           # misinformation, self harm
  aramco.json              # Aramco — energy/oil & gas domain, 5 policies
                           # Proprietary data, operational security, supply chain,
                           # cybersecurity, sanctions evasion

runs/                      # Pipeline run outputs (gitignored)
                           # Each subdirectory contains: *-taxonomy.yaml, *-domain-context.yaml,
                           # *-report.yaml, *-evaluation.json, dataset.jsonl,
                           # adversarial_prompts.jsonl, adversarial_prompts.html,
                           # debug/ (per-LLM-call JSON), assessment.md (qualitative analysis)
```

## Key Concepts

### Three-Layer Ontology Stack

1. **CCO** (mid-level) — semantic constraints and class definitions. e.g. `cco:AuthorityRole`, `cco:FinancialInstrument`, `cco:ProcessProhibition`
2. **Domain Ontology** (industry-level) — enumerations. FIBO for banking, OBO/SNOMED for healthcare, IOF for manufacturing, TMF SID for telecom
3. **Client Instances** — specific named entities from the policy JSON (anchors)

### CCO Classes as Variation Axes

Client entities are instances of CCO classes. The class defines the variation space for prompt generation — not just "Jenny Carlson (CEO)" but any `cco:Person` bearing `cco:AuthorityRole`. Each risk has multiple variation axes, each grounded in a CCO class.

### Cross-Mapping Amplifies Prompt Generation

A single client risk maps to multiple risks across the 600+ in the knowledge graph. Each cross-mapped risk provides an alternative framing, producing more diverse adversarial prompts from a single policy concept.

## Related Projects

- **AI Atlas Nexus**: `/Users/hjrnunes/workspace/redhat/ibm/ai-atlas-nexus`
  - Schema: `src/ai_atlas_nexus/ai_risk_ontology/schema/` (LinkML YAML)
  - Knowledge graph data: `src/ai_atlas_nexus/data/knowledge_graph/` (auto-discovered YAML)
  - Mappings: `src/ai_atlas_nexus/data/mappings/` (SSSOM TSV)
  - Python API: `AIAtlasNexus(base_dir=...)` for loading and querying
- **CCO source** (also at): `/Users/hjrnunes/workspace/sandbox/CommonCoreOntologies`

## Domain Ontologies by Industry

| Industry | Domain Ontologies | BFO? | Bridge Strategy | Notes |
|---|---|---|---|---|
| Banking/Finance | **FIBO** (~1,500 class subset) + OMG Commons | No (Commons-based) | CCO→Commons (~20-30 axioms) | ACTUS contract types included. KYC/AML extension needed. |
| Healthcare | **OGMS** + MONDO + HPO + UBERON + MAXO + OAE | All yes (OBO Foundry) | None needed | ~82k classes (DRON excluded — 770k label-only drug products). SNOMED CT + RxNorm via API only. |
| Telecom | **NORIA-O** + UCO Observable + TMF Open API extracts | No | Direct CCO bridge (~10 axioms) | Multi-source. OpenConfig/3GPP for network config. |
| Insurance | **FIBO FND/FBC** + custom extension (~50-100 classes) | No | Via FIBO's Commons bridge | No mature insurance ontology exists anywhere. |
| Government | **DPV EU AI Act** + CPSV-AP + Core Person + W3C ORG | No | Direct CCO bridge (~10 axioms) | DPV has ~170 AI Act concepts. NIEM for US scope. |
| Manufacturing | IOF | Yes (explicit BFO+CCO) | Already in `ontologies/ontology/` | Not a priority vertical currently. |
| Content Safety (cross-domain) | **CSO** (~195 classes) | No (standalone) | N/A | Always-included. Covers harm categories CCO lacks. |
| Cybersecurity (cross-domain) | **D3FEND** (4,366 classes) | OWL 2 DL, CCO mapping | Has `d3fend-cco.ttl` mapping | ATT&CK + CWE + ATLAS (AI) + SPARTA. Always-included domain. |

OMG Commons (22 modules, MIT) is the interoperability hub: IOF maps to it (in repo), FIBO imports ~16 modules from it. See Obsidian note "AI Atlas Nexus - Domain Ontology Selection" for full analysis.

https://industryportal.enit.fr/ontologies lists many industry ontologies (mostly manufacturing/construction)

## Ontology Foundation

BFO (Basic Formal Ontology) is the ISO-standard top-level ontology (~35 classes). CCO is the mid-level (~5,000 classes). Domain ontologies (IOF, FIBO, OBO) extend from BFO or BFO+CCO. All BFO-based ontologies share the same fundamental distinctions (Continuant vs Occurrent, Material Entity, Role, Process, etc.) which makes multi-ontology composition possible.

Finding CCO-aligned ontologies:
- CCO home page project list: https://commoncoreontology.github.io/cco-webpage/
- Industrial Ontology Portal: https://industryportal.enit.fr/ontologies/CCO
- OBO Foundry (BFO-aligned, bio/medical): https://obofoundry.org

Other mid-level ontologies (not BFO-based): DOLCE+DUL, SUMO (IEEE), UFO (OntoUML). We use BFO+CCO because of its domain ontology ecosystem.

## MCP Servers

Two MCP servers enable Claude Code to drive taxonomy generation and domain context workflows interactively via tool use. Both use stdio transport.

### Ontology MCP Server (`ontoquery-mcp`)

Extends the `ontoquery/` package. Requires a pre-existing ChromaDB index (`ontoquery index` must be run first).

**Tools (7):**
| Tool | Parameters | Returns |
|------|-----------|---------|
| `search_classes` | `query`, `top_k=10` | Semantic search over 85k+ ontology class labels/definitions |
| `get_class_definition` | `class_uri` | `{uri, label, definition, superclasses}` |
| `get_subclasses` | `class_uri`, `depth=1` | BFS subclasses with depth tracking |
| `get_superclasses` | `class_uri` | Direct named superclasses |
| `get_siblings` | `class_uri` | Classes sharing same superclass |
| `get_properties` | `class_uri` | Properties where class is domain or range |
| `explore_class` | `class_uri` | Composite: definition + subclasses + siblings + properties |

**Config:** `ONTOQUERY_CHROMA_DIR` env var (default: `.chroma/`)

### AI Atlas Nexus MCP Server (`nexus-mcp`)

Separate uv project at `nexus-mcp/`. Wraps the AIAtlasNexus Python API + ChromaDB semantic index over risk descriptions.

**Tools (8):**
| Tool | Parameters | Returns |
|------|-----------|---------|
| `search_risks` | `query`, `top_k=10` | Semantic search across all 10 frameworks |
| `get_risk_details` | `risk_id` | Full risk entry (supports ID or tag lookup) |
| `get_related_risks` | `risk_id` | Cross-framework mappings with type (exact/close/broad/narrow/related) |
| `get_related_actions` | `risk_id` | Mitigation actions linked to a risk |
| `list_taxonomies` | — | All frameworks with risk counts |
| `list_risk_groups` | `taxonomy=None` | Risk groups, optionally filtered |
| `explore_risk` | `risk_id` | Composite: details + mappings + actions |
| `gap_analysis` | `risk_descriptions`, `target_taxonomy`, `distance_threshold=0.5` | Coverage analysis: covered/gaps/percentage |

**Config:** `NEXUS_BASE_DIR` env var (required, path to ai-atlas-nexus repo), `NEXUS_CHROMA_DIR` (default: `.chroma/`)

### Design Patterns

- **`GraphBackend` Protocol** — `typing.Protocol` (structural subtyping) abstracts over `OxigraphBackend` (Rust/RocksDB, default) and `RdflibBackend` (pure Python, fallback). Consumers receive a backend, not a raw graph.
- **`create_tool_handlers()`** — both servers separate tool logic into a function returning a dict of callables, enabling testing without MCP transport
- **Lazy-singleton `_get_handlers()`** — heavy state (graph backend, ChromaDB, AIAtlasNexus) loaded once on first tool call
- **`get_related_risks()`** reads five mapping attributes directly from Risk objects to preserve mapping_type (the `nexus.get_related_risks()` API flattens and loses this)

**Spec:** `docs/superpowers/specs/2026-04-01-mcp-servers-design.md`
**Plan:** `docs/superpowers/plans/2026-04-01-mcp-servers.md`

## Refiner Pipeline

6-stage batch pipeline at `refiner/`. Transforms client policies → taxonomy YAML + domain context profiles.

**Stack:** Instructor + OpenAI SDK (`instructor.Mode.JSON`), self-hosted models via OpenAI-compatible endpoints (vLLM, TGI, llama.cpp). Tested with Gemma 2 9B IT Abliterated on OpenShift vLLM.

**Stages:**
1. **Classify** — A/B/C/D policy type classification
2. **Identify Domains** — LLM selects relevant domain ontologies (FIBO/OBO/IOF)
3. **Map Risks** — semantic search + LLM ranking of candidate risks; collects ground-truth cross-mappings from knowledge graph
4. **Anchor** — variation axis identification; ontology search filtered by selected domains
5. **Contextualize** — domain context profiles from subclasses (with sibling fallback for leaf nodes)
6. **Structure** — deterministic LinkML-conformant YAML assembly with ground-truth cross-mappings

**Key patterns:**
- **Slim response models:** Private `_`-prefixed Pydantic models without docstrings for LLM calls. Metadata stitched back programmatically. No docstrings — Instructor embeds them in JSON schema, confusing small models.
- **Ground-truth cross-mappings:** `get_related_risks()` from knowledge graph, not LLM-generated. Eliminates hallucinated cross-mapping IDs.
- **Domain filtering:** `identify_domains` stage selects ontologies; `anchor` stage filters `search_classes` results by URI namespace before sending to LLM. CCO, Commons, D3FEND, and CSO are always-included (domain-independent); FIBO/OBO/IOF are selectable.
- **Sibling fallback:** `contextualize` stage falls back to `get_siblings()` when `get_subclasses()` returns empty (leaf nodes). Many FIBO/CCO leaf classes have useful siblings. Each `AxisEnumeration` carries a `provenance` field (`"subclass"` or `"sibling"`) for downstream quality analysis.
- **Programmatic retrieval:** Python calls `create_tool_handlers()` dicts from ontoquery + nexus-mcp (no MCP transport). Ontoquery uses `GraphBackend` protocol (oxigraph by default). LLM receives pre-assembled context and produces structured output.
- **Per-call debug logging:** `--debug <dir>` writes JSON file per LLM call with full prompts, responses, and context. When `--track` is active, also creates MLflow trace spans (dual-write via `debug.log_call()`).

**Pipeline events:** Each stage emits structured events to a `RunReport` dataclass (14 event types: type_distribution, selected_domains, invalid_domain_key, weak_match, invalid_risk_index, match_count, domain_filtered, cache_hit, empty_axes, role_derivation, sibling_fallback, empty_enumerations, self_reference_filtered, cross_mapping_filtered). Report written as `*-report.yaml`.

**CLI:**
```bash
cd refiner
uv run refiner run ../policy_examples/swb.json --output /tmp/out --debug /tmp/debug
uv run refiner run ../policy_examples/swb.json --until identify_domains  # partial run
uv run refiner emit /tmp/out --policies ../policy_examples/swb.json --samples-per-risk 10
uv run refiner evaluate /tmp/out --policies ../policy_examples/swb.json  # post-hoc metrics
uv run refiner evaluate /tmp/out --emit /tmp/dataset.jsonl --adversarial /tmp/adv.jsonl  # full evaluation
uv run refiner evaluate /tmp/out --adversarial /tmp/adv.jsonl --judge --judge-sample 20  # with judge scoring

# MLflow tracking (requires: uv sync --extra tracking)
uv run refiner run ../policy_examples/swb.json --output /tmp/out --track --tracking-uri $MLFLOW_TRACKING_URI
uv run refiner evaluate /tmp/out --track --tracking-uri $MLFLOW_TRACKING_URI  # logs metrics to same MLflow run
uv run refiner track /tmp/out --tracking-uri $MLFLOW_TRACKING_URI  # backfill existing run
```

**Config:** `REFINER_BASE_URL`, `REFINER_MODEL`, `REFINER_API_KEY`, `NEXUS_BASE_DIR`, `ONTOQUERY_CHROMA_DIR`, `NEXUS_CHROMA_DIR`, `MLFLOW_TRACKING_URI`

**Spec:** `docs/superpowers/specs/2026-04-01-refiner-llm-layer-design.md`
**Plan:** `docs/superpowers/plans/2026-04-01-refiner-llm-layer.md`

## Emit Dataset

Pure Python command (`refiner emit`) that transforms domain context profiles (output of the refiner pipeline) into an sdg_hub-ready JSONL dataset for adversarial prompt generation. No LLM calls. Designed to be re-runnable with different sampling parameters without re-running the expensive refiner pipeline.

**Data flow:**
```
refiner run (LLM) → domain-context.yaml + taxonomy.yaml
                            ↓
refiner emit (pure Python) → dataset.jsonl
                            ↓
sdg_hub flow.generate() (LLM) → adversarial prompts
```

**Hybrid integration:** We do sampling + prompt building; sdg_hub does LLM execution + response parsing via a companion `redteam/flows/flow.yaml` (3 blocks: LLMChatBlock, ResponseExtractor, JSONParser).

**Key design:**
- **Relevance-weighted sampling:** `high=3, medium=2, low=1`, normalized per axis to probability distribution. Deduplication by URI tuple across axes.
- **Scenario-first prompts:** Domain context entities define the world; harm emerges naturally. Axis `role` field (agent, object, instrument, location, temporal) gives semantic guidance on how each entity participates.
- **Full ontology traceability:** `sampled_axes` column carries provenance: generated prompt → sampled value → ontology class URI → CCO axis → role in risk → risk → policy concept.
- **SampledAxis model:** `cco_class_uri`, `cco_class_label`, `role`, `sampled_uri`, `sampled_label`, `source_ontology`, `relevance`.

**Output columns:** `generation_prompt` (chat messages), `policy_concept`, `concept_definition`, `risk_id`, `risk_name`, `sampled_axes`.

**CLI:**
```bash
cd refiner

# Emit dataset (cheap, re-runnable with different params)
uv run refiner emit /tmp/refiner-out --policies ../policy_examples/swb.json \
  --samples-per-risk 10 --seed 42 --output /tmp/dataset.jsonl

# Generate adversarial prompts via sdg_hub (separate project)
cd ../redteam
uv run redteam /tmp/dataset.jsonl \
  --model hosted_vllm/my-model --api-base http://localhost:8080/v1
```

**Spec:** `docs/superpowers/specs/2026-04-01-emit-dataset-design.md`
**Plan:** `docs/superpowers/plans/2026-04-01-emit-dataset.md`

## Evaluation Framework

Post-hoc evaluation of pipeline outputs via `refiner evaluate`. Two components: structured pipeline events during execution, and metrics computed after.

**Pipeline events (evaluate.py: `aggregate_stage_quality`):**
- 14 event types across 6 stages, emitted to `RunReport` on `PipelineState`
- Each stage accepts `report=None` (backward compatible); events appended with `if report:` guards
- Written as `*-report.yaml` alongside taxonomy and domain context outputs

**Coverage metrics (evaluate.py):**
- `compute_risk_framework_coverage` — maps risk IDs to frameworks by prefix convention (ibm-risk-atlas-*, owasp-llm-*, etc.)
- `compute_policy_coverage` — per-policy risk counts, axis counts, enumeration counts; zero-match detection when policies JSON provided
- `compute_ontological_coverage` — unique axis classes, unique enumeration URIs, breakdown by source ontology
- `compute_cross_mapping_coverage` — cross-mapping utilization from taxonomy entries
- `compute_single_value_axis_dominance` — fraction of axes with ≤1 enumeration (predicts prompt repetition)
- `compute_enumeration_domain_mismatch` — enumerations from ontologies outside selected domains (e.g. FIBO in healthcare runs)

**Proxy quality metrics (evaluate.py):**
- `compute_generation_metrics` — axis diversity (sampled/available per risk), role distribution, relevance distribution, dedup saturation (samples vs combinatorial space)
- `compute_enumeration_concentration` — top-k share of sampled enumeration values (Herfindahl-style dominance)
- `compute_adversarial_metrics` — lexical diversity (TTR), mean prompt length, domain term hit rate, red-flag pattern scan (13 patterns), per-policy breakdown
- `compute_policy_coverage_balance` — Shannon entropy of prompt distribution across policies (normalized 0-1)
- `compute_jargon_leak_rate` — prompts containing ontology naming patterns (CamelCase, "Artifact Function", "Act of X")
- `compute_axis_fidelity` — per-prompt word-overlap check of sampled axis labels against prompt text; classifies prompts as full/partial/improvised
- `compute_named_entity_utilization` — extracts proper nouns from policy definitions (Title Case sequences, CamelCase), checks presence in prompts
- `compute_weak_match_impact` — groups prompts by weak-match vs strong-match risks, compares distributions; optionally compares judge scores between groups
- `compute_semantic_diversity` — TF-IDF cosine pairwise distance across prompts (catches meaning repetition that TTR misses); per-policy breakdown; pure Python, no extra deps
- `compute_sibling_relevance` — compares relevance distributions (high/medium/low) between subclass-sourced and sibling-sourced enumerations; uses `provenance` field on `AxisEnumeration`

**Judge-model evaluation (judge.py):**
- `judge_prompt` — Instructor-based LLM call scoring on 4 dimensions (1-5 scale): subtlety, plausibility, domain_grounding, policy_relevance
- `aggregate_judge_results` — mean/median/std per dimension
- CLI integration: `--judge` flag on `refiner evaluate`, with `--judge-model`, `--judge-base-url`, `--judge-api-key`, `--judge-sample`

**Orchestration (evaluate.py: `run_evaluation`):**
- Discovers `*-report.yaml`, `*-taxonomy.yaml`, `*-domain-context.yaml` via `_discover_file` glob
- Accepts optional `emit_path`, `adversarial_path`, `policies_path` for additional metrics layers
- Returns nested dict with sections: run, stage_quality, coverage (includes single_value_axis_dominance, enumeration_domain_mismatch, sibling_relevance), generation_metrics (includes enumeration_concentration), prompt_metrics (includes policy_coverage_balance, jargon_leak_rate, axis_fidelity, named_entity_utilization, weak_match_impact, semantic_diversity), judge_evaluation

**Spec:** `docs/superpowers/specs/2026-04-01-evaluation-metrics-design.md`
**Plan:** `docs/superpowers/plans/2026-04-01-evaluation-metrics.md`

## MLflow Tracking

Optional MLflow integration for cross-run comparison and experiment lifecycle tracking. Wraps `refiner run` (tracing) and `refiner evaluate` (metrics/artifacts).

**Install:** `uv sync --extra tracking` (adds `mlflow>=2.14`)

**Components:**
- `tracking.py` — Core MLflow logic: `log_run_to_mlflow()`, git context, metric flattening, artifact whitelisting, run linking
- `debug.py` — Dual-write: JSON files + MLflow trace spans per LLM call (via `try/except ImportError` guard)
- `cli.py` — `--track`, `--tracking-uri`, `--description` flags on `run`/`evaluate`; standalone `track` command

**Data flow:**
```
refiner run --track
  ├── mlflow.start_run() → creates MLflow run, writes .mlflow-run-id
  ├── pipeline executes → debug.log_call() creates trace spans per LLM call
  └── logs output artifacts (taxonomy, domain context, report YAML)

refiner evaluate --track
  ├── reads .mlflow-run-id → reopens existing run (or creates new)
  ├── computes all metrics
  └── logs flattened metrics + evaluation artifacts

refiner track <output-dir>
  ├── reads *-evaluation.json + .mlflow-run-id
  └── logs params + metrics + artifacts (backfill, no traces)
```

**Experiment organization:** One MLflow experiment per policy set (e.g. `swb`, `generic`, `aramco`). Runs vary by model, git SHA, and configuration. Cross-run comparison answers: "did this change make prompts better?"

**Run linking:** `refiner run --track` writes `.mlflow-run-id` to the output directory. `refiner evaluate --track` reads it to reopen the same run — traces and metrics live together. If absent, a new run is created.

**What gets logged:**
- **Params:** model, policy_set, selected_domains, git_sha, git_dirty
- **Tags:** description (optional), timestamp, stages_completed
- **Metrics (22 flattened scalars):** coverage.total_risks_matched, coverage.single_value_axis_rate, coverage.cross_mapping_utilization, generation.axis_diversity, prompt.lexical_diversity, prompt.semantic_diversity, judge.subtlety, etc. Conditional — absent metrics are simply not logged.
- **Artifacts:** Whitelisted glob patterns (*-taxonomy.yaml, *-evaluation.json, dataset.jsonl, adversarial_prompts.jsonl, assessment.md, debug/, etc.)
- **Traces:** One span per LLM call with full prompt/response payloads, named by stage + context slug (e.g. `map_risks-illegal-activity`)

**Key patterns:**
- **Optional dependency:** Everything works without mlflow. `tracking.py` imported only when `--track` is used. `debug.py` uses `try/except ImportError` for silent no-op.
- **Immutable params guard:** `log_run_to_mlflow()` skips `log_params` when reopening an existing run (MLflow params are immutable).
- **Artifact whitelist:** Only known pipeline outputs are uploaded — `.mlflow-run-id` and stale files excluded.
- **Git SHA tracking:** Captures code state (prompt templates, pipeline logic, filtering rules) via `git rev-parse HEAD` + `git status --porcelain`.

**Spec:** `docs/superpowers/specs/2026-04-02-mlflow-integration-design.md`
**Plan:** `docs/superpowers/plans/2026-04-02-mlflow-integration.md`

## Run Assessment

Qualitative assessment of adversarial prompt quality from pipeline runs. Each run directory in `runs/` gets an `assessment.md` with best/worst examples, systematic issues, distribution stats, and root cause analysis.

**Data extraction:**
```bash
cd refiner
uv run python tools/assess_run.py ../runs/<run-name>
```

`assess_run.py` reads all pipeline outputs (taxonomy, domain context, report, evaluation JSON, adversarial prompts JSONL, debug logs) and prints structured data: run metadata, taxonomy summary, pipeline events, domain context profiles (empty axes/enumerations, relevance distribution), all adversarial prompts with axes, evaluation metrics, and debug log token estimates.

**Assessment structure** (written as `runs/<run-name>/assessment.md`):
- Run metadata and dataset summary
- Best examples (5-6 prompts) — what makes them effective boundary probes
- Worst examples (4-5 prompts) — why they fail (off-domain, ontology jargon, no policy boundary tested)
- Systematic issues — patterns across the full set (axis saturation, ontology mismatches, empty axes)
- Pattern table — which ontology groundings produce effective vs ineffective prompts
- Root causes — why the issues exist (ontology coverage gaps, domain filter limitations, model behaviour)
- Distribution stats — source ontology, roles, policy coverage, prompt lengths, sampled values

**Known patterns from assessments:**
- Domain-specific policies (SWB banking) produce much stronger prompts than generic safety policies
- FIBO enumerations + named entities from policies = strongest prompts
- CCO safety vocabulary is shallow: `Act of Violence` (3 children), `Act of Deceptive Communication` (1 child)
- `Act of Propaganda` appears in ~30% of prompts across all runs — single child of `Act of Deceptive Communication`
- FIBO `SecurityIdentifier` matches "security" in infosec policies — semantic collision
- `Deception Artifact Function` siblings are all physical-world concepts (Thermal Control, Fuel, etc.)
- Malware and Obscene Content risks get zero axes after domain filtering — no relevant ontology loaded
- Model sometimes ignores bad axes and improvises better framings — useful but unreliable

## ontoquery CLI

Ontology query CLI at `ontoquery/`. Three commands:

```bash
cd ontoquery

# Index all ontologies into a single combined ChromaDB collection
uv run ontoquery index ../ontologies/CommonCoreOntologies/src/cco-modules/ \
  ../ontologies/commons/ ../ontologies/fibo/ ../ontologies/obo/
# → 338 files parsed, 85643 classes indexed

# Semantic search for a policy concept
uv run ontoquery search "Executive Compensation" "Information about compensation of senior executives"
# → JSON array with candidate classes ranked by distance

# Navigate class hierarchy
uv run ontoquery navigate "https://www.commoncoreontologies.org/ont00000449"
# → JSON with superclasses, subclasses, properties
```

### Key implementation details
- **Graph backend abstraction**: `GraphBackend` protocol in `backend.py` with two implementations:
  - **`OxigraphBackend`** (default): Rust-based via pyoxigraph, RocksDB persistent store at `.chroma/oxigraph/`. Parses 338 files in ~5s (vs ~6min with rdflib). Startup from persistent store: 8ms.
  - **`RdflibBackend`** (fallback): Pure Python, N-Triples cache at `.chroma/graph.nt`. Used when pyoxigraph is not installed.
  - Factory: `create_index_backend(files, chroma_dir)` for indexing, `load_backend(chroma_dir, source_dirs)` for runtime.
  - Pattern matching (`quads_for_pattern`) used for all traversals — faster than SPARQL for simple queries.
- **Definition extraction fallback**: `skos:definition` > `iof-av:naturalLanguageDefinition` > `obo:IAO_0000115` > `d3f:definition` > `rdfs:comment`
- **Format detection**: explicit `format="turtle"` for `.ttl`, `format="xml"` for `.rdf`/`.owl` (not auto-detected)
- **`owl:imports` not followed**: include imported ontology files in the indexed directory to get labels for cross-referenced classes
- **Property coverage**: `rdfs:domain`/`rdfs:range` only; OWL restrictions not yet extracted (most CCO/IOF relationships are via restrictions)
- **Graph utilities**: `get_siblings()`, `get_subclasses_recursive()` (BFS with depth), `get_class_definition()` — used by MCP server tools via backend protocol
- **CLI spec**: `docs/superpowers/specs/2026-03-31-ontoquery-cli-design.md`
- **CLI plan**: `docs/superpowers/plans/2026-03-31-ontoquery-cli.md`