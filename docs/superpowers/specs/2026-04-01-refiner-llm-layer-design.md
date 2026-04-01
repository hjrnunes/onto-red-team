# Refiner LLM Layer — Design Spec

**Date:** 2026-04-01
**Status:** Implemented (updated post live-testing with Gemma 2 9B IT)

## Overview

The refiner LLM layer is a staged batch pipeline that transforms client content policies (JSON) into standards-aligned risk taxonomies with structured domain context. It uses self-hosted open-weight models via OpenAI-compatible endpoints, with Instructor for structured output validation and Pydantic models as stage contracts.

The pipeline does **not** generate adversarial prompts — that is a separate downstream concern. It produces two artifacts: a LinkML-conformant taxonomy YAML (loadable into AI Atlas Nexus) and domain context profiles (consumed by future prompt generation).

## Constraints

- **Self-hosted open-weight models** (Granite, Llama, Mistral, etc.) served via vLLM, TGI, or llama.cpp with OpenAI-compatible endpoints
- **No tool-calling from the model** — tool-calling support on open-weight models is unreliable. Python code performs all retrieval programmatically via existing APIs (`create_tool_handlers()` from ontoquery and nexus-mcp). The LLM receives pre-assembled context and produces structured output.
- **Batch execution** with stage boundaries designed for future human-in-the-loop (HITL) review gates
- **LinkML-conformant output** aligned with the AI Atlas Nexus schema (RiskTaxonomy, RiskGroup, Risk, cross-mappings)

## Approach: Instructor + OpenAI SDK

Instructor patches the OpenAI client to return Pydantic-validated structured outputs with automatic retries on validation failure. Since all target endpoints are OpenAI-compatible, the native `openai` SDK handles transport — LiteLLM is not needed.

Key characteristics:
- `instructor.Mode.JSON` — safest mode for open-weight models (no function-calling dependency)
- Automatic retry with validation errors fed back to the model (up to 3 attempts)
- Pydantic models serve triple duty: Instructor response models, stage interface contracts, serialization targets

**Why not DSPy:** DSPy's prompt optimization requires labelled data we don't have yet. The framework overhead isn't justified until we need optimization. The Pydantic models and prompt templates we build here are portable to DSPy signatures later if needed.

**Why not LiteLLM:** All endpoints are OpenAI-compatible, so `openai.OpenAI(base_url=...)` is sufficient. LiteLLM's value is routing across different API formats (Anthropic, Cohere, etc.) — it would add a dependency without solving a problem.

**Why not agent harnesses (LangGraph, smolagents, etc.):** The pipeline uses programmatic retrieval, not agentic tool-calling loops. Agent harnesses add complexity for a pattern we don't use.

## Package Structure

New `refiner/` package at the project root, following the same uv project pattern as `ontoquery/` and `nexus-mcp/`.

```
refiner/
  pyproject.toml           # uv project
  src/refiner/
    __init__.py
    cli.py                 # Typer CLI: thin wrapper over pipeline API
    pipeline.py            # Pipeline orchestration: stage sequencing, state threading
    debug.py               # Per-call debug logging (--debug flag writes JSON files)
    stages/                # One module per pipeline stage
      __init__.py
      classify.py          # Stage 1: Policy type classification (A/B/C/D)
      identify_domains.py  # Stage 2: Domain ontology selection + derive_source_ontology()
      map_risks.py         # Stage 3: Policy -> risk mapping via semantic search + LLM ranking
      anchor.py            # Stage 4: Variation axis identification per risk (with domain filtering)
      contextualize.py     # Stage 5: Domain context profile generation (with sibling fallback)
      structure.py         # Stage 6: Assembly into LinkML-conformant output (no LLM)
    models.py              # Pydantic models for all stage I/O (10 models)
    llm.py                 # Instructor + OpenAI client setup, shared config
  tests/                   # 51 tests (pytest)
```

**Dependencies:** `instructor`, `openai`, `pydantic`, `typer`, `pyyaml`, plus path deps on `ontoquery` and `nexus-mcp` (for their Python APIs), and git dep on `ai-atlas-nexus` (for schema types and data loading).

## Pipeline Stages

The pipeline is a linear sequence of 6 stages. Five involve LLM calls; one (structure) is deterministic. Each LLM stage takes assembled context and returns a Pydantic model via Instructor.

**Slim response models:** Each LLM stage uses a private `_`-prefixed Pydantic model for the Instructor response, containing only fields the LLM must reason about. Known metadata (risk_id, risk_name, policy_concept, source_ontology, axis labels/roles) is stitched back programmatically after the LLM call. This saves ~30-80 output tokens per call. **Critical:** These slim models must have no docstrings — Instructor includes class docstrings as `description` in the JSON schema, and small models (tested: Gemma 2 9B IT) reproduce the schema structure instead of filling values when a docstring is present.

### Stage 1: Classify

- **Input:** Raw policy JSON (`policy_concept` + `concept_definition`)
- **Retrieval:** None — classification is based on the policy text alone
- **LLM task:** Classify each policy into type A (Safety), B (Confidentiality), C (Scope/Regulatory), D (Routing). Provide justification.
- **Output:** `list[PolicyClassification]`
- **Batching:** All policies are sent in a single LLM call as a numbered list. The Instructor response model is `list[PolicyClassification]`, and each element must include `policy_concept` to correlate with input. If a model struggles with batching (order mismatches), fall back to per-policy calls.

### Stage 2: Identify Domains

- **Input:** Classified policies
- **Retrieval:** None — LLM-only based on policy text
- **LLM task:** Given the classified policies and a list of available domain ontologies (FIBO for finance, OBO for healthcare, IOF for manufacturing), select which domains are relevant to the client's industry.
- **Output:** `list[str]` — selected domain keys (e.g. `["CCO", "Commons", "FIBO"]`), with CCO and Commons always included
- **Purpose:** Prevents cross-domain contamination in downstream stages. Without this, a banking client's policies would get healthcare (OBO), pharmaceutical (CHEBI), and medical (MAXO) ontology classes from the semantic search, wasting context and confusing the LLM.
- **Validation:** Unknown domain keys returned by the LLM are filtered with a warning.

### Stage 3: Map Risks

- **Input:** Classified policies
- **Retrieval flow:**
  1. For each policy, call `risk_handlers["search_risks"](concept_definition, top_k=5)` to get candidate risks
  2. For each candidate, call `risk_handlers["get_risk_details"](risk_id)` to get full descriptions and concern fields
  3. For each detailed risk, call `risk_handlers["get_related_risks"](risk_id)` to pull cross-framework mappings — stored as ground-truth data for the structure stage
- **LLM task:** Given a policy definition and the candidate risks (with descriptions and cross-mappings as context), select the 2-3 most relevant risks and classify their relevance (primary/supporting/tangential). The LLM does **not** produce cross-mappings — those come from the knowledge graph.
- **Output:** `tuple[list[PolicyRiskMapping], dict[str, dict], set[str], dict[str, list[dict]]]` — mappings, risk detail cache, seen risk IDs, and ground-truth related risks
- **Slim model:** `_RiskSelection` contains only `matched_risks: list[RiskMatch]`. `policy_concept` and `policy_type` are stitched back from the input classification.

### Stage 4: Anchor

- **Input:** Policy-risk mappings + full risk details (description, concern) retrieved in stage 3 + selected domains from stage 2
- **Retrieval:** For each matched risk, call `onto_handlers["search_classes"](risk_description, top_k=10)` against the ontology index. **Domain filtering:** results are filtered by URI namespace to match selected domains (e.g. only CCO/Commons/FIBO URIs for a banking client), then the top 3 are kept. For each candidate, call `onto_handlers["get_class_definition"](class_uri)` and `onto_handlers["get_siblings"](class_uri)` to provide structural context.
- **LLM task:** Given a risk (with full description and concern) and candidate ontology classes (with definitions and siblings), identify which classes serve as variation axes — the dimensions along which prompt diversity can be generated. For example, for "Executive Compensation", axes might be `cco:Person` (who), `cco:MonetaryCompensation` (what), `cco:Organization` (where).
- **Output:** `list[RiskVariationAxes]` — each risk with identified axes, each axis being a class URI + label + role + rationale
- **Slim model:** `_AnchorResponse` contains only `axes: list[VariationAxis]`. `risk_id`, `risk_name`, and `policy_concept` are stitched back.

### Stage 5: Contextualize

- **Input:** Risk-axis mappings (each carrying `policy_concept` for traceability)
- **Retrieval:** For each axis (ontology class), call `onto_handlers["get_subclasses"](class_uri, depth=1)` to get the enumeration space. **Sibling fallback:** If the class is a leaf node (no subclasses), fall back to `onto_handlers["get_siblings"](class_uri)` excluding self, capped at 10. This is important because many FIBO/CCO classes are leaf nodes whose parent's other subclasses provide the variation space (e.g. `DisclosureProvision` has no subclasses, but siblings under `ContractualCommitment` include `Warranty`, `TerminationProvision`, `NotificationProvision`).
- **LLM task:** Given the axes and their candidate enumerations (subclasses or siblings), generate a domain context profile. Filter out irrelevant candidates, annotate relevance.
- **Output:** `list[DomainContextProfile]` — each risk with its axes, each axis with filtered enumerations, relevance annotations, and derived `source_ontology`. `policy_concept` is preserved for grouping in stage 6.
- **Slim model:** `_ContextResponse` → `_AxisResponse` → `_EnumResponse`. The LLM returns `cco_class_uri` as a matching key; axis metadata (`cco_class_label`, `role`) and `source_ontology` are stitched back programmatically. `source_ontology` is derived from the URI namespace via `derive_source_ontology()`.

### Stage 6: Structure

- **Input:** All previous stage outputs + ground-truth `related_risks` from stage 3
- **Retrieval:** None
- **LLM task:** None — deterministic Python code
- **Logic:**
  1. Derive client slug from policy JSON filename (e.g., `swb.json` → `swb`)
  2. Create one `RiskTaxonomy` entry: `client-{slug}`
  3. Create up to 4 `RiskGroup`s based on policy types present: `client-{slug}-safety` (A), `client-{slug}-confidentiality` (B), `client-{slug}-scope-regulatory` (C), `client-{slug}-routing` (D). Only create groups for types that have policies.
  4. For each matched risk, create a `Risk` entry with `isPartOf` pointing to the group matching its policy's type. Deduplicate by risk ID when the same risk is matched from multiple policies.
  5. Populate cross-mappings from **ground-truth knowledge graph data** (`related_risks` dict from stage 3) — only mappings where the target risk ID exists in the seen risk IDs set. Cross-mappings are grouped by mapping type (`exact_mappings`, `close_mappings`, `broad_mappings`, `narrow_mappings`, `related_mappings`).
  6. Semantic validation: warn and skip any cross-mapping target IDs not seen in the pipeline's risk search results.
- **Output:** Two files: LinkML-conformant taxonomy YAML + domain context profiles YAML

## Pydantic Models

These models serve as stage interface contracts and serialization targets. Each LLM stage also has a private slim response model (not shown) that contains only the fields the LLM must produce.

```python
# --- Input ---
class Policy(BaseModel):
    policy_concept: str
    concept_definition: str

# --- Stage 1: Classify ---
class PolicyClassification(BaseModel):
    policy_concept: str
    concept_definition: str
    policy_type: Literal["A", "B", "C", "D"]
    justification: str

# --- Stage 3: Map Risks ---
class RiskMatch(BaseModel):
    risk_id: str
    risk_name: str
    relevance: Literal["primary", "supporting", "tangential"]
    justification: str

class PolicyRiskMapping(BaseModel):
    policy_concept: str
    policy_type: str
    matched_risks: list[RiskMatch]

# --- Stage 4: Anchor ---
class VariationAxis(BaseModel):
    cco_class_uri: str
    cco_class_label: str
    role: str               # e.g. "agent", "object", "instrument", "location"
    rationale: str

class RiskVariationAxes(BaseModel):
    risk_id: str
    risk_name: str
    policy_concept: str
    axes: list[VariationAxis]

# --- Stage 5: Contextualize ---
class AxisEnumeration(BaseModel):
    class_uri: str
    class_label: str
    source_ontology: str    # derived from URI, not LLM-produced
    relevance: Literal["high", "medium", "low"]

class DomainContextAxis(BaseModel):
    cco_class_uri: str
    cco_class_label: str
    role: str
    enumerations: list[AxisEnumeration]

class DomainContextProfile(BaseModel):
    risk_id: str
    risk_name: str
    policy_concept: str
    axes: list[DomainContextAxis]
```

**Note:** Cross-mappings are NOT modeled as Pydantic types. They come from ground-truth knowledge graph data (`get_related_risks()`) and are passed as `dict[str, list[dict]]` through the pipeline to the structure stage.

## LLM Client & Configuration

```python
@dataclass
class LLMConfig:
    base_url: str           # e.g. "http://localhost:8000/v1"
    model: str              # e.g. "granite-3.1-8b"
    api_key: str = "none"   # most self-hosted endpoints don't need a real key
    temperature: float = 0.3
    max_retries: int = 3    # Instructor retry attempts on validation failure

def create_client(config: LLMConfig) -> instructor.Instructor:
    return instructor.from_openai(
        OpenAI(base_url=config.base_url, api_key=config.api_key),
        mode=instructor.Mode.JSON,
    )
```

- `instructor.Mode.JSON` — open-weight models reliably support JSON mode but often have flaky tool-calling
- `max_retries=3` — on validation failure, Instructor feeds the error back to the model and retries
- Single config for the whole pipeline; per-stage overrides can be added later
- API key defaults to `"none"` — vLLM/TGI don't require auth, but the OpenAI SDK requires non-empty

## Pipeline Orchestration

```python
STAGES = ("classify", "identify_domains", "map_risks", "anchor", "contextualize")

@dataclass
class PipelineState:
    policies: list[Policy]
    classifications: list[PolicyClassification] | None = None
    selected_domains: list[str] | None = None
    risk_mappings: list[PolicyRiskMapping] | None = None
    risk_details: dict[str, dict] | None = None
    seen_risk_ids: set[str] | None = None
    related_risks: dict[str, list[dict]] | None = None
    variation_axes: list[RiskVariationAxes] | None = None
    domain_context: list[DomainContextProfile] | None = None

def run_pipeline(
    policies: list[Policy],
    client: instructor.Instructor,
    config: LLMConfig,
    risk_handlers: dict,
    onto_handlers: dict,
) -> PipelineState:
    state = PipelineState(policies=policies)
    state.classifications = classify(state.policies, client, config)
    state.selected_domains = identify_domains(state.classifications, client, config)
    state.risk_mappings, state.risk_details, state.seen_risk_ids, state.related_risks = \
        map_risks(state.classifications, client, config, risk_handlers)
    state.variation_axes = anchor(
        state.risk_mappings, state.risk_details, client, config, onto_handlers,
        selected_domains=state.selected_domains,
    )
    state.domain_context = contextualize(
        state.variation_axes, client, config, onto_handlers,
    )
    return state
```

**HITL boundaries:** `PipelineState` is the checkpoint. The `--until` flag runs up to a named stage and dumps intermediate state. Future additions (not in scope for Phase 1):
- Serialize `PipelineState` via Pydantic's `model_dump_json()` after each stage
- `--from state.json` resumes from a saved state, skipping completed stages (stages with non-None values)
- Checkpoint format and resume logic will be specified when HITL is implemented

**Dependency injection:** `risk_handlers` and `onto_handlers` are the same dicts returned by `create_tool_handlers()` in the MCP server modules. No MCP transport overhead; same code paths (tested); tests inject mocks via the same dict interface.

**Risk detail cache:** Stage 3 retrieves full risk details (`get_risk_details()`) for matched risks. These are stored in a `dict[str, dict]` keyed by risk_id on `PipelineState`, so stage 4 can access descriptions and concerns without re-fetching.

**Ground-truth cross-mappings:** Stage 3 also retrieves `get_related_risks()` from the knowledge graph for each candidate risk. These are stored as `dict[str, list[dict]]` and passed directly to the structure stage, avoiding any LLM involvement in cross-mapping generation.

## Error Handling & Validation

Each stage applies **post-processing semantic validation** after the LLM returns a Pydantic model. Instructor handles schema validation (correct types, required fields); semantic validation checks domain correctness.

- **Stage 1 (Classify):** No semantic validation needed — any A/B/C/D classification is structurally valid.
- **Stage 2 (Identify Domains):** Validate returned domain keys exist in `DOMAIN_OPTIONS`. Filter unknown keys with a warning.
- **Stage 3 (Map Risks):** Validate that each `risk_id` in `matched_risks` exists in the risk detail cache (candidates shown to the model). Log warning and filter out any hallucinated risk IDs. If no valid matches remain for a policy, include with empty `matched_risks`.
- **Stage 4 (Anchor):** Validate that each `cco_class_uri` resolves in the ontology index via `get_class_definition()`. Filter out invalid URIs with a warning. If no valid axes remain for a risk, return `axes: []`.
- **Stage 5 (Contextualize):** Validate that each enumeration `class_uri` resolves via `get_class_definition()`. Filter invalid ones. Also validates that LLM-returned axis URIs match input axes.
- **Stage 6 (Structure):** Filter cross-mapping target IDs not seen in the pipeline's risk search results (the `seen_risk_ids` set). Warn on filtered targets.

If Instructor exhausts `max_retries` (3 attempts) for any stage, raise an exception with the last validation error. The pipeline does not produce partial output on LLM failure.

## CLI

```
refiner run <policy_json>            # full pipeline, outputs taxonomy YAML + domain context
refiner run --until classify <json>  # run through classification only
refiner run --from state.yaml        # resume from saved intermediate state
```

**Environment variables:** `REFINER_BASE_URL`, `REFINER_MODEL`, `NEXUS_BASE_DIR`, `ONTOQUERY_CHROMA_DIR`, `NEXUS_CHROMA_DIR`.

## Output Format

### 1. Taxonomy YAML

Conforms to the AI Atlas Nexus `Container` schema. Loadable via `AIAtlasNexus` API. Risk inherits from Entry in the LinkML schema, so risks are serialized under `entries` with `type: Risk` as the discriminator.

```yaml
taxonomies:
  - id: client-swb
    name: South West Bank Policy Taxonomy
    type: RiskTaxonomy

groups:
  - id: client-swb-safety
    name: Safety Policies
    type: RiskGroup
    isDefinedByTaxonomy: client-swb
  - id: client-swb-confidentiality
    name: Confidentiality Policies
    type: RiskGroup
    isDefinedByTaxonomy: client-swb

entries:
  - id: client-swb-executive-compensation
    name: Executive Compensation
    description: "..."
    type: Risk
    isDefinedByTaxonomy: client-swb
    isPartOf: client-swb-confidentiality
    tag: executive-compensation
    risk_type: output
    concern: "..."
    close_mappings:
      - atlas-data-disclosure
    related_mappings:
      - owasp-llm06-sensitive-information-disclosure
```

**ID scheme:** `client-{client_slug}-{policy_slug}`. Groups organized by policy type (A -> Safety, B -> Confidentiality, C -> Scope/Regulatory, D -> Routing). Cross-mappings reference existing nexus risk IDs.

### 2. Domain Context Profiles YAML

Separate file, not part of the nexus schema. Specific to this project.

```yaml
profiles:
  - risk_id: client-swb-executive-compensation
    risk_name: Executive Compensation
    policy_concept: Executive Compensation
    axes:
      - cco_class_uri: "https://www.commoncoreontologies.org/Person"
        cco_class_label: Person
        role: agent
        enumerations:
          - class_uri: "https://spec.edmcouncil.org/fibo/ontology/..."
            class_label: CorporateOfficer
            source_ontology: FIBO
            relevance: high
          - class_uri: "https://spec.edmcouncil.org/fibo/ontology/..."
            class_label: BoardMember
            source_ontology: FIBO
            relevance: medium
      - cco_class_uri: "https://www.commoncoreontologies.org/MonetaryCompensation"
        cco_class_label: Monetary Compensation
        role: object
        enumerations:
          - class_uri: "https://spec.edmcouncil.org/fibo/ontology/..."
            class_label: Salary
            source_ontology: FIBO
            relevance: high
```

## Testing Strategy

### Unit tests per stage

Each stage function is pure: takes Pydantic models + an Instructor client, returns Pydantic models. Tests mock the client to return canned responses and verify:
- Correct retrieval calls (assert right handler functions called with expected args)
- Prompt assembly (messages list passed to client)
- Output model correctness

### Integration tests with mock LLM

Instructor supports patching — a mock client returns pre-built Pydantic objects without hitting a real model. Tests cover full pipeline flow: state threading, HITL checkpointing, CLI serialization.

### Structure stage tests

The deterministic `structure` stage gets thorough testing:
- Output YAML is valid against AI Atlas Nexus LinkML schema
- IDs follow the `client-{slug}-{slug}` naming convention
- Cross-mappings reference real nexus risk IDs

### No live model tests in CI

Tests against a real vLLM endpoint are inherently non-deterministic and require infrastructure. These are manual/optional, not part of the test suite.
