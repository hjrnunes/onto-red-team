# Domain Context Document Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat `list[DomainContextProfile]` output with a typed `DomainContext` envelope that normalizes risk data, groups groundings by policy, and carries pipeline provenance metadata.

**Architecture:** Add new Pydantic models to `models.py`, update `contextualize` to return a `DomainContext`, update all consumers (structure, emit, evaluate, provenance) to traverse the new structure, remove the old `DomainContextProfile` model.

**Tech Stack:** Pydantic, PyYAML, existing refiner pipeline

**Spec:** `docs/superpowers/specs/2026-04-14-domain-context-document-design.md`

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `refiner/src/refiner/models.py` | Add new models, update DomainContextAxis, remove DomainContextProfile |
| Modify | `refiner/src/refiner/stages/contextualize.py` | Return DomainContext instead of list[DomainContextProfile] |
| Modify | `refiner/src/refiner/pipeline.py` | Update PipelineState field type |
| Modify | `refiner/src/refiner/cli.py` | Risk enrichment builds RiskSummary list, YAML write uses document |
| Modify | `refiner/src/refiner/stages/structure.py` | Consume DomainContext |
| Modify | `refiner/src/refiner/emit.py` | Load and iterate DomainContext |
| Modify | `refiner/src/refiner/evaluate.py` | Update dict traversal for new YAML shape |
| Modify | `refiner/src/refiner/provenance.py` | Traverse new document structure |
| Modify | `refiner/tests/test_models.py` | Update model tests |
| Modify | `refiner/tests/test_contextualize_v2.py` | Update contextualize tests |
| Modify | `refiner/tests/test_pipeline.py` | Update pipeline threading test |
| Modify | `refiner/tests/test_structure.py` | Update structure tests |
| Modify | `refiner/tests/test_emit.py` | Update emit tests |
| Modify | `refiner/tests/test_evaluate.py` | Update evaluate tests |

---

### Task 1: Add New Models

**Files:**
- Modify: `refiner/src/refiner/models.py`
- Test: `refiner/tests/test_models.py`

- [ ] **Step 1: Write tests for new models**

Add to `refiner/tests/test_models.py`:

```python
from refiner.models import (
    VocabularyContext,
    PolicySourceRef,
    PipelineConfig,
    RiskSummary,
    RiskGrounding,
    PolicyDomainContext,
    DomainContext,
    DomainContextAxis,
    AxisEnumeration,
)


def test_vocabulary_context_defaults():
    vc = VocabularyContext()
    assert vc.stakeholders == []
    assert vc.prohibited_practices == []


def test_vocabulary_context_from_dict():
    vc = VocabularyContext(stakeholders=[{"concept_id": "airo:AIUser", "label": "AI User", "confidence": 0.9}])
    assert len(vc.stakeholders) == 1
    assert vc.stakeholders[0]["label"] == "AI User"


def test_risk_summary():
    rs = RiskSummary(risk_id="mit-7.4", risk_name="Lack of transparency")
    assert rs.risk_id == "mit-7.4"
    assert rs.cross_mappings == []


def test_risk_grounding():
    axis = DomainContextAxis(
        cco_class_uri="http://ex/P", cco_class_label="Person",
        enumerations=[AxisEnumeration(class_uri="http://ex/E", class_label="Employee",
                                       source_ontology="CCO", relevance="high")],
    )
    rg = RiskGrounding(risk_id="mit-7.4", axes=[axis])
    assert rg.risk_id == "mit-7.4"
    assert len(rg.axes) == 1


def test_policy_domain_context():
    pdc = PolicyDomainContext(policy_concept="Fraud", risk_groundings=[])
    assert pdc.policy_concept == "Fraud"


def test_domain_context_document_defaults():
    doc = DomainContext()
    assert doc.version == "0.1"
    assert doc.risks == []
    assert doc.policy_contexts == []


def test_domain_context_document_full():
    doc = DomainContext(
        model="phi-4",
        timestamp="2026-04-14T12:00:00",
        run_slug="my-run",
        selected_domains=["CCO", "FIBO"],
        policy_source=PolicySourceRef(organization="DHS", domain="government", policy_count=3),
        config=PipelineConfig(weak_match_threshold=0.4),
        risks=[RiskSummary(risk_id="r1", risk_name="Risk 1")],
        policy_contexts=[PolicyDomainContext(policy_concept="Fraud", risk_groundings=[])],
    )
    assert doc.model == "phi-4"
    assert len(doc.risks) == 1
    assert len(doc.policy_contexts) == 1


def test_domain_context_axis_vocabulary_context_typed():
    vc = VocabularyContext(stakeholders=[{"label": "AI User"}])
    axis = DomainContextAxis(
        cco_class_uri="http://ex/P", cco_class_label="Person",
        vocabulary_context=vc,
        enumerations=[],
    )
    assert isinstance(axis.vocabulary_context, VocabularyContext)
    assert axis.vocabulary_context.stakeholders[0]["label"] == "AI User"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd refiner && uv run pytest tests/test_models.py -v -k "vocabulary_context or risk_summary or risk_grounding or policy_domain_context or domain_context_document or domain_context_axis_vocabulary" 2>&1 | head -30`

Expected: ImportError — new models don't exist yet.

- [ ] **Step 3: Add new models to models.py**

Add after the `PolicyProfile` class (after line 73) and before `RiskMatch`:

```python
# --- Domain context document envelope ---


class VocabularyContext(BaseModel):
    stakeholders: list[dict] = []
    data_sensitivity: list[dict] = []
    rights: list[dict] = []
    justifications: list[dict] = []
    sector_purposes: list[dict] = []
    risk_concepts: list[dict] = []
    prohibited_practices: list[dict] = []


class PolicySourceRef(BaseModel):
    organization: str | None = None
    domain: str | None = None
    policy_count: int = 0


class PipelineConfig(BaseModel):
    weak_match_threshold: float = 0.4
    max_axes_per_risk: int = 3
    enumerations_per_axis: int = 8


class RiskSummary(BaseModel):
    risk_id: str
    risk_name: str
    risk_description: str | None = ""
    risk_concern: str | None = ""
    risk_framework: str | None = ""
    cross_mappings: list[dict] = []
```

Then update `DomainContextAxis.vocabulary_context` field type from `dict = {}` to `VocabularyContext = VocabularyContext()`. Add a field validator to coerce raw dicts:

```python
class DomainContextAxis(BaseModel):
    cco_class_uri: str
    cco_class_label: str
    bfo_category: str = ""
    vocabulary_concept: str = ""
    vocabulary_label: str = ""
    vocabulary_context: VocabularyContext = VocabularyContext()
    derivation: AxisDerivation | None = None
    enumerations: list[AxisEnumeration]
    roles: list[str] = []

    @field_validator("vocabulary_context", mode="before")
    @classmethod
    def _coerce_vocabulary_context(cls, v):
        if isinstance(v, dict):
            return VocabularyContext(**v)
        return v
```

Then add after `DomainContextProfile` (keep `DomainContextProfile` for now — it will be removed in Task 9):

```python
class RiskGrounding(BaseModel):
    risk_id: str
    axes: list[DomainContextAxis]


class PolicyDomainContext(BaseModel):
    policy_concept: str
    risk_groundings: list[RiskGrounding]


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

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd refiner && uv run pytest tests/test_models.py -v 2>&1 | tail -20`

Expected: All tests pass, including the existing `test_domain_context_profile` test (it still uses old model).

- [ ] **Step 5: Commit**

```bash
cd refiner && git add src/refiner/models.py tests/test_models.py
git commit -m "feat: add DomainContext envelope models and typed VocabularyContext"
```

---

### Task 2: Update Contextualize Stage

**Files:**
- Modify: `refiner/src/refiner/stages/contextualize.py`
- Test: `refiner/tests/test_contextualize_v2.py`

- [ ] **Step 1: Update tests to expect DomainContext**

In `refiner/tests/test_contextualize_v2.py`, update imports to include the new models:

```python
from refiner.models import (
    RiskVariationAxes, VariationAxis,
    DomainContext, PolicyDomainContext, RiskGrounding, RiskSummary,
)
```

Update each test to assert on `DomainContext` structure. The key pattern change is:

Old:
```python
result = contextualize(...)
assert len(result) == 1
assert result[0].risk_id == "r1"
assert result[0].axes[0].cco_class_label == "Person"
```

New:
```python
result = contextualize(...)
assert isinstance(result, DomainContext)
assert len(result.policy_contexts) == 1
pc = result.policy_contexts[0]
assert pc.policy_concept == "Fraud"
assert len(pc.risk_groundings) == 1
rg = pc.risk_groundings[0]
assert rg.risk_id == "r1"
assert rg.axes[0].cco_class_label == "Person"
```

For the cache test, verify that two RiskVariationAxes with the same risk_id but different policy_concept produce two `PolicyDomainContext` entries sharing the same risk grounding axes. Also verify `result.risks` is populated from `risk_details`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd refiner && uv run pytest tests/test_contextualize_v2.py -v 2>&1 | tail -20`

Expected: FAIL — contextualize still returns `list[DomainContextProfile]`.

- [ ] **Step 3: Update contextualize to return DomainContext**

In `refiner/src/refiner/stages/contextualize.py`:

Update imports:
```python
from refiner.models import (
    Policy,
    RiskVariationAxes,
    DomainContext,
    PolicyDomainContext,
    RiskGrounding,
    RiskSummary,
    DomainContextAxis,
    AxisEnumeration,
    RunReport,
)
```

Add new parameters to the function signature for envelope metadata:
```python
def contextualize(
    variation_axes: list[RiskVariationAxes],
    client: instructor.Instructor,
    config: LLMConfig,
    onto_handlers: dict,
    selected_domains: list[str] | None = None,
    risk_details: dict[str, dict] | None = None,
    report: RunReport | None = None,
    policies: list[Policy] | None = None,
    vocabulary_contexts: dict[str, dict] | None = None,
    run_slug: str = "",
    timestamp: str = "",
) -> DomainContext:
```

Replace the internal accumulation logic. Instead of `results: list[DomainContextProfile]`, track:

```python
    context_cache: dict[str, list[DomainContextAxis]] = {}
    # Accumulate per-policy groundings
    policy_groundings: dict[str, list[RiskGrounding]] = {}  # policy_concept -> groundings
    seen_risk_ids: set[str] = set()
```

In each loop iteration, after building `populated_axes` (or retrieving from cache), instead of appending a `DomainContextProfile`:

```python
        grounding = RiskGrounding(risk_id=rva.risk_id, axes=context_cache[rva.risk_id])
        policy_groundings.setdefault(rva.policy_concept, []).append(grounding)
        seen_risk_ids.add(rva.risk_id)
```

At the end, build and return the document:

```python
    # Build risk summaries from risk_details
    risks = []
    for rid in seen_risk_ids:
        details = risk_details.get(rid, {}) if risk_details else {}
        risks.append(RiskSummary(
            risk_id=rid,
            risk_name=details.get("name", ""),
            risk_description=details.get("description", ""),
            risk_concern=details.get("concern", ""),
        ))

    policy_contexts = [
        PolicyDomainContext(policy_concept=pc, risk_groundings=groundings)
        for pc, groundings in policy_groundings.items()
    ]

    return DomainContext(
        model=config.model,
        timestamp=timestamp,
        run_slug=run_slug,
        selected_domains=selected_domains or [],
        risks=risks,
        policy_contexts=policy_contexts,
    )
```

Note: `risk_name` for `RiskSummary` — look it up from the variation_axes since each `RiskVariationAxes` carries `risk_name`. Accumulate a `risk_names: dict[str, str]` mapping during iteration and use it in the summary construction:

```python
    risk_names: dict[str, str] = {}
    # ... inside loop:
    risk_names[rva.risk_id] = rva.risk_name
    # ... in summary construction:
    risks.append(RiskSummary(
        risk_id=rid,
        risk_name=risk_names.get(rid, ""),
        ...
    ))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd refiner && uv run pytest tests/test_contextualize_v2.py -v 2>&1 | tail -20`

Expected: All contextualize tests pass.

- [ ] **Step 5: Commit**

```bash
cd refiner && git add src/refiner/stages/contextualize.py tests/test_contextualize_v2.py
git commit -m "feat: contextualize returns DomainContext with envelope metadata"
```

---

### Task 3: Update PipelineState and Pipeline Orchestration

**Files:**
- Modify: `refiner/src/refiner/pipeline.py`
- Test: `refiner/tests/test_pipeline.py`

- [ ] **Step 1: Update pipeline test**

In `refiner/tests/test_pipeline.py`, update imports and the mock contextualize return value. Instead of returning `list[DomainContextProfile]`, return a `DomainContext`:

```python
from refiner.models import (
    ...,
    DomainContext, PolicyDomainContext, RiskGrounding,
    DomainContextAxis,
)
```

Update the `context_result` fixture:
```python
    context_result = DomainContext(
        model="test-model",
        policy_contexts=[
            PolicyDomainContext(
                policy_concept="Fraud",
                risk_groundings=[
                    RiskGrounding(
                        risk_id="r1",
                        axes=[DomainContextAxis(
                            cco_class_uri="http://ex/P", cco_class_label="P",
                            enumerations=[],
                        )],
                    ),
                ],
            ),
        ],
    )
```

Update the assertion from `assert state.domain_context == context_result` to verify the document structure:
```python
    assert isinstance(state.domain_context, DomainContext)
    assert len(state.domain_context.policy_contexts) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd refiner && uv run pytest tests/test_pipeline.py -v 2>&1 | tail -20`

Expected: FAIL — PipelineState.domain_context still typed as `list[DomainContextProfile] | None`.

- [ ] **Step 3: Update pipeline.py**

In `refiner/src/refiner/pipeline.py`:

Update imports:
```python
from refiner.models import (
    ...,
    DomainContext,
)
```

Change `PipelineState.domain_context` field type (line 36):
```python
    domain_context: DomainContext | None = None
```

Pass `run_slug` and `timestamp` to the `contextualize` call. The `run_slug` needs to come from somewhere — add it to PipelineState as an optional field:
```python
    run_slug: str = ""
```

Update the contextualize call to pass new params:
```python
    state.domain_context = contextualize(
        state.variation_axes, client, config, onto_handlers,
        selected_domains=state.selected_domains,
        risk_details=state.risk_details,
        report=report,
        policies=policies,
        vocabulary_contexts=state.vocabulary_contexts,
        run_slug=state.run_slug,
        timestamp=report.timestamp if report else "",
    )
```

Remove `DomainContextProfile` from imports if no longer used.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd refiner && uv run pytest tests/test_pipeline.py -v 2>&1 | tail -20`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd refiner && git add src/refiner/pipeline.py tests/test_pipeline.py
git commit -m "feat: PipelineState.domain_context now holds DomainContext"
```

---

### Task 4: Update CLI — Risk Enrichment and YAML Writing

**Files:**
- Modify: `refiner/src/refiner/cli.py`
- Test: `refiner/tests/test_cli.py`

- [ ] **Step 1: Update cli.py risk enrichment and YAML writing**

In `refiner/src/refiner/cli.py`, the block at lines 271-316 needs reworking.

Currently it iterates `state.domain_context` (list of profiles) to attach risk metadata. With the new structure, risk metadata is already in `doc.risks` (populated by contextualize from `risk_details`). What cli.py still needs to do:

1. Enrich `doc.risks` with `risk_framework` labels and `cross_mappings` (these aren't in `risk_details` directly)
2. Set `doc.policy_source` from the `PolicyProfile`
3. Write the document to YAML

Replace the profile enrichment loop (lines 285-297) with:

```python
        doc = state.domain_context  # DomainContext
        FRAMEWORK_LABELS = { ... }  # same as before

        # Enrich risk summaries with framework labels and cross-mappings
        for risk in doc.risks:
            for prefix, label in FRAMEWORK_LABELS.items():
                if risk.risk_id.startswith(prefix):
                    risk.risk_framework = label
                    break
            if state.related_risks:
                risk.cross_mappings = state.related_risks.get(risk.risk_id, [])

        # Set policy source from PolicyProfile
        if state.doc_context:
            from refiner.models import PolicySourceRef
            doc.policy_source = PolicySourceRef(
                organization=state.doc_context.organization.name if state.doc_context.organization else None,
                domain=state.doc_context.domain,
                policy_count=len(state.doc_context.policies),
            )

        # Set pipeline config snapshot
        from refiner.models import PipelineConfig
        doc.config = PipelineConfig(
            weak_match_threshold=config.get("weak_match_threshold", 0.4),
            max_axes_per_risk=config.get("max_axes_per_risk", 3),
            enumerations_per_axis=config.get("enumerations_per_axis", 8),
        )
```

Update the `structure()` call to pass the document:
```python
        taxonomy, dc_output = structure(
            client_slug, state.risk_mappings, state.domain_context,
            related_risks=state.related_risks,
            valid_risk_ids=valid_ids,
            report=report,
        )
```

Update YAML writing (lines 314-316) to serialize the document:
```python
        prof_path = out / f"{client_slug}-domain-context.yaml"
        prof_path.write_text(yaml.dump(
            doc.model_dump(), default_flow_style=False, sort_keys=False,
        ))
```

Also, set `state.run_slug` before calling `run_pipeline`. In the `run` command, after determining `client_slug`:
```python
        state = PipelineState(policies=doc.policies if doc else policies)
        state.run_slug = client_slug
```

- [ ] **Step 2: Run CLI tests**

Run: `cd refiner && uv run pytest tests/test_cli.py -v 2>&1 | tail -30`

Expected: May need test fixture updates in `test_cli.py` for mocked pipeline returns. Update mock return values to return `DomainContext` objects and update assertions on the written YAML content. The key change: the YAML file no longer has `{"profiles": [...]}` at the top — it has the full document envelope.

- [ ] **Step 3: Fix any failing CLI tests**

Update test fixtures and assertions as needed based on failures.

- [ ] **Step 4: Commit**

```bash
cd refiner && git add src/refiner/cli.py tests/test_cli.py
git commit -m "feat: cli enriches DomainContext risks and writes envelope YAML"
```

---

### Task 5: Update Structure Stage

**Files:**
- Modify: `refiner/src/refiner/stages/structure.py`
- Test: `refiner/tests/test_structure.py`

- [ ] **Step 1: Update structure tests**

In `refiner/tests/test_structure.py`, update imports:
```python
from refiner.models import (
    ...,
    DomainContext, PolicyDomainContext, RiskGrounding,
    DomainContextAxis, AxisEnumeration,
)
```

Update `_make_state_data()` helper — instead of building `domain_context = [DomainContextProfile(...)]`, build a `DomainContext`:

```python
    domain_context = DomainContext(
        policy_contexts=[
            PolicyDomainContext(
                policy_concept="Fraud",
                risk_groundings=[
                    RiskGrounding(
                        risk_id="atlas-fraud",
                        axes=[
                            DomainContextAxis(
                                cco_class_uri="http://example.org/Person",
                                cco_class_label="Person",
                                enumerations=[
                                    AxisEnumeration(class_uri="http://example.org/Employee",
                                                    class_label="Employee",
                                                    source_ontology="CCO", relevance="high"),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )
```

Update `test_structure_profiles_output` — the structure function no longer returns `{"profiles": [...]}`. It returns the `DomainContext.model_dump()` dict (or the document object itself — check structure.py return type changes).

Update `test_structure_includes_domain_context_summary` and `test_structure_summary_with_multiple_axes` to build their fixtures with the new structure.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd refiner && uv run pytest tests/test_structure.py -v 2>&1 | tail -30`

Expected: FAIL — structure() still expects `list[DomainContextProfile]`.

- [ ] **Step 3: Update structure.py**

Update imports:
```python
from refiner.models import (
    PolicyRiskMapping,
    DomainContext,
    RunReport,
)
```

Change function signature:
```python
def structure(
    client_slug: str,
    risk_mappings: list[PolicyRiskMapping],
    domain_context: DomainContext,
    related_risks: dict[str, list[dict]] | None = None,
    valid_risk_ids: set[str] | None = None,
    report: RunReport | None = None,
) -> tuple[dict, dict]:
```

Replace the `dc_by_risk_id` lookup construction. The new structure groups by policy → risk, so build a lookup from risk_id to axes across all policy contexts:

```python
    # Build lookup from risk_id to axes (first occurrence wins)
    dc_axes_by_risk_id: dict[str, list] = {}
    for pc in domain_context.policy_contexts:
        for rg in pc.risk_groundings:
            if rg.risk_id not in dc_axes_by_risk_id:
                dc_axes_by_risk_id[rg.risk_id] = rg.axes
```

Update the domain_context_summary block (lines 88-110) to use `dc_axes_by_risk_id`:
```python
            if "domain_context_summary" not in entry:
                axes = dc_axes_by_risk_id.get(rm.risk_id, [])
                if axes:
                    axes_summary = []
                    all_ontologies: set[str] = set()
                    total_enums = 0
                    for axis in axes:
                        enum_count = len(axis.enumerations)
                        total_enums += enum_count
                        for e in axis.enumerations:
                            all_ontologies.add(e.source_ontology)
                        axes_summary.append({
                            "class": axis.cco_class_label,
                            "uri": axis.cco_class_uri,
                            "roles": axis.roles,
                            "enumeration_count": enum_count,
                        })
                    entry["domain_context_summary"] = {
                        "axis_count": len(axes_summary),
                        "enumeration_count": total_enums,
                        "source_ontologies": sorted(all_ontologies),
                        "axes": axes_summary,
                    }
```

Update the profiles output at the end — instead of `{"profiles": [p.model_dump() ...]}`, return the document dict:
```python
    dc_output = domain_context.model_dump()
    return taxonomy, dc_output
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd refiner && uv run pytest tests/test_structure.py -v 2>&1 | tail -30`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd refiner && git add src/refiner/stages/structure.py tests/test_structure.py
git commit -m "feat: structure stage consumes DomainContext"
```

---

### Task 6: Update Emit Stage

**Files:**
- Modify: `refiner/src/refiner/emit.py`
- Test: `refiner/tests/test_emit.py`

- [ ] **Step 1: Update emit tests**

In `refiner/tests/test_emit.py`, update imports:
```python
from refiner.models import (
    AxisEnumeration,
    DomainContext, PolicyDomainContext, RiskGrounding, RiskSummary,
    DomainContextAxis, SampledAxis, Stakeholder,
)
```

Update `_make_profile()` helper to return a `DomainContext` (or adjust to return `PolicyDomainContext` + `RiskGrounding` as needed by the test). The key change: `sample_axes` signature changes from `sample_axes(profile, n)` to `sample_axes(axes, n)` since it only needs the axes list, not the full profile. Or alternatively, it takes a `RiskGrounding`.

For the `test_load_domain_context` test, update the YAML fixture to use the new envelope shape and verify the returned `DomainContext`.

For `test_emit_writes_jsonl` and related tests, update the YAML fixture and assertions.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd refiner && uv run pytest tests/test_emit.py -v 2>&1 | tail -30`

Expected: FAIL.

- [ ] **Step 3: Update emit.py**

Update imports:
```python
from refiner.models import (
    DomainContext, PolicyDomainContext, RiskGrounding, RiskSummary,
    DomainContextAxis, AxisEnumeration, SampledAxis, Policy, PolicyProfile,
)
```

Update `load_domain_context()`:
```python
def load_domain_context(path: Path) -> DomainContext:
    raw = yaml.safe_load(path.read_text())
    return DomainContext(**raw)
```

Update `sample_axes()` — change parameter from `profile: DomainContextProfile` to `axes: list[DomainContextAxis]`:
```python
def sample_axes(
    axes: list[DomainContextAxis],
    n: int,
) -> list[list[SampledAxis]]:
    usable_axes = [a for a in axes if a.enumerations]
    # ... rest unchanged
```

Update `emit()` function — restructure the iteration:
```python
def emit(
    output_dir: Path,
    policies_path: Path,
    samples_per_risk: int,
    output_path: Path,
    seed: int | None = None,
    technique_weights: dict[str, float] | None = None,
) -> None:
    dc_path = _discover_domain_context(output_dir)
    doc = load_domain_context(dc_path)
    policy_map, doc_context = load_policies(policies_path)

    if seed is not None:
        random.seed(seed)

    weights = technique_weights or DEFAULT_WEIGHTS

    # Build risk lookup
    risk_by_id = {r.risk_id: r for r in doc.risks}

    logger.info("Loaded %d policy contexts from %s", len(doc.policy_contexts), dc_path.name)

    rows: list[dict] = []
    for pc in doc.policy_contexts:
        policy = policy_map.get(pc.policy_concept)
        if policy is None:
            policy = _fuzzy_match_policy(pc.policy_concept, policy_map)
            if policy is not None:
                logger.info(
                    "Fuzzy-matched policy_concept '%s' to '%s'",
                    pc.policy_concept, policy.policy_concept,
                )
            else:
                logger.warning(
                    "Skipping policy_concept '%s' — not found in policies",
                    pc.policy_concept,
                )
                continue

        for grounding in pc.risk_groundings:
            risk = risk_by_id.get(grounding.risk_id)
            risk_name = risk.risk_name if risk else ""
            risk_description = risk.risk_description if risk else ""
            risk_concern = risk.risk_concern if risk else ""
            risk_framework = risk.risk_framework if risk else ""
            cross_mappings = risk.cross_mappings if risk else []

            samples = sample_axes(grounding.axes, n=samples_per_risk)
            if not samples:
                logger.warning("Skipping risk %s — no usable axes", grounding.risk_id)
                continue

            for sampled in samples:
                frame = select_frame(
                    weights,
                    risk_name=risk_name,
                    risk_description=risk_description or "",
                )
                prompt = build_prompt(
                    pc.policy_concept,
                    policy.concept_definition,
                    risk_name,
                    sampled,
                    policy=policy,
                    doc_context=doc_context,
                    frame=frame,
                )
                row = {
                    "generation_prompt": prompt,
                    "policy_concept": pc.policy_concept,
                    "concept_definition": policy.concept_definition,
                    "decomposition": policy.decomposition.model_dump() if policy.decomposition else None,
                    "risk_id": grounding.risk_id,
                    "risk_name": risk_name,
                    "risk_description": risk_description,
                    "risk_concern": risk_concern,
                    "risk_framework": risk_framework,
                    "cross_mappings": cross_mappings,
                    "technique": frame.name,
                    "technique_description": frame.description,
                    "sampled_axes": [sa.model_dump() for sa in sampled],
                    "domain_context_axes": [a.model_dump() for a in grounding.axes],
                }
                rows.append(row)

    # ... rest (write JSONL, curie_map, provenance) unchanged
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd refiner && uv run pytest tests/test_emit.py -v 2>&1 | tail -30`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd refiner && git add src/refiner/emit.py tests/test_emit.py
git commit -m "feat: emit loads and iterates DomainContext"
```

---

### Task 7: Update Evaluate Stage

**Files:**
- Modify: `refiner/src/refiner/evaluate.py`
- Test: `refiner/tests/test_evaluate.py`

- [ ] **Step 1: Update evaluate tests**

In `refiner/tests/test_evaluate.py`, update `_sample_domain_context()` to return the new YAML shape:

Old:
```python
def _sample_domain_context():
    return {"profiles": [{"risk_id": "r1", "policy_concept": "Fraud", "axes": [...]}]}
```

New:
```python
def _sample_domain_context():
    return {
        "version": "0.1",
        "risks": [{"risk_id": "r1", "risk_name": "Risk 1", ...}],
        "policy_contexts": [
            {
                "policy_concept": "Fraud",
                "risk_groundings": [
                    {
                        "risk_id": "r1",
                        "axes": [{"cco_class_uri": "http://ex/P", ...}],
                    },
                ],
            },
        ],
    }
```

Update all test functions that construct inline profile dicts to use the new shape. The metric functions will need a flattening step (see Step 3).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd refiner && uv run pytest tests/test_evaluate.py -v 2>&1 | tail -30`

Expected: FAIL.

- [ ] **Step 3: Update evaluate.py**

The evaluate functions work with raw dicts. The cleanest approach is to add a helper that flattens the new structure into the format the metric functions expect, avoiding changes to every metric function:

```python
def _flatten_to_profiles(dc_data: dict) -> list[dict]:
    """Flatten DomainContext dict into profile-like dicts for metrics."""
    risk_by_id = {r["risk_id"]: r for r in dc_data.get("risks", [])}
    profiles = []
    for pc in dc_data.get("policy_contexts", []):
        for rg in pc.get("risk_groundings", []):
            risk = risk_by_id.get(rg.get("risk_id", ""), {})
            profiles.append({
                "risk_id": rg.get("risk_id", ""),
                "risk_name": risk.get("risk_name", ""),
                "policy_concept": pc.get("policy_concept", ""),
                "axes": rg.get("axes", []),
                "risk_description": risk.get("risk_description", ""),
                "risk_concern": risk.get("risk_concern", ""),
                "risk_framework": risk.get("risk_framework", ""),
                "cross_mappings": risk.get("cross_mappings", []),
            })
    return profiles
```

Update `run_evaluation()` — replace `profiles = dc_data.get("profiles", [])` with:
```python
    profiles = _flatten_to_profiles(dc_data)
```

This keeps all existing metric functions unchanged — they still receive `list[dict]` with the same keys. The flattening is the single point of adaptation.

Also extract envelope metadata for the evaluation output:
```python
    if dc_data:
        evaluation["envelope"] = {
            "version": dc_data.get("version", ""),
            "model": dc_data.get("model", ""),
            "selected_domains": dc_data.get("selected_domains", []),
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd refiner && uv run pytest tests/test_evaluate.py -v 2>&1 | tail -30`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd refiner && git add src/refiner/evaluate.py tests/test_evaluate.py
git commit -m "feat: evaluate flattens DomainContext for metrics"
```

---

### Task 8: Update Provenance

**Files:**
- Modify: `refiner/src/refiner/provenance.py`
- Test: Run existing tests (provenance tests may be in test_emit.py or separate)

- [ ] **Step 1: Update provenance.py**

Update imports:
```python
from refiner.models import DomainContext
```

Update `_load_profiles()` to load the document:
```python
def _load_document(domain_context_path: Path) -> DomainContext:
    raw = yaml.safe_load(domain_context_path.read_text())
    return DomainContext(**raw)
```

Update `write_provenance()` to traverse the new structure:
```python
def write_provenance(
    domain_context_path: Path,
    dataset_path: Path,
    output_path: Path,
    model: str = "",
) -> None:
    doc = _load_document(domain_context_path)
    triples: list[dict] = []

    effective_model = model or doc.model

    for pc in doc.policy_contexts:
        for grounding in pc.risk_groundings:
            profile_id = f"profile:{grounding.risk_id}"

            triples.append({
                "entity": profile_id,
                "type": "RiskGrounding",
                "risk_id": grounding.risk_id,
                "policy_concept": pc.policy_concept,
                "wasGeneratedBy": "contextualize",
                "wasAssociatedWith": effective_model,
            })

            for axis in grounding.axes:
                axis_id = f"axis:{grounding.risk_id}:{axis.cco_class_uri}"

                axis_triple: dict = {
                    "entity": axis_id,
                    "type": "DomainContextAxis",
                    "cco_class_uri": axis.cco_class_uri,
                    "cco_class_label": axis.cco_class_label,
                    "bfo_category": axis.bfo_category,
                    "wasGeneratedBy": "anchor",
                    "wasAssociatedWith": effective_model,
                    "partOf": profile_id,
                }

                if axis.vocabulary_concept:
                    axis_triple["wasDerivedFrom"] = axis.vocabulary_concept
                    axis_triple["vocabulary_label"] = axis.vocabulary_label

                if axis.derivation:
                    d = axis.derivation
                    axis_triple["derivation_source"] = d.source
                    if d.seed_uri:
                        axis_triple["derivation_seed"] = d.seed_uri
                    if d.path:
                        axis_triple["derivation_path"] = d.path
                    if d.effective_confidence:
                        axis_triple["derivation_confidence"] = d.effective_confidence
                    if d.best_distance is not None:
                        axis_triple["derivation_distance"] = d.best_distance
                    if d.domain:
                        axis_triple["derivation_domain"] = d.domain

                triples.append(axis_triple)

                for enum in axis.enumerations:
                    enum_id = f"enum:{grounding.risk_id}:{enum.class_uri}"
                    enum_triple: dict = {
                        "entity": enum_id,
                        "type": "AxisEnumeration",
                        "class_uri": enum.class_uri,
                        "class_label": enum.class_label,
                        "source_ontology": enum.source_ontology,
                        "provenance": enum.provenance,
                        "relevance": enum.relevance,
                        "partOf": axis_id,
                    }
                    if enum.generated_by:
                        enum_triple["wasAssociatedWith"] = enum.generated_by
                    triples.append(enum_triple)

    # --- Prompt-level provenance (unchanged) ---
    # ... rest stays the same
```

- [ ] **Step 2: Run tests**

Run: `cd refiner && uv run pytest tests/ -v -k "provenance" 2>&1 | tail -20`

Expected: PASS (or fix any fixture issues).

- [ ] **Step 3: Commit**

```bash
cd refiner && git add src/refiner/provenance.py
git commit -m "feat: provenance traverses DomainContext structure"
```

---

### Task 9: Remove DomainContextProfile and Clean Up

**Files:**
- Modify: `refiner/src/refiner/models.py`
- Test: `refiner/tests/test_models.py`

- [ ] **Step 1: Remove DomainContextProfile from models.py**

Delete the `DomainContextProfile` class (lines 139-147).

- [ ] **Step 2: Remove old test**

Remove `test_domain_context_profile` from `test_models.py`.

- [ ] **Step 3: Grep for any remaining references**

Run: `cd refiner && grep -rn "DomainContextProfile" src/ tests/`

Fix any remaining references.

- [ ] **Step 4: Run full test suite**

Run: `cd refiner && uv run pytest -v 2>&1 | tail -40`

Expected: All ~350 tests pass.

- [ ] **Step 5: Commit**

```bash
cd refiner && git add -u
git commit -m "chore: remove DomainContextProfile, replaced by DomainContext"
```

---

### Task 10: Final Verification

- [ ] **Step 1: Run full test suite**

Run: `cd refiner && uv run pytest -v 2>&1 | tail -40`

Expected: All tests pass.

- [ ] **Step 2: Verify model serialization round-trip**

Run a quick check that DomainContext serializes and deserializes correctly:

```bash
cd refiner && uv run python -c "
from refiner.models import *
import yaml
doc = DomainContext(
    model='test', selected_domains=['CCO'],
    risks=[RiskSummary(risk_id='r1', risk_name='R1')],
    policy_contexts=[PolicyDomainContext(
        policy_concept='P1',
        risk_groundings=[RiskGrounding(risk_id='r1', axes=[
            DomainContextAxis(cco_class_uri='http://ex/P', cco_class_label='P',
                              vocabulary_context=VocabularyContext(stakeholders=[{'label':'User'}]),
                              enumerations=[AxisEnumeration(class_uri='http://ex/E', class_label='E',
                                                            source_ontology='CCO', relevance='high')])
        ])]
    )]
)
dumped = yaml.dump(doc.model_dump(), default_flow_style=False)
loaded = DomainContext(**yaml.safe_load(dumped))
assert loaded.risks[0].risk_id == 'r1'
assert loaded.policy_contexts[0].risk_groundings[0].axes[0].vocabulary_context.stakeholders[0]['label'] == 'User'
print('Round-trip OK')
"
```

Expected: `Round-trip OK`

- [ ] **Step 3: Commit any final fixes**

If any fixes were needed, commit them.
