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
  pyproject.toml           # uv project: rdflib, chromadb, typer, mcp[cli]
  src/ontoquery/
    cli.py                 # Typer CLI: index, search, navigate commands
    graph.py               # rdflib graph loading, class extraction, hierarchy navigation
                           # Includes: get_siblings, get_subclasses_recursive, get_class_definition
    index.py               # ChromaDB indexing and semantic search (OntologyIndex class)
                           # Includes: search_raw() for single-query MCP tool use
    mcp_server.py          # MCP server with 7 tools (FastMCP, stdio transport)
                           # Tools: search_classes, get_class_definition, get_subclasses,
                           # get_superclasses, get_siblings, get_properties, explore_class
                           # Entry point: ontoquery-mcp
  tests/                   # 52 tests (pytest)
  .chroma/                 # Runtime: ChromaDB persistent store + graph.nt cache (gitignored)

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
  dron-base.owl            # Drug Ontology — excluded from obo/ (770k classes,
                           # only 72 with definitions, too large for ChromaDB)

refiner/                   # LLM pipeline: policy → taxonomy + domain context
  pyproject.toml           # uv project: instructor, openai, pydantic, typer, pyyaml
  src/refiner/
    cli.py                 # Typer CLI: `refiner run` and `refiner emit` commands
    pipeline.py            # Pipeline orchestration: stage sequencing, state threading
    emit.py                # Emit dataset: domain context → sdg_hub-ready JSONL (pure Python)
    debug.py               # Per-call debug logging (--debug writes JSON per LLM call)
    models.py              # 11 Pydantic models for stage I/O contracts (incl. SampledAxis)
    llm.py                 # Instructor + OpenAI client setup, LLMConfig
    stages/
      classify.py          # Stage 1: Policy type classification (A/B/C/D)
      identify_domains.py  # Stage 2: LLM selects relevant domain ontologies
                           # Also contains derive_source_ontology() used by anchor + contextualize
      map_risks.py         # Stage 3: Policy→risk mapping + ground-truth cross-mappings
      anchor.py            # Stage 4: Variation axis identification (with domain filtering)
      contextualize.py     # Stage 5: Domain context profiles (with sibling fallback)
      structure.py         # Stage 6: LinkML-conformant YAML assembly (deterministic)
  flows/
    flow.yaml              # Companion sdg_hub flow for adversarial prompt generation
  tests/                   # 82 tests (pytest)

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

- **`create_tool_handlers()`** — both servers separate tool logic into a function returning a dict of callables, enabling testing without MCP transport
- **Lazy-singleton `_get_handlers()`** — heavy state (rdflib graph, ChromaDB, AIAtlasNexus) loaded once on first tool call
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
- **Domain filtering:** `identify_domains` stage selects ontologies; `anchor` stage filters `search_classes` results by URI namespace before sending to LLM.
- **Sibling fallback:** `contextualize` stage falls back to `get_siblings()` when `get_subclasses()` returns empty (leaf nodes). Many FIBO/CCO leaf classes have useful siblings.
- **Programmatic retrieval:** Python calls `create_tool_handlers()` dicts from ontoquery + nexus-mcp (no MCP transport). LLM receives pre-assembled context and produces structured output.
- **Per-call debug logging:** `--debug <dir>` writes JSON file per LLM call with full prompts, responses, and context.

**CLI:**
```bash
cd refiner
uv run refiner run ../policy_examples/swb.json --output /tmp/out --debug /tmp/debug
uv run refiner run ../policy_examples/swb.json --until identify_domains  # partial run
uv run refiner emit /tmp/out --policies ../policy_examples/swb.json --samples-per-risk 10
```

**Config:** `REFINER_BASE_URL`, `REFINER_MODEL`, `REFINER_API_KEY`, `NEXUS_BASE_DIR`, `ONTOQUERY_CHROMA_DIR`, `NEXUS_CHROMA_DIR`

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

**Hybrid integration:** We do sampling + prompt building; sdg_hub does LLM execution + response parsing via a companion `flow.yaml` (3 blocks: LLMChatBlock, ResponseExtractor, JSONParser).

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

# Then feed to sdg_hub:
# flow = Flow.from_yaml('refiner/flows/flow.yaml')
# dataset = pd.read_json('/tmp/dataset.jsonl', lines=True)
# result = flow.generate(dataset)
```

**Spec:** `docs/superpowers/specs/2026-04-01-emit-dataset-design.md`
**Plan:** `docs/superpowers/plans/2026-04-01-emit-dataset.md`

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
- **Definition extraction fallback**: `skos:definition` > `iof-av:naturalLanguageDefinition` > `obo:IAO_0000115` > `rdfs:comment`
- **Format detection**: explicit `format="turtle"` for `.ttl`, `format="xml"` for `.rdf`/`.owl` (not auto-detected)
- **Graph caching**: N-Triples dump at `.chroma/graph.nt` avoids re-parsing on every `navigate` call; invalidated on re-index
- **`owl:imports` not followed**: include imported ontology files in the indexed directory to get labels for cross-referenced classes
- **Property coverage**: `rdfs:domain`/`rdfs:range` only; OWL restrictions not yet extracted (most CCO/IOF relationships are via restrictions)
- **Graph utilities**: `get_siblings()`, `get_subclasses_recursive()` (BFS with depth), `get_class_definition()` — used by MCP server tools
- **CLI spec**: `docs/superpowers/specs/2026-03-31-ontoquery-cli-design.md`
- **CLI plan**: `docs/superpowers/plans/2026-03-31-ontoquery-cli.md`