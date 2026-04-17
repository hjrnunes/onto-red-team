# Data Artifact Stages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the refiner pipeline so that each stage produces a self-contained, serializable data artifact (with presentation companion), enabling full decoupling into independent tools and presentable intermediate outputs.

**Architecture:** Introduce a `RiskLandscape` model (consolidating 5 scattered PipelineState caches into one envelope), add `KnowledgeBaseRef` for provenance tracking, serialize each stage's output to disk, fold `identify_domains` into risk landscape building, refactor `structure.py` from pipeline stage to export layer, and add independent CLI commands per stage. The `DomainContext` remains the canonical hub artifact; taxonomy.yaml becomes a default export.

**Tech Stack:** Pydantic (models), PyYAML (serialization), Typer (CLI), pytest (testing)

---

### Task 1: Define KnowledgeBaseRef and RiskDetail models

**Files:**
- Modify: `refiner/src/refiner/models.py`
- Test: `refiner/tests/test_models.py`

- [ ] **Step 1: Write failing tests for KnowledgeBaseRef**

```python
# Add to refiner/tests/test_models.py

def test_knowledge_base_ref_round_trip():
    from refiner.models import KnowledgeBaseRef
    ref = KnowledgeBaseRef(
        nexus_commit="abc1234",
        nexus_risk_count=612,
        ontology_index_hash="sha256:deadbeef",
        ontology_domains={"CCO": 5000, "FIBO": 1500, "OBO": 95000},
        indexed_at="2026-04-14T12:00:00Z",
    )
    d = ref.model_dump()
    assert d["nexus_commit"] == "abc1234"
    assert d["nexus_risk_count"] == 612
    assert d["ontology_domains"]["CCO"] == 5000
    ref2 = KnowledgeBaseRef(**d)
    assert ref2 == ref


def test_knowledge_base_ref_defaults():
    from refiner.models import KnowledgeBaseRef
    ref = KnowledgeBaseRef()
    assert ref.nexus_commit == ""
    assert ref.nexus_risk_count == 0
    assert ref.ontology_domains == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd refiner && uv run pytest tests/test_models.py::test_knowledge_base_ref_round_trip tests/test_models.py::test_knowledge_base_ref_defaults -v`
Expected: FAIL with `ImportError: cannot import name 'KnowledgeBaseRef'`

- [ ] **Step 3: Write failing tests for RiskDetail**

```python
# Add to refiner/tests/test_models.py

def test_risk_detail_round_trip():
    from refiner.models import RiskDetail
    detail = RiskDetail(
        risk_id="atlas-personal-information-in-prompt",
        risk_name="Personal information",
        risk_description="Personal information or sensitive personal information...",
        risk_concern="If personal information is included in the prompt...",
        risk_framework="ibm-risk-atlas",
        cross_mappings=[{"id": "nist-data-privacy", "mapping_type": "broad"}],
        related_actions=["Minimize personal data in prompts"],
    )
    d = detail.model_dump()
    assert d["risk_id"] == "atlas-personal-information-in-prompt"
    assert d["related_actions"] == ["Minimize personal data in prompts"]
    detail2 = RiskDetail(**d)
    assert detail2 == detail


def test_risk_detail_defaults():
    from refiner.models import RiskDetail
    detail = RiskDetail(risk_id="test", risk_name="Test")
    assert detail.risk_description == ""
    assert detail.cross_mappings == []
    assert detail.related_actions == []
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `cd refiner && uv run pytest tests/test_models.py::test_risk_detail_round_trip tests/test_models.py::test_risk_detail_defaults -v`
Expected: FAIL with `ImportError: cannot import name 'RiskDetail'`

- [ ] **Step 5: Implement both models in models.py**

Add after `PipelineConfig` (line 95) and before `RiskSummary` (line 98) in `refiner/src/refiner/models.py`:

```python
class KnowledgeBaseRef(BaseModel):
    nexus_commit: str = ""
    nexus_risk_count: int = 0
    ontology_index_hash: str = ""
    ontology_domains: dict[str, int] = {}
    indexed_at: str = ""


class RiskDetail(BaseModel):
    risk_id: str
    risk_name: str
    risk_description: str | None = ""
    risk_concern: str | None = ""
    risk_framework: str | None = ""
    cross_mappings: list[dict] = []
    related_actions: list[str] = []
```

- [ ] **Step 6: Run all new tests to verify they pass**

Run: `cd refiner && uv run pytest tests/test_models.py::test_knowledge_base_ref_round_trip tests/test_models.py::test_knowledge_base_ref_defaults tests/test_models.py::test_risk_detail_round_trip tests/test_models.py::test_risk_detail_defaults -v`
Expected: 4 PASS

- [ ] **Step 7: Run full test_models.py to check for regressions**

Run: `cd refiner && uv run pytest tests/test_models.py -v`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
cd refiner && git add src/refiner/models.py tests/test_models.py
git commit -m "feat: add KnowledgeBaseRef and RiskDetail models

New Pydantic models for data artifact stage refactoring:
- KnowledgeBaseRef: tracks ontology index + nexus versions for reproducibility
- RiskDetail: consolidated risk metadata (replaces scattered cache dicts)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 2: Define RiskLandscape model

**Files:**
- Modify: `refiner/src/refiner/models.py`
- Test: `refiner/tests/test_models.py`

- [ ] **Step 1: Write failing tests for RiskLandscape**

```python
# Add to refiner/tests/test_models.py

def test_risk_landscape_round_trip():
    from refiner.models import (
        RiskLandscape, RiskDetail, PolicyRiskMapping, RiskMatch,
        KnowledgeBaseRef, PolicySourceRef,
    )
    landscape = RiskLandscape(
        model="gemma-3-12b-it",
        timestamp="2026-04-14T12:00:00Z",
        run_slug="swb-enriched",
        selected_domains=["CCO", "Commons", "FIBO", "D3FEND", "CSO", "LKIF"],
        policy_source=PolicySourceRef(organization="South West Bank", domain="banking", policy_count=6),
        knowledge_base=KnowledgeBaseRef(nexus_commit="abc1234", nexus_risk_count=612),
        risks=[
            RiskDetail(
                risk_id="atlas-personal-information-in-prompt",
                risk_name="Personal information",
                risk_description="Personal information...",
                cross_mappings=[{"id": "nist-data-privacy", "mapping_type": "broad"}],
                related_actions=["Minimize personal data"],
            ),
        ],
        policy_mappings=[
            PolicyRiskMapping(
                policy_concept="Executive Compensation",
                matched_risks=[
                    RiskMatch(
                        risk_id="atlas-personal-information-in-prompt",
                        risk_name="Personal information",
                        relevance="primary",
                        justification="Directly addresses PII concerns",
                        match_distance=0.234,
                    ),
                ],
            ),
        ],
        framework_coverage={"ibm-risk-atlas": 1},
        weak_matches=[],
    )
    d = landscape.model_dump()
    assert d["version"] == "0.1"
    assert d["selected_domains"][2] == "FIBO"
    assert len(d["risks"]) == 1
    assert d["risks"][0]["related_actions"] == ["Minimize personal data"]
    assert len(d["policy_mappings"]) == 1
    landscape2 = RiskLandscape(**d)
    assert landscape2.risks[0].risk_id == "atlas-personal-information-in-prompt"
    assert landscape2.policy_mappings[0].matched_risks[0].match_distance == 0.234


def test_risk_landscape_yaml_round_trip(tmp_path):
    import yaml
    from refiner.models import (
        RiskLandscape, RiskDetail, PolicyRiskMapping, RiskMatch,
    )
    landscape = RiskLandscape(
        model="test-model",
        timestamp="2026-04-14T12:00:00Z",
        run_slug="test",
        risks=[
            RiskDetail(risk_id="r1", risk_name="Risk One"),
        ],
        policy_mappings=[
            PolicyRiskMapping(
                policy_concept="Policy A",
                matched_risks=[
                    RiskMatch(risk_id="r1", risk_name="Risk One",
                              relevance="primary", justification="test"),
                ],
            ),
        ],
    )
    path = tmp_path / "risk-landscape.yaml"
    path.write_text(yaml.dump(landscape.model_dump(), default_flow_style=False, sort_keys=False))
    loaded = yaml.safe_load(path.read_text())
    landscape2 = RiskLandscape(**loaded)
    assert landscape2.risks[0].risk_id == "r1"
    assert landscape2.policy_mappings[0].policy_concept == "Policy A"


def test_risk_landscape_defaults():
    from refiner.models import RiskLandscape
    landscape = RiskLandscape()
    assert landscape.version == "0.1"
    assert landscape.risks == []
    assert landscape.policy_mappings == []
    assert landscape.framework_coverage == {}
    assert landscape.weak_matches == []
    assert landscape.selected_domains == []
    assert landscape.knowledge_base is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd refiner && uv run pytest tests/test_models.py::test_risk_landscape_round_trip tests/test_models.py::test_risk_landscape_yaml_round_trip tests/test_models.py::test_risk_landscape_defaults -v`
Expected: FAIL with `ImportError: cannot import name 'RiskLandscape'`

- [ ] **Step 3: Implement RiskLandscape model**

Add after `RiskDetail` in `refiner/src/refiner/models.py`:

```python
class WeakMatch(BaseModel):
    risk_id: str
    policy_concept: str
    distance: float


class RiskLandscape(BaseModel):
    version: str = "0.1"
    model: str = ""
    timestamp: str = ""
    run_slug: str = ""
    selected_domains: list[str] = []
    policy_source: PolicySourceRef | None = None
    knowledge_base: KnowledgeBaseRef | None = None
    risks: list[RiskDetail] = []
    policy_mappings: list[PolicyRiskMapping] = []
    framework_coverage: dict[str, int] = {}
    weak_matches: list[WeakMatch] = []
```

- [ ] **Step 4: Run all new tests to verify they pass**

Run: `cd refiner && uv run pytest tests/test_models.py::test_risk_landscape_round_trip tests/test_models.py::test_risk_landscape_yaml_round_trip tests/test_models.py::test_risk_landscape_defaults -v`
Expected: 3 PASS

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `cd refiner && uv run pytest tests/test_models.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
cd refiner && git add src/refiner/models.py tests/test_models.py
git commit -m "feat: add RiskLandscape model

Envelope model consolidating risk mapping data (previously 5 scattered
dicts in PipelineState) into a single serializable artifact. Follows
the same envelope pattern as PolicyProfile and DomainContext.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 3: Add build_risk_landscape() function

**Files:**
- Create: `refiner/src/refiner/stages/build_landscape.py`
- Test: `refiner/tests/test_build_landscape.py`

This function takes the raw outputs of `map_risks()` and `identify_domains()` and assembles them into a `RiskLandscape` artifact.

- [ ] **Step 1: Write failing tests**

```python
# refiner/tests/test_build_landscape.py

import pytest
from refiner.models import (
    RiskLandscape, RiskDetail, PolicyRiskMapping, RiskMatch,
    PolicySourceRef, PolicyProfile, Stakeholder,
)


def test_build_risk_landscape_basic():
    from refiner.stages.build_landscape import build_risk_landscape

    mappings = [
        PolicyRiskMapping(
            policy_concept="Executive Compensation",
            matched_risks=[
                RiskMatch(
                    risk_id="atlas-personal-info",
                    risk_name="Personal information",
                    relevance="primary",
                    justification="Direct PII concern",
                    match_distance=0.234,
                ),
            ],
        ),
    ]
    risk_details_cache = {
        "atlas-personal-info": {
            "id": "atlas-personal-info",
            "name": "Personal information",
            "description": "Personal information or sensitive...",
            "concern": "If personal information is included...",
        },
    }
    related_risks = {
        "atlas-personal-info": [
            {"id": "nist-data-privacy", "name": "Data Privacy",
             "taxonomy": "nist-ai-rmf", "mapping_type": "broad"},
        ],
    }
    risk_actions = {
        "atlas-personal-info": ["Minimize personal data in prompts"],
    }
    selected_domains = ["CCO", "Commons", "FIBO", "D3FEND", "CSO", "LKIF"]

    landscape = build_risk_landscape(
        mappings=mappings,
        risk_details_cache=risk_details_cache,
        related_risks=related_risks,
        risk_actions=risk_actions,
        selected_domains=selected_domains,
        model="gemma-3-12b-it",
        run_slug="swb-enriched",
        timestamp="2026-04-14T12:00:00Z",
    )

    assert isinstance(landscape, RiskLandscape)
    assert landscape.model == "gemma-3-12b-it"
    assert landscape.selected_domains == selected_domains
    assert len(landscape.risks) == 1
    assert landscape.risks[0].risk_id == "atlas-personal-info"
    assert landscape.risks[0].related_actions == ["Minimize personal data in prompts"]
    assert landscape.risks[0].cross_mappings == related_risks["atlas-personal-info"]
    assert len(landscape.policy_mappings) == 1
    assert landscape.policy_mappings[0].policy_concept == "Executive Compensation"


def test_build_risk_landscape_deduplicates_risks():
    from refiner.stages.build_landscape import build_risk_landscape

    # Same risk matched from two policies
    mappings = [
        PolicyRiskMapping(
            policy_concept="Policy A",
            matched_risks=[
                RiskMatch(risk_id="r1", risk_name="Risk One",
                          relevance="primary", justification="test"),
            ],
        ),
        PolicyRiskMapping(
            policy_concept="Policy B",
            matched_risks=[
                RiskMatch(risk_id="r1", risk_name="Risk One",
                          relevance="supporting", justification="test2"),
            ],
        ),
    ]
    risk_details_cache = {
        "r1": {"id": "r1", "name": "Risk One", "description": "desc"},
    }

    landscape = build_risk_landscape(
        mappings=mappings,
        risk_details_cache=risk_details_cache,
        model="test-model",
        run_slug="test",
        timestamp="2026-04-14T12:00:00Z",
    )

    # Risk stored once, referenced from both policy mappings
    assert len(landscape.risks) == 1
    assert len(landscape.policy_mappings) == 2


def test_build_risk_landscape_weak_matches():
    from refiner.stages.build_landscape import build_risk_landscape

    mappings = [
        PolicyRiskMapping(
            policy_concept="Policy A",
            matched_risks=[
                RiskMatch(risk_id="r1", risk_name="Risk One",
                          relevance="primary", justification="test",
                          match_distance=0.75),
            ],
        ),
    ]
    risk_details_cache = {
        "r1": {"id": "r1", "name": "Risk One", "description": "desc"},
    }

    landscape = build_risk_landscape(
        mappings=mappings,
        risk_details_cache=risk_details_cache,
        model="test-model",
        run_slug="test",
        timestamp="2026-04-14T12:00:00Z",
    )

    assert len(landscape.weak_matches) == 1
    assert landscape.weak_matches[0].risk_id == "r1"
    assert landscape.weak_matches[0].distance == 0.75


def test_build_risk_landscape_framework_coverage():
    from refiner.stages.build_landscape import build_risk_landscape

    mappings = [
        PolicyRiskMapping(
            policy_concept="Policy A",
            matched_risks=[
                RiskMatch(risk_id="atlas-fraud", risk_name="Fraud",
                          relevance="primary", justification="test"),
                RiskMatch(risk_id="nist-data-privacy", risk_name="Data Privacy",
                          relevance="supporting", justification="test"),
            ],
        ),
    ]
    risk_details_cache = {
        "atlas-fraud": {"id": "atlas-fraud", "name": "Fraud", "description": ""},
        "nist-data-privacy": {"id": "nist-data-privacy", "name": "Data Privacy", "description": ""},
    }

    landscape = build_risk_landscape(
        mappings=mappings,
        risk_details_cache=risk_details_cache,
        model="test-model",
        run_slug="test",
        timestamp="2026-04-14T12:00:00Z",
    )

    assert "ibm-risk-atlas" in landscape.framework_coverage or "atlas" in str(landscape.framework_coverage)


def test_build_risk_landscape_with_policy_source():
    from refiner.stages.build_landscape import build_risk_landscape

    doc_context = PolicyProfile(
        organization=Stakeholder(name="South West Bank"),
        domain="banking",
        policies=[],
    )
    landscape = build_risk_landscape(
        mappings=[],
        risk_details_cache={},
        model="test-model",
        run_slug="test",
        timestamp="2026-04-14T12:00:00Z",
        doc_context=doc_context,
    )

    assert landscape.policy_source is not None
    assert landscape.policy_source.organization == "South West Bank"
    assert landscape.policy_source.domain == "banking"


def test_build_risk_landscape_empty_inputs():
    from refiner.stages.build_landscape import build_risk_landscape

    landscape = build_risk_landscape(
        mappings=[],
        risk_details_cache={},
        model="test-model",
        run_slug="test",
        timestamp="2026-04-14T12:00:00Z",
    )

    assert landscape.risks == []
    assert landscape.policy_mappings == []
    assert landscape.framework_coverage == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd refiner && uv run pytest tests/test_build_landscape.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'refiner.stages.build_landscape'`

- [ ] **Step 3: Implement build_risk_landscape()**

Create `refiner/src/refiner/stages/build_landscape.py`:

```python
from refiner.models import (
    PolicyProfile,
    PolicyRiskMapping,
    PolicySourceRef,
    RiskDetail,
    RiskLandscape,
    KnowledgeBaseRef,
    WeakMatch,
)

WEAK_MATCH_THRESHOLD = 0.6

FRAMEWORK_PREFIXES = {
    "atlas-": "ibm-risk-atlas",
    "nist-": "nist-ai-rmf",
    "owasp-": "owasp-llm",
    "llm0": "owasp-llm",
    "air-": "air-2024",
    "mit-ai-risk": "mit-ai-risk",
    "ailuminate-": "ailuminate",
    "credo-": "credo",
    "aiuc-": "aiuc",
    "csiro-": "csiro",
}


def _detect_framework(risk_id: str) -> str:
    for prefix, framework in FRAMEWORK_PREFIXES.items():
        if risk_id.startswith(prefix):
            return framework
    return "unknown"


def build_risk_landscape(
    mappings: list[PolicyRiskMapping],
    risk_details_cache: dict[str, dict],
    related_risks: dict[str, list[dict]] | None = None,
    risk_actions: dict[str, list[str]] | None = None,
    selected_domains: list[str] | None = None,
    model: str = "",
    run_slug: str = "",
    timestamp: str = "",
    doc_context: PolicyProfile | None = None,
    knowledge_base: KnowledgeBaseRef | None = None,
) -> RiskLandscape:
    related_risks = related_risks or {}
    risk_actions = risk_actions or {}

    # Build normalized risk registry (deduplicated)
    seen_risk_ids: set[str] = set()
    risks: list[RiskDetail] = []
    framework_counts: dict[str, int] = {}
    weak_matches: list[WeakMatch] = []

    for mapping in mappings:
        for rm in mapping.matched_risks:
            # Collect weak matches
            if rm.match_distance is not None and rm.match_distance > WEAK_MATCH_THRESHOLD:
                weak_matches.append(WeakMatch(
                    risk_id=rm.risk_id,
                    policy_concept=mapping.policy_concept,
                    distance=rm.match_distance,
                ))

            if rm.risk_id in seen_risk_ids:
                continue
            seen_risk_ids.add(rm.risk_id)

            details = risk_details_cache.get(rm.risk_id, {})
            risks.append(RiskDetail(
                risk_id=rm.risk_id,
                risk_name=details.get("name", rm.risk_name),
                risk_description=details.get("description", ""),
                risk_concern=details.get("concern", ""),
                cross_mappings=related_risks.get(rm.risk_id, []),
                related_actions=risk_actions.get(rm.risk_id, []),
            ))

            framework = _detect_framework(rm.risk_id)
            framework_counts[framework] = framework_counts.get(framework, 0) + 1

    # Build policy source from PolicyProfile
    policy_source = None
    if doc_context:
        policy_source = PolicySourceRef(
            organization=doc_context.organization.name if doc_context.organization else None,
            domain=doc_context.domain,
            policy_count=len(doc_context.policies),
        )

    return RiskLandscape(
        model=model,
        timestamp=timestamp,
        run_slug=run_slug,
        selected_domains=selected_domains or [],
        policy_source=policy_source,
        knowledge_base=knowledge_base,
        risks=risks,
        policy_mappings=mappings,
        framework_coverage=framework_counts,
        weak_matches=weak_matches,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd refiner && uv run pytest tests/test_build_landscape.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
cd refiner && git add src/refiner/stages/build_landscape.py tests/test_build_landscape.py
git commit -m "feat: add build_risk_landscape() to assemble RiskLandscape artifact

Pure function that consolidates map_risks() outputs (risk_details_cache,
related_risks, risk_actions) + identify_domains result into a single
RiskLandscape envelope. Detects framework coverage and weak matches.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 4: Integrate RiskLandscape into pipeline and serialize to disk

**Files:**
- Modify: `refiner/src/refiner/pipeline.py`
- Modify: `refiner/src/refiner/cli.py`
- Test: `refiner/tests/test_pipeline.py`

- [ ] **Step 1: Write failing test for PipelineState with risk_landscape field**

```python
# Add to refiner/tests/test_pipeline.py

def test_pipeline_state_has_risk_landscape():
    from refiner.pipeline import PipelineState
    from refiner.models import Policy, RiskLandscape
    state = PipelineState(policies=[])
    assert state.risk_landscape is None
    state.risk_landscape = RiskLandscape(model="test")
    assert state.risk_landscape.model == "test"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd refiner && uv run pytest tests/test_pipeline.py::test_pipeline_state_has_risk_landscape -v`
Expected: FAIL with `AttributeError` (no `risk_landscape` field)

- [ ] **Step 3: Add risk_landscape to PipelineState**

In `refiner/src/refiner/pipeline.py`, add the import and field.

Add to imports (after existing model imports):
```python
from refiner.models import (
    Policy,
    PolicyProfile,
    PolicyRiskMapping,
    RiskLandscape,
    RiskVariationAxes,
    DomainContext,
    RunReport,
)
```

Add to PipelineState dataclass (after `risk_actions` field, before `variation_axes`):
```python
    risk_landscape: RiskLandscape | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd refiner && uv run pytest tests/test_pipeline.py::test_pipeline_state_has_risk_landscape -v`
Expected: PASS

- [ ] **Step 5: Update run_pipeline to build RiskLandscape after map_risks**

In `refiner/src/refiner/pipeline.py`, add import:
```python
from refiner.stages.build_landscape import build_risk_landscape
```

After `_stage_done("map_risks", t0)` (line 94), add:
```python
    state.risk_landscape = build_risk_landscape(
        mappings=state.risk_mappings,
        risk_details_cache=state.risk_details,
        related_risks=state.related_risks,
        risk_actions=state.risk_actions,
        selected_domains=state.selected_domains,
        model=config.model,
        run_slug=run_slug,
        timestamp=report.timestamp if report else "",
    )
```

- [ ] **Step 6: Update cli.py to serialize RiskLandscape to YAML**

In the `run` command in `cli.py`, in the block that handles full pipeline completion (the `if state.domain_context is not None and state.risk_mappings is not None:` block), add after `state.doc_context = doc_context` (line 231):

```python
    # Serialize RiskLandscape artifact
    if state.risk_landscape is not None:
        if state.doc_context:
            from refiner.models import PolicySourceRef
            state.risk_landscape.policy_source = PolicySourceRef(
                organization=state.doc_context.organization.name if state.doc_context.organization else None,
                domain=state.doc_context.domain,
                policy_count=len(state.doc_context.policies),
            )
        rl_path = out / f"{client_slug}-risk-landscape.yaml"
        rl_path.write_text(yaml.dump(
            state.risk_landscape.model_dump(), default_flow_style=False, sort_keys=False,
        ))
        typer.echo(f"Risk landscape written to {rl_path}")
```

Also in the partial run state dump block (the `else` block around line 330), add after the `if state.risk_details:` block:

```python
            if state.risk_landscape:
                rl_path = out / f"{client_slug}-risk-landscape.yaml"
                rl_path.write_text(yaml.dump(
                    state.risk_landscape.model_dump(), default_flow_style=False, sort_keys=False,
                ))
                typer.echo(f"Risk landscape written to {rl_path}")
```

- [ ] **Step 7: Run existing pipeline tests to check for regressions**

Run: `cd refiner && uv run pytest tests/test_pipeline.py -v`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
cd refiner && git add src/refiner/pipeline.py src/refiner/cli.py tests/test_pipeline.py
git commit -m "feat: integrate RiskLandscape into pipeline and serialize to disk

PipelineState now carries a risk_landscape field, populated after
map_risks. CLI serializes it as {slug}-risk-landscape.yaml alongside
existing artifacts. Backward compatible — old fields remain for now.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 5: Add KnowledgeBaseRef to DomainContext

**Files:**
- Modify: `refiner/src/refiner/models.py`
- Test: `refiner/tests/test_models.py`

- [ ] **Step 1: Write failing test**

```python
# Add to refiner/tests/test_models.py

def test_domain_context_document_has_knowledge_base():
    from refiner.models import DomainContext, KnowledgeBaseRef
    dcd = DomainContext(
        knowledge_base=KnowledgeBaseRef(nexus_commit="abc123"),
    )
    d = dcd.model_dump()
    assert d["knowledge_base"]["nexus_commit"] == "abc123"
    dcd2 = DomainContext(**d)
    assert dcd2.knowledge_base.nexus_commit == "abc123"


def test_domain_context_document_knowledge_base_defaults_none():
    from refiner.models import DomainContext
    dcd = DomainContext()
    assert dcd.knowledge_base is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd refiner && uv run pytest tests/test_models.py::test_domain_context_document_has_knowledge_base tests/test_models.py::test_domain_context_document_knowledge_base_defaults_none -v`
Expected: FAIL (field doesn't exist on DomainContext yet)

- [ ] **Step 3: Add knowledge_base field to DomainContext**

In `refiner/src/refiner/models.py`, in the `DomainContext` class, add after the `config` field:

```python
    knowledge_base: KnowledgeBaseRef | None = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd refiner && uv run pytest tests/test_models.py::test_domain_context_document_has_knowledge_base tests/test_models.py::test_domain_context_document_knowledge_base_defaults_none -v`
Expected: 2 PASS

- [ ] **Step 5: Run full model tests to check for regressions**

Run: `cd refiner && uv run pytest tests/test_models.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
cd refiner && git add src/refiner/models.py tests/test_models.py
git commit -m "feat: add knowledge_base field to DomainContext

Optional KnowledgeBaseRef on DCD for provenance tracking. Defaults to
None for backward compatibility with existing serialized artifacts.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 6: Refactor anchor to accept RiskLandscape

**Files:**
- Modify: `refiner/src/refiner/stages/anchor.py`
- Modify: `refiner/src/refiner/pipeline.py`
- Test: `refiner/tests/test_anchor_v2.py`

The anchor stage currently takes `risk_mappings`, `risk_details`, `risk_actions`, `related_risks`, and `selected_domains` as separate parameters. Refactor to also accept a `RiskLandscape` as an alternative entry point, while keeping the old signature for backward compatibility.

- [ ] **Step 1: Write failing test for anchor accepting RiskLandscape**

```python
# Add to refiner/tests/test_anchor_v2.py

def test_anchor_accepts_risk_landscape(mock_client, mock_config, mock_onto_handlers):
    from refiner.models import (
        RiskLandscape, RiskDetail, PolicyRiskMapping, RiskMatch,
    )
    from refiner.stages.anchor import anchor

    landscape = RiskLandscape(
        model="test-model",
        run_slug="test",
        selected_domains=["CCO", "Commons"],
        risks=[
            RiskDetail(
                risk_id="r1", risk_name="Risk One",
                risk_description="desc", related_actions=["action1"],
            ),
        ],
        policy_mappings=[
            PolicyRiskMapping(
                policy_concept="Policy A",
                matched_risks=[
                    RiskMatch(risk_id="r1", risk_name="Risk One",
                              relevance="primary", justification="test"),
                ],
            ),
        ],
    )

    # Should work with risk_landscape parameter
    result, vocab = anchor(
        risk_landscape=landscape,
        client=mock_client,
        config=mock_config,
        onto_handlers=mock_onto_handlers,
    )
    assert isinstance(result, list)
    assert isinstance(vocab, dict)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd refiner && uv run pytest tests/test_anchor_v2.py::test_anchor_accepts_risk_landscape -v`
Expected: FAIL (anchor doesn't accept `risk_landscape` parameter)

- [ ] **Step 3: Add risk_landscape parameter to anchor()**

In `refiner/src/refiner/stages/anchor.py`, modify the `anchor()` function signature (around line 481) to add the new parameter and extract fields from it:

Add `RiskLandscape` to imports at the top:
```python
from refiner.models import (
    AxisDerivation,
    PolicyRiskMapping,
    RiskLandscape,
    RiskVariationAxes,
    VariationAxis,
)
```

Change the function signature to:
```python
def anchor(
        risk_mappings: list[PolicyRiskMapping] | None = None,
        risk_details: dict[str, dict] | None = None,
        client: instructor.Instructor = None,
        config: LLMConfig = None,
        onto_handlers: dict = None,
        selected_domains: list[str] | None = None,
        risk_actions: dict[str, list[str]] | None = None,
        related_risks: dict[str, list[dict]] | None = None,
        nexus_handlers: dict | None = None,
        layer1_mappings=None,
        layer2_mappings=None,
        report=None,
        generic_safety_uris: set[str] | None = None,
        policies: list | None = None,
        bfo_fallbacks: dict[str, str] | None = None,
        risk_landscape: RiskLandscape | None = None,
) -> tuple[list[RiskVariationAxes], dict[str, dict]]:
```

Add at the start of the function body, before the `if not risk_mappings:` check:
```python
    # Extract fields from RiskLandscape if provided
    if risk_landscape is not None:
        risk_mappings = risk_mappings or risk_landscape.policy_mappings
        risk_details = risk_details or {
            r.risk_id: {
                "id": r.risk_id, "name": r.risk_name,
                "description": r.risk_description or "",
                "concern": r.risk_concern or "",
            }
            for r in risk_landscape.risks
        }
        selected_domains = selected_domains or risk_landscape.selected_domains
        risk_actions = risk_actions or {
            r.risk_id: r.related_actions
            for r in risk_landscape.risks if r.related_actions
        }
        related_risks = related_risks or {
            r.risk_id: r.cross_mappings
            for r in risk_landscape.risks if r.cross_mappings
        }
```

- [ ] **Step 4: Run the new test to verify it passes**

Run: `cd refiner && uv run pytest tests/test_anchor_v2.py::test_anchor_accepts_risk_landscape -v`
Expected: PASS

- [ ] **Step 5: Run all anchor tests for regressions**

Run: `cd refiner && uv run pytest tests/test_anchor.py tests/test_anchor_v2.py -v`
Expected: All PASS

- [ ] **Step 6: Run full test suite for regressions**

Run: `cd refiner && uv run pytest tests/ -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
cd refiner && git add src/refiner/stages/anchor.py tests/test_anchor_v2.py
git commit -m "feat: anchor accepts RiskLandscape as alternative input

anchor() now accepts an optional risk_landscape parameter. When
provided, it extracts risk_mappings, risk_details, risk_actions,
related_risks, and selected_domains from the landscape. Old parameter
signature still works for backward compatibility.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 7: Refactor contextualize to accept RiskLandscape

**Files:**
- Modify: `refiner/src/refiner/stages/contextualize.py`
- Test: `refiner/tests/test_contextualize_v2.py`

Same pattern as anchor — add `risk_landscape` parameter to extract `risk_details` and `selected_domains`.

- [ ] **Step 1: Write failing test**

```python
# Add to refiner/tests/test_contextualize_v2.py

def test_contextualize_accepts_risk_landscape(mock_client, mock_config, mock_onto_handlers):
    from refiner.models import (
        RiskLandscape, RiskDetail, PolicyRiskMapping, RiskMatch,
        RiskVariationAxes, VariationAxis,
    )
    from refiner.stages.contextualize import contextualize

    landscape = RiskLandscape(
        model="test-model",
        run_slug="test",
        selected_domains=["CCO", "Commons"],
        risks=[
            RiskDetail(
                risk_id="r1", risk_name="Risk One",
                risk_description="desc", risk_concern="concern",
            ),
        ],
    )

    axes = [
        RiskVariationAxes(
            risk_id="r1",
            risk_name="Risk One",
            policy_concept="Policy A",
            axes=[
                VariationAxis(
                    cco_class_uri="http://example.org/Class1",
                    cco_class_label="Class One",
                    rationale="test",
                ),
            ],
        ),
    ]

    mock_onto_handlers["get_subclasses"].return_value = []

    from unittest.mock import MagicMock
    from pydantic import BaseModel
    from typing import Literal

    class _MockVariation(BaseModel):
        instance: str
        relevance: Literal["high", "medium", "low"]

    class _MockResponse(BaseModel):
        variations: list[_MockVariation]

    mock_client.chat.completions.create.return_value = _MockResponse(
        variations=[_MockVariation(instance="test instance", relevance="high")]
    )

    result = contextualize(
        variation_axes=axes,
        client=mock_client,
        config=mock_config,
        onto_handlers=mock_onto_handlers,
        risk_landscape=landscape,
    )

    assert result.selected_domains == ["CCO", "Commons"]
    assert result.run_slug == "test"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd refiner && uv run pytest tests/test_contextualize_v2.py::test_contextualize_accepts_risk_landscape -v`
Expected: FAIL (unexpected keyword argument `risk_landscape`)

- [ ] **Step 3: Add risk_landscape parameter to contextualize()**

In `refiner/src/refiner/stages/contextualize.py`, add to imports:
```python
from refiner.models import (
    Policy,
    RiskLandscape,
    RiskVariationAxes,
    ...
)
```

Add `risk_landscape: RiskLandscape | None = None` parameter to the function signature.

At the start of the function body (before `if not variation_axes:`), add:
```python
    if risk_landscape is not None:
        selected_domains = selected_domains or risk_landscape.selected_domains
        risk_details = risk_details or {
            r.risk_id: {
                "id": r.risk_id, "name": r.risk_name,
                "description": r.risk_description or "",
                "concern": r.risk_concern or "",
            }
            for r in risk_landscape.risks
        }
        run_slug = run_slug or risk_landscape.run_slug
        timestamp = timestamp or risk_landscape.timestamp
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd refiner && uv run pytest tests/test_contextualize_v2.py::test_contextualize_accepts_risk_landscape -v`
Expected: PASS

- [ ] **Step 5: Run all contextualize tests for regressions**

Run: `cd refiner && uv run pytest tests/test_contextualize.py tests/test_contextualize_v2.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
cd refiner && git add src/refiner/stages/contextualize.py tests/test_contextualize_v2.py
git commit -m "feat: contextualize accepts RiskLandscape as alternative input

Extracts risk_details, selected_domains, run_slug, and timestamp from
the landscape when provided. Old parameter signature still works.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 8: Refactor structure.py to export layer

**Files:**
- Modify: `refiner/src/refiner/stages/structure.py` → rename to `refiner/src/refiner/export.py`
- Modify: `refiner/src/refiner/cli.py`
- Modify: `refiner/tests/test_structure.py`

Move `structure()` from a pipeline stage to an export function. Add a `export_taxonomy()` function name that better reflects its role. Keep the old name as an alias for backward compatibility.

- [ ] **Step 1: Create export.py with the taxonomy export function**

Create `refiner/src/refiner/export.py` that imports and re-exports from structure.py, adding the new function name:

```python
"""Export layer — projections from DomainContext to various formats.

The DomainContext is the canonical artifact. These functions produce
views/projections for specific consumers (AIRO taxonomy, SSSOM, etc.).
"""
from refiner.stages.structure import structure, slugify


def export_taxonomy(
    client_slug: str,
    domain_context,
    risk_mappings=None,
    risk_landscape=None,
    related_risks=None,
    valid_risk_ids=None,
    report=None,
):
    """Export DomainContext as AIRO-compatible LinkML taxonomy.

    Accepts either risk_mappings (legacy) or risk_landscape (new).
    Returns (taxonomy_dict, domain_context_dict).
    """
    if risk_mappings is None and risk_landscape is not None:
        risk_mappings = risk_landscape.policy_mappings
        if related_risks is None:
            related_risks = {
                r.risk_id: r.cross_mappings
                for r in risk_landscape.risks if r.cross_mappings
            }
        if valid_risk_ids is None:
            valid_risk_ids = {r.risk_id for r in risk_landscape.risks}

    return structure(
        client_slug=client_slug,
        risk_mappings=risk_mappings or [],
        domain_context=domain_context,
        related_risks=related_risks,
        valid_risk_ids=valid_risk_ids,
        report=report,
    )
```

- [ ] **Step 2: Write test for export_taxonomy**

```python
# Add to refiner/tests/test_structure.py

def test_export_taxonomy_from_risk_landscape():
    from refiner.export import export_taxonomy
    from refiner.models import (
        RiskLandscape, RiskDetail, PolicyRiskMapping, RiskMatch,
        DomainContext, PolicyDomainContext, RiskGrounding,
        DomainContextAxis, AxisEnumeration,
    )

    landscape = RiskLandscape(
        risks=[
            RiskDetail(
                risk_id="r1", risk_name="Risk One",
                cross_mappings=[{"id": "nist-r1", "mapping_type": "broad"}],
            ),
        ],
        policy_mappings=[
            PolicyRiskMapping(
                policy_concept="Policy A",
                matched_risks=[
                    RiskMatch(risk_id="r1", risk_name="Risk One",
                              relevance="primary", justification="test"),
                ],
            ),
        ],
    )

    dcd = DomainContext(
        policy_contexts=[
            PolicyDomainContext(
                policy_concept="Policy A",
                risk_groundings=[
                    RiskGrounding(
                        risk_id="r1",
                        axes=[
                            DomainContextAxis(
                                cco_class_uri="http://example.org/C1",
                                cco_class_label="Class One",
                                enumerations=[
                                    AxisEnumeration(
                                        class_uri="http://example.org/E1",
                                        class_label="Enum One",
                                        source_ontology="CSO",
                                        relevance="high",
                                    ),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )

    taxonomy, dc_output = export_taxonomy(
        client_slug="test",
        domain_context=dcd,
        risk_landscape=landscape,
    )

    assert len(taxonomy["entries"]) == 1
    assert taxonomy["entries"][0]["name"] == "Risk One"
    assert "broad_mappings" in taxonomy["entries"][0]
    assert "nist-r1" in taxonomy["entries"][0]["broad_mappings"]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd refiner && uv run pytest tests/test_structure.py::test_export_taxonomy_from_risk_landscape -v`
Expected: FAIL (module doesn't exist)

- [ ] **Step 4: Create the export.py file** (code from Step 1 above)

- [ ] **Step 5: Run test to verify it passes**

Run: `cd refiner && uv run pytest tests/test_structure.py::test_export_taxonomy_from_risk_landscape -v`
Expected: PASS

- [ ] **Step 6: Update cli.py to use export_taxonomy**

In `refiner/src/refiner/cli.py`, change:
```python
from refiner.stages.structure import structure
```
to:
```python
from refiner.export import export_taxonomy
```

And change the call site (around line 306) from:
```python
            taxonomy, _profiles = structure(
                client_slug, state.risk_mappings, state.domain_context,
                related_risks=state.related_risks,
                valid_risk_ids=valid_ids,
                report=report,
            )
```
to:
```python
            taxonomy, _profiles = export_taxonomy(
                client_slug,
                domain_context=state.domain_context,
                risk_landscape=state.risk_landscape,
                report=report,
            )
```

- [ ] **Step 7: Run full test suite**

Run: `cd refiner && uv run pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
cd refiner && git add src/refiner/export.py src/refiner/cli.py tests/test_structure.py
git commit -m "refactor: create export layer, move taxonomy generation out of pipeline

New export.py module with export_taxonomy() that accepts RiskLandscape.
structure.py remains for backward compat. CLI updated to use new path.
Taxonomy is now a projection/export of the DCD, not a pipeline stage.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 9: Add independent CLI commands for stage execution

**Files:**
- Modify: `refiner/src/refiner/cli.py`
- Test: `refiner/tests/test_cli.py`

Add CLI commands that run individual stages from serialized artifacts: `refiner map-risks` (reads PolicyProfile, writes RiskLandscape), `refiner ground` (reads RiskLandscape, writes DCD).

- [ ] **Step 1: Write failing test for map-risks CLI command**

```python
# Add to refiner/tests/test_cli.py

import json
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock
from typer.testing import CliRunner
from refiner.cli import app

runner = CliRunner()


def test_map_risks_cli_produces_risk_landscape(tmp_path):
    # Create input PolicyProfile
    policy_doc = {
        "organization": {"name": "TestOrg", "roles": []},
        "domain": "banking",
        "policies": [
            {"policy_concept": "Fraud", "concept_definition": "Prompts about fraud"},
        ],
    }
    input_path = tmp_path / "test-enriched.json"
    input_path.write_text(json.dumps(policy_doc))

    out_dir = tmp_path / "output"
    out_dir.mkdir()

    with patch("refiner.cli._create_risk_handlers") as mock_rh, \
         patch("refiner.stages.identify_domains.identify_domains") as mock_id, \
         patch("refiner.stages.map_risks.map_risks") as mock_mr:

        mock_id.return_value = ["CCO", "Commons", "D3FEND", "CSO", "LKIF"]
        mock_mr.return_value = (
            [],  # mappings
            {},  # risk_details
            set(),  # seen_risk_ids
            {},  # related_risks
            {},  # risk_actions
        )
        mock_rh.return_value = {}

        result = runner.invoke(app, [
            "map-risks", str(input_path),
            "--output", str(out_dir),
            "--base-url", "http://localhost:8000/v1",
            "--model", "test-model",
            "--nexus-base-dir", "/tmp/nexus",
        ])

    assert result.exit_code == 0, result.output
    # Check that risk-landscape.yaml was written
    rl_files = list(out_dir.glob("*-risk-landscape.yaml"))
    assert len(rl_files) == 1
    landscape = yaml.safe_load(rl_files[0].read_text())
    assert "version" in landscape
    assert "selected_domains" in landscape
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd refiner && uv run pytest tests/test_cli.py::test_map_risks_cli_produces_risk_landscape -v`
Expected: FAIL (no `map-risks` command)

- [ ] **Step 3: Implement map-risks CLI command**

Add to `refiner/src/refiner/cli.py`:

```python
@app.command("map-risks")
def map_risks_cmd(
    policy_json: Path = typer.Argument(..., help="Enriched PolicyProfile JSON"),
    output_dir: Path = typer.Option(None, "--output", "-o", help="Output directory"),
    base_url: str = typer.Option(None, "--base-url", envvar="REFINER_BASE_URL"),
    model: str = typer.Option(None, "--model", envvar="REFINER_MODEL"),
    api_key: str = typer.Option("none", "--api-key", envvar="REFINER_API_KEY"),
    nexus_base_dir: str = typer.Option(None, "--nexus-base-dir", envvar="NEXUS_BASE_DIR"),
    nexus_chroma_dir: Path = typer.Option(Path(".chroma"), "--nexus-chroma-dir", envvar="NEXUS_CHROMA_DIR"),
    debug_dir: Path = typer.Option(None, "--debug"),
):
    """Run risk landscape mapping on a PolicyProfile. Produces a RiskLandscape YAML artifact."""
    if not policy_json.exists():
        typer.echo(f"Error: {policy_json} does not exist", err=True)
        raise typer.Exit(1)
    if not base_url or not model:
        typer.echo("Error: --base-url and --model are required", err=True)
        raise typer.Exit(1)
    if not nexus_base_dir:
        typer.echo("Error: --nexus-base-dir is required", err=True)
        raise typer.Exit(1)

    raw = json.loads(policy_json.read_text())
    if isinstance(raw, list):
        typer.echo("Error: expected enriched PolicyProfile, got flat array. Run 'refiner ingest' first.", err=True)
        raise typer.Exit(1)
    doc = PolicyProfile(**raw)
    policies = doc.policies

    config = LLMConfig(base_url=base_url, model=model, api_key=api_key)
    tracker = TokenTracker()
    client = create_client(config, tracker=tracker)
    debug.configure(debug_dir)

    report = RunReport(
        model=config.model,
        policy_set=policy_json.name,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    risk_handlers = _create_risk_handlers(nexus_base_dir, nexus_chroma_dir)

    # Stage 1: identify domains
    from refiner.stages.identify_domains import identify_domains
    selected_domains = identify_domains(policies, client, config, report=report)

    # Stage 2: map risks
    from refiner.stages.map_risks import map_risks
    mappings, risk_details, seen_ids, related, actions = map_risks(
        policies, client, config, risk_handlers, report=report,
    )

    # Build RiskLandscape artifact
    from refiner.stages.build_landscape import build_risk_landscape
    landscape = build_risk_landscape(
        mappings=mappings,
        risk_details_cache=risk_details,
        related_risks=related,
        risk_actions=actions,
        selected_domains=selected_domains,
        model=config.model,
        run_slug=policy_json.stem,
        timestamp=report.timestamp,
        doc_context=doc,
    )

    out = output_dir or Path(".")
    out.mkdir(parents=True, exist_ok=True)
    client_slug = policy_json.stem

    rl_path = out / f"{client_slug}-risk-landscape.yaml"
    rl_path.write_text(yaml.dump(
        landscape.model_dump(), default_flow_style=False, sort_keys=False,
    ))
    typer.echo(f"Risk landscape written to {rl_path}")

    report_path = out / f"{client_slug}-report.yaml"
    report.token_usage = tracker.to_dict()
    report_path.write_text(yaml.dump(report.to_dict(), default_flow_style=False, sort_keys=False))
    typer.echo(f"Report written to {report_path}")
    _echo_token_usage(tracker)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd refiner && uv run pytest tests/test_cli.py::test_map_risks_cli_produces_risk_landscape -v`
Expected: PASS

- [ ] **Step 5: Write failing test for ground CLI command**

```python
# Add to refiner/tests/test_cli.py

def test_ground_cli_produces_dcd(tmp_path):
    # Create input RiskLandscape YAML
    landscape = {
        "version": "0.1",
        "model": "test-model",
        "timestamp": "2026-04-14T12:00:00Z",
        "run_slug": "test",
        "selected_domains": ["CCO", "Commons"],
        "risks": [
            {"risk_id": "r1", "risk_name": "Risk One", "risk_description": "desc"},
        ],
        "policy_mappings": [
            {
                "policy_concept": "Policy A",
                "matched_risks": [
                    {"risk_id": "r1", "risk_name": "Risk One",
                     "relevance": "primary", "justification": "test"},
                ],
            },
        ],
    }
    rl_path = tmp_path / "test-risk-landscape.yaml"
    rl_path.write_text(yaml.dump(landscape))

    # Create policies file
    policy_doc = {
        "organization": {"name": "TestOrg", "roles": []},
        "domain": "test",
        "policies": [
            {"policy_concept": "Policy A", "concept_definition": "test policy"},
        ],
    }
    policies_path = tmp_path / "test-enriched.json"
    policies_path.write_text(json.dumps(policy_doc))

    out_dir = tmp_path / "output"
    out_dir.mkdir()

    with patch("refiner.cli._create_onto_handlers") as mock_oh, \
         patch("refiner.stages.anchor.anchor") as mock_anchor, \
         patch("refiner.stages.contextualize.contextualize") as mock_ctx:

        from refiner.models import DomainContext
        mock_oh.return_value = {}
        mock_anchor.return_value = ([], {})
        mock_ctx.return_value = DomainContext(
            model="test-model", run_slug="test",
            selected_domains=["CCO", "Commons"],
        )

        result = runner.invoke(app, [
            "ground", str(rl_path),
            "--policies", str(policies_path),
            "--output", str(out_dir),
            "--base-url", "http://localhost:8000/v1",
            "--model", "test-model",
        ])

    assert result.exit_code == 0, result.output
    dcd_files = list(out_dir.glob("*-domain-context.yaml"))
    assert len(dcd_files) == 1
```

- [ ] **Step 6: Implement ground CLI command**

Add to `refiner/src/refiner/cli.py`:

```python
@app.command()
def ground(
    risk_landscape_yaml: Path = typer.Argument(..., help="RiskLandscape YAML from 'refiner map-risks'"),
    policies: Path = typer.Option(..., "--policies", help="Enriched PolicyProfile JSON"),
    output_dir: Path = typer.Option(None, "--output", "-o", help="Output directory"),
    base_url: str = typer.Option(None, "--base-url", envvar="REFINER_BASE_URL"),
    model: str = typer.Option(None, "--model", envvar="REFINER_MODEL"),
    api_key: str = typer.Option("none", "--api-key", envvar="REFINER_API_KEY"),
    ontoquery_chroma_dir: Path = typer.Option(Path(".chroma"), "--ontoquery-chroma-dir", envvar="ONTOQUERY_CHROMA_DIR"),
    nexus_base_dir: str = typer.Option(None, "--nexus-base-dir", envvar="NEXUS_BASE_DIR"),
    nexus_chroma_dir: Path = typer.Option(Path(".chroma"), "--nexus-chroma-dir", envvar="NEXUS_CHROMA_DIR"),
    debug_dir: Path = typer.Option(None, "--debug"),
):
    """Run ontological grounding on a RiskLandscape. Produces a DomainContext YAML + taxonomy export."""
    if not risk_landscape_yaml.exists():
        typer.echo(f"Error: {risk_landscape_yaml} does not exist", err=True)
        raise typer.Exit(1)
    if not policies.exists():
        typer.echo(f"Error: {policies} does not exist", err=True)
        raise typer.Exit(1)
    if not base_url or not model:
        typer.echo("Error: --base-url and --model are required", err=True)
        raise typer.Exit(1)

    from refiner.models import RiskLandscape
    landscape = RiskLandscape(**yaml.safe_load(risk_landscape_yaml.read_text()))

    raw = json.loads(policies.read_text())
    doc = PolicyProfile(**raw) if isinstance(raw, dict) else None
    policy_list = doc.policies if doc else [Policy(**p) for p in raw]

    config = LLMConfig(base_url=base_url, model=model, api_key=api_key)
    tracker = TokenTracker()
    client = create_client(config, tracker=tracker)
    debug.configure(debug_dir)

    report = RunReport(
        model=config.model,
        policy_set=policies.name,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    onto_handlers = _create_onto_handlers(ontoquery_chroma_dir)

    # Load SSSOM seeds
    data_dir = Path(__file__).parent.parent.parent / "data"
    layer1_path = data_dir / "risk-to-vocabulary.sssom.tsv"
    layer2_path = data_dir / "vocabulary-to-ontology.sssom.tsv"
    bfo_path = data_dir / "ontology-to-bfo.sssom.tsv"
    layer1_mappings = None
    layer2_mappings = None
    bfo_fallbacks = None
    if layer1_path.exists() and layer2_path.exists():
        from refiner.ontology_seeds import SSSOMIndex, load_bfo_fallbacks
        layer1_mappings = SSSOMIndex.from_tsv(layer1_path)
        layer2_mappings = SSSOMIndex.from_tsv(layer2_path, expand_objects=True)
        if bfo_path.exists():
            bfo_fallbacks = load_bfo_fallbacks(bfo_path)

    # Optional: nexus handlers for SSSOM resolution
    nexus_handlers = None
    if nexus_base_dir:
        nexus_handlers = _create_risk_handlers(nexus_base_dir, nexus_chroma_dir)

    # Compute CSO safety filter
    from refiner.stages.anchor import anchor, build_generic_safety_uris
    from refiner.stages.identify_domains import ALWAYS_INCLUDED
    generic_safety_uris: set[str] = set()
    domain_specific = set(landscape.selected_domains) - set(ALWAYS_INCLUDED)
    if domain_specific:
        uris = build_generic_safety_uris(onto_handlers)
        if uris:
            generic_safety_uris = uris

    # Anchor
    variation_axes, vocabulary_contexts = anchor(
        risk_landscape=landscape,
        client=client,
        config=config,
        onto_handlers=onto_handlers,
        nexus_handlers=nexus_handlers,
        layer1_mappings=layer1_mappings,
        layer2_mappings=layer2_mappings,
        report=report,
        generic_safety_uris=generic_safety_uris,
        policies=policy_list,
        bfo_fallbacks=bfo_fallbacks,
    )

    # Contextualize
    from refiner.stages.contextualize import contextualize
    dcd = contextualize(
        variation_axes, client, config, onto_handlers,
        risk_landscape=landscape,
        report=report,
        policies=policy_list,
        vocabulary_contexts=vocabulary_contexts,
    )

    # Enrich DCD with framework labels and cross-mappings from landscape
    for risk in dcd.risks:
        for lr in landscape.risks:
            if lr.risk_id == risk.risk_id:
                risk.risk_framework = lr.risk_framework or ""
                risk.cross_mappings = lr.cross_mappings
                break
    if doc:
        from refiner.models import PolicySourceRef
        dcd.policy_source = PolicySourceRef(
            organization=doc.organization.name if doc.organization else None,
            domain=doc.domain,
            policy_count=len(doc.policies),
        )

    out = output_dir or Path(".")
    out.mkdir(parents=True, exist_ok=True)
    client_slug = risk_landscape_yaml.stem.replace("-risk-landscape", "")

    # Write DCD
    dcd_path = out / f"{client_slug}-domain-context.yaml"
    dcd_path.write_text(yaml.dump(
        dcd.model_dump(), default_flow_style=False, sort_keys=False,
    ))
    typer.echo(f"Domain context written to {dcd_path}")

    # Export taxonomy
    from refiner.export import export_taxonomy
    taxonomy, _ = export_taxonomy(
        client_slug,
        domain_context=dcd,
        risk_landscape=landscape,
        report=report,
    )
    tax_path = out / f"{client_slug}-taxonomy.yaml"
    tax_path.write_text(yaml.dump(taxonomy, default_flow_style=False, sort_keys=False))
    typer.echo(f"Taxonomy written to {tax_path}")

    report.token_usage = tracker.to_dict()
    report_path = out / f"{client_slug}-report.yaml"
    report_path.write_text(yaml.dump(report.to_dict(), default_flow_style=False, sort_keys=False))
    typer.echo(f"Report written to {report_path}")
    _echo_token_usage(tracker)
```

- [ ] **Step 7: Run tests to verify both CLI commands work**

Run: `cd refiner && uv run pytest tests/test_cli.py::test_map_risks_cli_produces_risk_landscape tests/test_cli.py::test_ground_cli_produces_dcd -v`
Expected: 2 PASS

- [ ] **Step 8: Run full test suite**

Run: `cd refiner && uv run pytest tests/ -v`
Expected: All PASS

- [ ] **Step 9: Commit**

```bash
cd refiner && git add src/refiner/cli.py tests/test_cli.py
git commit -m "feat: add independent CLI commands for stage execution

New commands:
- refiner map-risks: PolicyProfile → RiskLandscape (YAML)
- refiner ground: RiskLandscape → DomainContext + taxonomy (YAML)

Each stage is now independently runnable from serialized artifacts,
enabling decoupled tool extraction and incremental re-runs.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 10: Update data-architecture.md with new artifact stages

**Files:**
- Modify: `docs/data-architecture.md`

- [ ] **Step 1: Add data artifact stages section**

Add a new section after the existing "9. Data boundary summary" section in `docs/data-architecture.md`:

```markdown
## 10. Data artifact stages

Each stage consumes serialized artifacts and produces new ones. Every stage is
independently runnable via CLI.

| Stage | CLI command | Input artifacts | Output data artifact | Output presentation |
|-------|-------------|-----------------|---------------------|-------------------|
| 0. Index | `just index-ontologies` | Ontology files (TTL/RDF/OWL) + Nexus YAML | ChromaDB + Oxigraph + manifest.json | Index report |
| 1. Canonicalize | `refiner ingest` | Raw policy (JSON/MD) | `PolicyProfile` (JSON) | Ingest report (HTML) |
| 2. Map Risk Landscape | `refiner map-risks` | `PolicyProfile` + Risk Knowledge Graph | `RiskLandscape` (YAML) | Risk landscape report |
| 3. Ground in Ontology | `refiner ground` | `RiskLandscape` + Ontology Index | `DomainContext` (YAML) + taxonomy.yaml export | Grounding report |
| 4. Emit Dataset | `refiner emit` | `DomainContext` + `PolicyProfile` | `dataset.jsonl` | Dataset report |
| 5. Generate | `redteam` | `dataset.jsonl` | `adversarial_prompts.jsonl` | Prompt browser (HTML) |
| 6. Evaluate | `refiner evaluate` | All prior artifacts | `evaluation.json` | Evaluation dashboard (HTML) |

### Convergence-divergence pattern

```
Raw Policy ─── canonicalize ──► PolicyProfile
                                    │
Risk Knowledge ── map risks ──► RiskLandscape
                                    │
Ontology Index ── ground ─────► DomainContext  ◄── THE HUB
                                    │
                          ┌─────────┼─────────┐
                          ▼         ▼         ▼
                    Adversarial   Utility    Training
                    Prompts     Benchmarks    Data
```

The `DomainContext` is the central artifact. Everything before it
converges toward building it; everything after diverges into specific uses.

### Export layer

The taxonomy is NOT a pipeline stage — it's an export/projection of the
`DomainContext` in AIRO-compatible LinkML format. Generated by default
alongside the DCD. Other future exports:

- SSSOM mapping file (cross-mappings in standard TSV)
- Compliance matrix (risks × frameworks × controls)
- SKOS concept scheme (for vocabulary interop)
```

- [ ] **Step 2: Commit**

```bash
git add docs/data-architecture.md
git commit -m "docs: document data artifact stages and convergence-divergence pattern

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 11: Clean up — remove redundant PipelineState cache fields

**Files:**
- Modify: `refiner/src/refiner/pipeline.py`
- Test: `refiner/tests/test_pipeline.py`

Now that `RiskLandscape` consolidates the scattered caches, the old cache fields in `PipelineState` can be deprecated. Keep them for now but add a property that extracts them from `risk_landscape` when available, so downstream code doesn't break.

- [ ] **Step 1: Write test for backward-compatible extraction**

```python
# Add to refiner/tests/test_pipeline.py

def test_pipeline_state_extracts_risk_details_from_landscape():
    from refiner.pipeline import PipelineState
    from refiner.models import (
        Policy, RiskLandscape, RiskDetail,
        PolicyRiskMapping, RiskMatch,
    )

    landscape = RiskLandscape(
        risks=[
            RiskDetail(
                risk_id="r1", risk_name="Risk One",
                risk_description="desc", risk_concern="concern",
                related_actions=["act1"],
                cross_mappings=[{"id": "x1", "mapping_type": "broad"}],
            ),
        ],
        policy_mappings=[
            PolicyRiskMapping(
                policy_concept="P1",
                matched_risks=[
                    RiskMatch(risk_id="r1", risk_name="Risk One",
                              relevance="primary", justification="j"),
                ],
            ),
        ],
    )

    state = PipelineState(policies=[], risk_landscape=landscape)

    # Old-style access should still work via landscape
    assert state.risk_mappings_resolved is not None
    assert len(state.risk_mappings_resolved) == 1
    assert state.risk_details_resolved["r1"]["name"] == "Risk One"
    assert state.risk_actions_resolved["r1"] == ["act1"]
    assert state.related_risks_resolved["r1"] == [{"id": "x1", "mapping_type": "broad"}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd refiner && uv run pytest tests/test_pipeline.py::test_pipeline_state_extracts_risk_details_from_landscape -v`
Expected: FAIL (no such properties)

- [ ] **Step 3: Add resolver properties to PipelineState**

In `refiner/src/refiner/pipeline.py`, add properties to PipelineState:

```python
    @property
    def risk_mappings_resolved(self) -> list[PolicyRiskMapping] | None:
        if self.risk_mappings is not None:
            return self.risk_mappings
        if self.risk_landscape is not None:
            return self.risk_landscape.policy_mappings
        return None

    @property
    def risk_details_resolved(self) -> dict[str, dict] | None:
        if self.risk_details is not None:
            return self.risk_details
        if self.risk_landscape is not None:
            return {
                r.risk_id: {
                    "id": r.risk_id, "name": r.risk_name,
                    "description": r.risk_description or "",
                    "concern": r.risk_concern or "",
                }
                for r in self.risk_landscape.risks
            }
        return None

    @property
    def risk_actions_resolved(self) -> dict[str, list[str]] | None:
        if self.risk_actions is not None:
            return self.risk_actions
        if self.risk_landscape is not None:
            return {
                r.risk_id: r.related_actions
                for r in self.risk_landscape.risks if r.related_actions
            }
        return None

    @property
    def related_risks_resolved(self) -> dict[str, list[dict]] | None:
        if self.related_risks is not None:
            return self.related_risks
        if self.risk_landscape is not None:
            return {
                r.risk_id: r.cross_mappings
                for r in self.risk_landscape.risks if r.cross_mappings
            }
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd refiner && uv run pytest tests/test_pipeline.py::test_pipeline_state_extracts_risk_details_from_landscape -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `cd refiner && uv run pytest tests/ -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
cd refiner && git add src/refiner/pipeline.py tests/test_pipeline.py
git commit -m "feat: add resolver properties to PipelineState for RiskLandscape compat

PipelineState now has *_resolved properties that extract data from
risk_landscape when the old cache fields are None. Enables gradual
migration — old code reads caches, new code reads landscape.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```
