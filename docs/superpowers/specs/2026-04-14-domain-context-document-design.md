# Domain Context Document — Canonical Envelope Design

**Date:** 2026-04-14  
**Status:** Draft  
**Approach:** B — Envelope + Restructured Profiles

## Motivation

The domain context output is currently a flat list of `DomainContextProfile` objects persisted as `{"profiles": [...]}` in YAML. Unlike `PolicyProfile`, it carries no metadata about how it was produced — no model, no selected domains, no ontology config, no policy source linkage. Risk metadata is denormalized into every profile, and `vocabulary_context` is an untyped dict.

This design introduces a `DomainContext` envelope that mirrors the `PolicyProfile` pattern: a single canonical artifact with typed provenance metadata, normalized risk data, and policy-grouped domain groundings.

## Model Hierarchy

### Envelope Metadata

```python
class PolicySourceRef(BaseModel):
    """Back-reference to the source policy document."""
    organization: str | None = None
    domain: str | None = None
    policy_count: int = 0

class PipelineConfig(BaseModel):
    """Snapshot of the config that produced this document."""
    weak_match_threshold: float = 0.4
    max_axes_per_risk: int = 3
    enumerations_per_axis: int = 8
```

### Typed Vocabulary Context

Replaces the raw `vocabulary_context: dict = {}` on `DomainContextAxis`.

```python
class VocabularyContext(BaseModel):
    stakeholders: list[dict] = []
    data_sensitivity: list[dict] = []
    rights: list[dict] = []
    justifications: list[dict] = []
    sector_purposes: list[dict] = []
    risk_concepts: list[dict] = []
    prohibited_practices: list[dict] = []
```

### Normalized Risk Registry

Risk metadata from the nexus, stored once per risk instead of duplicated per profile.

```python
class RiskSummary(BaseModel):
    risk_id: str
    risk_name: str
    risk_description: str | None = ""
    risk_concern: str | None = ""
    risk_framework: str | None = ""
    cross_mappings: list[dict] = []
```

### Per-Policy Grounding

```python
class RiskGrounding(BaseModel):
    """A risk's ontological grounding within a policy context."""
    risk_id: str                          # reference into risks list
    axes: list[DomainContextAxis]         # existing model, typed vocab_context

class PolicyDomainContext(BaseModel):
    """Domain context for a single policy."""
    policy_concept: str
    risk_groundings: list[RiskGrounding]
```

### The Envelope

```python
class DomainContext(BaseModel):
    version: str = "0.1"
    model: str = ""
    timestamp: str = ""
    run_slug: str = ""
    selected_domains: list[str] = []
    policy_source: PolicySourceRef | None = None
    config: PipelineConfig | None = None
    risks: list[RiskSummary] = []
    policy_contexts: list[PolicyDomainContext] = []
```

## YAML File Shape

Output file: `{client_slug}-domain-context.yaml`

```yaml
version: "0.1"
model: phi-4
timestamp: "2026-04-14T12:00:00"
run_slug: my-run
selected_domains: [CCO, Commons, FIBO, D3FEND, CSO, LKIF]
policy_source:
  organization: DHS
  domain: government
  policy_count: 12
config:
  weak_match_threshold: 0.4
  max_axes_per_risk: 3
  enumerations_per_axis: 8

risks:
  - risk_id: mit-ai-risk-subdomain-7.4
    risk_name: Lack of transparency
    risk_description: "..."
    risk_framework: MIT AI Risk Repository
    cross_mappings: [...]

policy_contexts:
  - policy_concept: Automated Enforcement & Benefit Denial
    risk_groundings:
      - risk_id: mit-ai-risk-subdomain-7.4
        axes:
          - cco_class_uri: https://...SoftwareAgent
            cco_class_label: software agent
            vocabulary_context:
              stakeholders: [...]
              data_sensitivity: [...]
            enumerations: [...]
  - policy_concept: Surveillance & Tracking
    risk_groundings:
      - risk_id: mit-ai-risk-subdomain-7.4
        axes: [...]
```

Risk metadata is written once. Multiple policies referencing the same risk share the `risk_id` without duplicating metadata.

## Pipeline Changes

### Production

The `contextualize` stage return type changes from `list[DomainContextProfile]` to `DomainContext`. It assembles the envelope from data already on `PipelineState`. The `run_slug` is not currently passed through the pipeline — it will need to be added to `PipelineState` or passed as a parameter to `contextualize`.

| Envelope field | Source |
|---|---|
| `model` | `RunReport.model` |
| `timestamp` | `RunReport.timestamp` |
| `run_slug` | CLI args (passed through pipeline) |
| `selected_domains` | `PipelineState.selected_domains` |
| `policy_source` | Derived from `PipelineState.doc_context` (`PolicyProfile`) |
| `config` | Snapshot from the config dict |
| `risks` | Extracted from `PipelineState.risk_details` |
| `policy_contexts` | Restructured from the current profile-building loop, grouped by `policy_concept` |

### Consumption

**`emit`**: `load_domain_context()` returns `DomainContext`. The emit loop changes from `for profile in profiles` to `for pc in doc.policy_contexts` → `for grounding in pc.risk_groundings` → `grounding.axes`. Risk metadata for prompt building comes from a lookup into `doc.risks` by `risk_id`.

**`evaluate`**: Works with raw dicts from YAML. Iteration changes from `for p in profiles` to `for pc in policy_contexts` → `for g in risk_groundings`, with a `risks` lookup dict built at the top. Same metrics, different traversal.

**`RunReport`**: Reads envelope metadata from the `DomainContext` instead of independently tracking model/domains/policy info.

**`provenance`**: Traverses the new structure — same data, different path.

**`structure`**: Receives `DomainContext` instead of `list[DomainContextProfile]`, reads `.policy_contexts` for taxonomy summaries.

No new pipeline stages. No new LLM calls.

### `PipelineState`

The `domain_context` field type changes from `list[DomainContextProfile] | None` to `DomainContext | None`.

## What Stays Unchanged

- **`DomainContextAxis`** — same fields, except `vocabulary_context` becomes `VocabularyContext` (typed model)
- **`AxisEnumeration`** / **`AxisDerivation`** — untouched
- **`SampledAxis`** — untouched
- **`ingest` stage** — produces `PolicyProfile`, unrelated
- **`identify_domains` / `map_risks` / `anchor` stages** — return types unchanged
- **`PolicyProfile`** and all its types — untouched
- **JSONL output format** from emit — rows keep the same shape

## What Gets Removed

- **`DomainContextProfile`** — replaced by `PolicyDomainContext` + `RiskGrounding` + `RiskSummary`
- The bare `{"profiles": [...]}` YAML wrapper in `cli.py`

## Relationship to RunReport

`DomainContext` is the canonical **artifact** — "what was produced and from what inputs" (declarative). `RunReport` remains the operational **log** — "what happened during production" (events, token counts, cache hits, timing). The report reads metadata from the document instead of tracking it independently, eliminating duplication. They are complementary, not overlapping.
