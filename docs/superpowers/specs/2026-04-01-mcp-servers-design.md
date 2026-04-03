# MCP Servers for Risk Taxonomy & Domain Context Generation

**Date:** 2026-04-01
**Status:** Draft

---

## Overview

Two MCP servers that expose ontology querying and AI risk knowledge graph tools to an LLM (Claude Code), enabling interactive risk taxonomy generation and domain context generation from client content policies.

### Goals

1. Wrap the existing `ontoquery` CLI (oxigraph/rdflib + ChromaDB) as an MCP server for ontology exploration
2. Wrap the existing `AIAtlasNexus` Python API as an MCP server for risk search, cross-mapping, and gap analysis
3. Enable Claude to drive the full taxonomy generation and domain context workflows interactively via tool use

### Non-goals

- Prompt generation (downstream consumer of the outputs, future work)
- Automated pipelines (the LLM orchestrates interactively, no batch mode)
- Industry profile configs (future work — currently the LLM navigates ontologies directly)

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│  Claude Code                                          │
│                                                        │
│  Reads policy JSON → uses both MCP servers → produces: │
│  - Risk taxonomy YAML                                  │
│  - SSSOM TSV mappings                                  │
│  - Gap analysis report                                 │
│  - Domain context YAML                                 │
└────────────┬──────────────────────┬───────────────────┘
             │ stdio                │ stdio
    ┌────────▼────────┐   ┌────────▼────────────┐
    │ Ontology MCP    │   │ AI Atlas Nexus MCP   │
    │ Server          │   │ Server               │
    │                 │   │                       │
    │ oxigraph/rdflib  │   │ AIAtlasNexus API     │
    │ + ChromaDB      │   │                       │
    │ 85k+ classes    │   │ + ChromaDB            │
    │                 │   │ 600+ risks            │
    │ CCO, FIBO, OBO, │   │ 10 frameworks         │
    │ IOF, Commons    │   │ cross-mappings        │
    └─────────────────┘   └───────────────────────┘
```

Both servers use stdio transport for Claude Code integration.

---

## Server 1: Ontology MCP Server

### Location

Extends the existing `ontoquery/` package. New file: `ontoquery/src/ontoquery/mcp_server.py`. New script entry point `ontoquery-mcp` in `pyproject.toml`.

### Dependencies

Add `mcp[cli]` to existing `ontoquery/pyproject.toml`.

### Configuration

- `chroma_dir`: path to ChromaDB directory (default: `.chroma/`, overridable via `ONTOQUERY_CHROMA_DIR` env var)
- Requires pre-existing index — user runs `ontoquery index` beforehand

### Server State

On startup the server loads two objects:

1. **ChromaDB collection** — connects to existing persistent client at `chroma_dir` for semantic search
2. **GraphBackend** — loads the graph for hierarchy navigation and class definition lookups. Prefers `OxigraphBackend` (opens RocksDB store at `{chroma_dir}/oxigraph/` in ~8ms), falls back to `RdflibBackend` (loads N-Triples from `{chroma_dir}/graph.nt`). Both implement the `GraphBackend` protocol (`backend.py`).

Both are required. If either is missing (no index or no graph store), the server fails with a clear error message.

### Tools (7)

#### `search_classes`

Semantic search over indexed ontology class labels and definitions.

- **Parameters:** `query: str`, `top_k: int = 10`
- **Returns:** `[{uri, label, definition, distance, source_file}]`
- **Implementation:** Requires a new `OntologyIndex.search_raw(query, top_k)` method that accepts a single query string (the existing `search(concept, description)` concatenates two parameters internally). The new method passes the query directly to ChromaDB.

#### `get_class_definition`

Get full details for a single ontology class.

- **Parameters:** `class_uri: str`
- **Returns:** `{uri, label, definition, superclasses: [{uri, label}]}`
- **Implementation:** New function. Combines `_get_label()`, `_get_definition()`, and `get_superclasses()` from `graph.py`.

#### `get_subclasses`

Get subclasses of an ontology class, optionally recursive.

- **Parameters:** `class_uri: str`, `depth: int = 1`
- **Returns:** `[{uri, label, depth}]`
- **Implementation:** New function `get_subclasses_recursive(graph, class_uri, depth)` that wraps `graph.get_subclasses()` with BFS traversal up to `depth` levels. Each result includes its depth from the target class. When `depth=1`, equivalent to the existing `get_subclasses()`.

#### `get_superclasses`

Get direct named superclasses of an ontology class.

- **Parameters:** `class_uri: str`
- **Returns:** `[{uri, label}]`
- **Implementation:** Wraps existing `graph.get_superclasses()`.

#### `get_siblings`

Get other classes that share the same direct superclass.

- **Parameters:** `class_uri: str`
- **Returns:** `[{uri, label, shared_parent: {uri, label}}]`
- **Implementation:** New function. For each direct superclass of the target, finds all other subclasses of that superclass. Excludes the target class itself.

#### `get_properties`

Get properties where this class appears as domain or range.

- **Parameters:** `class_uri: str`
- **Returns:** `[{uri, label, role: "domain"|"range", other_class: {uri, label}}]`
- **Implementation:** Wraps existing `graph.get_properties()`.

#### `explore_class`

Composite tool — returns everything about a class in a single call.

- **Parameters:** `class_uri: str`
- **Returns:** `{uri, label, definition, superclasses, subclasses, siblings, properties}`
- **Implementation:** Calls `get_class_definition`, `get_subclasses(depth=1)`, `get_siblings`, and `get_properties` internally.

---

## Server 2: AI Atlas Nexus MCP Server

### Location

New uv project at `nexus-mcp/` in the taxonomy-refiner repo root.

```
nexus-mcp/
  pyproject.toml
  src/nexus_mcp/
    __init__.py
    server.py              # MCP server entry point
    risk_index.py           # ChromaDB semantic index over risks
```

### Dependencies

- `mcp[cli]` — MCP Python SDK
- `chromadb` — vector store for semantic search
- `ai-atlas-nexus` — git dependency from the ai-atlas-nexus repo

### Configuration

- `nexus_base_dir`: path to AI Atlas Nexus data directory (configurable via `NEXUS_BASE_DIR` env var, no default — must be set explicitly)
- On startup:
  1. Instantiates `AIAtlasNexus(base_dir=nexus_base_dir)` to load the knowledge graph
  2. Builds or loads a ChromaDB index over all risk entries at `nexus-mcp/.chroma/`

### Risk Index

`risk_index.py` indexes all risks from the knowledge graph into ChromaDB for semantic search.

- **Document format:** `"{name}: {description}. Concern: {concern}"`
- **Metadata per entry:** `{id, name, taxonomy, risk_type, group}`
- **Index size:** ~600 entries, builds in seconds
- **Staleness check:** on startup, compares collection count against `AIAtlasNexus.get_all_risks()` count. Rebuilds if mismatched.

### Tools (8)

#### `search_risks`

Semantic search over risk descriptions across all frameworks.

- **Parameters:** `query: str`, `top_k: int = 10`
- **Returns:** `[{id, name, description, concern, taxonomy, distance}]`
- **Implementation:** ChromaDB query over the risk index.

#### `get_risk_details`

Get full details for a single risk entry.

- **Parameters:** `risk_id: str`
- **Returns:** `{id, name, description, concern, risk_type, descriptor, taxonomy, group}`
- **Implementation:** Wraps `nexus.get_risk(id=risk_id)`. Falls back to `get_risk(tag=risk_id)` if ID lookup fails.

#### `get_related_risks`

Get cross-framework mappings for a risk.

- **Parameters:** `risk_id: str`
- **Returns:** `[{id, name, description, taxonomy, mapping_type}]` where `mapping_type` is one of: exact, close, broad, narrow, related
- **Implementation:** Cannot use `nexus.get_related_risks()` directly because it flattens all mapping lists and discards the mapping type. Instead, reads the source risk via `nexus.get_risk(id=risk_id)` and iterates its five mapping attributes (`exact_mappings`, `close_mappings`, `broad_mappings`, `narrow_mappings`, `related_mappings`) individually, resolving each referenced risk ID and tagging it with the source mapping type.

#### `get_related_actions`

Get mitigation actions linked to a risk.

- **Parameters:** `risk_id: str`
- **Returns:** `[{id, name, description}]`
- **Implementation:** Wraps `nexus.get_related_actions(id=risk_id)`.

#### `list_taxonomies`

List all risk taxonomies in the knowledge graph.

- **Parameters:** none
- **Returns:** `[{id, name, description, risk_count}]`
- **Implementation:** Calls `nexus.get_all_taxonomies()` and filters for `RiskTaxonomy` instances. Enriches each with a count of risks via `nexus.get_all_risks(taxonomy=taxonomy_id)`.

#### `list_risk_groups`

List risk groups, optionally filtered by taxonomy.

- **Parameters:** `taxonomy: str = None`
- **Returns:** `[{id, name, taxonomy, risk_count}]`
- **Implementation:** Calls `nexus.get_all("groups")` and filters for `RiskGroup` instances. If `taxonomy` is provided, further filters by `isDefinedByTaxonomy`. Enriches each with a risk count.

#### `explore_risk`

Composite tool — returns risk details + all cross-mappings + related actions.

- **Parameters:** `risk_id: str`
- **Returns:** `{...risk_details, related_risks: [...], related_actions: [...]}`
- **Implementation:** Calls `get_risk_details`, `get_related_risks`, and `get_related_actions` internally.

#### `gap_analysis`

Compare client risk descriptions against a target taxonomy to find coverage gaps.

- **Parameters:** `risk_descriptions: list[str]`, `target_taxonomy: str = "ibm-risk-atlas"`, `distance_threshold: float = 0.5`
- **Returns:** `{covered: [{target_risk, matched_description, distance}], gaps: [{target_risk}], coverage_pct: float}`
- **Implementation:**
  1. Gets all risks from the target taxonomy via `nexus.get_all_risks(taxonomy=target_taxonomy)`
  2. For each client risk description, runs a ChromaDB query with `where={"taxonomy": target_taxonomy}` metadata filter to restrict search to the target taxonomy's risks only
  3. Marks a target risk as "covered" if any client description matches within `distance_threshold`
  4. Returns covered risks (with the matching client description and distance), gap risks (unmatched), and coverage percentage

---

## Workflow 1: Risk Taxonomy Generation

Input: client policy JSON file (e.g., `policy_examples/swb.json`).

The LLM drives this workflow interactively using both MCP servers.

### Step 1 — Classify

The LLM reads the policy JSON and classifies each concept into type A/B/C/D:

| Type | What it is | Example |
|------|-----------|---------|
| A — Safety | LLM should never do this | Fraud, Money Laundering |
| B — Confidentiality | LLM must not disclose specific info | Executive Compensation |
| C — Scope/Regulatory | LLM isn't authorized to do this | Investment Advice |
| D — Routing | Legitimate need, wrong channel | Suspicious Activity Reporting |

The LLM may call **ontology** `search_classes("process prohibition")` to ground the classification in CCO's regulatory classes, but classification is primarily LLM judgment.

Output per concept: `{policy_concept, type, rationale}`

### Step 2 — Enrich

For each concept, the LLM assigns:

- `risk_type`: input / output / non-technical (almost always `output` for content policies)
- `concern`: distilled reason why it's a risk (derived from concept_definition)
- `group`: clusters related concepts into RiskGroups (e.g., "Confidential Information", "Regulatory Compliance", "Financial Crime")

### Step 3 — Cross-map

For each concept, the LLM:

1. Calls **nexus** `search_risks(concept_definition)` to find semantically similar risks across all 10 frameworks
2. For promising matches, calls `explore_risk(risk_id)` to see full details + existing cross-mappings
3. Assigns a mapping type: `exact_mappings`, `close_mappings`, `broad_mappings`, `narrow_mappings`, or `related_mappings`

Mapping type criteria:
- **exact** — interchangeable concepts
- **close** — sufficiently similar for information retrieval
- **broad** — target is broader than client concept
- **narrow** — target is narrower
- **related** — associative link

### Step 4 — Gap analysis

The LLM calls **nexus** `gap_analysis(risk_descriptions=[...], target_taxonomy="ibm-risk-atlas")` with the client's concept definitions. Repeats for other taxonomies to show coverage from multiple angles.

### Step 5 — Output

Three artifacts, generated by the LLM:

1. **Taxonomy YAML** — follows AI Atlas Nexus data format (`taxonomies`, `groups`, `entries` sections). Ready to drop into `data/knowledge_graph/`.
2. **SSSOM TSV** — cross-mapping file following existing format in `data/mappings/`.
3. **Gap report** — markdown summary: coverage percentage per framework, identified gaps, recommendations.

---

## Workflow 2: Domain Context Generation

Input: the same policy JSON, plus knowledge of the client's industry.

### Step 1 — Extract named entities

The LLM reads the policy JSON and identifies client-specific entities: people, organizations, products, and other named entities embedded in the concept definitions.

### Step 2 — Map entities to CCO classes

For each entity, the LLM calls **ontology** `search_classes(entity_description)` to find the right CCO class, then `get_class_definition(uri)` to verify the fit.

Example mappings:
- Jenny Carlson (CEO) → `cco:Person` bearing `cco:AuthorityRole`
- South West Bank → `cco:CommercialOrganization`
- CreditAlpha → `cco:FinancialInstrument`

### Step 3 — Identify variation axes per risk

For each risk, the LLM determines which CCO classes define the variation space. It calls `explore_class(cco_uri)` to understand semantic constraints (definitions), structural relationships (properties), and available enumerations (subclasses).

Example for "Executive Compensation":
- WHO: `cco:AuthorityRole` — who holds the role
- WHAT: compensation information — `cco:InformationContentEntity`
- WHERE: `cco:CommercialOrganization` — organizational context
- HOW: attack vector framing (direct/indirect/comparative/social-engineering)

### Step 4 — Enumerate via domain ontology

For each variation axis, the LLM bridges from the CCO class to the domain ontology:

1. Calls **ontology** `search_classes("corporate officer")` → finds FIBO classes
2. Calls `get_subclasses(fibo_uri, depth=2)` → CEO, CFO, COO, BoardChair, ...
3. These become the enumeration values for that axis

Where domain ontology coverage is thin (as with Aramco/IOF for cybersecurity), the LLM notes this as an "LLM fallback zone" — the axis exists but enumerations come from world knowledge.

### Step 5 — Output

**Domain context YAML** structured as:

```yaml
client: South West Bank
industry: banking

entities:
  - name: Jenny Carlson
    cco_class: cco:Person
    role: cco:AuthorityRole
    role_label: CEO
    relevant_risks: [executive-compensation]

  - name: CreditAlpha
    cco_class: cco:FinancialInstrument
    product_type: credit card
    relevant_risks: [debt-repayment-negotiation]

  - name: South West Bank
    cco_class: cco:CommercialOrganization
    relevant_risks: [executive-compensation, debt-repayment-negotiation, investment-advice, suspicious-activity-reporting]

variation_axes:
  executive-compensation:
    who:
      cco_class: cco:AuthorityRole
      definition: "A Role realized by Processes which create, modify..."
      anchors: [Jenny Carlson, Mark Warden, Ursula Berger]
      enumerations:
        source: fibo
        values: [ChiefExecutiveOfficer, ChiefFinancialOfficer, ChiefOperatingOfficer, BoardChair, ChiefRiskOfficer]
    what:
      cco_class: cco:InformationContentEntity
      anchors: [salary, bonus, healthcare insurance, company cars]
      enumerations:
        source: llm_fallback
        domain: "executive compensation components"
    where:
      cco_class: cco:CommercialOrganization
      anchors: [South West Bank]
      enumerations:
        source: fibo
        values: [RetailBank, CommercialBank, InvestmentBank, DepositoryInstitution]

  debt-repayment-negotiation:
    who:
      cco_class: cco:Person
      anchors: []
      enumerations:
        source: llm_fallback
        domain: "bank customers in debt distress"
    what:
      cco_class: cco:FinancialInstrument
      anchors: [CreditAlpha]
      enumerations:
        source: fibo
        values: [CreditCardAgreement, MortgageLoan, RevolvingCreditFacility, TermLoan, Overdraft]
    action:
      cco_class: cco:ProcessProhibition
      anchors: [reduce payments, delay payments, negotiate terms]
      enumerations:
        source: llm_fallback
        domain: "debt restructuring actions"
```

---

## How the Workflows Connect

The taxonomy generation workflow produces the **what to test** (classified risks, cross-mappings, gap reports). The domain context workflow produces the **with what** (entities, variation axes, ontology-grounded enumerations). Both can be run in sequence on the same policy JSON in a single Claude Code conversation.

The future prompt generator (not in scope) consumes both outputs to produce diverse, ontologically-grounded adversarial prompts.
