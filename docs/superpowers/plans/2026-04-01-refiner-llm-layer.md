# Refiner LLM Layer Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a staged batch pipeline that transforms client policy JSON into LinkML-conformant risk taxonomies + domain context profiles, using self-hosted open-weight models via Instructor + OpenAI SDK.

**Architecture:** Five pipeline stages (classify, map_risks, anchor, contextualize, structure) with Pydantic models as stage contracts. Python code performs all retrieval via existing ontoquery/nexus-mcp handler dicts; the LLM receives assembled context and produces structured output via `instructor.Mode.JSON`. CLI is a thin Typer wrapper.

**Tech Stack:** Python 3.11+, uv, instructor, openai, pydantic, typer, pyyaml, pytest

**Spec:** `docs/superpowers/specs/2026-04-01-refiner-llm-layer-design.md`

---

## File Structure

```
refiner/
  pyproject.toml                    # uv project with hatchling build
  src/refiner/
    __init__.py                     # empty
    models.py                       # All Pydantic models (Policy, PolicyClassification, RiskMatch, etc.)
    llm.py                          # LLMConfig dataclass + create_client()
    stages/
      __init__.py                   # empty
      classify.py                   # classify() — Stage 1: policy type classification
      map_risks.py                  # map_risks() — Stage 2: policy-to-risk mapping
      anchor.py                     # anchor() — Stage 3: CCO variation axis identification
      contextualize.py              # contextualize() — Stage 4: domain context profile generation
      structure.py                  # structure() — Stage 5: deterministic assembly to YAML
    pipeline.py                     # PipelineState + run_pipeline() orchestration
    cli.py                          # Typer CLI: `refiner run`
  tests/
    __init__.py                     # empty
    conftest.py                     # Shared fixtures: mock_client, mock_config, mock handlers
    test_models.py                  # Model instantiation and validation
    test_llm.py                     # LLMConfig and create_client tests
    test_classify.py                # Stage 1 tests
    test_map_risks.py               # Stage 2 tests
    test_anchor.py                  # Stage 3 tests
    test_contextualize.py           # Stage 4 tests
    test_structure.py               # Stage 5 tests
    test_pipeline.py                # Pipeline integration tests
    test_cli.py                     # CLI invocation tests
```

---

### Task 1: Project Scaffolding

**Files:**
- Create: `refiner/pyproject.toml`
- Create: `refiner/src/refiner/__init__.py`
- Create: `refiner/src/refiner/stages/__init__.py`
- Create: `refiner/tests/__init__.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[project]
name = "refiner"
version = "0.1.0"
description = "LLM pipeline for transforming client policies into risk taxonomies with domain context"
requires-python = ">=3.11"
dependencies = [
    "instructor>=1.0",
    "openai>=1.0",
    "pydantic>=2.0",
    "typer>=0.12",
    "pyyaml>=6.0",
    "ontoquery",
    "nexus-mcp",
]

[project.scripts]
refiner = "refiner.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/refiner"]

[tool.hatch.metadata]
allow-direct-references = true

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.uv]
dev-dependencies = ["pytest>=8.0"]

[tool.uv.sources]
ontoquery = { path = "../ontoquery", editable = true }
nexus-mcp = { path = "../nexus-mcp", editable = true }
```

Note: `ontoquery` and `nexus-mcp` are local path dependencies resolved via `[tool.uv.sources]`. They bring `ai-atlas-nexus` (git dep) transitively through `nexus-mcp`. The CLI imports these at runtime to create handler dicts. Core pipeline code (models, stages, pipeline) only uses plain dicts and Pydantic models — no direct imports from these packages.

- [ ] **Step 2: Create empty `__init__.py` files**

Create empty files at:
- `refiner/src/refiner/__init__.py`
- `refiner/src/refiner/stages/__init__.py`
- `refiner/tests/__init__.py`

- [ ] **Step 3: Verify uv sync**

Run: `cd refiner && uv sync`
Expected: Dependencies resolve and install successfully.

- [ ] **Step 4: Verify pytest runs**

Run: `cd refiner && uv run pytest -v`
Expected: "no tests ran" (0 collected), exit code 5 (no tests found).

---

### Task 2: Pydantic Models

**Files:**
- Create: `refiner/src/refiner/models.py`
- Create: `refiner/tests/test_models.py`

- [ ] **Step 1: Write model validation tests**

```python
# tests/test_models.py
import pytest
from refiner.models import (
    Policy,
    PolicyClassification,
    RiskMatch,
    CrossMapping,
    PolicyRiskMapping,
    VariationAxis,
    RiskVariationAxes,
    AxisEnumeration,
    DomainContextAxis,
    DomainContextProfile,
)


def test_policy_creation():
    p = Policy(policy_concept="Fraud", concept_definition="Prompts about fraud")
    assert p.policy_concept == "Fraud"


def test_policy_classification_valid_types():
    for t in ("A", "B", "C", "D"):
        pc = PolicyClassification(
            policy_concept="X",
            concept_definition="Y",
            policy_type=t,
            justification="reason",
        )
        assert pc.policy_type == t


def test_policy_classification_invalid_type():
    with pytest.raises(Exception):
        PolicyClassification(
            policy_concept="X",
            concept_definition="Y",
            policy_type="Z",
            justification="reason",
        )


def test_risk_match_valid_relevance():
    for r in ("primary", "supporting", "tangential"):
        rm = RiskMatch(risk_id="r1", risk_name="Risk", relevance=r, justification="j")
        assert rm.relevance == r


def test_cross_mapping_valid_types():
    for mt in ("exact", "close", "broad", "narrow", "related"):
        cm = CrossMapping(
            source_risk_id="r1",
            target_risk_id="r2",
            target_risk_name="Risk2",
            target_taxonomy="tax",
            mapping_type=mt,
        )
        assert cm.mapping_type == mt


def test_policy_risk_mapping():
    prm = PolicyRiskMapping(
        policy_concept="Fraud",
        policy_type="A",
        matched_risks=[],
        cross_mappings=[],
    )
    assert prm.matched_risks == []


def test_variation_axis():
    va = VariationAxis(
        cco_class_uri="http://example.org/Person",
        cco_class_label="Person",
        role="agent",
        rationale="Actors who commit fraud",
    )
    assert va.role == "agent"


def test_risk_variation_axes():
    rva = RiskVariationAxes(
        risk_id="r1",
        risk_name="Fraud",
        policy_concept="Fraud",
        axes=[],
    )
    assert rva.axes == []


def test_axis_enumeration_valid_relevance():
    for r in ("high", "medium", "low"):
        ae = AxisEnumeration(
            class_uri="http://example.org/C",
            class_label="Class",
            source_ontology="CCO",
            relevance=r,
        )
        assert ae.relevance == r


def test_domain_context_profile():
    dcp = DomainContextProfile(
        risk_id="r1",
        risk_name="Fraud",
        policy_concept="Fraud",
        axes=[
            DomainContextAxis(
                cco_class_uri="http://example.org/Person",
                cco_class_label="Person",
                role="agent",
                enumerations=[],
            )
        ],
    )
    assert len(dcp.axes) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd refiner && uv run pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'refiner.models'`

- [ ] **Step 3: Implement models.py**

```python
# src/refiner/models.py
from typing import Literal
from pydantic import BaseModel


class Policy(BaseModel):
    policy_concept: str
    concept_definition: str


class PolicyClassification(BaseModel):
    policy_concept: str
    concept_definition: str
    policy_type: Literal["A", "B", "C", "D"]
    justification: str


class RiskMatch(BaseModel):
    risk_id: str
    risk_name: str
    relevance: Literal["primary", "supporting", "tangential"]
    justification: str


class CrossMapping(BaseModel):
    source_risk_id: str
    target_risk_id: str
    target_risk_name: str
    target_taxonomy: str
    mapping_type: Literal["exact", "close", "broad", "narrow", "related"]


class PolicyRiskMapping(BaseModel):
    policy_concept: str
    policy_type: str
    matched_risks: list[RiskMatch]
    cross_mappings: list[CrossMapping]


class VariationAxis(BaseModel):
    cco_class_uri: str
    cco_class_label: str
    role: str
    rationale: str


class RiskVariationAxes(BaseModel):
    risk_id: str
    risk_name: str
    policy_concept: str
    axes: list[VariationAxis]


class AxisEnumeration(BaseModel):
    class_uri: str
    class_label: str
    source_ontology: str
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

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd refiner && uv run pytest tests/test_models.py -v`
Expected: All 11 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add refiner/src/refiner/models.py refiner/tests/test_models.py
git commit -m "feat(refiner): add Pydantic models for all pipeline stages"
```

---

### Task 3: LLM Client & Configuration

**Files:**
- Create: `refiner/src/refiner/llm.py`
- Create: `refiner/tests/test_llm.py`

- [ ] **Step 1: Write LLM config tests**

```python
# tests/test_llm.py
from refiner.llm import LLMConfig, create_client


def test_config_defaults():
    cfg = LLMConfig(base_url="http://localhost:8000/v1", model="test-model")
    assert cfg.api_key == "none"
    assert cfg.temperature == 0.3
    assert cfg.max_retries == 3


def test_config_custom():
    cfg = LLMConfig(
        base_url="http://host:9000/v1",
        model="granite-3.1-8b",
        api_key="secret",
        temperature=0.7,
        max_retries=5,
    )
    assert cfg.base_url == "http://host:9000/v1"
    assert cfg.api_key == "secret"


def test_create_client_returns_instructor_instance(monkeypatch):
    cfg = LLMConfig(base_url="http://localhost:8000/v1", model="test-model")
    client = create_client(cfg)
    # Instructor wraps the OpenAI client — verify it has the expected interface
    assert hasattr(client, "chat")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd refiner && uv run pytest tests/test_llm.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'refiner.llm'`

- [ ] **Step 3: Implement llm.py**

```python
# src/refiner/llm.py
from dataclasses import dataclass

import instructor
from openai import OpenAI


@dataclass
class LLMConfig:
    base_url: str
    model: str
    api_key: str = "none"
    temperature: float = 0.3
    max_retries: int = 3


def create_client(config: LLMConfig) -> instructor.Instructor:
    return instructor.from_openai(
        OpenAI(base_url=config.base_url, api_key=config.api_key),
        mode=instructor.Mode.JSON,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd refiner && uv run pytest tests/test_llm.py -v`
Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add refiner/src/refiner/llm.py refiner/tests/test_llm.py
git commit -m "feat(refiner): add LLM client config and create_client"
```

---

### Task 4: Test Fixtures & Shared Conftest

**Files:**
- Create: `refiner/tests/conftest.py`

This task sets up shared test infrastructure used by all stage tests.

- [ ] **Step 1: Create conftest.py**

```python
# tests/conftest.py
import pytest
from unittest.mock import MagicMock
from refiner.llm import LLMConfig


@pytest.fixture
def mock_config():
    return LLMConfig(base_url="http://localhost:8000/v1", model="test-model")


@pytest.fixture
def mock_client():
    """Mock Instructor client. Tests set return_value on chat.completions.create."""
    client = MagicMock()
    return client


@pytest.fixture
def mock_risk_handlers():
    """Mock nexus-mcp risk handlers dict."""
    return {
        "search_risks": MagicMock(return_value=[]),
        "get_risk_details": MagicMock(return_value=None),
        "get_related_risks": MagicMock(return_value=[]),
        "get_related_actions": MagicMock(return_value=[]),
        "list_taxonomies": MagicMock(return_value=[]),
        "list_risk_groups": MagicMock(return_value=[]),
        "explore_risk": MagicMock(return_value=None),
        "gap_analysis": MagicMock(return_value={}),
    }


@pytest.fixture
def mock_onto_handlers():
    """Mock ontoquery ontology handlers dict."""
    return {
        "search_classes": MagicMock(return_value=[]),
        "get_class_definition": MagicMock(return_value=None),
        "get_subclasses": MagicMock(return_value=[]),
        "get_superclasses": MagicMock(return_value=[]),
        "get_siblings": MagicMock(return_value=[]),
        "get_properties": MagicMock(return_value=[]),
        "explore_class": MagicMock(return_value=None),
    }
```

- [ ] **Step 2: Verify fixtures load**

Run: `cd refiner && uv run pytest --fixtures tests/ | grep mock_client`
Expected: `mock_client` fixture is listed.

- [ ] **Step 3: Commit**

```bash
git add refiner/tests/conftest.py
git commit -m "feat(refiner): add shared test fixtures for mock LLM and handlers"
```

---

### Task 5: Stage 1 — Classify

**Files:**
- Create: `refiner/src/refiner/stages/classify.py`
- Create: `refiner/tests/test_classify.py`

- [ ] **Step 1: Write classify tests**

```python
# tests/test_classify.py
import logging
from refiner.models import Policy, PolicyClassification
from refiner.stages.classify import classify


def test_classify_returns_classifications(mock_client, mock_config):
    policies = [
        Policy(policy_concept="Fraud", concept_definition="Prompts about fraud"),
        Policy(policy_concept="Executive Compensation", concept_definition="Prompts about exec pay"),
    ]
    mock_client.chat.completions.create.return_value = [
        PolicyClassification(
            policy_concept="Fraud",
            concept_definition="Prompts about fraud",
            policy_type="A",
            justification="Safety concern",
        ),
        PolicyClassification(
            policy_concept="Executive Compensation",
            concept_definition="Prompts about exec pay",
            policy_type="B",
            justification="Confidentiality concern",
        ),
    ]
    result = classify(policies, mock_client, mock_config)
    assert len(result) == 2
    assert result[0].policy_type == "A"
    assert result[1].policy_type == "B"


def test_classify_calls_client_with_correct_params(mock_client, mock_config):
    policies = [Policy(policy_concept="X", concept_definition="Y")]
    mock_client.chat.completions.create.return_value = [
        PolicyClassification(
            policy_concept="X", concept_definition="Y", policy_type="A", justification="j"
        ),
    ]
    classify(policies, mock_client, mock_config)
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "test-model"
    assert call_kwargs["temperature"] == 0.3
    assert "messages" in call_kwargs


def test_classify_empty_policies(mock_client, mock_config):
    result = classify([], mock_client, mock_config)
    assert result == []
    mock_client.chat.completions.create.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd refiner && uv run pytest tests/test_classify.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'refiner.stages.classify'`

- [ ] **Step 3: Implement classify.py**

```python
# src/refiner/stages/classify.py
import logging

import instructor
from refiner.llm import LLMConfig
from refiner.models import Policy, PolicyClassification

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are classifying client content policies for an LLM deployment.

Classify each policy into exactly one type:
- A (Safety): Harmful content, violence, illegal activity, hate speech, self-harm, etc.
- B (Confidentiality): Protecting sensitive, proprietary, or personal information
- C (Scope/Regulatory): Regulatory compliance, scope limitations, sanctions, jurisdiction
- D (Routing): Redirecting certain queries to humans or other systems

For each policy, return the policy_concept, concept_definition, policy_type, and a brief justification."""


def classify(
    policies: list[Policy],
    client: instructor.Instructor,
    config: LLMConfig,
) -> list[PolicyClassification]:
    if not policies:
        return []

    policy_lines = []
    for i, p in enumerate(policies, 1):
        policy_lines.append(f"{i}. {p.policy_concept}: {p.concept_definition}")
    user_content = "Classify these policies:\n\n" + "\n".join(policy_lines)

    result = client.chat.completions.create(
        model=config.model,
        response_model=list[PolicyClassification],
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=config.temperature,
        max_retries=config.max_retries,
    )
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd refiner && uv run pytest tests/test_classify.py -v`
Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add refiner/src/refiner/stages/classify.py refiner/tests/test_classify.py
git commit -m "feat(refiner): implement Stage 1 classify with tests"
```

---

### Task 6: Stage 2 — Map Risks

**Files:**
- Create: `refiner/src/refiner/stages/map_risks.py`
- Create: `refiner/tests/test_map_risks.py`

- [ ] **Step 1: Write map_risks tests**

```python
# tests/test_map_risks.py
import logging
from refiner.models import (
    PolicyClassification,
    PolicyRiskMapping,
    RiskMatch,
    CrossMapping,
)
from refiner.stages.map_risks import map_risks


def _make_classification(concept="Fraud", policy_type="A"):
    return PolicyClassification(
        policy_concept=concept,
        concept_definition=f"Prompts about {concept.lower()}",
        policy_type=policy_type,
        justification="test",
    )


def test_map_risks_calls_search_and_details(mock_client, mock_config, mock_risk_handlers):
    classifications = [_make_classification()]
    mock_risk_handlers["search_risks"].return_value = [
        {"id": "atlas-fraud", "name": "Fraud", "description": "Fraud risk", "distance": 0.2},
    ]
    mock_risk_handlers["get_risk_details"].return_value = {
        "id": "atlas-fraud",
        "name": "Fraud",
        "description": "Fraud risk",
        "concern": "Financial loss",
        "risk_type": "output",
        "taxonomy": "ibm-risk-atlas",
    }
    mock_risk_handlers["get_related_risks"].return_value = []
    mock_client.chat.completions.create.return_value = PolicyRiskMapping(
        policy_concept="Fraud",
        policy_type="A",
        matched_risks=[
            RiskMatch(risk_id="atlas-fraud", risk_name="Fraud", relevance="primary", justification="j"),
        ],
        cross_mappings=[],
    )
    mappings, details = map_risks(classifications, mock_client, mock_config, mock_risk_handlers)
    assert len(mappings) == 1
    assert mappings[0].matched_risks[0].risk_id == "atlas-fraud"
    mock_risk_handlers["search_risks"].assert_called_once()
    mock_risk_handlers["get_risk_details"].assert_called_once_with("atlas-fraud")


def test_map_risks_filters_hallucinated_risk_ids(mock_client, mock_config, mock_risk_handlers):
    classifications = [_make_classification()]
    mock_risk_handlers["search_risks"].return_value = [
        {"id": "atlas-fraud", "name": "Fraud", "description": "Fraud risk", "distance": 0.2},
    ]
    mock_risk_handlers["get_risk_details"].side_effect = lambda rid: (
        {"id": "atlas-fraud", "name": "Fraud", "description": "d", "concern": "c",
         "risk_type": "output", "taxonomy": "ibm-risk-atlas"}
        if rid == "atlas-fraud" else None
    )
    mock_risk_handlers["get_related_risks"].return_value = []
    # LLM hallucinates a risk_id that doesn't exist
    mock_client.chat.completions.create.return_value = PolicyRiskMapping(
        policy_concept="Fraud",
        policy_type="A",
        matched_risks=[
            RiskMatch(risk_id="atlas-fraud", risk_name="Fraud", relevance="primary", justification="j"),
            RiskMatch(risk_id="hallucinated-id", risk_name="Fake", relevance="supporting", justification="j"),
        ],
        cross_mappings=[],
    )
    mappings, details = map_risks(classifications, mock_client, mock_config, mock_risk_handlers)
    # Hallucinated ID should be filtered out
    assert len(mappings[0].matched_risks) == 1
    assert mappings[0].matched_risks[0].risk_id == "atlas-fraud"


def test_map_risks_returns_risk_details_cache(mock_client, mock_config, mock_risk_handlers):
    classifications = [_make_classification()]
    risk_detail = {
        "id": "atlas-fraud", "name": "Fraud", "description": "Fraud risk",
        "concern": "Financial loss", "risk_type": "output", "taxonomy": "ibm-risk-atlas",
    }
    mock_risk_handlers["search_risks"].return_value = [
        {"id": "atlas-fraud", "name": "Fraud", "description": "Fraud risk", "distance": 0.2},
    ]
    mock_risk_handlers["get_risk_details"].return_value = risk_detail
    mock_risk_handlers["get_related_risks"].return_value = []
    mock_client.chat.completions.create.return_value = PolicyRiskMapping(
        policy_concept="Fraud", policy_type="A",
        matched_risks=[RiskMatch(risk_id="atlas-fraud", risk_name="Fraud", relevance="primary", justification="j")],
        cross_mappings=[],
    )
    _, details = map_risks(classifications, mock_client, mock_config, mock_risk_handlers)
    assert "atlas-fraud" in details
    assert details["atlas-fraud"]["description"] == "Fraud risk"


def test_map_risks_empty_classifications(mock_client, mock_config, mock_risk_handlers):
    mappings, details = map_risks([], mock_client, mock_config, mock_risk_handlers)
    assert mappings == []
    assert details == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd refiner && uv run pytest tests/test_map_risks.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement map_risks.py**

```python
# src/refiner/stages/map_risks.py
import logging

import instructor
from refiner.llm import LLMConfig
from refiner.models import (
    PolicyClassification,
    PolicyRiskMapping,
    RiskMatch,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are mapping client content policies to known AI risk entries from a knowledge graph.

Given a policy definition and a list of candidate risks (with descriptions and cross-framework mappings), select the most relevant risks and classify their relevance:
- primary: Directly addresses the policy concern
- supporting: Related but not the primary match
- tangential: Loosely related

Also identify which cross-framework mappings add genuine coverage vs. redundancy.

Return a PolicyRiskMapping with matched_risks and cross_mappings."""


def map_risks(
    classifications: list[PolicyClassification],
    client: instructor.Instructor,
    config: LLMConfig,
    risk_handlers: dict,
) -> tuple[list[PolicyRiskMapping], dict[str, dict]]:
    if not classifications:
        return [], {}

    risk_details_cache: dict[str, dict] = {}
    mappings: list[PolicyRiskMapping] = []

    for cls in classifications:
        # 1. Semantic search for candidate risks
        candidates = risk_handlers["search_risks"](cls.concept_definition, top_k=10)

        # 2. Get full details for each candidate
        enriched_candidates = []
        for c in candidates:
            details = risk_handlers["get_risk_details"](c["id"])
            if details is None:
                continue
            risk_details_cache[c["id"]] = details
            # 3. Get cross-framework mappings
            related = risk_handlers["get_related_risks"](c["id"])
            enriched_candidates.append({**details, "cross_mappings": related})

        if not enriched_candidates:
            mappings.append(PolicyRiskMapping(
                policy_concept=cls.policy_concept,
                policy_type=cls.policy_type,
                matched_risks=[],
                cross_mappings=[],
            ))
            continue

        # Build context for LLM
        candidate_lines = []
        for ec in enriched_candidates:
            line = f"- {ec['id']}: {ec['name']} — {ec.get('description', '')}"
            if ec.get("concern"):
                line += f" (Concern: {ec['concern']})"
            if ec["cross_mappings"]:
                xm = ", ".join(f"{x['id']}[{x['mapping_type']}]" for x in ec["cross_mappings"])
                line += f"\n  Cross-mappings: {xm}"
            candidate_lines.append(line)

        user_content = (
            f"Policy: {cls.policy_concept}\n"
            f"Definition: {cls.concept_definition}\n"
            f"Policy Type: {cls.policy_type}\n\n"
            f"Candidate risks:\n" + "\n".join(candidate_lines)
        )

        result = client.chat.completions.create(
            model=config.model,
            response_model=PolicyRiskMapping,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=config.temperature,
            max_retries=config.max_retries,
        )

        # Post-processing: validate risk IDs exist
        valid_ids = set(risk_details_cache.keys())
        valid_risks = []
        for rm in result.matched_risks:
            if rm.risk_id in valid_ids:
                valid_risks.append(rm)
            else:
                logger.warning("Filtering hallucinated risk_id: %s", rm.risk_id)
        result = result.model_copy(update={"matched_risks": valid_risks})

        mappings.append(result)

    return mappings, risk_details_cache
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd refiner && uv run pytest tests/test_map_risks.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add refiner/src/refiner/stages/map_risks.py refiner/tests/test_map_risks.py
git commit -m "feat(refiner): implement Stage 2 map_risks with semantic validation"
```

---

### Task 7: Stage 3 — Anchor

**Files:**
- Create: `refiner/src/refiner/stages/anchor.py`
- Create: `refiner/tests/test_anchor.py`

- [ ] **Step 1: Write anchor tests**

```python
# tests/test_anchor.py
import logging
from refiner.models import (
    PolicyRiskMapping,
    RiskMatch,
    RiskVariationAxes,
    VariationAxis,
)
from refiner.stages.anchor import anchor


def _make_mapping():
    return PolicyRiskMapping(
        policy_concept="Fraud",
        policy_type="A",
        matched_risks=[
            RiskMatch(risk_id="atlas-fraud", risk_name="Fraud", relevance="primary", justification="j"),
        ],
        cross_mappings=[],
    )


def _make_risk_details():
    return {
        "atlas-fraud": {
            "id": "atlas-fraud",
            "name": "Fraud",
            "description": "Fraudulent activities targeting financial systems",
            "concern": "Financial loss and trust erosion",
        }
    }


def test_anchor_searches_ontology(mock_client, mock_config, mock_onto_handlers):
    mappings = [_make_mapping()]
    risk_details = _make_risk_details()
    mock_onto_handlers["search_classes"].return_value = [
        {"uri": "http://example.org/Person", "label": "Person", "definition": "A human.", "distance": 0.3},
    ]
    mock_onto_handlers["get_class_definition"].return_value = {
        "uri": "http://example.org/Person", "label": "Person", "definition": "A human.",
        "superclasses": [],
    }
    mock_onto_handlers["get_siblings"].return_value = []
    mock_client.chat.completions.create.return_value = RiskVariationAxes(
        risk_id="atlas-fraud",
        risk_name="Fraud",
        policy_concept="Fraud",
        axes=[
            VariationAxis(
                cco_class_uri="http://example.org/Person",
                cco_class_label="Person",
                role="agent",
                rationale="Person committing fraud",
            ),
        ],
    )
    result = anchor(mappings, risk_details, mock_client, mock_config, mock_onto_handlers)
    assert len(result) == 1
    assert result[0].axes[0].cco_class_uri == "http://example.org/Person"
    mock_onto_handlers["search_classes"].assert_called_once()


def test_anchor_filters_invalid_uris(mock_client, mock_config, mock_onto_handlers):
    mappings = [_make_mapping()]
    risk_details = _make_risk_details()
    mock_onto_handlers["search_classes"].return_value = [
        {"uri": "http://example.org/Person", "label": "Person", "definition": "A human.", "distance": 0.3},
    ]
    mock_onto_handlers["get_class_definition"].side_effect = lambda uri: (
        {"uri": uri, "label": "Person", "definition": "A human.", "superclasses": []}
        if uri == "http://example.org/Person" else None
    )
    mock_onto_handlers["get_siblings"].return_value = []
    # LLM returns a valid and an invalid URI
    mock_client.chat.completions.create.return_value = RiskVariationAxes(
        risk_id="atlas-fraud", risk_name="Fraud", policy_concept="Fraud",
        axes=[
            VariationAxis(cco_class_uri="http://example.org/Person", cco_class_label="Person", role="agent", rationale="r"),
            VariationAxis(cco_class_uri="http://example.org/Fake", cco_class_label="Fake", role="object", rationale="r"),
        ],
    )
    result = anchor(mappings, risk_details, mock_client, mock_config, mock_onto_handlers)
    assert len(result[0].axes) == 1
    assert result[0].axes[0].cco_class_uri == "http://example.org/Person"


def test_anchor_empty_mappings(mock_client, mock_config, mock_onto_handlers):
    result = anchor([], {}, mock_client, mock_config, mock_onto_handlers)
    assert result == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd refiner && uv run pytest tests/test_anchor.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement anchor.py**

```python
# src/refiner/stages/anchor.py
import logging

import instructor
from refiner.llm import LLMConfig
from refiner.models import (
    PolicyRiskMapping,
    RiskVariationAxes,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are identifying variation axes for AI risk concepts using ontology classes.

A variation axis is a CCO (Common Core Ontology) class that represents a dimension along which diverse prompts can be generated. Each axis has a semantic role relative to the risk:
- agent: Who performs or is affected by the action
- object: What is acted upon
- instrument: What tool/means is used
- location: Where it occurs
- temporal: When it occurs

Given a risk (with description and concern) and candidate ontology classes (with definitions and siblings), identify the most relevant CCO classes as variation axes.

Return a RiskVariationAxes with the risk_id, risk_name, policy_concept, and a list of axes."""


def anchor(
    risk_mappings: list[PolicyRiskMapping],
    risk_details: dict[str, dict],
    client: instructor.Instructor,
    config: LLMConfig,
    onto_handlers: dict,
) -> list[RiskVariationAxes]:
    if not risk_mappings:
        return []

    results: list[RiskVariationAxes] = []

    for mapping in risk_mappings:
        for rm in mapping.matched_risks:
            details = risk_details.get(rm.risk_id, {})
            description = details.get("description", rm.risk_name)
            concern = details.get("concern", "")

            # Search ontology for candidate classes
            candidates = onto_handlers["search_classes"](description, top_k=10)

            # Enrich candidates with definitions and siblings
            enriched = []
            known_uris = set()
            for c in candidates:
                defn = onto_handlers["get_class_definition"](c["uri"])
                if defn is None:
                    continue
                known_uris.add(c["uri"])
                siblings = onto_handlers["get_siblings"](c["uri"])
                for s in siblings:
                    known_uris.add(s.get("uri", ""))
                enriched.append({**defn, "siblings": siblings})

            if not enriched:
                results.append(RiskVariationAxes(
                    risk_id=rm.risk_id,
                    risk_name=rm.risk_name,
                    policy_concept=mapping.policy_concept,
                    axes=[],
                ))
                continue

            # Build context for LLM
            class_lines = []
            for ec in enriched:
                line = f"- {ec['uri']}: {ec.get('label', '')} — {ec.get('definition', '')}"
                if ec.get("siblings"):
                    sibs = ", ".join(s.get("label", s.get("uri", "")) for s in ec["siblings"][:5])
                    line += f"\n  Siblings: {sibs}"
                class_lines.append(line)

            user_content = (
                f"Risk: {rm.risk_name}\n"
                f"Description: {description}\n"
                f"Concern: {concern}\n"
                f"Policy: {mapping.policy_concept}\n\n"
                f"Candidate ontology classes:\n" + "\n".join(class_lines)
            )

            result = client.chat.completions.create(
                model=config.model,
                response_model=RiskVariationAxes,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                temperature=config.temperature,
                max_retries=config.max_retries,
            )

            # Post-processing: validate URIs exist in ontology
            valid_axes = []
            for axis in result.axes:
                check = onto_handlers["get_class_definition"](axis.cco_class_uri)
                if check is not None:
                    valid_axes.append(axis)
                else:
                    logger.warning("Filtering invalid cco_class_uri: %s", axis.cco_class_uri)
            result = result.model_copy(update={"axes": valid_axes})

            results.append(result)

    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd refiner && uv run pytest tests/test_anchor.py -v`
Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add refiner/src/refiner/stages/anchor.py refiner/tests/test_anchor.py
git commit -m "feat(refiner): implement Stage 3 anchor with URI validation"
```

---

### Task 8: Stage 4 — Contextualize

**Files:**
- Create: `refiner/src/refiner/stages/contextualize.py`
- Create: `refiner/tests/test_contextualize.py`

- [ ] **Step 1: Write contextualize tests**

```python
# tests/test_contextualize.py
from refiner.models import (
    RiskVariationAxes,
    VariationAxis,
    DomainContextProfile,
    DomainContextAxis,
    AxisEnumeration,
)
from refiner.stages.contextualize import contextualize


def _make_axes():
    return RiskVariationAxes(
        risk_id="atlas-fraud",
        risk_name="Fraud",
        policy_concept="Fraud",
        axes=[
            VariationAxis(
                cco_class_uri="http://example.org/Person",
                cco_class_label="Person",
                role="agent",
                rationale="Actor",
            ),
        ],
    )


def test_contextualize_gets_subclasses(mock_client, mock_config, mock_onto_handlers):
    axes = [_make_axes()]
    mock_onto_handlers["get_subclasses"].return_value = [
        {"uri": "http://example.org/Employee", "label": "Employee", "depth": 1},
        {"uri": "http://example.org/Manager", "label": "Manager", "depth": 2},
    ]
    mock_client.chat.completions.create.return_value = DomainContextProfile(
        risk_id="atlas-fraud",
        risk_name="Fraud",
        policy_concept="Fraud",
        axes=[
            DomainContextAxis(
                cco_class_uri="http://example.org/Person",
                cco_class_label="Person",
                role="agent",
                enumerations=[
                    AxisEnumeration(class_uri="http://example.org/Employee", class_label="Employee", source_ontology="CCO", relevance="high"),
                ],
            ),
        ],
    )
    result = contextualize(axes, mock_client, mock_config, mock_onto_handlers)
    assert len(result) == 1
    assert result[0].axes[0].enumerations[0].class_label == "Employee"
    mock_onto_handlers["get_subclasses"].assert_called_once_with("http://example.org/Person", depth=2)


def test_contextualize_preserves_policy_concept(mock_client, mock_config, mock_onto_handlers):
    axes = [_make_axes()]
    mock_onto_handlers["get_subclasses"].return_value = []
    mock_client.chat.completions.create.return_value = DomainContextProfile(
        risk_id="atlas-fraud", risk_name="Fraud", policy_concept="Fraud",
        axes=[DomainContextAxis(cco_class_uri="http://example.org/Person", cco_class_label="Person", role="agent", enumerations=[])],
    )
    result = contextualize(axes, mock_client, mock_config, mock_onto_handlers)
    assert result[0].policy_concept == "Fraud"


def test_contextualize_filters_invalid_enumeration_uris(mock_client, mock_config, mock_onto_handlers):
    axes = [_make_axes()]
    mock_onto_handlers["get_subclasses"].return_value = [
        {"uri": "http://example.org/Employee", "label": "Employee", "depth": 1},
    ]
    mock_onto_handlers["get_class_definition"].side_effect = lambda uri: (
        {"uri": uri, "label": "Employee", "definition": "d", "superclasses": []}
        if uri == "http://example.org/Employee" else None
    )
    mock_client.chat.completions.create.return_value = DomainContextProfile(
        risk_id="atlas-fraud", risk_name="Fraud", policy_concept="Fraud",
        axes=[
            DomainContextAxis(
                cco_class_uri="http://example.org/Person", cco_class_label="Person", role="agent",
                enumerations=[
                    AxisEnumeration(class_uri="http://example.org/Employee", class_label="Employee", source_ontology="CCO", relevance="high"),
                    AxisEnumeration(class_uri="http://example.org/FakeClass", class_label="Fake", source_ontology="CCO", relevance="low"),
                ],
            ),
        ],
    )
    result = contextualize(axes, mock_client, mock_config, mock_onto_handlers)
    assert len(result[0].axes[0].enumerations) == 1
    assert result[0].axes[0].enumerations[0].class_uri == "http://example.org/Employee"


def test_contextualize_empty_axes(mock_client, mock_config, mock_onto_handlers):
    result = contextualize([], mock_client, mock_config, mock_onto_handlers)
    assert result == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd refiner && uv run pytest tests/test_contextualize.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement contextualize.py**

```python
# src/refiner/stages/contextualize.py
import logging

import instructor
from refiner.llm import LLMConfig
from refiner.models import (
    RiskVariationAxes,
    DomainContextProfile,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are generating domain context profiles for AI risk variation axes.

For each variation axis (a CCO ontology class), you are given its subclasses from domain ontologies. These subclasses form the enumeration space — the specific values that can be substituted when generating diverse prompts.

Filter out irrelevant subclasses and annotate each remaining one with:
- source_ontology: Which ontology it comes from (e.g., "FIBO", "CCO", "OBO", "IOF")
- relevance: "high" (directly relevant), "medium" (potentially relevant), "low" (edge case)

Return a DomainContextProfile preserving the risk_id, risk_name, and policy_concept."""


def contextualize(
    variation_axes: list[RiskVariationAxes],
    client: instructor.Instructor,
    config: LLMConfig,
    onto_handlers: dict,
) -> list[DomainContextProfile]:
    if not variation_axes:
        return []

    results: list[DomainContextProfile] = []

    for rva in variation_axes:
        if not rva.axes:
            results.append(DomainContextProfile(
                risk_id=rva.risk_id,
                risk_name=rva.risk_name,
                policy_concept=rva.policy_concept,
                axes=[],
            ))
            continue

        # Gather subclasses for each axis
        axis_context = []
        for axis in rva.axes:
            subclasses = onto_handlers["get_subclasses"](axis.cco_class_uri, depth=2)
            sub_lines = []
            for sc in subclasses:
                sub_lines.append(f"  - {sc.get('uri', '')}: {sc.get('label', '')} (depth {sc.get('depth', '?')})")
            axis_context.append(
                f"Axis: {axis.cco_class_label} ({axis.cco_class_uri})\n"
                f"Role: {axis.role}\n"
                f"Subclasses:\n" + ("\n".join(sub_lines) if sub_lines else "  (none)")
            )

        user_content = (
            f"Risk: {rva.risk_name} (ID: {rva.risk_id})\n"
            f"Policy: {rva.policy_concept}\n\n"
            + "\n\n".join(axis_context)
        )

        result = client.chat.completions.create(
            model=config.model,
            response_model=DomainContextProfile,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=config.temperature,
            max_retries=config.max_retries,
        )

        # Post-processing: validate enumeration URIs resolve in ontology
        validated_axes = []
        for axis in result.axes:
            valid_enums = []
            for enum in axis.enumerations:
                check = onto_handlers["get_class_definition"](enum.class_uri)
                if check is not None:
                    valid_enums.append(enum)
                else:
                    logger.warning("Filtering invalid enumeration class_uri: %s", enum.class_uri)
            validated_axes.append(axis.model_copy(update={"enumerations": valid_enums}))
        result = result.model_copy(update={"axes": validated_axes})

        results.append(result)

    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd refiner && uv run pytest tests/test_contextualize.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add refiner/src/refiner/stages/contextualize.py refiner/tests/test_contextualize.py
git commit -m "feat(refiner): implement Stage 4 contextualize with domain profiles"
```

---

### Task 9: Stage 5 — Structure

**Files:**
- Create: `refiner/src/refiner/stages/structure.py`
- Create: `refiner/tests/test_structure.py`

This stage is deterministic (no LLM). It assembles all previous stage outputs into two YAML-serializable dicts.

- [ ] **Step 1: Write structure tests**

```python
# tests/test_structure.py
import pytest
from refiner.models import (
    Policy,
    PolicyClassification,
    PolicyRiskMapping,
    RiskMatch,
    CrossMapping,
    DomainContextProfile,
    DomainContextAxis,
    AxisEnumeration,
)
from refiner.stages.structure import structure, slugify


def test_slugify():
    assert slugify("Executive Compensation") == "executive-compensation"
    assert slugify("Debt Repayment Negotiation") == "debt-repayment-negotiation"
    assert slugify("Fraud") == "fraud"
    assert slugify("Security & Malware") == "security-malware"


def _make_state_data():
    classifications = [
        PolicyClassification(
            policy_concept="Fraud", concept_definition="About fraud",
            policy_type="A", justification="Safety",
        ),
        PolicyClassification(
            policy_concept="Executive Compensation", concept_definition="About exec pay",
            policy_type="B", justification="Confidentiality",
        ),
    ]
    risk_mappings = [
        PolicyRiskMapping(
            policy_concept="Fraud", policy_type="A",
            matched_risks=[
                RiskMatch(risk_id="atlas-fraud", risk_name="Fraud", relevance="primary", justification="j"),
            ],
            cross_mappings=[
                CrossMapping(
                    source_risk_id="atlas-fraud", target_risk_id="owasp-fraud",
                    target_risk_name="OWASP Fraud", target_taxonomy="owasp",
                    mapping_type="close",
                ),
            ],
        ),
        PolicyRiskMapping(
            policy_concept="Executive Compensation", policy_type="B",
            matched_risks=[
                RiskMatch(risk_id="atlas-data-disclosure", risk_name="Data Disclosure", relevance="primary", justification="j"),
            ],
            cross_mappings=[],
        ),
    ]
    domain_context = [
        DomainContextProfile(
            risk_id="atlas-fraud", risk_name="Fraud", policy_concept="Fraud",
            axes=[
                DomainContextAxis(
                    cco_class_uri="http://example.org/Person", cco_class_label="Person", role="agent",
                    enumerations=[
                        AxisEnumeration(class_uri="http://example.org/Employee", class_label="Employee", source_ontology="CCO", relevance="high"),
                    ],
                ),
            ],
        ),
    ]
    return classifications, risk_mappings, domain_context


def test_structure_taxonomy_has_correct_id():
    classifications, risk_mappings, domain_context = _make_state_data()
    taxonomy, profiles = structure("swb", classifications, risk_mappings, domain_context)
    assert taxonomy["taxonomies"][0]["id"] == "client-swb"
    assert taxonomy["taxonomies"][0]["type"] == "RiskTaxonomy"


def test_structure_creates_groups_per_policy_type():
    classifications, risk_mappings, domain_context = _make_state_data()
    taxonomy, _ = structure("swb", classifications, risk_mappings, domain_context)
    group_ids = {g["id"] for g in taxonomy["groups"]}
    assert "client-swb-safety" in group_ids  # type A
    assert "client-swb-confidentiality" in group_ids  # type B
    assert "client-swb-scope-regulatory" not in group_ids  # no type C policies
    assert "client-swb-routing" not in group_ids  # no type D policies


def test_structure_entries_have_correct_isPartOf():
    classifications, risk_mappings, domain_context = _make_state_data()
    taxonomy, _ = structure("swb", classifications, risk_mappings, domain_context)
    entries = taxonomy["entries"]
    fraud_entry = next(e for e in entries if "fraud" in e["id"])
    assert fraud_entry["isPartOf"] == "client-swb-safety"
    disclosure_entry = next(e for e in entries if "data-disclosure" in e["id"])
    assert disclosure_entry["isPartOf"] == "client-swb-confidentiality"


def test_structure_entries_have_cross_mappings():
    classifications, risk_mappings, domain_context = _make_state_data()
    taxonomy, _ = structure("swb", classifications, risk_mappings, domain_context)
    fraud_entry = next(e for e in taxonomy["entries"] if "fraud" in e["id"])
    assert "owasp-fraud" in fraud_entry.get("close_mappings", [])


def test_structure_filters_invalid_cross_mapping_targets():
    classifications, risk_mappings, domain_context = _make_state_data()
    # Only "owasp-fraud" is in the valid set; any other target would be filtered
    taxonomy, _ = structure("swb", classifications, risk_mappings, domain_context,
                            valid_risk_ids={"owasp-fraud"})
    fraud_entry = next(e for e in taxonomy["entries"] if "fraud" in e["id"])
    assert "owasp-fraud" in fraud_entry.get("close_mappings", [])


def test_structure_warns_on_unknown_cross_mapping_targets():
    classifications, risk_mappings, domain_context = _make_state_data()
    # Empty valid set means all cross-mappings are filtered
    taxonomy, _ = structure("swb", classifications, risk_mappings, domain_context,
                            valid_risk_ids=set())
    fraud_entry = next(e for e in taxonomy["entries"] if "fraud" in e["id"])
    assert "close_mappings" not in fraud_entry


def test_structure_no_validation_when_valid_ids_none():
    """When valid_risk_ids is None, all cross-mappings pass through (backwards compat)."""
    classifications, risk_mappings, domain_context = _make_state_data()
    taxonomy, _ = structure("swb", classifications, risk_mappings, domain_context,
                            valid_risk_ids=None)
    fraud_entry = next(e for e in taxonomy["entries"] if "fraud" in e["id"])
    assert "owasp-fraud" in fraud_entry.get("close_mappings", [])


def test_structure_profiles_output():
    classifications, risk_mappings, domain_context = _make_state_data()
    _, profiles = structure("swb", classifications, risk_mappings, domain_context)
    assert len(profiles["profiles"]) == 1
    assert profiles["profiles"][0]["risk_id"] == "atlas-fraud"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd refiner && uv run pytest tests/test_structure.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement structure.py**

```python
# src/refiner/stages/structure.py
import logging
import re

from refiner.models import (
    PolicyClassification,
    PolicyRiskMapping,
    DomainContextProfile,
)

logger = logging.getLogger(__name__)

POLICY_TYPE_GROUPS = {
    "A": ("safety", "Safety Policies"),
    "B": ("confidentiality", "Confidentiality Policies"),
    "C": ("scope-regulatory", "Scope & Regulatory Policies"),
    "D": ("routing", "Routing Policies"),
}


def slugify(text: str) -> str:
    slug = text.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug)
    return slug


def structure(
    client_slug: str,
    classifications: list[PolicyClassification],
    risk_mappings: list[PolicyRiskMapping],
    domain_context: list[DomainContextProfile],
    valid_risk_ids: set[str] | None = None,
) -> tuple[dict, dict]:
    taxonomy_id = f"client-{client_slug}"

    # Determine which policy types are present
    policy_types_present = {c.policy_type for c in classifications}

    # Build groups
    groups = []
    for ptype in sorted(policy_types_present):
        slug, name = POLICY_TYPE_GROUPS[ptype]
        groups.append({
            "id": f"{taxonomy_id}-{slug}",
            "name": name,
            "type": "RiskGroup",
            "isDefinedByTaxonomy": taxonomy_id,
        })

    # Build policy_concept -> policy_type lookup
    concept_to_type = {c.policy_concept: c.policy_type for c in classifications}

    # Build entries from risk mappings
    entries = []
    for mapping in risk_mappings:
        ptype = mapping.policy_type
        group_slug = POLICY_TYPE_GROUPS.get(ptype, ("unknown", "Unknown"))[0]
        group_id = f"{taxonomy_id}-{group_slug}"

        # Collect cross-mappings grouped by type
        cross_maps_by_type: dict[str, list[str]] = {}
        for cm in mapping.cross_mappings:
            key = f"{cm.mapping_type}_mappings"
            cross_maps_by_type.setdefault(key, []).append(cm.target_risk_id)

        for rm in mapping.matched_risks:
            entry = {
                "id": f"{taxonomy_id}-{slugify(rm.risk_name)}",
                "name": rm.risk_name,
                "type": "Risk",
                "isDefinedByTaxonomy": taxonomy_id,
                "isPartOf": group_id,
                "tag": slugify(rm.risk_name),
            }
            # Add cross-mappings for this risk's source
            for cm in mapping.cross_mappings:
                if cm.source_risk_id == rm.risk_id:
                    # Validate target exists if valid_risk_ids provided
                    if valid_risk_ids is not None and cm.target_risk_id not in valid_risk_ids:
                        logger.warning("Skipping unknown cross-mapping target: %s", cm.target_risk_id)
                        continue
                    key = f"{cm.mapping_type}_mappings"
                    entry.setdefault(key, []).append(cm.target_risk_id)
            entries.append(entry)

    taxonomy = {
        "taxonomies": [
            {
                "id": taxonomy_id,
                "name": f"Client {client_slug.upper()} Policy Taxonomy",
                "type": "RiskTaxonomy",
            },
        ],
        "groups": groups,
        "entries": entries,
    }

    # Build domain context profiles output
    profiles = {
        "profiles": [p.model_dump() for p in domain_context],
    }

    return taxonomy, profiles
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd refiner && uv run pytest tests/test_structure.py -v`
Expected: All 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add refiner/src/refiner/stages/structure.py refiner/tests/test_structure.py
git commit -m "feat(refiner): implement Stage 5 structure with LinkML-conformant output"
```

---

### Task 10: Pipeline Orchestration

**Files:**
- Create: `refiner/src/refiner/pipeline.py`
- Create: `refiner/tests/test_pipeline.py`

- [ ] **Step 1: Write pipeline tests**

```python
# tests/test_pipeline.py
from unittest.mock import patch, MagicMock
from refiner.models import (
    Policy,
    PolicyClassification,
    PolicyRiskMapping,
    RiskMatch,
    RiskVariationAxes,
    VariationAxis,
    DomainContextProfile,
    DomainContextAxis,
)
from refiner.pipeline import PipelineState, run_pipeline


def test_pipeline_threads_state(mock_client, mock_config, mock_risk_handlers, mock_onto_handlers):
    policies = [Policy(policy_concept="Fraud", concept_definition="About fraud")]

    classify_result = [
        PolicyClassification(
            policy_concept="Fraud", concept_definition="About fraud",
            policy_type="A", justification="j",
        ),
    ]
    map_result = (
        [PolicyRiskMapping(
            policy_concept="Fraud", policy_type="A",
            matched_risks=[RiskMatch(risk_id="r1", risk_name="R1", relevance="primary", justification="j")],
            cross_mappings=[],
        )],
        {"r1": {"id": "r1", "name": "R1", "description": "d", "concern": "c"}},
    )
    anchor_result = [
        RiskVariationAxes(
            risk_id="r1", risk_name="R1", policy_concept="Fraud",
            axes=[VariationAxis(cco_class_uri="http://ex/P", cco_class_label="P", role="agent", rationale="r")],
        ),
    ]
    context_result = [
        DomainContextProfile(
            risk_id="r1", risk_name="R1", policy_concept="Fraud",
            axes=[DomainContextAxis(cco_class_uri="http://ex/P", cco_class_label="P", role="agent", enumerations=[])],
        ),
    ]

    with patch("refiner.pipeline.classify", return_value=classify_result) as m_classify, \
         patch("refiner.pipeline.map_risks", return_value=map_result) as m_map, \
         patch("refiner.pipeline.anchor", return_value=anchor_result) as m_anchor, \
         patch("refiner.pipeline.contextualize", return_value=context_result) as m_ctx:

        state = run_pipeline(policies, mock_client, mock_config, mock_risk_handlers, mock_onto_handlers)

        assert state.classifications == classify_result
        assert state.risk_mappings == map_result[0]
        assert state.risk_details == map_result[1]
        assert state.variation_axes == anchor_result
        assert state.domain_context == context_result

        # Verify stage calls received correct inputs
        m_classify.assert_called_once_with(policies, mock_client, mock_config)
        m_map.assert_called_once_with(classify_result, mock_client, mock_config, mock_risk_handlers)
        m_anchor.assert_called_once_with(
            map_result[0], map_result[1], mock_client, mock_config, mock_onto_handlers
        )
        m_ctx.assert_called_once_with(anchor_result, mock_client, mock_config, mock_onto_handlers)


def test_pipeline_until_classify(mock_client, mock_config, mock_risk_handlers, mock_onto_handlers):
    policies = [Policy(policy_concept="Fraud", concept_definition="About fraud")]
    classify_result = [
        PolicyClassification(
            policy_concept="Fraud", concept_definition="About fraud",
            policy_type="A", justification="j",
        ),
    ]

    with patch("refiner.pipeline.classify", return_value=classify_result), \
         patch("refiner.pipeline.map_risks") as m_map:

        state = run_pipeline(
            policies, mock_client, mock_config, mock_risk_handlers, mock_onto_handlers,
            until="classify",
        )

        assert state.classifications is not None
        assert state.risk_mappings is None
        m_map.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd refiner && uv run pytest tests/test_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement pipeline.py**

```python
# src/refiner/pipeline.py
from dataclasses import dataclass, field

import instructor
from refiner.llm import LLMConfig
from refiner.models import (
    Policy,
    PolicyClassification,
    PolicyRiskMapping,
    RiskVariationAxes,
    DomainContextProfile,
)
from refiner.stages.classify import classify
from refiner.stages.map_risks import map_risks
from refiner.stages.anchor import anchor
from refiner.stages.contextualize import contextualize

STAGES = ("classify", "map_risks", "anchor", "contextualize")


@dataclass
class PipelineState:
    policies: list[Policy]
    classifications: list[PolicyClassification] | None = None
    risk_mappings: list[PolicyRiskMapping] | None = None
    risk_details: dict[str, dict] | None = None
    variation_axes: list[RiskVariationAxes] | None = None
    domain_context: list[DomainContextProfile] | None = None


def run_pipeline(
    policies: list[Policy],
    client: instructor.Instructor,
    config: LLMConfig,
    risk_handlers: dict,
    onto_handlers: dict,
    until: str | None = None,
) -> PipelineState:
    state = PipelineState(policies=policies)

    state.classifications = classify(state.policies, client, config)
    if until == "classify":
        return state

    state.risk_mappings, state.risk_details = map_risks(
        state.classifications, client, config, risk_handlers
    )
    if until == "map_risks":
        return state

    state.variation_axes = anchor(
        state.risk_mappings, state.risk_details, client, config, onto_handlers
    )
    if until == "anchor":
        return state

    state.domain_context = contextualize(
        state.variation_axes, client, config, onto_handlers
    )
    return state
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd refiner && uv run pytest tests/test_pipeline.py -v`
Expected: All 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add refiner/src/refiner/pipeline.py refiner/tests/test_pipeline.py
git commit -m "feat(refiner): implement pipeline orchestration with --until support"
```

---

### Task 11: CLI

**Files:**
- Create: `refiner/src/refiner/cli.py`
- Create: `refiner/tests/test_cli.py`

The CLI imports ontoquery and nexus-mcp to create handler dicts. For tests, we mock these imports and the pipeline.

- [ ] **Step 1: Write CLI tests**

```python
# tests/test_cli.py
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from typer.testing import CliRunner
from refiner.cli import app
from refiner.models import (
    Policy,
    PolicyClassification,
    PolicyRiskMapping,
    RiskVariationAxes,
    DomainContextProfile,
)
from refiner.pipeline import PipelineState

runner = CliRunner()


def _make_policy_file(tmp_path: Path) -> Path:
    policies = [
        {"policy_concept": "Fraud", "concept_definition": "About fraud"},
    ]
    p = tmp_path / "test.json"
    p.write_text(json.dumps(policies))
    return p


def _make_completed_state():
    state = PipelineState(
        policies=[Policy(policy_concept="Fraud", concept_definition="About fraud")],
        classifications=[
            PolicyClassification(
                policy_concept="Fraud", concept_definition="About fraud",
                policy_type="A", justification="j",
            ),
        ],
        risk_mappings=[
            PolicyRiskMapping(
                policy_concept="Fraud", policy_type="A",
                matched_risks=[], cross_mappings=[],
            ),
        ],
        risk_details={},
        variation_axes=[],
        domain_context=[],
    )
    return state


@patch("refiner.cli._create_risk_handlers")
@patch("refiner.cli._create_onto_handlers")
@patch("refiner.cli.create_client")
@patch("refiner.cli.run_pipeline")
def test_cli_run_full_pipeline(mock_run, mock_create_client, mock_onto, mock_risk, tmp_path):
    policy_file = _make_policy_file(tmp_path)
    mock_run.return_value = _make_completed_state()
    mock_create_client.return_value = MagicMock()
    mock_risk.return_value = {}
    mock_onto.return_value = {}

    result = runner.invoke(app, ["run", str(policy_file)], env={
        "REFINER_BASE_URL": "http://localhost:8000/v1",
        "REFINER_MODEL": "test-model",
    })
    assert result.exit_code == 0, result.output
    mock_run.assert_called_once()


@patch("refiner.cli._create_risk_handlers")
@patch("refiner.cli._create_onto_handlers")
@patch("refiner.cli.create_client")
@patch("refiner.cli.run_pipeline")
def test_cli_run_with_until(mock_run, mock_create_client, mock_onto, mock_risk, tmp_path):
    policy_file = _make_policy_file(tmp_path)
    state = _make_completed_state()
    state.risk_mappings = None
    mock_run.return_value = state
    mock_create_client.return_value = MagicMock()
    mock_risk.return_value = {}
    mock_onto.return_value = {}

    result = runner.invoke(app, ["run", "--until", "classify", str(policy_file)], env={
        "REFINER_BASE_URL": "http://localhost:8000/v1",
        "REFINER_MODEL": "test-model",
    })
    assert result.exit_code == 0, result.output
    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs.get("until") == "classify"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd refiner && uv run pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement cli.py**

```python
# src/refiner/cli.py
import json
import os
import sys
from pathlib import Path

import typer
import yaml

from refiner.llm import LLMConfig, create_client
from refiner.models import Policy
from refiner.pipeline import run_pipeline, STAGES
from refiner.stages.structure import structure

app = typer.Typer()


def _create_risk_handlers() -> dict:
    from nexus_mcp.server import create_tool_handlers
    from nexus_mcp.risk_index import RiskIndex
    nexus_base_dir = os.environ.get("NEXUS_BASE_DIR")
    if not nexus_base_dir:
        typer.echo("Error: NEXUS_BASE_DIR environment variable must be set", err=True)
        raise typer.Exit(1)
    from ai_atlas_nexus import AIAtlasNexus
    nexus = AIAtlasNexus(base_dir=nexus_base_dir)
    all_risks = nexus.get_all_risks()
    risks_by_id = {r.id: r for r in all_risks}
    all_actions = nexus.get_all_actions()
    actions_by_id = {a.id: a for a in all_actions}
    taxonomies = nexus.get_all_taxonomies()
    groups = nexus.get_all("groups")
    chroma_dir = Path(os.environ.get("NEXUS_CHROMA_DIR", ".chroma"))
    chroma_dir.mkdir(parents=True, exist_ok=True)
    idx = RiskIndex(chroma_dir)
    if idx.needs_reindex(len(all_risks)):
        idx.index_risks(all_risks)
    return create_tool_handlers(
        risk_index=idx, risks_by_id=risks_by_id, actions_by_id=actions_by_id,
        taxonomies=taxonomies, groups=groups,
    )


def _create_onto_handlers() -> dict:
    from ontoquery.mcp_server import create_tool_handlers
    chroma_dir = Path(os.environ.get("ONTOQUERY_CHROMA_DIR", ".chroma"))
    return create_tool_handlers(chroma_dir)


@app.command()
def run(
    policy_json: Path = typer.Argument(..., help="Path to policy JSON file"),
    until: str = typer.Option(None, "--until", help=f"Run up to this stage: {', '.join(STAGES)}"),
    output_dir: Path = typer.Option(None, "--output", "-o", help="Output directory (default: current dir)"),
):
    """Run the refiner pipeline on a policy JSON file."""
    if not policy_json.exists():
        typer.echo(f"Error: {policy_json} does not exist", err=True)
        raise typer.Exit(1)

    if until and until not in STAGES:
        typer.echo(f"Error: --until must be one of: {', '.join(STAGES)}", err=True)
        raise typer.Exit(1)

    # Load policies
    raw = json.loads(policy_json.read_text())
    policies = [Policy(**p) for p in raw]
    typer.echo(f"Loaded {len(policies)} policies from {policy_json.name}")

    # Config from environment
    base_url = os.environ.get("REFINER_BASE_URL")
    model = os.environ.get("REFINER_MODEL")
    if not base_url or not model:
        typer.echo("Error: REFINER_BASE_URL and REFINER_MODEL must be set", err=True)
        raise typer.Exit(1)

    config = LLMConfig(base_url=base_url, model=model)
    client = create_client(config)

    # Create handlers
    risk_handlers = _create_risk_handlers()
    onto_handlers = _create_onto_handlers()

    # Run pipeline
    typer.echo(f"Running pipeline{f' until {until}' if until else ''}...")
    state = run_pipeline(policies, client, config, risk_handlers, onto_handlers, until=until)

    # Output
    out = output_dir or Path(".")
    out.mkdir(parents=True, exist_ok=True)
    client_slug = policy_json.stem

    if state.domain_context is not None and state.classifications is not None and state.risk_mappings is not None:
        # Collect valid nexus risk IDs for cross-mapping validation
        valid_ids = set(state.risk_details.keys()) if state.risk_details else None
        taxonomy, profiles = structure(
            client_slug, state.classifications, state.risk_mappings, state.domain_context,
            valid_risk_ids=valid_ids,
        )
        tax_path = out / f"{client_slug}-taxonomy.yaml"
        tax_path.write_text(yaml.dump(taxonomy, default_flow_style=False, sort_keys=False))
        typer.echo(f"Taxonomy written to {tax_path}")

        prof_path = out / f"{client_slug}-domain-context.yaml"
        prof_path.write_text(yaml.dump(profiles, default_flow_style=False, sort_keys=False))
        typer.echo(f"Domain context written to {prof_path}")
    else:
        # Partial run — dump intermediate state as JSON
        state_path = out / f"{client_slug}-state.json"
        state_data = {
            "policies": [p.model_dump() for p in state.policies],
        }
        if state.classifications:
            state_data["classifications"] = [c.model_dump() for c in state.classifications]
        if state.risk_mappings:
            state_data["risk_mappings"] = [m.model_dump() for m in state.risk_mappings]
        if state.risk_details:
            state_data["risk_details"] = state.risk_details
        if state.variation_axes:
            state_data["variation_axes"] = [a.model_dump() for a in state.variation_axes]
        state_path.write_text(json.dumps(state_data, indent=2))
        typer.echo(f"Intermediate state written to {state_path}")


if __name__ == "__main__":
    app()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd refiner && uv run pytest tests/test_cli.py -v`
Expected: All 2 tests PASS.

- [ ] **Step 5: Run full test suite**

Run: `cd refiner && uv run pytest -v`
Expected: All tests PASS (approx. 40 tests).

- [ ] **Step 6: Commit**

```bash
git add refiner/src/refiner/cli.py refiner/tests/test_cli.py
git commit -m "feat(refiner): implement CLI with run command and --until support"
```
