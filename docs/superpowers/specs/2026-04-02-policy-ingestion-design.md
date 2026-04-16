# Policy Document Ingestion — Design Spec

**Date:** 2026-04-02
**Status:** Draft

## Problem

The refiner pipeline requires policies as a flat JSON array of `{policy_concept, concept_definition}` objects. This means someone must manually read a policy document, identify the distinct policy concepts, and write definitions — a lossy, subjective process that discards valuable structure from the source document (boundary examples, acceptable uses, governance constraints, organizational context).

Real-world policy documents like the [RDaSH NHS AI Policy](../../../policy_examples/references/rdash-nhs-ai-policy.md) contain rich structure that would directly improve adversarial prompt generation if preserved.

## Solution

Add a `refiner ingest` command — a multi-pass LLM extraction stage that transforms policy documents (markdown/text) or existing flat JSON policy arrays into an enriched `PolicyProfile` format. This is the universal entry point for all policy inputs into the refiner pipeline.

The extraction schema is mapped to the [AIRO ontology](https://delaramglp.github.io/airo/) (AI Risk Ontology, ADAPT Centre), providing principled categories grounded in the EU AI Act and ISO 31000, with URI provenance for future interoperability with [GAF-Guard](https://github.com/IBM/risk-atlas-nexus-demos/tree/main/gaf-guard) and other AIRO-aligned tooling.

### Design decisions

1. **Standalone pre-pipeline command** — `refiner ingest` produces an inspectable, editable JSON file before `refiner run`. Follows the project's philosophy of explicit steps with reviewable intermediates.
2. **Multi-pass LLM extraction** — Three focused passes rather than single-shot. Consistent with the refiner's staged approach and validated by the nexus `identify_risks_from_usecases()` multi-method pattern.
3. **AIRO schema-mapped, not AIRO-dependent** — Pydantic models reference AIRO URIs as provenance but don't depend on the AIRO OWL file at runtime. No non-BFO ontology added to the graph.
4. **Universal entry point** — Both markdown documents and existing flat JSON arrays go through `ingest`. The passes adapt to input format.
5. **Markdown/plain text only** — Format conversion (PDF, HTML) is orthogonal and can be added later.
6. **CoT example bank** — Ship worked extraction examples (inspired by the nexus `risk_generation_cot.json` pattern) to guide small models.
7. **Prompt enrichment downstream** — Boundary examples are fed into `emit.py` generation prompts as direct context. No structural changes to the emit pipeline or sdg_hub flow.

## Enriched Policy Schema

### `PolicyProfile` (document-level)

| Field | Type | AIRO Class | URI | Description |
|---|---|---|---|---|
| `airo_version` | `str` | — | — | AIRO version used for schema mapping (currently `"0.2"`) |
| `organization` | `str` | AIDeployer | `airo:AIDeployer` | Who operates the AI system |
| `domain` | `str` | Domain | `airo:Domain` | Industry/sector (e.g., "healthcare", "financial services") |
| `purpose` | `list[str]` | Purpose | `airo:Purpose` | What the AI is used for |
| `ai_systems` | `list[str]` | AISystem | `airo:AISystem` | Specific tools in scope |
| `ai_users` | `list[str]` | AIUser | `airo:AIUser` | Who uses the system |
| `ai_subjects` | `list[str]` | AISubject | `airo:AISubject` | Who is affected |
| `governing_regulations` | `list[str]` | Regulation | `airo:Regulation` | Regulatory references |
| `named_entities` | `list[NamedEntity]` | — | — | Governance roles, org-specific names |
| `policies` | `list[Policy]` | — | — | Extracted/enriched policy concepts |

All fields except `airo_version` and `policies` default to empty (empty string or empty list) to handle cases where inference fails or information is not present in the source. A warning is logged when key fields (`organization`, `domain`) come back empty.

### `NamedEntity`

| Field | Type | Description |
|---|---|---|
| `name` | `str` | Entity name (e.g., "Caldicott Guardian") |
| `role` | `str` | Entity role/description |

### `Policy` (per-policy, extended)

Existing fields unchanged. New fields are optional with empty defaults.

**Safety note:** `Policy` is never used as an Instructor `response_model` — it is only a data carrier. The LLM stages use private `_Slim*` models. Extending `Policy` with optional fields does not affect LLM JSON schemas.

| Field | Type | AIRO Class | New? | Description |
|---|---|---|---|---|
| `policy_concept` | `str` | — | no | Short name for the policy concept |
| `concept_definition` | `str` | — | no | Rich definition of the policy boundary |
| `boundary_examples` | `list[BoundaryExample]` | — | yes | Prohibited/acceptable pairs |
| `acceptable_uses` | `list[str]` | Purpose (scoped) | yes | What IS allowed near this boundary |
| `risk_controls` | `list[str]` | RiskControl | yes | Safeguards (DPIA, consent, training) |
| `human_involvement` | `str \| None` | HumanInvolvement | yes | Accountability constraint |

### `BoundaryExample`

| Field | Type | Description |
|---|---|---|
| `prohibited` | `str` | What is NOT allowed |
| `acceptable` | `str` | What IS allowed (the near-boundary counterpart) |

### Example output

```json
{
  "airo_version": "0.2",
  "organization": "Rotherham Doncaster and South Humber NHS Foundation Trust",
  "domain": "healthcare",
  "purpose": ["clinical administration", "document drafting", "information summarisation", "research"],
  "ai_systems": ["Microsoft 365 Copilot", "ChatGPT", "publicly available AI"],
  "ai_users": ["staff", "volunteers", "students", "temporary workers", "contractors"],
  "ai_subjects": ["patients"],
  "governing_regulations": ["GMC Framework", "Health Research Authority", "GDPR"],
  "named_entities": [
    {"name": "Caldicott Guardian", "role": "Patient information processing oversight"},
    {"name": "Clinical Safety Officer", "role": "Clinical IT system safety assessment"}
  ],
  "policies": [
    {
      "policy_concept": "Clinical Decision-Making",
      "concept_definition": "AI systems must not be used for making clinical decisions, determining diagnoses or treatment plans, creating individualised care plans for named patients, or generating clinical entries directly into patient records. Clinicians remain personally accountable for all decisions regarding patient care.",
      "boundary_examples": [
        {
          "prohibited": "Using Copilot chat to create a care plan for John Smith",
          "acceptable": "Using Copilot chat to summarise NICE guidelines on diabetes management"
        }
      ],
      "acceptable_uses": [
        "Exploring general health concepts (not patient-specific)",
        "Summarising clinical guidelines"
      ],
      "risk_controls": ["Clinical validation required before use", "Final responsibility rests with clinician"],
      "human_involvement": "Clinicians remain personally accountable for all decisions regarding patient care"
    },
    {
      "policy_concept": "Protected Health Information",
      "concept_definition": "No person-identifiable data may be input to public AI tools. No business-sensitive or confidential data processing. Combined details of a local area, a rare disease and a very young age may enable a patient to be identified — careful anonymisation assessment required.",
      "boundary_examples": [],
      "acceptable_uses": [
        "Administrative and business support via M365 Copilot",
        "Non-clinical document drafting"
      ],
      "risk_controls": ["DPIA required before implementation", "Legal basis must be established", "Explicit patient consent"],
      "human_involvement": "Data Protection Officer oversight for compliance"
    }
  ]
}
```

## Multi-Pass Extraction

Three LLM passes, each focused on a different AIRO dimension. Each pass uses slim response models (private `_`-prefixed, no docstrings), Instructor structured output, and supports `--debug` logging.

The passes adapt to input format:

| Pass | Markdown/text input | JSON array input |
|---|---|---|
| **1: Context** | Extract from document text | Infer from policy definitions collectively |
| **2: Policy concepts** | Full extraction from document | No-op — concepts already provided |
| **3: Boundary enrichment** | Extract from document + concepts | Generate from concept definitions |

### Pass 1: AI Use Context

**AIRO dimensions:** `Domain`, `Purpose`, `AISystem`, `AIDeployer`, `AIUser`, `AISubject`, `Regulation`

- **Input:** Full document text (markdown) or all concept definitions concatenated (JSON)
- **Output:** `PolicyProfileContext` — all `PolicyProfile` fields except `policies`
- **LLM task:** Extract organizational context. For markdown, this is mostly explicit in the document. For JSON, the LLM infers from policy content (e.g., "South West Bank" → organization, "financial services" → domain).
- **CoT:** 1-2 examples showing document excerpts → extracted context.
- **Weak inference handling:** When input is a flat JSON with generic policies (e.g., `generic.json` — no domain terminology), the LLM may return empty or vague results. Fields default to empty. CLI overrides `--domain` and `--organization` allow the user to supplement LLM inference when the source material lacks explicit context.

### Pass 2: Policy Concept Distillation

**AIRO dimensions:** `RiskConcept`, `RiskSource`, `Consequence`

- **Input:** Full document text + Pass 1 context
- **Output:** `list[Policy]` with `policy_concept` and `concept_definition` only
- **LLM task:** "Given this policy document from a {domain} {organization}, identify the distinct policy concepts that define what the AI system must not do, or must handle carefully."
- **Skip condition:** When input is a JSON array, concepts are already provided. Pass 2 is a no-op — the existing `policy_concept` and `concept_definition` values are used as-is.
- **CoT:** 1-2 examples showing document text → extracted policy concepts.

### Pass 3: Boundary Enrichment

**AIRO dimensions:** `RiskControl`, `HumanInvolvement`

- **Input:** Full document text (or concept definitions for JSON) + Pass 1 context + Pass 2 concepts
- **Output:** Per-policy enrichments: `boundary_examples`, `acceptable_uses`, `risk_controls`, `human_involvement`
- **LLM task:** "For each policy concept, extract (or generate) boundary examples, acceptable uses, risk controls, and human involvement requirements."
- For markdown: extracts from the document and attributes to the correct concept.
- For JSON: generates boundary examples and acceptable uses from the concept definitions. The LLM infers what the acceptable counterpart would be for each prohibition.
- **CoT:** 1-2 examples showing policy concepts + source text → enrichments, including the prohibited/acceptable pair pattern.
- **Optional for JSON input:** A `--skip-enrichment` flag allows skipping Pass 3, producing a `PolicyProfile` with context metadata but no boundary enrichments. Useful when Pass 1 context (organization, domain) is the primary goal, or when model quality is insufficient for boundary generation.
- **Feasibility note:** Generating high-quality boundary examples is a creative, nuanced task. Small models (Gemma 2 9B) may produce low-quality pairs. The CoT examples are critical for guiding this pass. Empty `boundary_examples` lists are acceptable — downstream `emit.py` falls back gracefully.

### Pass ordering rationale

- Pass 1 → Pass 2: Domain context helps the LLM write better concept definitions.
- Pass 2 → Pass 3: The LLM needs to know the policy concepts before it can attribute boundary examples to them.

### Orchestration

```python
def ingest(
    document_text: str,
    input_format: Literal["markdown", "json_array"],
    client: instructor.Instructor,
    config: LLMConfig,
    skip_enrichment: bool = False,
    report: RunReport | None = None,
) -> PolicyProfile:
    context = extract_context(document_text, client, config, report=report)

    if input_format == "json_array":
        policies = parse_json_policies(document_text)
    else:
        policies = extract_policies(document_text, context, client, config, report=report)

    if not skip_enrichment:
        policies = enrich_policies(document_text, context, policies, client, config, report=report)

    return PolicyProfile(airo_version="0.2", **context.model_dump(), policies=policies)
```

### RunReport events

The ingest stage emits the following event types:

| Event type | Stage | Description |
|---|---|---|
| `input_format_detected` | ingest | `{"format": "markdown" \| "json_array"}` |
| `context_extracted` | Pass 1 | `{"organization": str, "domain": str, "fields_populated": int}` |
| `context_weak_inference` | Pass 1 | Logged when key fields (organization, domain) are empty after inference |
| `policies_extracted` | Pass 2 | `{"count": int}` or `{"skipped": true}` for JSON input |
| `enrichment_stats` | Pass 3 | `{"policies_enriched": int, "boundary_pairs_total": int, "policies_with_zero_pairs": int}` |
| `enrichment_skipped` | Pass 3 | Logged when `--skip-enrichment` is used |

### Document length

Real-world policy documents can exceed the context window of small models (Gemma 2 9B: 8K tokens). Each pass sends the full document text plus CoT examples plus system prompt. For long documents, the CLI warns if the estimated token count exceeds 6K (leaving headroom for response) and suggests splitting the document or using a larger-context model. No automatic truncation or chunking — the user decides how to handle it.

## CoT Example Bank

Following the nexus `risk_generation_cot.json` / `risk_questionnaire_cot.json` pattern: external JSON file with per-pass worked examples.

**File:** `refiner/src/refiner/templates/ingest_cot.json`

Loaded at runtime via `Path(__file__).parent / "templates" / "ingest_cot.json"`, matching the existing pattern used by `evaluation_report_template.html`.

```json
{
  "context_examples": [
    {
      "input_excerpt": "Rotherham Doncaster and South Humber NHS Foundation Trust (RDaSH). Applies to all staff, volunteers...",
      "extracted": {
        "organization": "RDaSH NHS Foundation Trust",
        "domain": "healthcare",
        "ai_users": ["staff", "volunteers", "contractors"],
        "ai_subjects": ["patients"]
      }
    }
  ],
  "policy_examples": [
    {
      "input_excerpt": "AI systems must NOT be used for: Making clinical decisions...",
      "extracted": [
        {
          "policy_concept": "Clinical Decision-Making",
          "concept_definition": "AI systems must not be used for making clinical decisions..."
        }
      ]
    }
  ],
  "enrichment_examples": [
    {
      "policy_concept": "Clinical Decision-Making",
      "input_excerpt": "Inappropriate: Using Copilot chat to create a care plan for John Smith. Appropriate: Using Copilot chat to summarise NICE guidelines...",
      "extracted": {
        "boundary_examples": [
          {
            "prohibited": "Using Copilot chat to create a care plan for John Smith",
            "acceptable": "Using Copilot chat to summarise NICE guidelines on diabetes management"
          }
        ],
        "acceptable_uses": ["Exploring general health concepts (not patient-specific)"],
        "risk_controls": ["Clinical validation required before use"],
        "human_involvement": "Clinicians remain personally accountable"
      }
    }
  ]
}
```

Prompt construction uses simple string templates (following the nexus `PromptBuilder` pattern) rather than inline f-strings. CoT examples are rendered into prompts as few-shot demonstrations.

## CLI Command

New Typer command: `refiner ingest`.

```bash
# From a policy document (markdown/text)
refiner ingest policy.md -o policies.json

# From existing flat JSON
refiner ingest swb.json -o swb-enriched.json

# With model config
refiner ingest policy.md -o policies.json \
  --base-url http://localhost:8080/v1 --model gemma-2-9b-it

# With debug logging
refiner ingest policy.md -o policies.json --debug /tmp/debug

# Skip boundary enrichment (Pass 3) — only extract context + concepts
refiner ingest swb.json -o swb-enriched.json --skip-enrichment

# Override domain/org when source lacks explicit context
refiner ingest generic.json -o generic-enriched.json \
  --domain "general" --organization "Generic Safety Policies"

# Run only through a specific pass
refiner ingest policy.md -o policies.json --until context
```

**Arguments & options:**

| Arg/Option | Type | Required | Default | Notes |
|---|---|---|---|---|
| `document` | Path | yes | — | Policy document (`.md`, `.txt`) or flat JSON (`.json`) |
| `--output`, `-o` | Path | no | `<stem>-enriched.json` | Output path for enriched PolicyProfile |
| `--base-url` | str | yes | `REFINER_BASE_URL` | LLM API endpoint |
| `--model` | str | yes | `REFINER_MODEL` | Model name |
| `--api-key` | str | no | `REFINER_API_KEY` / `"none"` | LLM API key |
| `--debug` | Path | no | — | Per-call debug log directory |
| `--skip-enrichment` | bool | no | `false` | Skip Pass 3 (boundary enrichment) |
| `--domain` | str | no | — | Override/supplement inferred domain |
| `--organization` | str | no | — | Override/supplement inferred organization |
| `--until` | str | no | — | Run up to a specific pass: `context`, `policies`, `enrichment` |

**Input format detection:** By file extension. `.json` → parse and check: if array, treat as flat JSON (`json_array`); if object with `policies` key, error with message "Already an enriched PolicyProfile — use `refiner run` directly." `.md` / `.txt` / other → treat as document text (`markdown`).

**No new dependencies.** Uses the same `LLMConfig`, `create_client`, Instructor, and `debug.configure` as existing commands.

## Downstream Pipeline Changes

### `refiner run` — accept enriched format

`cli.py` changes to load from the enriched `PolicyProfile` format. During a transition period, both formats are accepted:

```python
raw = json.loads(policy_json.read_text())
if isinstance(raw, list):
    # Legacy flat format — wrap in minimal PolicyProfile
    policies = [Policy(**p) for p in raw]
    doc_context = None
else:
    # Enriched PolicyProfile format
    doc = PolicyProfile(**raw)
    policies = doc.policies
    doc_context = doc
```

`PipelineState` gains an optional `doc_context: PolicyProfile | None` field, threaded through to stages that can exploit it.

### `emit.py` — format-aware policy loading and enriched prompts

**`load_policies()`** (line 127-129) currently expects a flat JSON array. Updated to handle both formats:

```python
def load_policies(path: Path) -> tuple[dict[str, Policy], PolicyProfile | None]:
    raw = json.loads(path.read_text())
    if isinstance(raw, list):
        policies = {p["policy_concept"]: Policy(**p) for p in raw}
        return policies, None
    else:
        doc = PolicyProfile(**raw)
        policies = {p.policy_concept: p for p in doc.policies}
        return policies, doc
```

Returns `Policy` objects (not just `concept_definition` strings) so downstream code can access `boundary_examples`, `acceptable_uses`, etc.

**`build_generation_prompt`** gains boundary context when available:

```
The organization's policy prohibits: {policy_concept} — "{concept_definition}"

Known boundary examples:
- PROHIBITED: {boundary.prohibited}
- ACCEPTABLE: {boundary.acceptable}

The system also permits: {acceptable_uses}

Organization: {doc_context.organization} ({doc_context.domain})
AI subjects: {doc_context.ai_subjects}

Generate a scenario that tests this boundary...
```

Pure prompt enrichment — no structural changes to the emit pipeline. The sdg_hub companion `flow.yaml` is unchanged. When boundary examples are empty (e.g., the source document didn't have them), the generation prompt falls back to the current format.

### `evaluate.py` — format-aware policy loading

**`run_evaluation()`** (line 326-327) loads policies the same way as `emit.py`. Updated with the same format detection logic. Evaluation metrics themselves are unchanged — they key on `policy_concept` strings. However, the enriched format enables a future metric: measuring how well generated adversarial prompts probe the documented boundaries (out of scope for initial implementation).

### `identify_domains` — domain hint

When `doc_context.domain` is present, use it as a strong hint for ontology selection. The document-level domain (explicitly stated in the source) is more reliable than LLM inference from policy text alone.

## File Structure

```
refiner/src/refiner/
  models.py                    # Add BoundaryExample, NamedEntity, PolicyProfile models
  stages/
    ingest.py                  # Three extraction passes + orchestration
  templates/
    ingest_cot.json            # Few-shot examples for each pass
  cli.py                       # Add ingest command, update run/emit/evaluate format detection
  emit.py                      # Update load_policies + build_generation_prompt
  evaluate.py                  # Update policy loading for enriched format
  pipeline.py                  # Add doc_context to PipelineState
```

## Workflow

```
                    markdown/text
                         |
                    +-----------+
  flat JSON -----→ |  ingest   | ←--- AIRO-mapped multi-pass extraction
                    +-----------+
                         |
                  enriched PolicyProfile JSON
                         |
                    (user review/edit)
                         |
                    +-----------+
                    |    run    | ←--- existing 6-stage pipeline
                    +-----------+
                         |
               taxonomy + domain context YAML
                         |
                    +-----------+
                    |   emit    | ←--- boundary-enriched generation prompts
                    +-----------+
                         |
                    dataset.jsonl
                         |
                    +-----------+
                    |  redteam  | ←--- sdg_hub adversarial generation
                    +-----------+
```

## Testing Strategy

- **Unit tests for each pass**: Mock Instructor responses, verify schema validation and post-processing.
- **CoT loading tests**: Verify `ingest_cot.json` loads via `Path(__file__).parent` and renders into prompts.
- **Format detection tests**: Flat JSON array, already-enriched JSON (should error), markdown, plain text.
- **Idempotency test**: Running `ingest` on an already-enriched `PolicyProfile` JSON errors with a clear message.
- **Round-trip test**: Ingest a flat JSON → verify output is valid `PolicyProfile` → feed to `refiner run` (mocked).
- **Backward compatibility test**: Existing `swb.json` through updated `refiner run` (flat array wrapping).
- **Emit enrichment test**: Verify `build_generation_prompt` includes boundary examples when present, falls back gracefully when absent.
- **Emit format test**: Verify `load_policies` handles both flat and enriched formats.
- **Evaluate format test**: Verify `run_evaluation` handles both flat and enriched policy formats.
- **Weak inference test**: Generic policies (no domain context) produce empty metadata fields with warnings.
- **CLI override test**: `--domain` and `--organization` override inferred values.
- **Skip enrichment test**: `--skip-enrichment` skips Pass 3, output has empty enrichment fields.
- **Until test**: `--until context` stops after Pass 1.
- **RunReport event tests**: Verify event types are emitted for each pass.

## AIRO Provenance

Each field in the extraction schema carries an implicit AIRO URI mapping (documented in this spec's schema tables). The output JSON includes `airo_version: "0.2"` for traceability. No runtime dependency on the AIRO OWL file.

Future integration: AIRO URIs enable interop with GAF-Guard and other AIRO-aligned tooling. A `PolicyProfile` could be transformed into AIRO RDF triples for exchange with governance systems, but this is out of scope for the initial implementation.

## References

- **AIRO ontology:** https://delaramglp.github.io/airo/ (v0.2, CC-BY-4.0)
- **GAF-Guard:** https://arxiv.org/html/2507.02986v2
- **Nexus use case lifting:** `ai-atlas-nexus/src/ai_atlas_nexus/library.py::identify_risks_from_usecases()`
- **Nexus CoT examples:** `ai-atlas-nexus/src/ai_atlas_nexus/data/templates/risk_generation_cot.json`
- **RDaSH NHS AI Policy:** `policy_examples/references/rdash-nhs-ai-policy.md`
- **AIRO assessment note:** Obsidian "AI Atlas Nexus - GAF-Guard and AIRO Assessment"
