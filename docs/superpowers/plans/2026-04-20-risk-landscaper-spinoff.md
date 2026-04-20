# Risk Landscaper Spin-off Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract ontology-independent pipeline stages (ingest, domain detection, map_risks, build_landscape) into a standalone `risk-landscaper` sub-project, then modify refiner to consume its output.

**Architecture:** Move & Decouple — stage code moves from refiner to risk-landscaper. The two projects communicate exclusively through a `risk-landscape.yaml` artifact. Each project owns its own Pydantic models. risk-landscaper depends on nexus-mcp (sibling) but NOT ontoquery.

**Tech Stack:** Python 3.11+, uv, hatchling, instructor, openai, pydantic, typer, pyyaml, nexus-mcp

---

## File Structure

### Files to create

| File | Responsibility |
|------|---------------|
| `risk-landscaper/pyproject.toml` | uv project config, dependencies, CLI entry point |
| `risk-landscaper/src/risk_landscaper/__init__.py` | Package marker |
| `risk-landscaper/src/risk_landscaper/models.py` | All Pydantic models (policy, risk, landscape) |
| `risk-landscaper/src/risk_landscaper/llm.py` | LLMConfig, TokenTracker, create_client |
| `risk-landscaper/src/risk_landscaper/debug.py` | Debug logging (simplified from refiner — no MLflow) |
| `risk-landscaper/src/risk_landscaper/nexus_adapter.py` | Nexus-format detection + risk→policy projection |
| `risk-landscaper/src/risk_landscaper/stages/__init__.py` | Package marker |
| `risk-landscaper/src/risk_landscaper/stages/ingest.py` | Policy decomposition (3-pass LLM extraction) |
| `risk-landscaper/src/risk_landscaper/stages/detect_domain.py` | Simplified domain detection from fixed menu |
| `risk-landscaper/src/risk_landscaper/stages/map_risks.py` | Risk identification via nexus-mcp semantic search |
| `risk-landscaper/src/risk_landscaper/stages/build_landscape.py` | Landscape assembly (pure data transformation) |
| `risk-landscaper/src/risk_landscaper/templates/ingest_cot.json` | Chain-of-thought examples for ingest prompts |
| `risk-landscaper/src/risk_landscaper/cli.py` | Typer CLI with single `run` command |
| `risk-landscaper/tests/__init__.py` | Package marker |
| `risk-landscaper/tests/conftest.py` | Shared fixtures (mock_client, mock_config, mock_risk_handlers) |
| `risk-landscaper/tests/test_models.py` | Model validation tests |
| `risk-landscaper/tests/test_detect_domain.py` | Domain detection tests |
| `risk-landscaper/tests/test_ingest.py` | Ingest stage tests (migrated from refiner) |
| `risk-landscaper/tests/test_map_risks.py` | Risk mapping tests (migrated from refiner) |
| `risk-landscaper/tests/test_build_landscape.py` | Landscape assembly tests (migrated from refiner) |
| `risk-landscaper/tests/test_nexus_adapter.py` | Nexus adapter tests (migrated from refiner) |
| `risk-landscaper/tests/test_cli.py` | CLI integration tests |

### Files to modify

| File | Change |
|------|--------|
| `refiner/src/refiner/pipeline.py` | Add `--landscape` path support, skip early stages when provided |
| `refiner/src/refiner/cli.py` | Add `--landscape` option to `run` command |
| `scripts/run_battery.py` | Split ingest into risk-landscaper call, pass landscape to refiner |

### Files to delete from refiner (after risk-landscaper is working)

| File | Reason |
|------|--------|
| `refiner/src/refiner/stages/ingest.py` | Moved to risk-landscaper |
| `refiner/src/refiner/stages/identify_domains.py` | Replaced by detect_domain in risk-landscaper |
| `refiner/src/refiner/stages/map_risks.py` | Moved to risk-landscaper |
| `refiner/src/refiner/stages/build_landscape.py` | Moved to risk-landscaper |
| `refiner/src/refiner/nexus_adapter.py` | Moved to risk-landscaper |
| `refiner/tests/test_ingest.py` | Moved to risk-landscaper |
| `refiner/tests/test_map_risks.py` | Moved to risk-landscaper |
| `refiner/tests/test_build_landscape.py` | Moved to risk-landscaper |
| `refiner/tests/test_nexus_adapter.py` | Moved to risk-landscaper |
| `refiner/tests/test_models_ingest.py` | Covered by risk-landscaper tests |

---

### Task 1: Project scaffolding and models

**Files:**
- Create: `risk-landscaper/pyproject.toml`
- Create: `risk-landscaper/src/risk_landscaper/__init__.py`
- Create: `risk-landscaper/src/risk_landscaper/models.py`
- Create: `risk-landscaper/src/risk_landscaper/stages/__init__.py`
- Test: `risk-landscaper/tests/test_models.py`

- [ ] **Step 1: Create project directories**

```bash
mkdir -p risk-landscaper/src/risk_landscaper/stages
mkdir -p risk-landscaper/src/risk_landscaper/templates
mkdir -p risk-landscaper/tests
```

- [ ] **Step 2: Create pyproject.toml**

```toml
[project]
name = "risk-landscaper"
version = "0.1.0"
description = "Policy-driven risk landscape generation using AI Atlas Nexus"
requires-python = ">=3.11"
dependencies = [
    "instructor>=1.0",
    "openai>=1.0",
    "pydantic>=2.0",
    "typer>=0.12",
    "pyyaml>=6.0",
    "nexus-mcp",
]

[project.scripts]
risk-landscaper = "risk_landscaper.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/risk_landscaper"]

[tool.hatch.metadata]
allow-direct-references = true

[tool.pytest.ini_options]
testpaths = ["tests"]

[dependency-groups]
dev = ["pytest>=8.0"]

[tool.uv.sources]
nexus-mcp = { path = "../nexus-mcp", editable = true }
```

- [ ] **Step 3: Create `__init__.py` files**

`risk-landscaper/src/risk_landscaper/__init__.py` — empty file.

`risk-landscaper/src/risk_landscaper/stages/__init__.py` — empty file.

`risk-landscaper/tests/__init__.py` — empty file.

- [ ] **Step 4: Create models.py**

Copy the relevant models from `refiner/src/refiner/models.py`. Include only the models needed for stages 1-3 (not anchor/contextualize models like `VariationAxis`, `DomainContext`, etc.).

Models to include:
- `BoundaryExample`, `NamedEntity`
- `Stakeholder`, `AiSystem`, `GovernedSystem` (alias), `RegulatoryReference`
- `PolicyDecomposition`, `Policy`, `PolicyProfile`
- `RiskMatch`, `PolicyRiskMapping`, `CoverageGap`
- `PolicySourceRef`, `KnowledgeBaseRef`, `RiskDetail`, `WeakMatch`, `RiskLandscape`
- `RunReport` (dataclass)

Source: `refiner/src/refiner/models.py` — copy lines 1-189 plus `RunReport` (lines 275-295). Update the `RunReport` class to remove `token_usage` references to models not present.

- [ ] **Step 5: Write model tests**

Create `risk-landscaper/tests/test_models.py`:

```python
from risk_landscaper.models import (
    Policy,
    PolicyProfile,
    PolicyDecomposition,
    BoundaryExample,
    Stakeholder,
    AiSystem,
    RiskMatch,
    PolicyRiskMapping,
    RiskDetail,
    RiskLandscape,
    CoverageGap,
    RunReport,
)


def test_policy_profile_round_trip():
    profile = PolicyProfile(
        organization=Stakeholder(name="Acme Corp"),
        domain="finance",
        policies=[
            Policy(
                policy_concept="Fraud",
                concept_definition="Do not assist with fraud",
            ),
        ],
    )
    data = profile.model_dump()
    restored = PolicyProfile(**data)
    assert restored.organization.name == "Acme Corp"
    assert len(restored.policies) == 1


def test_policy_profile_coerce_organization_string():
    profile = PolicyProfile(organization="Acme Corp")
    assert profile.organization.name == "Acme Corp"


def test_policy_profile_migrate_governed_systems():
    data = {"governed_systems": [{"name": "ChatBot"}], "policies": []}
    profile = PolicyProfile(**data)
    assert len(profile.ai_systems) == 1
    assert profile.ai_systems[0].name == "ChatBot"


def test_risk_landscape_serialization():
    landscape = RiskLandscape(
        model="test-model",
        risks=[
            RiskDetail(
                risk_id="atlas-1",
                risk_name="Test Risk",
                risk_framework="IBM Risk Atlas",
            ),
        ],
        policy_mappings=[
            PolicyRiskMapping(
                policy_concept="Fraud",
                matched_risks=[
                    RiskMatch(
                        risk_id="atlas-1",
                        risk_name="Test Risk",
                        relevance="primary",
                        justification="Direct match",
                    ),
                ],
            ),
        ],
    )
    data = landscape.model_dump()
    assert data["risks"][0]["risk_id"] == "atlas-1"
    restored = RiskLandscape(**data)
    assert len(restored.risks) == 1


def test_coverage_gap_creation():
    gap = CoverageGap(
        policy_concept="Novel Risk",
        concept_definition="Something new",
        gap_type="novel",
        confidence=0.85,
        nearest_risks=[{"id": "atlas-1", "name": "Similar", "distance": 0.7}],
        reasoning="No existing risk covers this",
    )
    assert gap.gap_type == "novel"
    assert gap.confidence == 0.85


def test_run_report_to_dict():
    report = RunReport(model="test", policy_set="test.json", timestamp="2026-01-01")
    report.stages_completed.append("ingest")
    d = report.to_dict()
    assert d["stages_completed"] == ["ingest"]
```

- [ ] **Step 6: Run uv sync and tests**

```bash
cd risk-landscaper && uv sync
uv run pytest tests/test_models.py -v
```

Expected: all 6 tests pass.

- [ ] **Step 7: Commit**

```bash
git add risk-landscaper/
git commit -m "feat(risk-landscaper): scaffold project with models"
```

---

### Task 2: LLM infrastructure and debug module

**Files:**
- Create: `risk-landscaper/src/risk_landscaper/llm.py`
- Create: `risk-landscaper/src/risk_landscaper/debug.py`
- Create: `risk-landscaper/tests/conftest.py`

- [ ] **Step 1: Create llm.py**

Copy from `refiner/src/refiner/llm.py` (78 lines). Change nothing — the module is self-contained. The full content:

```python
import threading
from dataclasses import dataclass, field

import instructor
from openai import OpenAI


@dataclass
class LLMConfig:
    base_url: str
    model: str
    api_key: str = "none"
    temperature: float = 0.3
    max_retries: int = 3
    max_tokens: int = 8192
    max_concurrent: int = 1


@dataclass
class TokenTracker:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    calls: int = 0
    per_stage: dict[str, dict[str, int]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, usage, stage: str | None = None) -> None:
        if usage is None:
            return
        pt = getattr(usage, "prompt_tokens", 0) or 0
        ct = getattr(usage, "completion_tokens", 0) or 0
        tt = getattr(usage, "total_tokens", 0) or 0
        with self._lock:
            self.prompt_tokens += pt
            self.completion_tokens += ct
            self.total_tokens += tt
            self.calls += 1
            if stage:
                s = self.per_stage.setdefault(stage, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "calls": 0})
                s["prompt_tokens"] += pt
                s["completion_tokens"] += ct
                s["total_tokens"] += tt
                s["calls"] += 1

    def to_dict(self) -> dict:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "calls": self.calls,
            "per_stage": dict(self.per_stage),
        }


def create_client(
    config: LLMConfig,
    tracker: TokenTracker | None = None,
) -> instructor.Instructor:
    client = instructor.from_openai(
        OpenAI(base_url=config.base_url, api_key=config.api_key),
        mode=instructor.Mode.JSON,
    )
    if tracker is not None:
        _wrap_with_tracking(client, tracker)
    return client


def _wrap_with_tracking(client: instructor.Instructor, tracker: TokenTracker) -> None:
    original_create = client.chat.completions.create

    def tracked_create(**kwargs):
        result, completion = client.chat.completions.create_with_completion(**kwargs)
        tracker.add(getattr(completion, "usage", None))
        return result

    client.chat.completions.create = tracked_create
```

- [ ] **Step 2: Create debug.py**

Simplified version of `refiner/src/refiner/debug.py` — keep `configure()`, `log_call()`, and `log_event()`. Drop MLflow tracing and markdown rendering (risk-landscaper doesn't need them).

```python
import json
import logging
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

_call_counter = 0
_counter_lock = threading.Lock()
_debug_dir: Path | None = None


def configure(debug_dir: Path | None) -> None:
    global _debug_dir, _call_counter
    _debug_dir = debug_dir
    _call_counter = 0
    if _debug_dir:
        _debug_dir.mkdir(parents=True, exist_ok=True)


def log_call(
    stage: str,
    messages: list[dict],
    response,
    *,
    context: dict | None = None,
) -> None:
    global _call_counter
    with _counter_lock:
        _call_counter += 1
        call_num = _call_counter

    slug = ""
    if context:
        for key in ("policy_concept", "risk_name", "risk_id"):
            if key in context:
                slug = "-" + context[key].lower().replace(" ", "-").replace("/", "-")[:40]
                break

    if _debug_dir is not None:
        if hasattr(response, "model_dump"):
            response_data = response.model_dump()
        elif isinstance(response, list):
            response_data = [r.model_dump() if hasattr(r, "model_dump") else r for r in response]
        else:
            response_data = str(response)

        entry = {
            "call_number": call_num,
            "stage": stage,
            "messages": messages,
            "response": response_data,
        }
        if context:
            entry["context"] = context

        filename = f"{call_num:02d}-{stage}{slug}.json"
        path = _debug_dir / filename
        path.write_text(json.dumps(entry, indent=2, default=str))
        logger.debug("Debug log written to %s", path)


def log_event(
    stage: str,
    data: dict,
    *,
    context: dict | None = None,
) -> None:
    global _call_counter
    with _counter_lock:
        _call_counter += 1
        call_num = _call_counter

    slug = ""
    if context:
        for key in ("policy_concept", "risk_name", "risk_id"):
            if key in context:
                slug = "-" + context[key].lower().replace(" ", "-").replace("/", "-")[:40]
                break

    if _debug_dir is not None:
        entry = {
            "call_number": call_num,
            "stage": stage,
            "messages": [],
            "response": data,
        }
        if context:
            entry["context"] = context

        filename = f"{call_num:02d}-{stage}{slug}.json"
        path = _debug_dir / filename
        path.write_text(json.dumps(entry, indent=2, default=str))
        logger.debug("Debug event written to %s", path)
```

- [ ] **Step 3: Create conftest.py**

```python
import pytest
from unittest.mock import MagicMock
from risk_landscaper.llm import LLMConfig


@pytest.fixture
def mock_config():
    return LLMConfig(base_url="http://localhost:8000/v1", model="test-model")


@pytest.fixture
def mock_client():
    client = MagicMock()
    return client


@pytest.fixture
def mock_risk_handlers():
    return {
        "search_risks": MagicMock(return_value=[]),
        "get_risk_details": MagicMock(return_value=None),
        "get_related_risks": MagicMock(return_value=[]),
        "get_related_actions": MagicMock(return_value=[]),
    }
```

- [ ] **Step 4: Run uv sync**

```bash
cd risk-landscaper && uv sync
uv run pytest tests/test_models.py -v
```

Expected: existing model tests still pass.

- [ ] **Step 5: Commit**

```bash
git add risk-landscaper/src/risk_landscaper/llm.py risk-landscaper/src/risk_landscaper/debug.py risk-landscaper/tests/conftest.py
git commit -m "feat(risk-landscaper): add LLM infrastructure and debug module"
```

---

### Task 3: Ingest stage

**Files:**
- Create: `risk-landscaper/src/risk_landscaper/stages/ingest.py`
- Copy: `risk-landscaper/src/risk_landscaper/templates/ingest_cot.json` (from `refiner/src/refiner/templates/ingest_cot.json`)
- Create: `risk-landscaper/tests/test_ingest.py`

- [ ] **Step 1: Copy the ingest CoT template**

```bash
cp refiner/src/refiner/templates/ingest_cot.json risk-landscaper/src/risk_landscaper/templates/ingest_cot.json
```

- [ ] **Step 2: Create ingest.py**

Copy from `refiner/src/refiner/stages/ingest.py` (471 lines). Update imports:

- `from refiner.llm import LLMConfig` → `from risk_landscaper.llm import LLMConfig`
- `from refiner.models import (...)` → `from risk_landscaper.models import (...)`
- `from refiner import debug` → `from risk_landscaper import debug`

The `RunReport` import comes from `risk_landscaper.models`.

No other code changes needed — the module is self-contained.

- [ ] **Step 3: Migrate ingest tests**

Copy `refiner/tests/test_ingest.py` to `risk-landscaper/tests/test_ingest.py`. Update all imports:

- `from refiner.models import ...` → `from risk_landscaper.models import ...`
- `from refiner.stages.ingest import ...` → `from risk_landscaper.stages.ingest import ...`

- [ ] **Step 4: Run tests**

```bash
cd risk-landscaper && uv run pytest tests/test_ingest.py -v
```

Expected: all 15 ingest tests pass.

- [ ] **Step 5: Commit**

```bash
git add risk-landscaper/src/risk_landscaper/stages/ingest.py risk-landscaper/src/risk_landscaper/templates/ risk-landscaper/tests/test_ingest.py
git commit -m "feat(risk-landscaper): add ingest stage"
```

---

### Task 4: detect_domain stage (new)

**Files:**
- Create: `risk-landscaper/src/risk_landscaper/stages/detect_domain.py`
- Create: `risk-landscaper/tests/test_detect_domain.py`

- [ ] **Step 1: Write detect_domain tests**

```python
from unittest.mock import MagicMock
from risk_landscaper.models import Policy, PolicyProfile, RunReport
from risk_landscaper.stages.detect_domain import (
    detect_domain,
    normalize_domain,
    DOMAIN_MENU,
    _DomainDetection,
)


def _make_report():
    return RunReport(model="test", policy_set="test", timestamp="2026-01-01")


def test_normalize_domain_exact_match():
    assert normalize_domain("healthcare") == "healthcare"
    assert normalize_domain("financial_services") == "financial_services"


def test_normalize_domain_case_insensitive():
    assert normalize_domain("Healthcare") == "healthcare"
    assert normalize_domain("ENERGY") == "energy"


def test_normalize_domain_partial_match():
    assert normalize_domain("banking and finance") == "financial_services"
    assert normalize_domain("medical") == "healthcare"


def test_normalize_domain_unknown():
    assert normalize_domain("underwater basket weaving") == "general"


def test_detect_domain_uses_profile_domain_when_set():
    profile = PolicyProfile(
        domain="healthcare",
        policies=[Policy(policy_concept="Test", concept_definition="Test def")],
    )
    client = MagicMock()
    from risk_landscaper.llm import LLMConfig
    config = LLMConfig(base_url="http://localhost:8000/v1", model="test")
    result = detect_domain(profile, client, config)
    assert result == ["healthcare"]
    client.chat.completions.create.assert_not_called()


def test_detect_domain_calls_llm_when_no_domain(mock_client, mock_config):
    profile = PolicyProfile(
        policies=[Policy(policy_concept="Fraud", concept_definition="Do not assist with fraud")],
    )
    mock_client.chat.completions.create.return_value = _DomainDetection(domain="financial_services")
    result = detect_domain(profile, mock_client, mock_config)
    assert result == ["financial_services"]
    mock_client.chat.completions.create.assert_called_once()


def test_detect_domain_normalizes_llm_output(mock_client, mock_config):
    profile = PolicyProfile(
        policies=[Policy(policy_concept="Treatment", concept_definition="Medical treatment policy")],
    )
    mock_client.chat.completions.create.return_value = _DomainDetection(domain="Healthcare")
    result = detect_domain(profile, mock_client, mock_config)
    assert result == ["healthcare"]


def test_detect_domain_falls_back_to_general(mock_client, mock_config):
    profile = PolicyProfile(
        policies=[Policy(policy_concept="Test", concept_definition="Test")],
    )
    mock_client.chat.completions.create.return_value = _DomainDetection(domain="alien_technology")
    result = detect_domain(profile, mock_client, mock_config)
    assert result == ["general"]


def test_detect_domain_emits_report_events(mock_client, mock_config):
    profile = PolicyProfile(
        domain="energy",
        policies=[Policy(policy_concept="Test", concept_definition="Test")],
    )
    report = _make_report()
    detect_domain(profile, mock_client, mock_config, report=report)
    events = [e for e in report.events if e["event"] == "domain_detected"]
    assert len(events) == 1
    assert events[0]["domain"] == "energy"
    assert events[0]["source"] == "profile"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd risk-landscaper && uv run pytest tests/test_detect_domain.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'risk_landscaper.stages.detect_domain'`

- [ ] **Step 3: Implement detect_domain.py**

```python
import logging

import instructor
from pydantic import BaseModel

from risk_landscaper.llm import LLMConfig
from risk_landscaper.models import PolicyProfile, RunReport
from risk_landscaper import debug

logger = logging.getLogger(__name__)

DOMAIN_MENU = {
    "healthcare": ["health", "medical", "clinical", "hospital", "patient", "pharma", "biomedical"],
    "financial_services": ["finance", "banking", "insurance", "investment", "trading", "loan", "credit"],
    "energy": ["energy", "oil", "gas", "power", "utility", "renewable", "petroleum"],
    "government": ["government", "public sector", "defense", "military", "intelligence", "civic"],
    "legal": ["legal", "law", "compliance", "regulatory", "judicial", "litigation"],
    "manufacturing": ["manufacturing", "industrial", "supply chain", "logistics", "engineering"],
    "technology": ["technology", "software", "cyber", "data", "cloud", "ai", "computing"],
    "education": ["education", "academic", "university", "school", "training", "research"],
    "general": [],
}

SYSTEM_PROMPT = """\
You are detecting the primary industry domain of a set of client content policies.

Given the policies below, identify the single most relevant domain from this list:
{domain_list}

Return just the domain key. If none fits well, return "general"."""


class _DomainDetection(BaseModel):
    domain: str


def normalize_domain(raw: str) -> str:
    lower = raw.lower().strip()
    if lower in DOMAIN_MENU:
        return lower
    for domain, keywords in DOMAIN_MENU.items():
        if domain == "general":
            continue
        for kw in keywords:
            if kw in lower:
                return domain
    return "general"


def detect_domain(
    profile: PolicyProfile,
    client: instructor.Instructor,
    config: LLMConfig,
    report: RunReport | None = None,
) -> list[str]:
    if profile.domain:
        normalized = normalize_domain(profile.domain)
        logger.info("Domain from profile: %s (normalized: %s)", profile.domain, normalized)
        if report:
            report.events.append({
                "stage": "detect_domain",
                "event": "domain_detected",
                "domain": normalized,
                "source": "profile",
            })
        return [normalized]

    if not profile.policies:
        if report:
            report.events.append({
                "stage": "detect_domain",
                "event": "domain_detected",
                "domain": "general",
                "source": "default",
            })
        return ["general"]

    domain_list = "\n".join(f"- {key}" for key in DOMAIN_MENU if key != "general")
    system_content = SYSTEM_PROMPT.format(domain_list=domain_list)

    policy_lines = [f"- {p.policy_concept}: {p.concept_definition}" for p in profile.policies]
    user_content = "Policies:\n\n" + "\n".join(policy_lines)

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]
    result = client.chat.completions.create(
        model=config.model,
        response_model=_DomainDetection,
        messages=messages,
        temperature=config.temperature,
        max_retries=config.max_retries,
        max_tokens=config.max_tokens,
    )
    debug.log_call("detect_domain", messages, result)

    normalized = normalize_domain(result.domain)
    logger.info("Detected domain: %s (raw: %s, normalized: %s)", result.domain, result.domain, normalized)

    if report:
        report.events.append({
            "stage": "detect_domain",
            "event": "domain_detected",
            "domain": normalized,
            "source": "llm",
            "raw": result.domain,
        })

    return [normalized]
```

- [ ] **Step 4: Run tests**

```bash
cd risk-landscaper && uv run pytest tests/test_detect_domain.py -v
```

Expected: all 9 tests pass.

- [ ] **Step 5: Commit**

```bash
git add risk-landscaper/src/risk_landscaper/stages/detect_domain.py risk-landscaper/tests/test_detect_domain.py
git commit -m "feat(risk-landscaper): add detect_domain stage"
```

---

### Task 5: map_risks stage

**Files:**
- Create: `risk-landscaper/src/risk_landscaper/stages/map_risks.py`
- Create: `risk-landscaper/tests/test_map_risks.py`

- [ ] **Step 1: Create map_risks.py**

Copy from `refiner/src/refiner/stages/map_risks.py` (424 lines). Update imports:

- `from refiner.llm import LLMConfig` → `from risk_landscaper.llm import LLMConfig`
- `from refiner.models import (...)` → `from risk_landscaper.models import (...)`
- `from refiner import debug` → `from risk_landscaper import debug`

No other code changes needed.

- [ ] **Step 2: Migrate map_risks tests**

Copy `refiner/tests/test_map_risks.py` to `risk-landscaper/tests/test_map_risks.py`. Update all imports:

- `from refiner.models import ...` → `from risk_landscaper.models import ...`
- `from refiner.stages.map_risks import ...` → `from risk_landscaper.stages.map_risks import ...`

- [ ] **Step 3: Run tests**

```bash
cd risk-landscaper && uv run pytest tests/test_map_risks.py -v
```

Expected: all 35 map_risks tests pass.

- [ ] **Step 4: Commit**

```bash
git add risk-landscaper/src/risk_landscaper/stages/map_risks.py risk-landscaper/tests/test_map_risks.py
git commit -m "feat(risk-landscaper): add map_risks stage"
```

---

### Task 6: build_landscape stage

**Files:**
- Create: `risk-landscaper/src/risk_landscaper/stages/build_landscape.py`
- Create: `risk-landscaper/tests/test_build_landscape.py`

- [ ] **Step 1: Create build_landscape.py**

Copy from `refiner/src/refiner/stages/build_landscape.py` (109 lines). Update imports:

- `from refiner.models import (...)` → `from risk_landscaper.models import (...)`

No other code changes needed — this module has no LLM or debug dependencies.

- [ ] **Step 2: Migrate build_landscape tests**

Copy `refiner/tests/test_build_landscape.py` to `risk-landscaper/tests/test_build_landscape.py`. Update all imports:

- `from refiner.models import ...` → `from risk_landscaper.models import ...`
- `from refiner.stages.build_landscape import ...` → `from risk_landscaper.stages.build_landscape import ...`

- [ ] **Step 3: Run tests**

```bash
cd risk-landscaper && uv run pytest tests/test_build_landscape.py -v
```

Expected: all 8 build_landscape tests pass.

- [ ] **Step 4: Commit**

```bash
git add risk-landscaper/src/risk_landscaper/stages/build_landscape.py risk-landscaper/tests/test_build_landscape.py
git commit -m "feat(risk-landscaper): add build_landscape stage"
```

---

### Task 7: Nexus adapter

**Files:**
- Create: `risk-landscaper/src/risk_landscaper/nexus_adapter.py`
- Create: `risk-landscaper/tests/test_nexus_adapter.py`

- [ ] **Step 1: Create nexus_adapter.py**

Copy from `refiner/src/refiner/nexus_adapter.py` (138 lines). Update imports:

- `from refiner.models import (...)` → `from risk_landscaper.models import (...)`

No other code changes needed.

- [ ] **Step 2: Migrate nexus_adapter tests**

Copy `refiner/tests/test_nexus_adapter.py` (if it exists) to `risk-landscaper/tests/test_nexus_adapter.py`. Update imports. If no test file exists, create basic tests:

```python
from risk_landscaper.nexus_adapter import (
    detect_nexus_format,
    project_risk_to_policy,
    nexus_to_policy_profile,
)


def test_detect_nexus_format_with_risks():
    assert detect_nexus_format({"risks": [{"id": "r1"}]}) is True


def test_detect_nexus_format_with_policies():
    assert detect_nexus_format({"policies": []}) is False


def test_detect_nexus_format_with_list():
    assert detect_nexus_format([{"policy_concept": "test"}]) is False


def test_project_risk_to_policy():
    risk = {"name": "Data Leakage", "concern": "Sensitive data exposed", "description": "Desc"}
    policy = project_risk_to_policy(risk)
    assert policy.policy_concept == "Data Leakage"
    assert policy.concept_definition == "Sensitive data exposed"


def test_project_risk_to_policy_fallback_to_description():
    risk = {"name": "Data Leakage", "description": "Desc"}
    policy = project_risk_to_policy(risk)
    assert policy.concept_definition == "Desc"


def test_nexus_to_policy_profile_basic():
    payload = {
        "ai_system": {
            "name": "ChatBot",
            "isDevelopedBy": "Acme",
            "isAppliedWithinDomain": "finance",
        },
        "risks": [
            {"name": "Bias", "concern": "Unfair outcomes"},
        ],
    }
    profile = nexus_to_policy_profile(payload)
    assert profile.organization.name == "Acme"
    assert profile.domain == "finance"
    assert len(profile.policies) == 1
    assert profile.policies[0].policy_concept == "Bias"
```

- [ ] **Step 3: Run tests**

```bash
cd risk-landscaper && uv run pytest tests/test_nexus_adapter.py -v
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add risk-landscaper/src/risk_landscaper/nexus_adapter.py risk-landscaper/tests/test_nexus_adapter.py
git commit -m "feat(risk-landscaper): add nexus adapter"
```

---

### Task 8: CLI

**Files:**
- Create: `risk-landscaper/src/risk_landscaper/cli.py`
- Create: `risk-landscaper/tests/test_cli.py`

- [ ] **Step 1: Write CLI tests**

```python
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from typer.testing import CliRunner

from risk_landscaper.cli import app
from risk_landscaper.models import PolicyProfile, Policy, Stakeholder


runner = CliRunner()


def test_run_missing_file():
    result = runner.invoke(app, ["run", "/nonexistent/policy.json", "--output", "/tmp/out", "--base-url", "http://localhost:8000/v1", "--model", "test"])
    assert result.exit_code != 0
    assert "does not exist" in result.output


def test_run_missing_base_url(tmp_path):
    policy_file = tmp_path / "test.json"
    policy_file.write_text(json.dumps([{"policy_concept": "Test", "concept_definition": "Def"}]))
    result = runner.invoke(app, ["run", str(policy_file), "--output", str(tmp_path / "out"), "--model", "test"])
    assert result.exit_code != 0
    assert "base-url" in result.output.lower() or "required" in result.output.lower()


def test_run_missing_model(tmp_path):
    policy_file = tmp_path / "test.json"
    policy_file.write_text(json.dumps([{"policy_concept": "Test", "concept_definition": "Def"}]))
    result = runner.invoke(app, ["run", str(policy_file), "--output", str(tmp_path / "out"), "--base-url", "http://localhost:8000/v1"])
    assert result.exit_code != 0
    assert "model" in result.output.lower() or "required" in result.output.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd risk-landscaper && uv run pytest tests/test_cli.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'risk_landscaper.cli'`

- [ ] **Step 3: Implement cli.py**

```python
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import typer
import yaml

from risk_landscaper import debug
from risk_landscaper.llm import LLMConfig, TokenTracker, create_client
from risk_landscaper.models import Policy, PolicyProfile, RunReport
from risk_landscaper.nexus_adapter import detect_nexus_format, nexus_to_policy_profile

app = typer.Typer()


def _load_input(path: Path) -> tuple[str, str, PolicyProfile | None]:
    """Load input file, returning (text, format, optional pre-parsed profile).

    Returns:
        text: raw document text
        input_format: "markdown", "json_array", or "policy_profile"
        profile: PolicyProfile if already parsed, else None
    """
    text = path.read_text()
    if path.suffix == ".json":
        raw = json.loads(text)
        if isinstance(raw, list):
            return text, "json_array", None
        if detect_nexus_format(raw):
            profile = nexus_to_policy_profile(raw)
            return text, "policy_profile", profile
        if "policies" in raw:
            profile = PolicyProfile(**raw)
            return text, "policy_profile", profile
    return text, "markdown", None


def _create_risk_handlers(nexus_base_dir: str, nexus_chroma_dir: Path) -> dict:
    from nexus_mcp.server import create_tool_handlers
    from nexus_mcp.risk_index import RiskIndex
    from ai_atlas_nexus import AIAtlasNexus

    nexus = AIAtlasNexus(base_dir=nexus_base_dir)
    all_risks = nexus.get_all_risks()
    risks_by_id = {r.id: r for r in all_risks}
    all_actions = nexus.get_all_actions()
    actions_by_id = {a.id: a for a in all_actions}
    taxonomies = nexus.get_all_taxonomies()
    groups = nexus.get_all("groups")
    nexus_chroma_dir.mkdir(parents=True, exist_ok=True)

    from nexus_mcp.risk_index import build_structural_context

    idx = RiskIndex(nexus_chroma_dir)
    if idx.needs_reindex(len(all_risks)):
        ctx = build_structural_context(risks_by_id, groups, actions_by_id)
        idx.index_risks(all_risks, structural_context=ctx)
    return create_tool_handlers(
        risk_index=idx, risks_by_id=risks_by_id, actions_by_id=actions_by_id,
        taxonomies=taxonomies, groups=groups,
    )


@app.command()
def run(
    policy_file: Path = typer.Argument(..., help="Policy document (.md/.txt/.json)"),
    output: Path = typer.Option(..., "--output", "-o", help="Output directory"),
    base_url: str = typer.Option(None, "--base-url", envvar="REFINER_BASE_URL", help="LLM API base URL"),
    model: str = typer.Option(None, "--model", envvar="REFINER_MODEL", help="LLM model name"),
    api_key: str = typer.Option("none", "--api-key", envvar="REFINER_API_KEY", help="LLM API key"),
    nexus_base_dir: str = typer.Option(None, "--nexus-base-dir", envvar="NEXUS_BASE_DIR", help="Path to ai-atlas-nexus repo"),
    nexus_chroma_dir: Path = typer.Option(Path(".chroma"), "--nexus-chroma-dir", envvar="NEXUS_CHROMA_DIR", help="Nexus ChromaDB directory"),
    debug_dir: Path = typer.Option(None, "--debug", help="Directory for per-call debug logs"),
    skip_enrichment: bool = typer.Option(False, "--skip-enrichment", help="Skip ingest enrichment pass"),
    max_concurrent: int = typer.Option(1, "--max-concurrent", help="Max parallel LLM calls in map_risks"),
    input_format: str = typer.Option(None, "--input-format", help="Input format: markdown or json_array (auto-detected if omitted)"),
):
    """Run the risk landscaper pipeline: ingest → detect_domain → map_risks → build_landscape."""
    if not policy_file.exists():
        typer.echo(f"Error: {policy_file} does not exist", err=True)
        raise typer.Exit(1)

    if not base_url or not model:
        typer.echo("Error: --base-url and --model are required (or set REFINER_BASE_URL / REFINER_MODEL)", err=True)
        raise typer.Exit(1)

    if not nexus_base_dir:
        typer.echo("Error: --nexus-base-dir is required (or set NEXUS_BASE_DIR)", err=True)
        raise typer.Exit(1)

    config = LLMConfig(base_url=base_url, model=model, api_key=api_key, max_concurrent=max_concurrent)
    tracker = TokenTracker()
    client = create_client(config, tracker=tracker)
    debug.configure(debug_dir)

    report = RunReport(
        model=config.model,
        policy_set=policy_file.name,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    output.mkdir(parents=True, exist_ok=True)

    # --- Stage 1: Ingest ---
    text, detected_format, pre_parsed = _load_input(policy_file)
    fmt = input_format or detected_format

    if pre_parsed is not None:
        profile = pre_parsed
        typer.echo(f"Loaded pre-parsed profile: {len(profile.policies)} policies")
        report.stages_completed.append("ingest")
    else:
        from risk_landscaper.stages.ingest import ingest
        typer.echo(f"Ingesting {policy_file.name} (format: {fmt})...")
        profile = ingest(
            text, fmt, client, config,
            skip_enrichment=skip_enrichment,
            report=report,
        )
        report.stages_completed.append("ingest")
        typer.echo(f"  Organization: {profile.organization.name if profile.organization else ''}")
        typer.echo(f"  Domain: {profile.domain}")
        typer.echo(f"  Policies: {len(profile.policies)}")

    profile_path = output / "policy-profile.json"
    profile_path.write_text(json.dumps(profile.model_dump(), indent=2))

    # --- Stage 2: Detect domain ---
    from risk_landscaper.stages.detect_domain import detect_domain
    selected_domains = detect_domain(profile, client, config, report=report)
    report.stages_completed.append("detect_domain")
    typer.echo(f"  Domain: {selected_domains}")

    # --- Stage 3: Map risks ---
    from risk_landscaper.stages.map_risks import map_risks
    risk_handlers = _create_risk_handlers(nexus_base_dir, nexus_chroma_dir)
    typer.echo(f"Mapping {len(profile.policies)} policies to risks...")
    mappings, risk_details, seen_ids, related_risks, risk_actions, coverage_gaps = map_risks(
        profile.policies, client, config, risk_handlers, report=report,
    )
    report.stages_completed.append("map_risks")
    total_matches = sum(len(m.matched_risks) for m in mappings)
    typer.echo(f"  {total_matches} risk matches across {len(mappings)} policies")
    if coverage_gaps:
        typer.echo(f"  {len(coverage_gaps)} coverage gap(s) detected")

    # --- Stage 4: Build landscape ---
    from risk_landscaper.stages.build_landscape import build_risk_landscape
    from risk_landscaper.models import PolicySourceRef

    landscape = build_risk_landscape(
        mappings=mappings,
        risk_details_cache=risk_details,
        related_risks=related_risks,
        risk_actions=risk_actions,
        selected_domains=selected_domains,
        model=config.model,
        run_slug=policy_file.stem,
        timestamp=report.timestamp,
        coverage_gaps=coverage_gaps,
        policy_profile=profile,
    )
    report.stages_completed.append("build_landscape")

    landscape_path = output / "risk-landscape.yaml"
    landscape_path.write_text(yaml.dump(
        landscape.model_dump(), default_flow_style=False, sort_keys=False,
    ))
    typer.echo(f"Risk landscape written to {landscape_path}")
    typer.echo(f"  {len(landscape.risks)} unique risks, {len(landscape.framework_coverage)} frameworks")

    # --- Write report ---
    report.token_usage = tracker.to_dict()
    report_path = output / "run-report.json"
    report_path.write_text(json.dumps(report.to_dict(), indent=2))

    typer.echo(f"Token usage: {tracker.prompt_tokens:,} prompt + {tracker.completion_tokens:,} completion = {tracker.total_tokens:,} total ({tracker.calls} calls)")
    typer.echo("Done.")
```

- [ ] **Step 4: Run tests**

```bash
cd risk-landscaper && uv run pytest tests/test_cli.py -v
```

Expected: all 3 CLI tests pass.

- [ ] **Step 5: Run full test suite**

```bash
cd risk-landscaper && uv run pytest -v
```

Expected: all tests pass (models + detect_domain + ingest + map_risks + build_landscape + nexus_adapter + cli).

- [ ] **Step 6: Commit**

```bash
git add risk-landscaper/src/risk_landscaper/cli.py risk-landscaper/tests/test_cli.py
git commit -m "feat(risk-landscaper): add CLI with run command"
```

---

### Task 9: Refiner `--landscape` flag

**Files:**
- Modify: `refiner/src/refiner/pipeline.py`
- Modify: `refiner/src/refiner/cli.py`

- [ ] **Step 1: Modify pipeline.py to accept a pre-built landscape**

In `refiner/src/refiner/pipeline.py`, modify `run_pipeline()` to accept an optional `landscape` parameter. When provided, skip identify_domains, map_risks, and build_landscape — populate state from the landscape.

Add a `landscape: RiskLandscape | None = None` parameter to `run_pipeline()`. When it's set, populate `state.risk_landscape` and `state.selected_domains` from it, then skip directly to anchor.

In `refiner/src/refiner/pipeline.py`, change `run_pipeline` signature (line 92) to add the parameter:

```python
def run_pipeline(
    policies: list[Policy],
    client: instructor.Instructor,
    config: LLMConfig,
    risk_handlers: dict,
    onto_handlers: dict,
    until: str | None = None,
    report: RunReport | None = None,
    layer1_mappings=None,
    layer2_mappings=None,
    bfo_fallbacks: dict[str, str] | None = None,
    run_slug: str = "",
    landscape: RiskLandscape | None = None,
) -> PipelineState:
```

Then at line 105, after creating `state`, add:

```python
    if landscape is not None:
        state.risk_landscape = landscape
        state.selected_domains = landscape.selected_domains
        logger.info("Using pre-built risk landscape: %d risks, %d policy mappings",
                     len(landscape.risks), len(landscape.policy_mappings))
        if report:
            report.events.append({
                "stage": "pipeline", "event": "landscape_loaded",
                "risk_count": len(landscape.risks),
                "policy_mapping_count": len(landscape.policy_mappings),
            })
    else:
        # existing identify_domains + map_risks + build_landscape code
```

Wrap the existing identify_domains → build_landscape block (lines 119-157) in the `else` branch.

The anchor stage (lines 159-172) stays unchanged — it already uses `state.risk_mappings_resolved` etc. which reconstruct from `state.risk_landscape`.

- [ ] **Step 2: Modify cli.py run command to accept --landscape**

In `refiner/src/refiner/cli.py`, add a `--landscape` option to the `run` command (around line 170):

```python
    landscape_path: Path = typer.Option(None, "--landscape", help="Pre-built risk-landscape.yaml from risk-landscaper"),
```

Then in the body, after creating `report` (around line 215), add landscape loading:

```python
    pre_landscape = None
    if landscape_path:
        if not landscape_path.exists():
            typer.echo(f"Error: landscape file {landscape_path} does not exist", err=True)
            raise typer.Exit(1)
        from refiner.models import RiskLandscape
        landscape_data = yaml.safe_load(landscape_path.read_text())
        pre_landscape = RiskLandscape(**landscape_data)
        typer.echo(f"Loaded pre-built landscape: {len(pre_landscape.risks)} risks")
```

Then update the `run_pipeline` call (around line 256) to pass it:

```python
    state = run_pipeline(
        policies, client, config, risk_handlers, onto_handlers,
        until=until, report=report,
        layer1_mappings=layer1_mappings,
        layer2_mappings=layer2_mappings,
        bfo_fallbacks=bfo_fallbacks,
        run_slug=client_slug,
        landscape=pre_landscape,
    )
```

Also update the handler creation guard — when `--landscape` is provided, risk_handlers aren't needed unless `until` goes past map_risks:

```python
    needs_risk = until not in ("identify_domains",) and not landscape_path
    needs_onto = until not in ("identify_domains", "map_risks")
```

- [ ] **Step 3: Run refiner tests to verify no regressions**

```bash
cd refiner && uv run pytest -v
```

Expected: all existing tests pass (the new `landscape` parameter defaults to `None`, so existing behavior is unchanged).

- [ ] **Step 4: Commit**

```bash
git add refiner/src/refiner/pipeline.py refiner/src/refiner/cli.py
git commit -m "feat(refiner): add --landscape flag to accept pre-built risk landscape"
```

---

### Task 10: Battery script updates

**Files:**
- Modify: `scripts/run_battery.py`

- [ ] **Step 1: Add build_landscape_cmd function**

In `scripts/run_battery.py`, add a new function after `build_ingest_cmd` (around line 104):

```python
def build_landscape_cmd(
        *, input_file: Path, run_dir: Path, policy: str, model_name: str, model_url: str,
        api_key: str, nexus_base_dir: Path, nexus_chroma: Path, max_concurrent: int = 1,
) -> tuple[list[str], str]:
    cmd = [
        "uv", "run", "risk-landscaper", "run", str(input_file),
        "--output", str(run_dir),
        "--base-url", model_url,
        "--model", model_name,
        "--nexus-base-dir", str(nexus_base_dir),
        "--nexus-chroma-dir", str(nexus_chroma),
    ]
    if api_key:
        cmd.extend(["--api-key", api_key])
    if max_concurrent > 1:
        cmd.extend(["--max-concurrent", str(max_concurrent)])
    return cmd, "risk-landscaper"
```

- [ ] **Step 2: Update build_refine_cmd to accept --landscape**

Add a `landscape_path: Path | None = None` parameter. When set, pass `--landscape` and drop `--nexus-base-dir` / `--nexus-chroma-dir` (not needed when skipping early stages):

```python
def build_refine_cmd(
        *,
        input_file: Path,
        run_dir: Path,
        model_name: str,
        model_url: str,
        api_key: str,
        nexus_base_dir: Path,
        onto_chroma: Path,
        nexus_chroma: Path,
        tracking_uri: str,
        tags: list[str],
        max_concurrent: int = 1,
        landscape_path: Path | None = None,
) -> tuple[list[str], str]:
    cmd = [
        "uv", "run", "refiner", "run", str(input_file),
        "--output", str(run_dir),
        "--debug", str(run_dir / "debug"),
        "--base-url", model_url,
        "--model", model_name,
    ]
    if api_key:
        cmd.extend(["--api-key", api_key])
    if landscape_path:
        cmd.extend(["--landscape", str(landscape_path)])
    cmd.extend([
        "--nexus-base-dir", str(nexus_base_dir),
        "--ontoquery-chroma-dir", str(onto_chroma),
        "--nexus-chroma-dir", str(nexus_chroma),
    ])
    if max_concurrent > 1:
        cmd.extend(["--max-concurrent", str(max_concurrent)])
    if tracking_uri:
        cmd.extend(["--track", "--tracking-uri", tracking_uri])
    for tag in tags:
        cmd.extend(["--tag", tag])
    return cmd, "refiner"
```

- [ ] **Step 3: Update _run_policy to use new two-stage flow**

In `_run_policy`, replace the ingest+refine flow with landscape+refine:

After the `skip_ingest` block (the ingest stage), add a landscape stage and wire it into refine:

```python
    # risk-landscaper stage (replaces old ingest → map_risks → build_landscape in refiner)
    landscape_path = None
    if not skip_ingest:
        _progress(_stage_msg("landscape"))
        input_file = resolve_policy_file(policy, policy_dir, run_dir=run_dir, prefer_enriched=True)
        cmd, cwd = build_landscape_cmd(
            input_file=input_file, run_dir=run_dir, policy=policy,
            model_name=model_name, model_url=model_url, api_key=api_key,
            nexus_base_dir=cfg["nexus_base_dir"],
            nexus_chroma=tmp_nexus,
            max_concurrent=cfg.get("max_concurrent", 1),
        )
        _run_stage(cmd, cwd, **stage_kw)
        landscape_path = run_dir / "risk-landscape.yaml"
```

Then pass `landscape_path` to `build_refine_cmd`:

```python
    if not skip_refine:
        _progress(_stage_msg("refine"))
        input_file = resolve_policy_file(policy, policy_dir, run_dir=run_dir, prefer_enriched=True)
        cmd, cwd = build_refine_cmd(
            input_file=input_file, run_dir=run_dir, model_name=model_name,
            model_url=model_url, api_key=api_key, nexus_base_dir=cfg["nexus_base_dir"],
            onto_chroma=tmp_onto, nexus_chroma=tmp_nexus,
            tracking_uri=cfg["tracking_uri"], tags=tags,
            max_concurrent=cfg.get("max_concurrent", 1),
            landscape_path=landscape_path,
        )
        _run_stage(cmd, cwd, **stage_kw)
```

Update the stage list building to include "landscape" instead of just "ingest":

```python
    stages: list[str] = []
    if not skip_ingest:
        stages.append("ingest")
        stages.append("landscape")
    if not skip_refine:
        stages.append("refine")
```

- [ ] **Step 4: Dry-run test**

```bash
uv run scripts/run_battery.py test-run --dry-run --policy swb --model mistral-small-3-1-24b
```

Expected: prints commands showing `risk-landscaper run ...` followed by `refiner run ... --landscape ...`.

- [ ] **Step 5: Commit**

```bash
git add scripts/run_battery.py
git commit -m "feat(battery): split pipeline into risk-landscaper + refiner stages"
```

---

### Task 11: Remove moved code from refiner

**Files:**
- Delete: `refiner/src/refiner/stages/ingest.py`
- Delete: `refiner/src/refiner/stages/identify_domains.py`
- Delete: `refiner/src/refiner/stages/map_risks.py`
- Delete: `refiner/src/refiner/stages/build_landscape.py`
- Delete: `refiner/src/refiner/nexus_adapter.py`
- Delete: `refiner/tests/test_ingest.py`
- Delete: `refiner/tests/test_map_risks.py`
- Delete: `refiner/tests/test_build_landscape.py`
- Delete: `refiner/tests/test_nexus_adapter.py`
- Delete: `refiner/tests/test_models_ingest.py`
- Modify: `refiner/src/refiner/pipeline.py` (remove early-stage imports and code)
- Modify: `refiner/src/refiner/cli.py` (remove ingest command, map-risks command, early-stage handler creation)
- Modify: `refiner/pyproject.toml` (remove nexus-mcp dependency if no longer needed directly)

- [ ] **Step 1: Remove stage files and their tests**

```bash
rm refiner/src/refiner/stages/ingest.py
rm refiner/src/refiner/stages/identify_domains.py
rm refiner/src/refiner/stages/map_risks.py
rm refiner/src/refiner/stages/build_landscape.py
rm refiner/src/refiner/nexus_adapter.py
rm refiner/tests/test_ingest.py
rm refiner/tests/test_map_risks.py
rm refiner/tests/test_build_landscape.py
```

Also remove `refiner/tests/test_nexus_adapter.py` and `refiner/tests/test_models_ingest.py` if they exist.

- [ ] **Step 2: Update pipeline.py**

Remove imports of the deleted stages. The `else` branch (from Task 9) that called identify_domains, map_risks, build_landscape should now error if `landscape` is None:

```python
    if landscape is not None:
        state.risk_landscape = landscape
        state.selected_domains = landscape.selected_domains
        logger.info("Using pre-built risk landscape: %d risks, %d policy mappings",
                     len(landscape.risks), len(landscape.policy_mappings))
    else:
        raise ValueError(
            "No pre-built landscape provided. Run risk-landscaper first, "
            "then pass the result via --landscape."
        )
```

Remove the imports of `identify_domains`, `map_risks`, `build_risk_landscape` from the top of the file. Keep the `STAGES` constant for backward compat or update it to `("anchor", "contextualize")`.

Also remove the import of `ALWAYS_INCLUDED` from `identify_domains`.

- [ ] **Step 3: Update cli.py**

Remove the `ingest` command and `map_risks_cmd` (the `map-risks` standalone command). Remove the `_load_policies` helper if it's no longer used (check — `run` command may still use it). Remove `from refiner.nexus_adapter import ...`. 

Make `--landscape` required instead of optional on the `run` command (since refiner can no longer run stages 1-3 itself).

Update `_create_risk_handlers` — if refiner still needs risk_handlers for the anchor stage (it does — anchor uses `nexus_handlers`), keep it. But if risk_handlers are only used by map_risks, remove.

Check: `pipeline.py` line 165 shows anchor receives `nexus_handlers=risk_handlers`. So keep `_create_risk_handlers` in refiner's cli.py.

- [ ] **Step 4: Remove nexus-mcp dependency check**

Check if refiner still needs nexus-mcp. Looking at `pipeline.py:165`, anchor receives `nexus_handlers=risk_handlers` — so refiner still needs nexus-mcp for anchor. Keep the dependency in `pyproject.toml`.

- [ ] **Step 5: Run refiner tests**

```bash
cd refiner && uv run pytest -v
```

Expected: remaining tests pass. Tests that imported from deleted modules are gone. Tests for anchor, contextualize, emit, evaluate should still pass.

Fix any import errors in remaining test files that may have referenced deleted modules.

- [ ] **Step 6: Run risk-landscaper tests**

```bash
cd risk-landscaper && uv run pytest -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add -A refiner/ risk-landscaper/
git commit -m "refactor: remove moved stages from refiner, require --landscape"
```

---

### Task 12: End-to-end verification

**Files:** None created/modified — verification only.

- [ ] **Step 1: Run risk-landscaper full test suite**

```bash
cd risk-landscaper && uv run pytest -v
```

Expected: all tests pass.

- [ ] **Step 2: Run refiner full test suite**

```bash
cd refiner && uv run pytest -v
```

Expected: all remaining tests pass.

- [ ] **Step 3: Dry-run battery**

```bash
uv run scripts/run_battery.py verify --dry-run --policy swb --model mistral-small-3-1-24b
```

Expected: shows risk-landscaper → refiner → emit → evaluate command sequence.

- [ ] **Step 4: Verify CLI entry point works**

```bash
cd risk-landscaper && uv run risk-landscaper --help
```

Expected: shows the `run` command with all documented flags.

- [ ] **Step 5: Commit (if any fixups were needed)**

```bash
git add -A
git commit -m "fix: end-to-end verification fixes"
```
