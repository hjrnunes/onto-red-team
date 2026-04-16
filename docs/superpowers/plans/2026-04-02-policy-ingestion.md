# Policy Document Ingestion Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `refiner ingest` command that transforms policy documents (markdown) or flat JSON policy arrays into an enriched `PolicyProfile` format using AIRO-mapped multi-pass LLM extraction.

**Architecture:** Three-pass LLM extraction (context → concepts → boundary enrichment) using Instructor structured output. Each pass uses slim `_`-prefixed Pydantic response models. Follows existing refiner stage patterns (mock_client fixtures, RunReport events, debug logging). The enriched output feeds into the existing `refiner run` pipeline.

**Tech Stack:** Python, Pydantic, Instructor, OpenAI SDK, Typer, pytest

**Spec:** `docs/superpowers/specs/2026-04-02-policy-ingestion-design.md`

---

## File Structure

```
refiner/src/refiner/
  models.py                     # MODIFY: Add BoundaryExample, NamedEntity, PolicyProfile, extend Policy
  stages/
    ingest.py                   # CREATE: Three extraction passes + orchestration
  templates/
    ingest_cot.json             # CREATE: Few-shot examples for each pass
  cli.py                        # MODIFY: Add ingest command, update run format detection
  emit.py                       # MODIFY: Update load_policies + build_prompt for enriched format
  evaluate.py                   # MODIFY: Update policy loading for enriched format
  pipeline.py                   # MODIFY: Add doc_context to PipelineState

refiner/tests/
  test_models_ingest.py         # CREATE: Schema validation tests for new models
  test_ingest.py                # CREATE: Per-pass unit tests + orchestration tests
  test_emit.py                  # MODIFY: Add enriched format tests
  test_cli.py                   # MODIFY: Add ingest CLI tests, update run tests
  test_evaluate.py              # MODIFY: Add enriched format loading test
```

---

### Task 1: Add enriched policy models to `models.py`

**Files:**
- Modify: `refiner/src/refiner/models.py`
- Create: `refiner/tests/test_models_ingest.py`

- [ ] **Step 1: Write failing tests for new models**

Create `refiner/tests/test_models_ingest.py`:

```python
from refiner.models import BoundaryExample, NamedEntity, PolicyProfile, Policy


def test_boundary_example():
    be = BoundaryExample(
        prohibited="Using AI to create care plan for John Smith",
        acceptable="Using AI to summarise NICE guidelines",
    )
    assert be.prohibited == "Using AI to create care plan for John Smith"
    assert be.acceptable == "Using AI to summarise NICE guidelines"


def test_named_entity():
    ne = NamedEntity(name="Caldicott Guardian", role="Patient info oversight")
    assert ne.name == "Caldicott Guardian"


def test_policy_new_fields_optional():
    """Existing flat JSON should still deserialize — new fields default to empty."""
    p = Policy(policy_concept="Fraud", concept_definition="About fraud")
    assert p.boundary_examples == []
    assert p.acceptable_uses == []
    assert p.risk_controls == []
    assert p.human_involvement is None


def test_policy_with_enrichments():
    p = Policy(
        policy_concept="Clinical Decision-Making",
        concept_definition="No clinical decisions",
        boundary_examples=[
            BoundaryExample(prohibited="care plan for John", acceptable="summarise guidelines")
        ],
        acceptable_uses=["General health concepts"],
        risk_controls=["Clinical validation required"],
        human_involvement="Clinician accountable",
    )
    assert len(p.boundary_examples) == 1
    assert p.human_involvement == "Clinician accountable"


def test_policy_document():
    doc = PolicyProfile(
        airo_version="0.2",
        organization="Test Org",
        domain="healthcare",
        policies=[
            Policy(policy_concept="Test", concept_definition="Test def"),
        ],
    )
    assert doc.organization == "Test Org"
    assert len(doc.policies) == 1
    assert doc.purpose == []
    assert doc.ai_systems == []
    assert doc.ai_users == []
    assert doc.ai_subjects == []
    assert doc.governing_regulations == []
    assert doc.named_entities == []


def test_policy_document_from_dict():
    """Round-trip: dict → PolicyProfile → dict."""
    data = {
        "airo_version": "0.2",
        "organization": "RDaSH",
        "domain": "healthcare",
        "purpose": ["admin"],
        "ai_systems": ["Copilot"],
        "ai_users": ["staff"],
        "ai_subjects": ["patients"],
        "governing_regulations": ["GMC"],
        "named_entities": [{"name": "DPO", "role": "compliance"}],
        "policies": [
            {
                "policy_concept": "PHI",
                "concept_definition": "No PII in AI",
                "boundary_examples": [
                    {"prohibited": "enter patient data", "acceptable": "draft template"}
                ],
                "acceptable_uses": ["non-clinical drafting"],
                "risk_controls": ["DPIA required"],
                "human_involvement": "DPO oversight",
            }
        ],
    }
    doc = PolicyProfile(**data)
    assert doc.organization == "RDaSH"
    assert doc.policies[0].boundary_examples[0].prohibited == "enter patient data"
    roundtrip = doc.model_dump()
    assert roundtrip["organization"] == "RDaSH"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd refiner && uv run pytest tests/test_models_ingest.py -v`
Expected: FAIL — `BoundaryExample`, `NamedEntity`, `PolicyProfile` not importable.

- [ ] **Step 3: Add new models to `models.py`**

Add after the `Policy` class (line 8) in `refiner/src/refiner/models.py`:

```python
class BoundaryExample(BaseModel):
    prohibited: str
    acceptable: str


class NamedEntity(BaseModel):
    name: str
    role: str
```

Extend `Policy` (line 6-8) with optional fields:

```python
class Policy(BaseModel):
    policy_concept: str
    concept_definition: str
    boundary_examples: list[BoundaryExample] = []
    acceptable_uses: list[str] = []
    risk_controls: list[str] = []
    human_involvement: str | None = None
```

Add `PolicyProfile` after `Policy`:

```python
class PolicyProfile(BaseModel):
    airo_version: str = "0.2"
    organization: str = ""
    domain: str = ""
    purpose: list[str] = []
    ai_systems: list[str] = []
    ai_users: list[str] = []
    ai_subjects: list[str] = []
    governing_regulations: list[str] = []
    named_entities: list[NamedEntity] = []
    policies: list[Policy] = []
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd refiner && uv run pytest tests/test_models_ingest.py -v`
Expected: All 6 tests PASS.

- [ ] **Step 5: Run full test suite to verify no regressions**

Run: `cd refiner && uv run pytest -v`
Expected: All existing tests still pass. The new optional fields on `Policy` don't break any code — `Policy` is never used as an Instructor response model.

- [ ] **Step 6: Commit**

```bash
git add refiner/src/refiner/models.py refiner/tests/test_models_ingest.py
git commit -m "feat(refiner): add BoundaryExample, NamedEntity, PolicyProfile models

Extend Policy with optional enrichment fields (boundary_examples,
acceptable_uses, risk_controls, human_involvement). Add PolicyProfile
wrapper for AIRO-mapped extraction output."
```

---

### Task 2: Create CoT example bank

**Files:**
- Create: `refiner/src/refiner/templates/ingest_cot.json`

- [ ] **Step 1: Create templates directory and CoT file**

Create `refiner/src/refiner/templates/ingest_cot.json` with worked examples for each pass. Based on the RDaSH NHS AI Policy reference document:

```json
{
  "context_examples": [
    {
      "input_excerpt": "Rotherham Doncaster and South Humber NHS Foundation Trust (RDaSH). Applies to all staff, volunteers, students, temporary workers, contractors, suppliers, and third parties.\n\nAI systems must NOT be used for: Making clinical decisions or determining diagnoses/treatment. Processing identifiable patient data.\n\nMicrosoft 365 Copilot can be used for administrative and business support. ChatGPT and publicly available AI tools may be used for document drafting and idea generation.\n\nGMC Framework: Clinicians remain personally accountable. Health Research Authority approval required for research applications.",
      "extracted": {
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
        ]
      }
    }
  ],
  "policy_examples": [
    {
      "input_excerpt": "AI systems must NOT be used for: Making clinical decisions or determining diagnoses/treatment. Processing identifiable patient data. Replacing professional judgment. Generating clinical entries directly into patient records. Creating individualised care plans for named patients.\n\nNo person-identifiable data input to public AI tools. No business-sensitive information sharing. Combined details of a local area, a rare disease and a very young age may enable a patient to be identified.",
      "extracted": [
        {
          "policy_concept": "Clinical Decision-Making",
          "concept_definition": "AI systems must not be used for making clinical decisions, determining diagnoses or treatment plans, creating individualised care plans for named patients, or generating clinical entries directly into patient records. Clinicians remain personally accountable for all decisions regarding patient care."
        },
        {
          "policy_concept": "Protected Health Information",
          "concept_definition": "No person-identifiable data may be input to public AI tools. No business-sensitive or confidential data processing. Combined details of a local area, a rare disease and a very young age may enable a patient to be identified — careful anonymisation assessment required."
        }
      ]
    }
  ],
  "enrichment_examples": [
    {
      "policy_concept": "Clinical Decision-Making",
      "input_excerpt": "AI systems must NOT be used for: Making clinical decisions or determining diagnoses/treatment. Creating individualised care plans for named patients.\n\nInappropriate: Using Copilot chat to create a care plan for John Smith.\nAppropriate: Using Copilot chat to summarise NICE guidelines on diabetes management.\n\nAcceptable uses: Exploring general health concepts (not patient-specific). Document drafting for non-clinical purposes.\n\nClinicians remain personally accountable for all decisions regarding patient care. AI outputs require validation before use.",
      "extracted": {
        "boundary_examples": [
          {
            "prohibited": "Using Copilot chat to create a care plan for John Smith",
            "acceptable": "Using Copilot chat to summarise NICE guidelines on diabetes management"
          }
        ],
        "acceptable_uses": [
          "Exploring general health concepts (not patient-specific)",
          "Document drafting for non-clinical purposes"
        ],
        "risk_controls": [
          "Clinical validation required before use",
          "Final responsibility rests with clinician"
        ],
        "human_involvement": "Clinicians remain personally accountable for all decisions regarding patient care"
      }
    }
  ]
}
```

- [ ] **Step 2: Verify the file loads correctly**

Run: `cd refiner && python -c "import json; json.loads(open('src/refiner/templates/ingest_cot.json').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add refiner/src/refiner/templates/ingest_cot.json
git commit -m "feat(refiner): add CoT example bank for policy ingestion

Worked examples for each extraction pass based on RDaSH NHS AI Policy.
Loaded at runtime via Path(__file__).parent / templates/."
```

---

### Task 3: Implement extraction passes in `stages/ingest.py`

**Files:**
- Create: `refiner/src/refiner/stages/ingest.py`
- Create: `refiner/tests/test_ingest.py`

This is the largest task. Implement the three passes and the orchestration function.

- [ ] **Step 1: Write failing test for Pass 1 (context extraction)**

Create `refiner/tests/test_ingest.py`:

```python
import json
from unittest.mock import MagicMock, patch
from refiner.llm import LLMConfig
from refiner.models import RunReport


config = LLMConfig(base_url="http://localhost:8000/v1", model="test-model")


def _make_report():
    return RunReport(model="test", policy_set="test", timestamp="2026-01-01")


def test_extract_context_from_markdown(mock_client):
    from refiner.stages.ingest import extract_context, _SlimContext

    mock_client.chat.completions.create.return_value = _SlimContext(
        organization="Test Hospital",
        domain="healthcare",
        purpose=["clinical admin"],
        ai_systems=["Copilot"],
        ai_users=["staff"],
        ai_subjects=["patients"],
        governing_regulations=["GDPR"],
        named_entities=[{"name": "DPO", "role": "compliance"}],
    )

    result = extract_context("Some policy document text", mock_client, config)
    assert result.organization == "Test Hospital"
    assert result.domain == "healthcare"
    assert mock_client.chat.completions.create.called


def test_extract_context_emits_report_events(mock_client):
    from refiner.stages.ingest import extract_context, _SlimContext

    mock_client.chat.completions.create.return_value = _SlimContext(
        organization="Test Org",
        domain="finance",
        purpose=["trading"],
        ai_systems=[],
        ai_users=["traders"],
        ai_subjects=["customers"],
        governing_regulations=[],
        named_entities=[],
    )

    report = _make_report()
    extract_context("doc text", mock_client, config, report=report)
    events = [e for e in report.events if e["event"] == "context_extracted"]
    assert len(events) == 1
    assert events[0]["organization"] == "Test Org"


def test_extract_context_warns_on_empty_domain(mock_client):
    from refiner.stages.ingest import extract_context, _SlimContext

    mock_client.chat.completions.create.return_value = _SlimContext(
        organization="",
        domain="",
        purpose=[],
        ai_systems=[],
        ai_users=[],
        ai_subjects=[],
        governing_regulations=[],
        named_entities=[],
    )

    report = _make_report()
    extract_context("generic policies", mock_client, config, report=report)
    weak_events = [e for e in report.events if e["event"] == "context_weak_inference"]
    assert len(weak_events) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd refiner && uv run pytest tests/test_ingest.py::test_extract_context_from_markdown -v`
Expected: FAIL — `refiner.stages.ingest` does not exist.

- [ ] **Step 3: Create `stages/__init__.py` if needed and implement Pass 1**

Create `refiner/src/refiner/stages/ingest.py`:

```python
"""Policy document ingestion — AIRO-mapped multi-pass LLM extraction."""

import json
import logging
from pathlib import Path
from typing import Literal

import instructor

from refiner.llm import LLMConfig
from refiner.models import (
    BoundaryExample,
    NamedEntity,
    Policy,
    PolicyProfile,
    RunReport,
)

logger = logging.getLogger(__name__)

INGEST_PASSES = ("context", "policies", "enrichment")

_COT_PATH = Path(__file__).parent.parent / "templates" / "ingest_cot.json"


def _load_cot() -> dict:
    if _COT_PATH.exists():
        return json.loads(_COT_PATH.read_text())
    logger.warning("CoT file not found at %s — using zero-shot", _COT_PATH)
    return {}


# --- Slim response models (no docstrings — Instructor embeds them in schema) ---

from pydantic import BaseModel


class _SlimNamedEntity(BaseModel):
    name: str
    role: str


class _SlimContext(BaseModel):
    organization: str
    domain: str
    purpose: list[str]
    ai_systems: list[str]
    ai_users: list[str]
    ai_subjects: list[str]
    governing_regulations: list[str]
    named_entities: list[_SlimNamedEntity]


class _SlimPolicy(BaseModel):
    policy_concept: str
    concept_definition: str


class _SlimPolicyList(BaseModel):
    policies: list[_SlimPolicy]


class _SlimBoundaryExample(BaseModel):
    prohibited: str
    acceptable: str


class _SlimEnrichment(BaseModel):
    policy_concept: str
    boundary_examples: list[_SlimBoundaryExample]
    acceptable_uses: list[str]
    risk_controls: list[str]
    human_involvement: str


class _SlimEnrichmentList(BaseModel):
    enrichments: list[_SlimEnrichment]


# --- Pass 1: Context Extraction ---


def _build_context_prompt(document_text: str) -> str:
    cot = _load_cot()
    examples = cot.get("context_examples", [])

    parts = [
        "You are an AI governance analyst. Extract the organizational context "
        "from this policy document.\n\n"
        "Extract: organization name, industry domain, stated purposes for AI use, "
        "specific AI systems mentioned, who uses the AI (users), who is affected "
        "by the AI (subjects), governing regulations or standards, and named "
        "governance roles or entities.\n\n"
        "If information is not present in the document, return an empty string "
        "or empty list for that field. Do not fabricate information."
    ]

    for ex in examples:
        parts.append(
            f"\n\n--- Example ---\nDocument excerpt:\n{ex['input_excerpt']}\n\n"
            f"Extracted:\n{json.dumps(ex['extracted'], indent=2)}"
        )

    parts.append(f"\n\n--- Your task ---\nDocument:\n{document_text}")

    return "\n".join(parts)


def extract_context(
    document_text: str,
    client: instructor.Instructor,
    config: LLMConfig,
    report: RunReport | None = None,
) -> _SlimContext:
    prompt = _build_context_prompt(document_text)

    result = client.chat.completions.create(
        model=config.model,
        response_model=_SlimContext,
        messages=[{"role": "user", "content": prompt}],
        temperature=config.temperature,
        max_retries=config.max_retries,
        max_tokens=config.max_tokens,
    )

    populated = sum(1 for v in [
        result.organization, result.domain, result.purpose,
        result.ai_systems, result.ai_users, result.ai_subjects,
        result.governing_regulations, result.named_entities,
    ] if v)

    if report:
        report.events.append({
            "stage": "ingest", "event": "context_extracted",
            "organization": result.organization,
            "domain": result.domain,
            "fields_populated": populated,
        })
        if not result.organization or not result.domain:
            report.events.append({
                "stage": "ingest", "event": "context_weak_inference",
                "organization": result.organization,
                "domain": result.domain,
            })
            logger.warning(
                "Weak context inference — organization=%r, domain=%r",
                result.organization, result.domain,
            )

    return result


# --- Pass 2: Policy Concept Distillation ---


def _build_policies_prompt(document_text: str, context: _SlimContext) -> str:
    cot = _load_cot()
    examples = cot.get("policy_examples", [])

    org = context.organization or "the organization"
    domain = context.domain or "the given domain"

    parts = [
        f"You are an AI governance analyst reviewing a policy document from "
        f"{org} in the {domain} sector.\n\n"
        f"Identify the distinct policy concepts — each one defines something "
        f"the AI system must not do, or must handle carefully. For each concept, "
        f"write a short name (policy_concept) and a rich definition "
        f"(concept_definition) that captures the boundary being drawn.\n\n"
        f"Group related prohibitions under a single concept when they share "
        f"the same boundary. Do not fabricate concepts not present in the document."
    ]

    for ex in examples:
        parts.append(
            f"\n\n--- Example ---\nDocument excerpt:\n{ex['input_excerpt']}\n\n"
            f"Extracted:\n{json.dumps(ex['extracted'], indent=2)}"
        )

    parts.append(f"\n\n--- Your task ---\nDocument:\n{document_text}")

    return "\n".join(parts)


def extract_policies(
    document_text: str,
    context: _SlimContext,
    client: instructor.Instructor,
    config: LLMConfig,
    report: RunReport | None = None,
) -> list[Policy]:
    prompt = _build_policies_prompt(document_text, context)

    result = client.chat.completions.create(
        model=config.model,
        response_model=_SlimPolicyList,
        messages=[{"role": "user", "content": prompt}],
        temperature=config.temperature,
        max_retries=config.max_retries,
        max_tokens=config.max_tokens,
    )

    policies = [
        Policy(policy_concept=p.policy_concept, concept_definition=p.concept_definition)
        for p in result.policies
    ]

    if report:
        report.events.append({
            "stage": "ingest", "event": "policies_extracted",
            "count": len(policies),
        })

    logger.info("Extracted %d policy concepts", len(policies))
    return policies


def parse_json_policies(json_text: str) -> list[Policy]:
    raw = json.loads(json_text)
    return [Policy(**p) for p in raw]


# --- Pass 3: Boundary Enrichment ---


def _build_enrichment_prompt(
    document_text: str,
    context: _SlimContext,
    policies: list[Policy],
) -> str:
    cot = _load_cot()
    examples = cot.get("enrichment_examples", [])

    policy_list = "\n".join(
        f"- {p.policy_concept}: {p.concept_definition}" for p in policies
    )

    parts = [
        "You are an AI governance analyst. For each policy concept below, "
        "extract or generate:\n"
        "1. boundary_examples: pairs of (prohibited, acceptable) — showing what "
        "is NOT allowed and the closest thing that IS allowed.\n"
        "2. acceptable_uses: what IS explicitly permitted near this boundary.\n"
        "3. risk_controls: safeguards, validation requirements, or oversight.\n"
        "4. human_involvement: who remains accountable and how.\n\n"
        "If the document does not contain explicit examples for a concept, "
        "generate plausible boundary examples based on the concept definition. "
        "Return an entry for EVERY policy concept listed below.\n\n"
        f"Policy concepts:\n{policy_list}"
    ]

    for ex in examples:
        parts.append(
            f"\n\n--- Example ---\nPolicy concept: {ex['policy_concept']}\n"
            f"Document excerpt:\n{ex['input_excerpt']}\n\n"
            f"Extracted:\n{json.dumps(ex['extracted'], indent=2)}"
        )

    parts.append(f"\n\n--- Your task ---\nDocument:\n{document_text}")

    return "\n".join(parts)


def enrich_policies(
    document_text: str,
    context: _SlimContext,
    policies: list[Policy],
    client: instructor.Instructor,
    config: LLMConfig,
    report: RunReport | None = None,
) -> list[Policy]:
    prompt = _build_enrichment_prompt(document_text, context, policies)

    result = client.chat.completions.create(
        model=config.model,
        response_model=_SlimEnrichmentList,
        messages=[{"role": "user", "content": prompt}],
        temperature=config.temperature,
        max_retries=config.max_retries,
        max_tokens=config.max_tokens,
    )

    enrichment_by_concept = {e.policy_concept: e for e in result.enrichments}

    enriched = []
    pairs_total = 0
    zero_pairs = 0
    for policy in policies:
        e = enrichment_by_concept.get(policy.policy_concept)
        if e:
            policy.boundary_examples = [
                BoundaryExample(prohibited=b.prohibited, acceptable=b.acceptable)
                for b in e.boundary_examples
            ]
            policy.acceptable_uses = e.acceptable_uses
            policy.risk_controls = e.risk_controls
            policy.human_involvement = e.human_involvement or None
            pairs_total += len(e.boundary_examples)
        if not policy.boundary_examples:
            zero_pairs += 1
        enriched.append(policy)

    if report:
        report.events.append({
            "stage": "ingest", "event": "enrichment_stats",
            "policies_enriched": len(enriched),
            "boundary_pairs_total": pairs_total,
            "policies_with_zero_pairs": zero_pairs,
        })

    logger.info(
        "Enriched %d policies (%d boundary pairs, %d with zero pairs)",
        len(enriched), pairs_total, zero_pairs,
    )
    return enriched


# --- Orchestration ---


def ingest(
    document_text: str,
    input_format: Literal["markdown", "json_array"],
    client: instructor.Instructor,
    config: LLMConfig,
    skip_enrichment: bool = False,
    until: str | None = None,
    domain_override: str | None = None,
    organization_override: str | None = None,
    report: RunReport | None = None,
) -> PolicyProfile:
    if report:
        report.events.append({
            "stage": "ingest", "event": "input_format_detected",
            "format": input_format,
        })

    context = extract_context(document_text, client, config, report=report)

    if domain_override:
        context.domain = domain_override
    if organization_override:
        context.organization = organization_override

    if until == "context":
        return PolicyProfile(
            organization=context.organization,
            domain=context.domain,
            purpose=context.purpose,
            ai_systems=context.ai_systems,
            ai_users=context.ai_users,
            ai_subjects=context.ai_subjects,
            governing_regulations=context.governing_regulations,
            named_entities=[
                NamedEntity(name=ne.name, role=ne.role)
                for ne in context.named_entities
            ],
        )

    if input_format == "json_array":
        policies = parse_json_policies(document_text)
        if report:
            report.events.append({
                "stage": "ingest", "event": "policies_extracted",
                "count": len(policies), "skipped": True,
            })
    else:
        policies = extract_policies(document_text, context, client, config, report=report)

    if until == "policies":
        return PolicyProfile(
            organization=context.organization,
            domain=context.domain,
            purpose=context.purpose,
            ai_systems=context.ai_systems,
            ai_users=context.ai_users,
            ai_subjects=context.ai_subjects,
            governing_regulations=context.governing_regulations,
            named_entities=[
                NamedEntity(name=ne.name, role=ne.role)
                for ne in context.named_entities
            ],
            policies=policies,
        )

    if not skip_enrichment:
        policies = enrich_policies(document_text, context, policies, client, config, report=report)
    elif report:
        report.events.append({
            "stage": "ingest", "event": "enrichment_skipped",
        })

    return PolicyProfile(
        organization=context.organization,
        domain=context.domain,
        purpose=context.purpose,
        ai_systems=context.ai_systems,
        ai_users=context.ai_users,
        ai_subjects=context.ai_subjects,
        governing_regulations=context.governing_regulations,
        named_entities=[
            NamedEntity(name=ne.name, role=ne.role)
            for ne in context.named_entities
        ],
        policies=policies,
    )
```

- [ ] **Step 4: Run Pass 1 tests to verify they pass**

Run: `cd refiner && uv run pytest tests/test_ingest.py -k "extract_context" -v`
Expected: All 3 context extraction tests PASS.

- [ ] **Step 5: Write tests for Pass 2 (policy extraction)**

Add to `refiner/tests/test_ingest.py`:

```python
def test_extract_policies(mock_client):
    from refiner.stages.ingest import extract_policies, _SlimContext, _SlimPolicyList, _SlimPolicy

    context = _SlimContext(
        organization="Test Org", domain="healthcare",
        purpose=[], ai_systems=[], ai_users=[], ai_subjects=[],
        governing_regulations=[], named_entities=[],
    )
    mock_client.chat.completions.create.return_value = _SlimPolicyList(
        policies=[
            _SlimPolicy(policy_concept="PHI", concept_definition="No PII in AI"),
            _SlimPolicy(policy_concept="Clinical", concept_definition="No clinical decisions"),
        ]
    )

    result = extract_policies("doc text", context, mock_client, config)
    assert len(result) == 2
    assert result[0].policy_concept == "PHI"
    assert result[0].boundary_examples == []  # Not enriched yet


def test_parse_json_policies():
    from refiner.stages.ingest import parse_json_policies

    json_text = json.dumps([
        {"policy_concept": "Fraud", "concept_definition": "About fraud"},
        {"policy_concept": "Safety", "concept_definition": "About safety"},
    ])
    result = parse_json_policies(json_text)
    assert len(result) == 2
    assert result[0].policy_concept == "Fraud"


def test_extract_policies_emits_report(mock_client):
    from refiner.stages.ingest import extract_policies, _SlimContext, _SlimPolicyList, _SlimPolicy

    context = _SlimContext(
        organization="", domain="", purpose=[], ai_systems=[],
        ai_users=[], ai_subjects=[], governing_regulations=[], named_entities=[],
    )
    mock_client.chat.completions.create.return_value = _SlimPolicyList(
        policies=[_SlimPolicy(policy_concept="X", concept_definition="Y")]
    )

    report = _make_report()
    extract_policies("doc", context, mock_client, config, report=report)
    events = [e for e in report.events if e["event"] == "policies_extracted"]
    assert len(events) == 1
    assert events[0]["count"] == 1
```

- [ ] **Step 6: Run Pass 2 tests**

Run: `cd refiner && uv run pytest tests/test_ingest.py -k "policies" -v`
Expected: All PASS.

- [ ] **Step 7: Write tests for Pass 3 (enrichment)**

Add to `refiner/tests/test_ingest.py`:

```python
from refiner.models import Policy


def test_enrich_policies(mock_client):
    from refiner.stages.ingest import enrich_policies, _SlimContext, _SlimEnrichmentList, _SlimEnrichment, _SlimBoundaryExample

    context = _SlimContext(
        organization="Test", domain="healthcare",
        purpose=[], ai_systems=[], ai_users=[], ai_subjects=[],
        governing_regulations=[], named_entities=[],
    )
    policies = [
        Policy(policy_concept="Clinical", concept_definition="No clinical decisions"),
    ]

    mock_client.chat.completions.create.return_value = _SlimEnrichmentList(
        enrichments=[
            _SlimEnrichment(
                policy_concept="Clinical",
                boundary_examples=[
                    _SlimBoundaryExample(prohibited="care plan for John", acceptable="summarise guidelines")
                ],
                acceptable_uses=["General health concepts"],
                risk_controls=["Validation required"],
                human_involvement="Clinician accountable",
            )
        ]
    )

    result = enrich_policies("doc text", context, policies, mock_client, config)
    assert len(result) == 1
    assert len(result[0].boundary_examples) == 1
    assert result[0].boundary_examples[0].prohibited == "care plan for John"
    assert result[0].human_involvement == "Clinician accountable"


def test_enrich_policies_missing_concept(mock_client):
    """When LLM doesn't return enrichment for a concept, policy keeps empty defaults."""
    from refiner.stages.ingest import enrich_policies, _SlimContext, _SlimEnrichmentList

    context = _SlimContext(
        organization="", domain="", purpose=[], ai_systems=[],
        ai_users=[], ai_subjects=[], governing_regulations=[], named_entities=[],
    )
    policies = [
        Policy(policy_concept="Missing", concept_definition="Won't be enriched"),
    ]

    mock_client.chat.completions.create.return_value = _SlimEnrichmentList(enrichments=[])

    report = _make_report()
    result = enrich_policies("doc", context, policies, mock_client, config, report=report)
    assert len(result) == 1
    assert result[0].boundary_examples == []
    stats = [e for e in report.events if e["event"] == "enrichment_stats"]
    assert stats[0]["policies_with_zero_pairs"] == 1
```

- [ ] **Step 8: Run Pass 3 tests**

Run: `cd refiner && uv run pytest tests/test_ingest.py -k "enrich" -v`
Expected: All PASS.

- [ ] **Step 9: Write orchestration tests**

Add to `refiner/tests/test_ingest.py`:

```python
def test_ingest_markdown(mock_client):
    from refiner.stages.ingest import ingest, _SlimContext, _SlimPolicyList, _SlimPolicy, _SlimEnrichmentList, _SlimEnrichment, _SlimBoundaryExample

    # Mock responses for 3 passes
    mock_client.chat.completions.create.side_effect = [
        _SlimContext(
            organization="Test Org", domain="healthcare",
            purpose=["admin"], ai_systems=["Copilot"], ai_users=["staff"],
            ai_subjects=["patients"], governing_regulations=["GDPR"],
            named_entities=[],
        ),
        _SlimPolicyList(policies=[
            _SlimPolicy(policy_concept="PHI", concept_definition="No PII"),
        ]),
        _SlimEnrichmentList(enrichments=[
            _SlimEnrichment(
                policy_concept="PHI",
                boundary_examples=[
                    _SlimBoundaryExample(prohibited="enter patient data", acceptable="draft template")
                ],
                acceptable_uses=["non-clinical drafting"],
                risk_controls=["DPIA required"],
                human_involvement="DPO oversight",
            ),
        ]),
    ]

    result = ingest("# Policy doc\n...", "markdown", mock_client, config)
    assert result.organization == "Test Org"
    assert len(result.policies) == 1
    assert result.policies[0].boundary_examples[0].prohibited == "enter patient data"
    assert mock_client.chat.completions.create.call_count == 3


def test_ingest_json_array(mock_client):
    from refiner.stages.ingest import ingest, _SlimContext, _SlimEnrichmentList, _SlimEnrichment, _SlimBoundaryExample

    json_text = json.dumps([
        {"policy_concept": "Fraud", "concept_definition": "About fraud"},
    ])

    mock_client.chat.completions.create.side_effect = [
        _SlimContext(
            organization="South West Bank", domain="financial services",
            purpose=["customer service"], ai_systems=[], ai_users=["staff"],
            ai_subjects=["customers"], governing_regulations=[],
            named_entities=[],
        ),
        # Pass 2 skipped for json_array
        _SlimEnrichmentList(enrichments=[
            _SlimEnrichment(
                policy_concept="Fraud",
                boundary_examples=[
                    _SlimBoundaryExample(prohibited="commit fraud", acceptable="report suspicious activity")
                ],
                acceptable_uses=["fraud reporting"],
                risk_controls=[],
                human_involvement="",
            ),
        ]),
    ]

    result = ingest(json_text, "json_array", mock_client, config)
    assert result.organization == "South West Bank"
    assert len(result.policies) == 1
    assert result.policies[0].policy_concept == "Fraud"  # From original JSON
    assert mock_client.chat.completions.create.call_count == 2  # Pass 2 skipped


def test_ingest_skip_enrichment(mock_client):
    from refiner.stages.ingest import ingest, _SlimContext

    json_text = json.dumps([
        {"policy_concept": "Fraud", "concept_definition": "About fraud"},
    ])

    mock_client.chat.completions.create.return_value = _SlimContext(
        organization="Bank", domain="finance",
        purpose=[], ai_systems=[], ai_users=[], ai_subjects=[],
        governing_regulations=[], named_entities=[],
    )

    report = _make_report()
    result = ingest(json_text, "json_array", mock_client, config, skip_enrichment=True, report=report)
    assert result.organization == "Bank"
    assert result.policies[0].boundary_examples == []
    assert mock_client.chat.completions.create.call_count == 1  # Only Pass 1
    skip_events = [e for e in report.events if e["event"] == "enrichment_skipped"]
    assert len(skip_events) == 1


def test_ingest_until_context(mock_client):
    from refiner.stages.ingest import ingest, _SlimContext

    mock_client.chat.completions.create.return_value = _SlimContext(
        organization="Org", domain="healthcare",
        purpose=[], ai_systems=[], ai_users=[], ai_subjects=[],
        governing_regulations=[], named_entities=[],
    )

    result = ingest("doc text", "markdown", mock_client, config, until="context")
    assert result.organization == "Org"
    assert result.policies == []
    assert mock_client.chat.completions.create.call_count == 1


def test_ingest_domain_override(mock_client):
    from refiner.stages.ingest import ingest, _SlimContext, _SlimEnrichmentList

    json_text = json.dumps([
        {"policy_concept": "Safety", "concept_definition": "Generic safety"},
    ])

    mock_client.chat.completions.create.side_effect = [
        _SlimContext(
            organization="", domain="",
            purpose=[], ai_systems=[], ai_users=[], ai_subjects=[],
            governing_regulations=[], named_entities=[],
        ),
        _SlimEnrichmentList(enrichments=[]),
    ]

    result = ingest(
        json_text, "json_array", mock_client, config,
        domain_override="general", organization_override="Generic Policies",
    )
    assert result.domain == "general"
    assert result.organization == "Generic Policies"
```

- [ ] **Step 10: Run all ingest tests**

Run: `cd refiner && uv run pytest tests/test_ingest.py -v`
Expected: All tests PASS.

- [ ] **Step 11: Run full test suite**

Run: `cd refiner && uv run pytest -v`
Expected: All existing tests still pass.

- [ ] **Step 12: Commit**

```bash
git add refiner/src/refiner/stages/ingest.py refiner/tests/test_ingest.py
git commit -m "feat(refiner): implement AIRO-mapped policy ingestion passes

Three-pass extraction: context (Pass 1), policy concepts (Pass 2),
boundary enrichment (Pass 3). Adapts to input format — Pass 2 skipped
for JSON array input. CoT examples rendered into prompts. RunReport
events for each pass."
```

---

### Task 4: Add `refiner ingest` CLI command

**Files:**
- Modify: `refiner/src/refiner/cli.py`
- Modify: `refiner/tests/test_cli.py`

- [ ] **Step 1: Write failing test for ingest CLI command**

Add to `refiner/tests/test_cli.py`:

```python
@patch("refiner.cli.create_client")
def test_cli_ingest_markdown(mock_create_client, tmp_path, monkeypatch):
    from refiner.stages.ingest import _SlimContext, _SlimPolicyList, _SlimPolicy, _SlimEnrichmentList, _SlimEnrichment, _SlimBoundaryExample

    monkeypatch.setenv("REFINER_BASE_URL", "http://localhost:8000/v1")
    monkeypatch.setenv("REFINER_MODEL", "test-model")

    doc = tmp_path / "policy.md"
    doc.write_text("# Test Policy\nAI must not do bad things.")

    mock_client = MagicMock()
    mock_create_client.return_value = mock_client
    mock_client.chat.completions.create.side_effect = [
        _SlimContext(
            organization="Test", domain="general", purpose=[], ai_systems=[],
            ai_users=[], ai_subjects=[], governing_regulations=[], named_entities=[],
        ),
        _SlimPolicyList(policies=[
            _SlimPolicy(policy_concept="Safety", concept_definition="No harm"),
        ]),
        _SlimEnrichmentList(enrichments=[
            _SlimEnrichment(
                policy_concept="Safety",
                boundary_examples=[
                    _SlimBoundaryExample(prohibited="cause harm", acceptable="discuss safety")
                ],
                acceptable_uses=[], risk_controls=[], human_involvement="",
            ),
        ]),
    ]

    out = tmp_path / "output.json"
    result = runner.invoke(app, [
        "ingest", str(doc), "-o", str(out),
    ])
    assert result.exit_code == 0, result.output
    assert out.exists()

    import json as json_mod
    data = json_mod.loads(out.read_text())
    assert data["organization"] == "Test"
    assert len(data["policies"]) == 1


@patch("refiner.cli.create_client")
def test_cli_ingest_json(mock_create_client, tmp_path, monkeypatch):
    from refiner.stages.ingest import _SlimContext, _SlimEnrichmentList

    monkeypatch.setenv("REFINER_BASE_URL", "http://localhost:8000/v1")
    monkeypatch.setenv("REFINER_MODEL", "test-model")

    policy_file = tmp_path / "policies.json"
    policy_file.write_text(json.dumps([
        {"policy_concept": "Fraud", "concept_definition": "About fraud"},
    ]))

    mock_client = MagicMock()
    mock_create_client.return_value = mock_client
    mock_client.chat.completions.create.side_effect = [
        _SlimContext(
            organization="Bank", domain="finance", purpose=[], ai_systems=[],
            ai_users=[], ai_subjects=[], governing_regulations=[], named_entities=[],
        ),
        _SlimEnrichmentList(enrichments=[]),
    ]

    out = tmp_path / "enriched.json"
    result = runner.invoke(app, [
        "ingest", str(policy_file), "-o", str(out),
    ])
    assert result.exit_code == 0, result.output

    import json as json_mod
    data = json_mod.loads(out.read_text())
    assert data["domain"] == "finance"
    assert data["policies"][0]["policy_concept"] == "Fraud"


def test_cli_ingest_already_enriched(tmp_path, monkeypatch):
    """Ingesting an already-enriched PolicyProfile should error."""
    monkeypatch.setenv("REFINER_BASE_URL", "http://localhost:8000/v1")
    monkeypatch.setenv("REFINER_MODEL", "test-model")

    enriched = tmp_path / "enriched.json"
    enriched.write_text(json.dumps({
        "airo_version": "0.2",
        "organization": "Test",
        "domain": "general",
        "policies": [{"policy_concept": "X", "concept_definition": "Y"}],
    }))

    result = runner.invoke(app, ["ingest", str(enriched)])
    assert result.exit_code == 1
    assert "Already an enriched PolicyProfile" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd refiner && uv run pytest tests/test_cli.py -k "ingest" -v`
Expected: FAIL — no `ingest` command defined.

- [ ] **Step 3: Add ingest command to `cli.py`**

Add the ingest command to `refiner/src/refiner/cli.py`, after the existing imports and before the `run` command. Update the import at top:

```python
from refiner.models import Policy, PolicyProfile, RunReport
```

Add the command (before the `run` function):

```python
INGEST_PASSES = ("context", "policies", "enrichment")


@app.command()
def ingest(
    document: Path = typer.Argument(..., help="Policy document (.md/.txt) or flat JSON (.json)"),
    output: Path = typer.Option(None, "--output", "-o", help="Output path (default: <stem>-enriched.json)"),
    base_url: str = typer.Option(None, "--base-url", envvar="REFINER_BASE_URL", help="LLM API base URL"),
    model: str = typer.Option(None, "--model", envvar="REFINER_MODEL", help="LLM model name"),
    api_key: str = typer.Option("none", "--api-key", envvar="REFINER_API_KEY", help="LLM API key"),
    debug_dir: Path = typer.Option(None, "--debug", help="Directory for per-call debug logs"),
    skip_enrichment: bool = typer.Option(False, "--skip-enrichment", help="Skip boundary enrichment (Pass 3)"),
    domain: str = typer.Option(None, "--domain", help="Override inferred domain"),
    organization: str = typer.Option(None, "--organization", help="Override inferred organization"),
    until: str = typer.Option(None, "--until", help=f"Run up to this pass: {', '.join(INGEST_PASSES)}"),
):
    """Ingest a policy document or flat JSON into enriched PolicyProfile format."""
    if not document.exists():
        typer.echo(f"Error: {document} does not exist", err=True)
        raise typer.Exit(1)

    if until and until not in INGEST_PASSES:
        typer.echo(f"Error: --until must be one of: {', '.join(INGEST_PASSES)}", err=True)
        raise typer.Exit(1)

    if not base_url or not model:
        typer.echo("Error: --base-url and --model are required (or set REFINER_BASE_URL / REFINER_MODEL)", err=True)
        raise typer.Exit(1)

    # Detect input format
    document_text = document.read_text()
    if document.suffix == ".json":
        import json as json_mod
        raw = json_mod.loads(document_text)
        if isinstance(raw, dict) and "policies" in raw:
            typer.echo("Error: Already an enriched PolicyProfile — use 'refiner run' directly.", err=True)
            raise typer.Exit(1)
        input_format = "json_array"
    else:
        input_format = "markdown"

    config = LLMConfig(base_url=base_url, model=model, api_key=api_key)
    client = create_client(config)
    debug.configure(debug_dir)

    report = RunReport(
        model=config.model,
        policy_set=document.name,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    from refiner.stages.ingest import ingest as do_ingest
    result = do_ingest(
        document_text, input_format, client, config,
        skip_enrichment=skip_enrichment, until=until,
        domain_override=domain, organization_override=organization,
        report=report,
    )

    out_path = output or document.with_stem(f"{document.stem}-enriched").with_suffix(".json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result.model_dump(), indent=2))
    typer.echo(f"Enriched PolicyProfile written to {out_path}")
    typer.echo(f"  Organization: {result.organization}")
    typer.echo(f"  Domain: {result.domain}")
    typer.echo(f"  Policies: {len(result.policies)}")
```

- [ ] **Step 4: Run ingest CLI tests**

Run: `cd refiner && uv run pytest tests/test_cli.py -k "ingest" -v`
Expected: All 3 ingest CLI tests PASS.

- [ ] **Step 5: Run full test suite**

Run: `cd refiner && uv run pytest -v`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add refiner/src/refiner/cli.py refiner/tests/test_cli.py
git commit -m "feat(refiner): add 'refiner ingest' CLI command

Accepts markdown/text or flat JSON, detects format, runs AIRO-mapped
extraction passes, writes enriched PolicyProfile JSON. Supports
--skip-enrichment, --until, --domain, --organization overrides."
```

---

### Task 5: Update `refiner run` for enriched format

**Files:**
- Modify: `refiner/src/refiner/cli.py:67-70`
- Modify: `refiner/src/refiner/pipeline.py:23`
- Modify: `refiner/tests/test_cli.py`

- [ ] **Step 1: Write failing test for enriched format loading in `refiner run`**

Add to `refiner/tests/test_cli.py`:

```python
def _make_enriched_policy_file(tmp_path: Path) -> Path:
    doc = {
        "airo_version": "0.2",
        "organization": "Test Org",
        "domain": "healthcare",
        "purpose": [],
        "ai_systems": [],
        "ai_users": [],
        "ai_subjects": [],
        "governing_regulations": [],
        "named_entities": [],
        "policies": [
            {"policy_concept": "Fraud", "concept_definition": "About fraud"},
        ],
    }
    p = tmp_path / "enriched.json"
    p.write_text(json.dumps(doc))
    return p


@patch("refiner.cli.structure")
@patch("refiner.cli._create_risk_handlers")
@patch("refiner.cli._create_onto_handlers")
@patch("refiner.cli.create_client")
@patch("refiner.cli.run_pipeline")
def test_cli_run_enriched_format(mock_run, mock_create_client, mock_onto, mock_risk, mock_structure, tmp_path, monkeypatch):
    monkeypatch.setenv("REFINER_BASE_URL", "http://localhost:8000/v1")
    monkeypatch.setenv("REFINER_MODEL", "test-model")
    monkeypatch.setenv("NEXUS_BASE_DIR", "/tmp/nexus")

    policy_file = _make_enriched_policy_file(tmp_path)
    mock_run.return_value = _make_completed_state()
    mock_structure.return_value = ({"entries": []}, {"profiles": []})

    result = runner.invoke(app, [
        "run", str(policy_file), "-o", str(tmp_path),
    ])
    assert result.exit_code == 0, result.output
    # Verify pipeline was called with Policy objects
    call_args = mock_run.call_args
    policies = call_args[0][0]  # first positional arg
    assert len(policies) == 1
    assert policies[0].policy_concept == "Fraud"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd refiner && uv run pytest tests/test_cli.py::test_cli_run_enriched_format -v`
Expected: FAIL — current code tries `[Policy(**p) for p in raw]` on a dict.

- [ ] **Step 3: Update `cli.py` run command to detect format**

In `refiner/src/refiner/cli.py`, replace lines 67-70:

```python
    # Load policies
    raw = json.loads(policy_json.read_text())
    policies = [Policy(**p) for p in raw]
    typer.echo(f"Loaded {len(policies)} policies from {policy_json.name}")
```

With:

```python
    # Load policies — detect flat array vs enriched PolicyProfile
    raw = json.loads(policy_json.read_text())
    if isinstance(raw, list):
        policies = [Policy(**p) for p in raw]
        doc_context = None
    else:
        doc = PolicyProfile(**raw)
        policies = doc.policies
        doc_context = doc
    typer.echo(f"Loaded {len(policies)} policies from {policy_json.name}")
```

- [ ] **Step 4: Add `doc_context` to `PipelineState`**

In `refiner/src/refiner/pipeline.py`, add import and field:

```python
from refiner.models import PolicyProfile
```

Add to `PipelineState` class (after `report`):

```python
    doc_context: PolicyProfile | None = None
```

- [ ] **Step 5: Run test**

Run: `cd refiner && uv run pytest tests/test_cli.py::test_cli_run_enriched_format -v`
Expected: PASS.

- [ ] **Step 6: Run full test suite**

Run: `cd refiner && uv run pytest -v`
Expected: All tests pass (existing flat JSON tests still work via array detection).

- [ ] **Step 7: Commit**

```bash
git add refiner/src/refiner/cli.py refiner/src/refiner/pipeline.py refiner/tests/test_cli.py
git commit -m "feat(refiner): accept enriched PolicyProfile format in 'refiner run'

Format detection: JSON array → flat format, JSON object → enriched
PolicyProfile. Adds doc_context to PipelineState. Backward compatible."
```

---

### Task 6: Update `emit.py` for enriched format

**Files:**
- Modify: `refiner/src/refiner/emit.py:81-114,127-129,141-197`
- Modify: `refiner/tests/test_emit.py`

- [ ] **Step 1: Write failing test for enriched `load_policies`**

Add to `refiner/tests/test_emit.py`:

```python
def test_load_policies_enriched_format(tmp_path):
    from refiner.emit import load_policies
    from refiner.models import PolicyProfile

    doc = {
        "airo_version": "0.2",
        "organization": "Test Org",
        "domain": "healthcare",
        "policies": [
            {
                "policy_concept": "PHI",
                "concept_definition": "No PII",
                "boundary_examples": [
                    {"prohibited": "enter patient data", "acceptable": "draft template"}
                ],
                "acceptable_uses": ["non-clinical drafting"],
            },
        ],
    }
    p = tmp_path / "enriched.json"
    p.write_text(json.dumps(doc))

    policies, doc_context = load_policies(p)
    assert "PHI" in policies
    assert doc_context is not None
    assert doc_context.organization == "Test Org"
    assert len(policies["PHI"].boundary_examples) == 1


def test_load_policies_flat_format(tmp_path):
    from refiner.emit import load_policies

    flat = [{"policy_concept": "Fraud", "concept_definition": "About fraud"}]
    p = tmp_path / "flat.json"
    p.write_text(json.dumps(flat))

    policies, doc_context = load_policies(p)
    assert "Fraud" in policies
    assert doc_context is None
    assert policies["Fraud"].boundary_examples == []
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd refiner && uv run pytest tests/test_emit.py -k "load_policies" -v`
Expected: FAIL — `load_policies` returns `dict[str, str]` not `tuple`.

- [ ] **Step 3: Update `load_policies` in `emit.py`**

Replace `load_policies` (line 127-129) with:

```python
def load_policies(path: Path) -> tuple[dict[str, Policy], PolicyProfile | None]:
    raw = json.loads(path.read_text())
    if isinstance(raw, list):
        return {p["policy_concept"]: Policy(**p) for p in raw}, None
    doc = PolicyProfile(**raw)
    return {p.policy_concept: p for p in doc.policies}, doc
```

Add `PolicyProfile` to the import from `refiner.models` at the top.

- [ ] **Step 4: Update `build_prompt` to include boundary context**

Update `build_prompt` (line 81) to accept an optional `Policy` object and include boundary info:

```python
def build_prompt(
    policy_concept: str,
    concept_definition: str,
    risk_name: str,
    sampled_axes: list[SampledAxis],
    policy: Policy | None = None,
    doc_context: PolicyProfile | None = None,
) -> list[dict]:
```

Add boundary context to the user content, after the prohibition line and before "The request must NOT":

```python
    boundary_block = ""
    if policy and policy.boundary_examples:
        boundary_lines = "\n".join(
            f"- PROHIBITED: {be.prohibited}\n  ACCEPTABLE: {be.acceptable}"
            for be in policy.boundary_examples
        )
        boundary_block = f"\nKnown boundary examples:\n{boundary_lines}\n"

    acceptable_block = ""
    if policy and policy.acceptable_uses:
        acceptable_block = (
            "\nThe system also permits: "
            + "; ".join(policy.acceptable_uses) + "\n"
        )

    org_block = ""
    if doc_context and doc_context.organization:
        org_parts = [f"Organization: {doc_context.organization}"]
        if doc_context.domain:
            org_parts[0] += f" ({doc_context.domain})"
        if doc_context.ai_subjects:
            org_parts.append(f"AI subjects: {', '.join(doc_context.ai_subjects)}")
        org_block = "\n" + "\n".join(org_parts) + "\n"
```

Insert these blocks into the user_content string.

- [ ] **Step 5: Update `emit` function to use enriched `load_policies`**

Update the `emit` function (line 141-198) to work with the new return type. Change `policy_defs` to use `Policy` objects:

```python
    policy_map, doc_context = load_policies(policies_path)
```

And update the loop to pass `Policy` objects to `build_prompt`:

```python
        concept_def = policy_map.get(profile.policy_concept)
        if concept_def is None:
            ...
            continue
        ...
        for sampled in samples:
            prompt = build_prompt(
                profile.policy_concept,
                concept_def.concept_definition,
                profile.risk_name,
                sampled,
                policy=concept_def,
                doc_context=doc_context,
            )
            row = {
                ...
                "concept_definition": concept_def.concept_definition,
                ...
            }
```

- [ ] **Step 6: Update existing emit tests for new return type**

Find all existing tests that call `load_policies` or `build_prompt` and update them to handle the new signatures. Tests that mock `load_policies` need to return `(dict, None)` tuple.

- [ ] **Step 7: Write test for boundary-enriched prompt**

Add to `refiner/tests/test_emit.py`:

```python
def test_build_prompt_with_boundary_examples():
    from refiner.emit import build_prompt
    from refiner.models import Policy, BoundaryExample, PolicyProfile

    policy = Policy(
        policy_concept="Clinical",
        concept_definition="No clinical decisions",
        boundary_examples=[
            BoundaryExample(prohibited="care plan for John", acceptable="summarise guidelines")
        ],
        acceptable_uses=["General health concepts"],
    )
    doc_ctx = PolicyProfile(
        organization="NHS Trust",
        domain="healthcare",
        ai_subjects=["patients"],
    )

    messages = build_prompt("Clinical", "No clinical decisions", "Misdiagnosis", [], policy=policy, doc_context=doc_ctx)
    user_msg = messages[1]["content"]
    assert "PROHIBITED: care plan for John" in user_msg
    assert "ACCEPTABLE: summarise guidelines" in user_msg
    assert "General health concepts" in user_msg
    assert "NHS Trust" in user_msg
    assert "patients" in user_msg


def test_build_prompt_without_enrichments():
    """Backward compatible — no boundary info when policy has no enrichments."""
    from refiner.emit import build_prompt

    messages = build_prompt("Fraud", "About fraud", "Financial Fraud", [])
    user_msg = messages[1]["content"]
    assert "PROHIBITED:" not in user_msg
    assert "About fraud" in user_msg  # concept_definition still present
```

- [ ] **Step 8: Run all emit tests**

Run: `cd refiner && uv run pytest tests/test_emit.py -v`
Expected: All pass.

- [ ] **Step 9: Run full test suite**

Run: `cd refiner && uv run pytest -v`
Expected: All pass.

- [ ] **Step 10: Commit**

```bash
git add refiner/src/refiner/emit.py refiner/tests/test_emit.py
git commit -m "feat(refiner): boundary-enriched generation prompts in emit

Update load_policies for both flat and enriched formats. Add boundary
examples, acceptable uses, and org context to generation prompts when
available. Backward compatible — falls back to current format."
```

---

### Task 7: Update `evaluate.py` for enriched format

**Files:**
- Modify: `refiner/src/refiner/evaluate.py:325-327`
- Modify: `refiner/tests/test_evaluate.py`

- [ ] **Step 1: Write failing test**

Add to `refiner/tests/test_evaluate.py`:

```python
def test_run_evaluation_enriched_policies(tmp_path):
    """run_evaluation should handle enriched PolicyProfile format."""
    import json

    # Create minimal pipeline output files
    report = {"model": "test", "policy_set": "test", "timestamp": "2026-01-01",
              "stages_completed": ["classify"], "events": []}
    (tmp_path / "test-report.yaml").write_text(yaml.dump(report))

    enriched = {
        "airo_version": "0.2",
        "organization": "Test",
        "domain": "healthcare",
        "policies": [
            {"policy_concept": "PHI", "concept_definition": "No PII"},
        ],
    }
    policies_path = tmp_path / "enriched.json"
    policies_path.write_text(json.dumps(enriched))

    from refiner.evaluate import run_evaluation
    result = run_evaluation(tmp_path, policies_path=policies_path)
    assert result["run"]["model"] == "test"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd refiner && uv run pytest tests/test_evaluate.py -k "enriched" -v`
Expected: FAIL — `run_evaluation` tries to iterate enriched JSON as array.

- [ ] **Step 3: Update policy loading in `evaluate.py`**

In `refiner/src/refiner/evaluate.py`, replace lines 325-327:

```python
    all_policies = None
    if policies_path and policies_path.exists():
        raw_policies = json.loads(policies_path.read_text())
        all_policies = {p["policy_concept"]: p["concept_definition"] for p in raw_policies}
```

With:

```python
    all_policies = None
    if policies_path and policies_path.exists():
        raw_policies = json.loads(policies_path.read_text())
        if isinstance(raw_policies, list):
            all_policies = {p["policy_concept"]: p["concept_definition"] for p in raw_policies}
        else:
            all_policies = {
                p["policy_concept"]: p["concept_definition"]
                for p in raw_policies.get("policies", [])
            }
```

- [ ] **Step 4: Run test**

Run: `cd refiner && uv run pytest tests/test_evaluate.py -k "enriched" -v`
Expected: PASS.

- [ ] **Step 5: Run full test suite**

Run: `cd refiner && uv run pytest -v`
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add refiner/src/refiner/evaluate.py refiner/tests/test_evaluate.py
git commit -m "fix(refiner): handle enriched PolicyProfile format in evaluate

Format detection for policy loading — flat array or object with policies key.
Backward compatible with existing flat JSON files."
```

---

### Task 8: Integration test and final verification

**Files:**
- Modify: `refiner/tests/test_cli.py`

- [ ] **Step 1: Write end-to-end integration test**

Add to `refiner/tests/test_cli.py`:

```python
@patch("refiner.cli.create_client")
def test_ingest_then_run_integration(mock_create_client, tmp_path, monkeypatch):
    """Full workflow: ingest flat JSON → enriched JSON → refiner run accepts it."""
    from refiner.stages.ingest import _SlimContext, _SlimEnrichmentList, _SlimEnrichment, _SlimBoundaryExample

    monkeypatch.setenv("REFINER_BASE_URL", "http://localhost:8000/v1")
    monkeypatch.setenv("REFINER_MODEL", "test-model")

    # Create flat JSON
    flat_json = tmp_path / "policies.json"
    flat_json.write_text(json.dumps([
        {"policy_concept": "Fraud", "concept_definition": "About fraud"},
    ]))

    # Mock client for ingest
    mock_client = MagicMock()
    mock_create_client.return_value = mock_client
    mock_client.chat.completions.create.side_effect = [
        _SlimContext(
            organization="Bank", domain="finance", purpose=["services"],
            ai_systems=["ChatBot"], ai_users=["staff"], ai_subjects=["customers"],
            governing_regulations=[], named_entities=[],
        ),
        _SlimEnrichmentList(enrichments=[
            _SlimEnrichment(
                policy_concept="Fraud",
                boundary_examples=[
                    _SlimBoundaryExample(prohibited="commit fraud", acceptable="report fraud")
                ],
                acceptable_uses=["fraud reporting"],
                risk_controls=[], human_involvement="",
            ),
        ]),
    ]

    enriched = tmp_path / "enriched.json"
    result = runner.invoke(app, ["ingest", str(flat_json), "-o", str(enriched)])
    assert result.exit_code == 0, result.output
    assert enriched.exists()

    # Verify enriched file is valid PolicyProfile
    import json as json_mod
    data = json_mod.loads(enriched.read_text())
    assert data["organization"] == "Bank"
    assert data["policies"][0]["boundary_examples"][0]["prohibited"] == "commit fraud"

    # Verify refiner run would accept this file (just test the loading, not full pipeline)
    from refiner.models import PolicyProfile
    doc = PolicyProfile(**data)
    assert len(doc.policies) == 1
    assert doc.policies[0].policy_concept == "Fraud"
```

- [ ] **Step 2: Run integration test**

Run: `cd refiner && uv run pytest tests/test_cli.py::test_ingest_then_run_integration -v`
Expected: PASS.

- [ ] **Step 3: Run full test suite one final time**

Run: `cd refiner && uv run pytest -v`
Expected: All tests pass (140 existing + ~25 new).

- [ ] **Step 4: Commit**

```bash
git add refiner/tests/test_cli.py
git commit -m "test(refiner): add ingest→run integration test

Verifies full workflow: flat JSON → ingest → enriched PolicyProfile →
loadable by refiner run."
```

---

## Task Dependency Summary

```
Task 1 (models) ──→ Task 2 (CoT) ──→ Task 3 (ingest.py) ──→ Task 4 (CLI)
                                                                    │
                                              Task 5 (run format) ←─┘
                                              Task 6 (emit enrichment)
                                              Task 7 (evaluate format)
                                                        │
                                              Task 8 (integration) ←─┘
```

Tasks 5, 6, 7 are independent of each other but depend on Tasks 1-4. Task 8 depends on all prior tasks.
