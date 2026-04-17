# Coverage Gap Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect when a policy concern doesn't match any existing nexus risk well, classify the gap type (domain_specialization / compositional / novel), and surface it in RunReport events + RiskLandscape + the risk landscape HTML report.

**Architecture:** After the existing LLM mapping loop in `map_risks`, compute a gap score from three signals (candidate distance, match quality, decomposition coherence). Policies exceeding the threshold get a second LLM call to classify the gap type. Compositional gaps are downweighted (0.6x) because LLMs over-compose. Results flow into `CoverageGap` model entries on `RiskLandscape` and as events on `RunReport`. The HTML template gets a new section styled in purple.

**Tech Stack:** Pydantic models, Instructor constrained decoding, Jinja-style HTML template (inline Alpine.js)

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `refiner/src/refiner/models.py` | Modify | Add `CoverageGap` model, add `coverage_gaps` field to `RiskLandscape` |
| `refiner/src/refiner/stages/map_risks.py` | Modify | Add gap detection logic + LLM characterization call after mapping loop |
| `refiner/src/refiner/stages/build_landscape.py` | Modify | Thread `coverage_gaps` from map_risks into `RiskLandscape` |
| `refiner/src/refiner/pipeline.py` | Modify | Pass coverage_gaps through pipeline state |
| `refiner/src/refiner/risk_landscape_report_template.html` | Modify | Add Coverage Gaps section |
| `refiner/tests/test_models.py` | Modify | Tests for `CoverageGap` model |
| `refiner/tests/test_map_risks.py` | Modify | Tests for gap detection + characterization |
| `refiner/tests/test_build_landscape.py` | Modify | Tests for coverage_gaps threading |

---

### Task 1: Add CoverageGap model

**Files:**
- Modify: `refiner/src/refiner/models.py:161-178` (after `WeakMatch`, before `RiskLandscape`)
- Test: `refiner/tests/test_models.py`

- [ ] **Step 1: Write the failing test**

Add to the end of `refiner/tests/test_models.py`:

```python
def test_coverage_gap_model():
    from refiner.models import CoverageGap, PolicyDecomposition

    gap = CoverageGap(
        policy_concept="AI triage liability",
        concept_definition="AI systems making triage decisions may create liability",
        gap_type="novel",
        confidence=0.82,
        nearest_risks=[
            {"id": "atlas-liability", "name": "Liability", "distance": 0.65},
        ],
        reasoning="No existing risk covers AI-specific triage liability",
    )
    assert gap.gap_type == "novel"
    assert gap.confidence == 0.82
    assert gap.decomposition is None


def test_coverage_gap_with_decomposition():
    from refiner.models import CoverageGap, PolicyDecomposition

    gap = CoverageGap(
        policy_concept="AI triage liability",
        concept_definition="AI systems making triage decisions may create liability",
        gap_type="domain_specialization",
        confidence=0.71,
        nearest_risks=[],
        reasoning="Domain-specific variant of general liability risk",
        decomposition=PolicyDecomposition(
            agent="AI triage system",
            activity="diagnose",
            entity="patient symptoms",
        ),
    )
    assert gap.decomposition.agent == "AI triage system"


def test_risk_landscape_has_coverage_gaps():
    from refiner.models import RiskLandscape, CoverageGap

    landscape = RiskLandscape()
    assert landscape.coverage_gaps == []

    landscape_with = RiskLandscape(
        coverage_gaps=[
            CoverageGap(
                policy_concept="test",
                concept_definition="test def",
                gap_type="novel",
                confidence=0.8,
                nearest_risks=[],
                reasoning="test",
            ),
        ],
    )
    assert len(landscape_with.coverage_gaps) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd refiner && uv run pytest tests/test_models.py::test_coverage_gap_model tests/test_models.py::test_coverage_gap_with_decomposition tests/test_models.py::test_risk_landscape_has_coverage_gaps -v`
Expected: FAIL — `CoverageGap` not defined

- [ ] **Step 3: Write the implementation**

In `refiner/src/refiner/models.py`, add after the `WeakMatch` class (line ~165) and before `RiskLandscape`:

```python
class CoverageGap(BaseModel):
    policy_concept: str
    concept_definition: str
    gap_type: Literal["domain_specialization", "compositional", "novel"]
    confidence: float
    nearest_risks: list[dict]
    reasoning: str
    decomposition: PolicyDecomposition | None = None
```

In `RiskLandscape`, add after `weak_matches`:

```python
    coverage_gaps: list[CoverageGap] = []
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd refiner && uv run pytest tests/test_models.py::test_coverage_gap_model tests/test_models.py::test_coverage_gap_with_decomposition tests/test_models.py::test_risk_landscape_has_coverage_gaps -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add refiner/src/refiner/models.py refiner/tests/test_models.py
git commit -m "feat(models): add CoverageGap model and coverage_gaps field on RiskLandscape"
```

---

### Task 2: Gap detection logic in map_risks

**Files:**
- Modify: `refiner/src/refiner/stages/map_risks.py`
- Test: `refiner/tests/test_map_risks.py`

The gap detection computes a weighted score from three signals after the LLM mapping loop. The score is computed per-policy, not per-risk. The LLM characterization call is a separate step (Task 3). This task only adds the scoring and threshold detection.

- [ ] **Step 1: Write the failing tests**

Add to the end of `refiner/tests/test_map_risks.py`:

```python
from refiner.stages.map_risks import compute_gap_score


def test_gap_score_all_distant_no_primary():
    """High distance + no primary match + decomposition = high gap score."""
    from refiner.models import PolicyDecomposition
    score = compute_gap_score(
        min_distance=0.7,
        primary_count=0,
        has_decomposition=True,
    )
    # 0.45*0.7 + 0.35*1.0 + 0.20*1.0 = 0.315 + 0.35 + 0.20 = 0.865
    assert abs(score - 0.865) < 0.01


def test_gap_score_close_match_with_primary():
    """Low distance + primary match = low gap score."""
    score = compute_gap_score(
        min_distance=0.15,
        primary_count=2,
        has_decomposition=True,
    )
    # 0.45*0.15 + 0.35*0.0 + 0.20*1.0 = 0.0675 + 0 + 0.20 = 0.2675
    assert score < 0.4


def test_gap_score_no_decomposition_still_works():
    """Without decomposition, the score degrades gracefully (lower ceiling)."""
    score = compute_gap_score(
        min_distance=0.8,
        primary_count=0,
        has_decomposition=False,
    )
    # 0.45*0.8 + 0.35*1.0 + 0.20*0.0 = 0.36 + 0.35 + 0 = 0.71
    assert abs(score - 0.71) < 0.01


def test_gap_score_moderate_distance_tangential_only():
    """Moderate distance, no primary but has matches = moderate score."""
    score = compute_gap_score(
        min_distance=0.5,
        primary_count=0,
        has_decomposition=True,
    )
    # 0.45*0.5 + 0.35*1.0 + 0.20*1.0 = 0.225 + 0.35 + 0.20 = 0.775
    assert 0.7 < score < 0.85
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd refiner && uv run pytest tests/test_map_risks.py::test_gap_score_all_distant_no_primary tests/test_map_risks.py::test_gap_score_close_match_with_primary tests/test_map_risks.py::test_gap_score_no_decomposition_still_works tests/test_map_risks.py::test_gap_score_moderate_distance_tangential_only -v`
Expected: FAIL — `compute_gap_score` not defined

- [ ] **Step 3: Write the implementation**

In `refiner/src/refiner/stages/map_risks.py`, add after the `WEAK_MATCH_THRESHOLD` constant:

```python
GAP_SCORE_THRESHOLD = 0.65


def compute_gap_score(
    min_distance: float,
    primary_count: int,
    has_decomposition: bool,
) -> float:
    return (
        0.45 * min_distance
        + 0.35 * (1.0 if primary_count == 0 else 0.0)
        + 0.20 * (1.0 if has_decomposition else 0.0)
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd refiner && uv run pytest tests/test_map_risks.py::test_gap_score_all_distant_no_primary tests/test_map_risks.py::test_gap_score_close_match_with_primary tests/test_map_risks.py::test_gap_score_no_decomposition_still_works tests/test_map_risks.py::test_gap_score_moderate_distance_tangential_only -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add refiner/src/refiner/stages/map_risks.py refiner/tests/test_map_risks.py
git commit -m "feat(map_risks): add compute_gap_score function for coverage gap detection"
```

---

### Task 3: LLM gap characterization call

**Files:**
- Modify: `refiner/src/refiner/stages/map_risks.py`
- Test: `refiner/tests/test_map_risks.py`

When gap_score exceeds the threshold, a second LLM call classifies the gap type. The compositional type gets a 0.6x discount on the confidence score.

- [ ] **Step 1: Write the failing tests**

Add to `refiner/tests/test_map_risks.py`:

```python
from refiner.stages.map_risks import characterize_gap, _GapClassification, GAP_TYPE_WEIGHTS


def test_characterize_gap_novel(mock_client, mock_config):
    mock_client.chat.completions.create.return_value = _GapClassification(
        gap_type="novel",
        reasoning="No existing risk covers multi-agent collusion",
    )
    result = characterize_gap(
        policy_concept="Multi-agent collusion",
        concept_definition="Multiple AI agents coordinating to bypass safety controls",
        nearest_candidates=[
            {"name": "Dangerous use", "description": "Dangerous capabilities", "distance": 0.72},
        ],
        client=mock_client,
        config=mock_config,
    )
    assert result.gap_type == "novel"
    assert "multi-agent" in result.reasoning.lower() or "collusion" in result.reasoning.lower() or "No existing" in result.reasoning


def test_characterize_gap_compositional_downweighted(mock_client, mock_config):
    mock_client.chat.completions.create.return_value = _GapClassification(
        gap_type="compositional",
        reasoning="Combination of bias and hiring discrimination",
    )
    result = characterize_gap(
        policy_concept="Automated hiring discrimination",
        concept_definition="AI hiring tools that discriminate via training data bias",
        nearest_candidates=[
            {"name": "Bias", "description": "Model bias", "distance": 0.55},
            {"name": "Discrimination", "description": "Discrimination in outputs", "distance": 0.58},
        ],
        client=mock_client,
        config=mock_config,
    )
    assert result.gap_type == "compositional"


def test_gap_type_weights():
    assert GAP_TYPE_WEIGHTS["compositional"] == 0.6
    assert GAP_TYPE_WEIGHTS["novel"] == 1.0
    assert GAP_TYPE_WEIGHTS["domain_specialization"] == 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd refiner && uv run pytest tests/test_map_risks.py::test_characterize_gap_novel tests/test_map_risks.py::test_characterize_gap_compositional_downweighted tests/test_map_risks.py::test_gap_type_weights -v`
Expected: FAIL — `characterize_gap`, `_GapClassification`, `GAP_TYPE_WEIGHTS` not defined

- [ ] **Step 3: Write the implementation**

In `refiner/src/refiner/stages/map_risks.py`, add the Pydantic response model, the weights, and the characterization function:

```python
GAP_TYPE_WEIGHTS = {
    "domain_specialization": 1.0,
    "compositional": 0.6,
    "novel": 1.0,
}


class _GapClassification(BaseModel):
    gap_type: Literal["domain_specialization", "compositional", "novel"]
    reasoning: str


GAP_CHARACTERIZATION_PROMPT = """\
You are classifying a coverage gap in an AI risk taxonomy.

A policy concern was not well matched to any existing risk in the knowledge graph. Your job is to determine WHY.

Three gap types:
- domain_specialization: The concern is a domain-specific variant of an existing risk (e.g. "AI triage liability" is healthcare-specific "Liability"). The risk concept exists but needs domain narrowing.
- compositional: The concern can be fully expressed as a combination of multiple existing risks (e.g. "automated hiring discrimination via training data bias" = "Bias" + "Discrimination"). No new risk concept is needed.
- novel: The concern names a fundamentally different failure mode not covered by existing risks, even in combination (e.g. "multi-agent collusion", "AI welfare").

Prefer domain_specialization over compositional. Prefer compositional over novel. Only classify as novel if the concern truly cannot be expressed using existing risks.

Return the gap_type and a one-sentence reasoning."""


def characterize_gap(
    policy_concept: str,
    concept_definition: str,
    nearest_candidates: list[dict],
    client: instructor.Instructor,
    config: LLMConfig,
) -> _GapClassification:
    candidate_lines = []
    for c in nearest_candidates[:5]:
        line = f"- {c.get('name', '?')}: {c.get('description', '')}"
        if c.get("distance") is not None:
            line += f" (distance: {c['distance']:.3f})"
        candidate_lines.append(line)

    user_content = (
        f"Policy concern: {policy_concept}\n"
        f"Definition: {concept_definition}\n\n"
        f"Nearest existing risks (none matched well):\n"
        + "\n".join(candidate_lines)
    )

    messages = [
        {"role": "system", "content": GAP_CHARACTERIZATION_PROMPT},
        {"role": "user", "content": user_content},
    ]
    result = client.chat.completions.create(
        model=config.model,
        response_model=_GapClassification,
        messages=messages,
        temperature=config.temperature,
        max_retries=config.max_retries,
        max_tokens=config.max_tokens,
    )
    debug.log_call("characterize_gap", messages, result, context={
        "policy_concept": policy_concept,
    })
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd refiner && uv run pytest tests/test_map_risks.py::test_characterize_gap_novel tests/test_map_risks.py::test_characterize_gap_compositional_downweighted tests/test_map_risks.py::test_gap_type_weights -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add refiner/src/refiner/stages/map_risks.py refiner/tests/test_map_risks.py
git commit -m "feat(map_risks): add LLM gap characterization with compositional downweighting"
```

---

### Task 4: Wire gap detection into map_risks loop

**Files:**
- Modify: `refiner/src/refiner/stages/map_risks.py` (the `map_risks` function)
- Test: `refiner/tests/test_map_risks.py`

Integrate `compute_gap_score` and `characterize_gap` into the `map_risks` function. The function return type gains a sixth element: the coverage gaps list.

- [ ] **Step 1: Write the failing tests**

Add to `refiner/tests/test_map_risks.py`:

```python
from refiner.models import RunReport, CoverageGap, PolicyDecomposition


def test_map_risks_detects_coverage_gap(mock_client, mock_config, mock_risk_handlers):
    """When all candidates are distant and LLM returns no primary, detect a gap."""
    pol = Policy(
        policy_concept="Multi-agent collusion",
        concept_definition="Multiple AI agents coordinating to bypass safety controls",
        decomposition=PolicyDecomposition(agent="AI agents", activity="coordinate", entity="safety controls"),
    )
    mock_risk_handlers["search_risks"].return_value = [
        {"id": "atlas-dangerous-use", "name": "Dangerous use", "description": "Dangerous capabilities", "distance": 0.75},
    ]
    mock_risk_handlers["get_risk_details"].return_value = {
        "id": "atlas-dangerous-use", "name": "Dangerous use", "description": "Dangerous capabilities",
        "concern": "Misuse risk", "risk_type": "output", "taxonomy": "ibm-risk-atlas",
    }
    mock_risk_handlers["get_related_risks"].return_value = []
    mock_risk_handlers["get_related_actions"].return_value = []

    # First LLM call: risk mapping — returns only tangential
    # Second LLM call: gap characterization — returns novel
    mock_client.chat.completions.create.side_effect = [
        _RiskSelection(
            matched_risks=[_SlimRiskMatch(risk_index=1, risk_name="Dangerous use", relevance="tangential", justification="j")],
        ),
        _GapClassification(gap_type="novel", reasoning="Multi-agent collusion is a new failure mode"),
    ]

    report = RunReport(model="m", policy_set="p", timestamp="t")
    mappings, _, _, _, _, coverage_gaps = map_risks([pol], mock_client, mock_config, mock_risk_handlers, report=report)

    assert len(coverage_gaps) == 1
    assert coverage_gaps[0].gap_type == "novel"
    assert coverage_gaps[0].policy_concept == "Multi-agent collusion"
    assert coverage_gaps[0].confidence > 0.6
    assert len(coverage_gaps[0].nearest_risks) > 0
    assert coverage_gaps[0].decomposition is not None

    gap_events = [e for e in report.events if e["event"] == "coverage_gap"]
    assert len(gap_events) == 1
    assert gap_events[0]["gap_type"] == "novel"


def test_map_risks_no_gap_on_strong_match(mock_client, mock_config, mock_risk_handlers):
    """When there's a close primary match, no gap is detected."""
    pol = _make_policy()
    mock_risk_handlers["search_risks"].return_value = [
        {"id": "atlas-fraud", "name": "Fraud", "description": "Fraud risk", "distance": 0.15},
    ]
    mock_risk_handlers["get_risk_details"].return_value = {
        "id": "atlas-fraud", "name": "Fraud", "description": "Fraud risk",
        "concern": "Financial loss", "risk_type": "output", "taxonomy": "ibm-risk-atlas",
    }
    mock_risk_handlers["get_related_risks"].return_value = []
    mock_risk_handlers["get_related_actions"].return_value = []
    mock_client.chat.completions.create.return_value = _RiskSelection(
        matched_risks=[_SlimRiskMatch(risk_index=1, risk_name="Fraud", relevance="primary", justification="j")],
    )

    mappings, _, _, _, _, coverage_gaps = map_risks([pol], mock_client, mock_config, mock_risk_handlers)
    assert len(coverage_gaps) == 0


def test_map_risks_compositional_gap_downweighted(mock_client, mock_config, mock_risk_handlers):
    """Compositional gaps get a 0.6x confidence discount."""
    pol = Policy(
        policy_concept="Automated hiring discrimination",
        concept_definition="AI hiring tools that discriminate via training data bias",
    )
    mock_risk_handlers["search_risks"].return_value = [
        {"id": "atlas-bias", "name": "Bias", "description": "Model bias", "distance": 0.62},
        {"id": "atlas-discrimination", "name": "Discrimination", "description": "Outputs that discriminate", "distance": 0.65},
    ]
    mock_risk_handlers["get_risk_details"].side_effect = lambda rid: {
        "id": rid, "name": rid.replace("atlas-", "").title(), "description": "desc",
        "concern": "concern", "risk_type": "output", "taxonomy": "ibm-risk-atlas",
    }
    mock_risk_handlers["get_related_risks"].return_value = []
    mock_risk_handlers["get_related_actions"].return_value = []

    mock_client.chat.completions.create.side_effect = [
        _RiskSelection(matched_risks=[]),
        _GapClassification(gap_type="compositional", reasoning="Combination of bias and discrimination"),
    ]

    mappings, _, _, _, _, coverage_gaps = map_risks([pol], mock_client, mock_config, mock_risk_handlers)
    assert len(coverage_gaps) == 1
    assert coverage_gaps[0].gap_type == "compositional"
    # Compositional confidence should be lower than the raw gap_score
    # Raw: 0.45*0.62 + 0.35*1.0 + 0.20*0.0 = 0.279 + 0.35 + 0 = 0.629
    # After discount: 0.629 * 0.6 ≈ 0.377 — below threshold, BUT gap_score was above threshold
    # so the gap IS detected but confidence is discounted
    assert coverage_gaps[0].confidence < 0.65


def test_map_risks_empty_returns_six_tuple(mock_client, mock_config, mock_risk_handlers):
    """Empty input returns six-element tuple with empty coverage_gaps."""
    mappings, details, seen_ids, related, risk_actions, coverage_gaps = map_risks(
        [], mock_client, mock_config, mock_risk_handlers,
    )
    assert coverage_gaps == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd refiner && uv run pytest tests/test_map_risks.py::test_map_risks_detects_coverage_gap tests/test_map_risks.py::test_map_risks_no_gap_on_strong_match tests/test_map_risks.py::test_map_risks_compositional_gap_downweighted tests/test_map_risks.py::test_map_risks_empty_returns_six_tuple -v`
Expected: FAIL — return value unpacking fails (5 vs 6 elements)

- [ ] **Step 3: Write the implementation**

Modify the `map_risks` function in `refiner/src/refiner/stages/map_risks.py`:

1. Add `CoverageGap` to imports from `refiner.models`
2. Change the return type to include `list[CoverageGap]` as the sixth element
3. Initialize `coverage_gaps: list[CoverageGap] = []` at the top
4. Update the empty-input early return to `return [], {}, set(), {}, {}, []`
5. After the post-processing block for each policy (after the `mappings.append` call), add gap detection:

```python
        # --- Coverage gap detection ---
        min_distance = min(
            (ec.get("distance") or 0.0) for ec in enriched_candidates
        ) if enriched_candidates else 1.0
        primary_count = sum(1 for r in valid_risks if r.relevance == "primary")
        has_decomposition = (
            pol.decomposition is not None
            and bool(pol.decomposition.agent or pol.decomposition.activity or pol.decomposition.entity)
        )

        gap_score = compute_gap_score(min_distance, primary_count, has_decomposition)
        if gap_score >= GAP_SCORE_THRESHOLD:
            nearest = [
                {"id": ec["id"], "name": ec.get("name", ""), "distance": ec.get("distance")}
                for ec in enriched_candidates[:3]
            ]
            classification = characterize_gap(
                pol.policy_concept,
                pol.concept_definition,
                enriched_candidates[:5],
                client,
                config,
            )
            adjusted_confidence = gap_score * GAP_TYPE_WEIGHTS[classification.gap_type]
            gap = CoverageGap(
                policy_concept=pol.policy_concept,
                concept_definition=pol.concept_definition,
                gap_type=classification.gap_type,
                confidence=round(adjusted_confidence, 3),
                nearest_risks=nearest,
                reasoning=classification.reasoning,
                decomposition=pol.decomposition,
            )
            coverage_gaps.append(gap)
            logger.info(
                "Coverage gap detected for '%s': type=%s confidence=%.3f",
                pol.policy_concept, classification.gap_type, adjusted_confidence,
            )
            if report:
                report.events.append({
                    "stage": "map_risks", "event": "coverage_gap",
                    "policy_concept": pol.policy_concept,
                    "gap_type": classification.gap_type,
                    "confidence": round(adjusted_confidence, 3),
                    "gap_score_raw": round(gap_score, 3),
                    "nearest_risks": nearest,
                })
```

6. Update the final return: `return mappings, risk_details_cache, seen_risk_ids, related_risks, risk_actions_cache, coverage_gaps`

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd refiner && uv run pytest tests/test_map_risks.py::test_map_risks_detects_coverage_gap tests/test_map_risks.py::test_map_risks_no_gap_on_strong_match tests/test_map_risks.py::test_map_risks_compositional_gap_downweighted tests/test_map_risks.py::test_map_risks_empty_returns_six_tuple -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add refiner/src/refiner/stages/map_risks.py refiner/tests/test_map_risks.py
git commit -m "feat(map_risks): wire gap detection and characterization into mapping loop"
```

---

### Task 5: Fix existing tests for new return signature

**Files:**
- Modify: `refiner/tests/test_map_risks.py` (all existing tests that unpack 5 elements)

The `map_risks` function now returns a 6-tuple. All existing tests that unpack 5 elements need updating.

- [ ] **Step 1: Update all existing test call sites**

In `refiner/tests/test_map_risks.py`, find all lines matching this pattern:
```python
mappings, details, seen_ids, related, _ = map_risks(...)
```
or similar 5-element unpacking, and add a sixth element `_` or `coverage_gaps`:

```python
# Change every instance of 5-element unpacking to 6-element:
mappings, details, seen_ids, related, _, _ = map_risks(...)
# or
_, details, _, _, _, _ = map_risks(...)
# etc.
```

The specific tests to update (search for `= map_risks(`):
- `test_map_risks_calls_search_and_details` — `mappings, details, seen_ids, related, _ =` -> `mappings, details, seen_ids, related, _, _ =`
- `test_map_risks_filters_hallucinated_risk_ids` — same pattern
- `test_map_risks_returns_risk_details_cache` — `_, details, _, _, _ =` -> `_, details, _, _, _, _ =`
- `test_map_risks_seen_ids_includes_related` — `_, _, seen_ids, _, _ =` -> `_, _, seen_ids, _, _, _ =`
- `test_map_risks_returns_related_risks` — `_, _, _, related_risks, _ =` -> `_, _, _, related_risks, _, _ =`
- `test_map_risks_populates_match_distance` — `mappings, _, _, _, _ =` -> `mappings, _, _, _, _, _ =`
- `test_map_risks_warns_on_weak_match` — `mappings, _, _, _, _ =` -> `mappings, _, _, _, _, _ =`
- `test_map_risks_empty_classifications` — `mappings, details, seen_ids, related, risk_actions =` -> `mappings, details, seen_ids, related, risk_actions, coverage_gaps =` and add `assert coverage_gaps == []`
- `test_map_risks_emits_weak_match` — `mappings, _, _, _, _ =` -> `mappings, _, _, _, _, _ =`
- `test_map_risks_emits_invalid_risk_index` — `mappings, _, _, _, _ =` -> `mappings, _, _, _, _, _ =`
- `test_map_risks_emits_match_count` — `mappings, _, _, _, _ =` -> `mappings, _, _, _, _, _ =`
- `test_map_risks_no_report_works` — `mappings, _, _, _, _ =` -> `mappings, _, _, _, _, _ =`
- `test_map_risks_returns_risk_actions` — update unpacking similarly

- [ ] **Step 2: Run the full test suite**

Run: `cd refiner && uv run pytest tests/test_map_risks.py -v`
Expected: ALL PASS

- [ ] **Step 3: Fix any callers in pipeline and CLI**

In `refiner/src/refiner/pipeline.py` line 139, update the unpacking:

```python
# Before:
state.risk_mappings, state.risk_details, state.seen_risk_ids, state.related_risks, state.risk_actions = map_risks(...)

# After:
state.risk_mappings, state.risk_details, state.seen_risk_ids, state.related_risks, state.risk_actions, coverage_gaps = map_risks(...)
```

Store coverage_gaps on `PipelineState` — add to the dataclass:

```python
coverage_gaps: list = field(default_factory=list)
```

And after the unpacking:

```python
state.coverage_gaps = coverage_gaps
```

Check `refiner/src/refiner/cli.py` for any direct calls to `map_risks` — grep for `= map_risks(`. The `refine` command at ~line 484 calls `map_risks` directly. Update that unpacking too:

```python
mappings, risk_details, seen_ids, related, risk_actions, coverage_gaps = map_risks(...)
```

- [ ] **Step 4: Run the full test suite**

Run: `cd refiner && uv run pytest -v`
Expected: ALL PASS (or only pre-existing failures)

- [ ] **Step 5: Commit**

```bash
git add refiner/src/refiner/stages/map_risks.py refiner/tests/test_map_risks.py refiner/src/refiner/pipeline.py refiner/src/refiner/cli.py
git commit -m "refactor: update all call sites for map_risks 6-tuple return"
```

---

### Task 6: Thread coverage_gaps into build_landscape

**Files:**
- Modify: `refiner/src/refiner/stages/build_landscape.py`
- Modify: `refiner/src/refiner/pipeline.py`
- Test: `refiner/tests/test_build_landscape.py`

- [ ] **Step 1: Write the failing test**

Add to the end of `refiner/tests/test_build_landscape.py`:

```python
from refiner.models import CoverageGap


def test_build_risk_landscape_with_coverage_gaps():
    from refiner.stages.build_landscape import build_risk_landscape

    gaps = [
        CoverageGap(
            policy_concept="Multi-agent collusion",
            concept_definition="AI agents coordinating to bypass controls",
            gap_type="novel",
            confidence=0.82,
            nearest_risks=[{"id": "atlas-dangerous-use", "name": "Dangerous use", "distance": 0.75}],
            reasoning="No existing risk covers multi-agent coordination failures",
        ),
    ]

    landscape = build_risk_landscape(
        mappings=[],
        risk_details_cache={},
        coverage_gaps=gaps,
        model="test-model",
        run_slug="test",
        timestamp="2026-04-16T12:00:00Z",
    )

    assert len(landscape.coverage_gaps) == 1
    assert landscape.coverage_gaps[0].gap_type == "novel"
    assert landscape.coverage_gaps[0].policy_concept == "Multi-agent collusion"


def test_build_risk_landscape_empty_coverage_gaps():
    from refiner.stages.build_landscape import build_risk_landscape

    landscape = build_risk_landscape(
        mappings=[],
        risk_details_cache={},
        model="test-model",
        run_slug="test",
        timestamp="2026-04-16T12:00:00Z",
    )

    assert landscape.coverage_gaps == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd refiner && uv run pytest tests/test_build_landscape.py::test_build_risk_landscape_with_coverage_gaps tests/test_build_landscape.py::test_build_risk_landscape_empty_coverage_gaps -v`
Expected: FAIL — `build_risk_landscape()` got unexpected keyword argument `coverage_gaps`

- [ ] **Step 3: Write the implementation**

In `refiner/src/refiner/stages/build_landscape.py`:

1. Add `CoverageGap` to the imports from `refiner.models`
2. Add `coverage_gaps: list[CoverageGap] | None = None` parameter to `build_risk_landscape`
3. Pass it through to the `RiskLandscape` constructor: `coverage_gaps=coverage_gaps or []`

In `refiner/src/refiner/pipeline.py`, after `state.risk_landscape = build_risk_landscape(...)`, pass coverage_gaps:

```python
state.risk_landscape = build_risk_landscape(
    mappings=state.risk_mappings,
    risk_details_cache=state.risk_details,
    related_risks=state.related_risks,
    risk_actions=state.risk_actions,
    coverage_gaps=state.coverage_gaps,
    selected_domains=state.selected_domains,
    model=config.model,
    run_slug=run_slug,
    timestamp=report.timestamp if report else "",
)
```

Also update the `build_risk_landscape` call in `cli.py` for the `refine` command (~line 488) to pass `coverage_gaps=coverage_gaps`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd refiner && uv run pytest tests/test_build_landscape.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add refiner/src/refiner/stages/build_landscape.py refiner/src/refiner/pipeline.py refiner/src/refiner/cli.py refiner/tests/test_build_landscape.py
git commit -m "feat(landscape): thread coverage_gaps through build_landscape and pipeline"
```

---

### Task 7: Add Coverage Gaps section to HTML template

**Files:**
- Modify: `refiner/src/refiner/risk_landscape_report_template.html`

- [ ] **Step 1: Add coverage gaps count to the Overview Cards section**

In the Overview Cards section (after the "Weak Matches" card div, around line 143), add a fifth card:

```html
        <div class="tip text-center p-4 bg-gray-50 rounded-lg" data-tip="Policy concerns that could not be well-matched to any existing risk in the knowledge graph. May indicate taxonomy gaps.">
          <p class="text-3xl font-bold"
             :class="(data.coverage_gaps || []).length > 0 ? 'text-purple-600' : 'text-green-600'"
             x-text="(data.coverage_gaps || []).length"></p>
          <p class="text-xs text-gray-400 mt-1">Coverage Gaps</p>
        </div>
```

- [ ] **Step 2: Add the Coverage Gaps detail section**

After the Weak Matches section (after line ~345, before the closing `</div>` and `<script>`), add:

```html
    <!-- Coverage Gaps -->
    <section x-show="(data.coverage_gaps || []).length > 0" class="bg-purple-50 rounded-xl shadow-sm border border-purple-200 p-5">
      <h2 class="text-sm font-semibold text-purple-900 uppercase tracking-wide mb-3">
        <span class="tip" data-tip="Policy concerns that could not be well-matched to any existing risk in the knowledge graph. These may represent taxonomy gaps — risks not yet catalogued in any framework. Gap types: domain_specialization (existing risk needs narrowing), compositional (combination of existing risks, downweighted), novel (fundamentally new failure mode).">Coverage Gaps</span>
        <span class="tip-icon tip" data-tip="Policy concerns with no good risk match — potential taxonomy gaps.">i</span>
      </h2>
      <div class="space-y-3">
        <template x-for="gap in data.coverage_gaps || []" :key="gap.policy_concept">
          <div class="border border-purple-200 rounded-lg bg-white"
               x-data="{ expanded: false }">
            <div class="flex items-start justify-between p-3 cursor-pointer hover:bg-purple-50/50"
                 @click="expanded = !expanded">
              <div class="flex-1 min-w-0">
                <div class="flex flex-wrap items-center gap-2 mb-1">
                  <span class="font-semibold text-gray-900" x-text="gap.policy_concept"></span>
                  <span class="tip px-2 py-0.5 rounded text-xs font-medium"
                        :class="{
                          'bg-blue-100 text-blue-800': gap.gap_type === 'domain_specialization',
                          'bg-gray-200 text-gray-600': gap.gap_type === 'compositional',
                          'bg-red-100 text-red-800': gap.gap_type === 'novel'
                        }"
                        :data-tip="gap.gap_type === 'domain_specialization' ? 'Existing risk needs domain narrowing' : gap.gap_type === 'compositional' ? 'Combination of existing risks (downweighted confidence)' : 'Fundamentally new failure mode'"
                        x-text="gap.gap_type.replace('_', ' ')"></span>
                  <span class="tip px-2 py-0.5 rounded text-xs font-mono"
                        :class="{
                          'bg-red-100 text-red-800': gap.confidence >= 0.8,
                          'bg-amber-100 text-amber-800': gap.confidence >= 0.5 && gap.confidence < 0.8,
                          'bg-gray-100 text-gray-600': gap.confidence < 0.5
                        }"
                        data-tip="Confidence that this is a genuine taxonomy gap (0-1). Compositional gaps are discounted by 0.6x."
                        x-text="`conf: ${gap.confidence.toFixed(3)}`"></span>
                </div>
                <p class="text-sm text-gray-600 line-clamp-1" x-text="gap.concept_definition"></p>
              </div>
              <svg class="w-5 h-5 text-gray-400 transition-transform mt-1"
                   :class="expanded ? 'rotate-180' : ''"
                   fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
              </svg>
            </div>
            <div x-show="expanded" class="px-3 pb-3 pt-0 space-y-3 border-t border-purple-100">
              <div>
                <p class="tip text-xs text-gray-400 uppercase mb-1" data-tip="Full definition of the policy concern that was not matched.">Definition</p>
                <p class="text-sm text-gray-700" x-text="gap.concept_definition"></p>
              </div>
              <div>
                <p class="tip text-xs text-gray-400 uppercase mb-1" data-tip="Why this was classified as this gap type.">Reasoning</p>
                <p class="text-sm text-gray-700" x-text="gap.reasoning"></p>
              </div>
              <template x-if="gap.decomposition">
                <div>
                  <p class="tip text-xs text-gray-400 uppercase mb-1" data-tip="Agent/activity/entity decomposition from policy enrichment — confirms the policy concern is coherent.">Decomposition</p>
                  <div class="flex flex-wrap gap-2 text-xs">
                    <template x-if="gap.decomposition.agent">
                      <span class="px-2 py-1 rounded bg-purple-100 text-purple-800">
                        <span class="font-medium">Agent:</span> <span x-text="gap.decomposition.agent"></span>
                      </span>
                    </template>
                    <template x-if="gap.decomposition.activity">
                      <span class="px-2 py-1 rounded bg-purple-100 text-purple-800">
                        <span class="font-medium">Activity:</span> <span x-text="gap.decomposition.activity"></span>
                      </span>
                    </template>
                    <template x-if="gap.decomposition.entity">
                      <span class="px-2 py-1 rounded bg-purple-100 text-purple-800">
                        <span class="font-medium">Entity:</span> <span x-text="gap.decomposition.entity"></span>
                      </span>
                    </template>
                  </div>
                </div>
              </template>
              <template x-if="gap.nearest_risks?.length">
                <div>
                  <p class="tip text-xs text-gray-400 uppercase mb-1" data-tip="Closest existing risks from the knowledge graph — all too distant for a confident match.">Nearest Risks</p>
                  <div class="space-y-1">
                    <template x-for="nr in gap.nearest_risks" :key="nr.id">
                      <div class="flex items-center justify-between text-sm">
                        <span class="font-mono text-xs text-gray-600" x-text="nr.id"></span>
                        <span class="text-xs text-gray-500" x-text="nr.name"></span>
                        <span class="tip px-2 py-0.5 rounded text-xs font-mono bg-red-100 text-red-800"
                              data-tip="Semantic distance — all nearest risks are distant, confirming the gap."
                              x-text="nr.distance?.toFixed(3) || '?'"></span>
                      </div>
                    </template>
                  </div>
                </div>
              </template>
            </div>
          </div>
        </template>
      </div>
    </section>
```

- [ ] **Step 3: Update the overview grid to accommodate 5 cards**

Change the grid on line 125 from `grid-cols-2 md:grid-cols-4` to `grid-cols-2 md:grid-cols-5`:

```html
      <div class="grid grid-cols-2 md:grid-cols-5 gap-4">
```

- [ ] **Step 4: Verify with a test landscape HTML**

Create a quick test by checking the existing `refiner/test-risk-landscape.html` file — it should still render. Then to test coverage gaps rendering, you can manually add a `coverage_gaps` array to the `DATA` object in a copy.

Run: `cd refiner && uv run pytest tests/test_artifact_reports.py -v`
Expected: PASS (template renders without error)

- [ ] **Step 5: Commit**

```bash
git add refiner/src/refiner/risk_landscape_report_template.html
git commit -m "feat(reports): add Coverage Gaps section to risk landscape HTML report"
```

---

### Task 8: Run full test suite and verify

**Files:** None (verification only)

- [ ] **Step 1: Run the full refiner test suite**

Run: `cd refiner && uv run pytest -v`
Expected: ALL PASS (or only pre-existing failures unrelated to this change)

- [ ] **Step 2: Run a dry integration check**

Run: `cd refiner && uv run python -c "from refiner.models import CoverageGap, RiskLandscape; print('CoverageGap fields:', list(CoverageGap.model_fields.keys())); rl = RiskLandscape(); print('RiskLandscape.coverage_gaps:', rl.coverage_gaps)"`

Expected output:
```
CoverageGap fields: ['policy_concept', 'concept_definition', 'gap_type', 'confidence', 'nearest_risks', 'reasoning', 'decomposition']
RiskLandscape.coverage_gaps: []
```

- [ ] **Step 3: Verify map_risks import chain**

Run: `cd refiner && uv run python -c "from refiner.stages.map_risks import compute_gap_score, characterize_gap, GAP_SCORE_THRESHOLD, GAP_TYPE_WEIGHTS; print('threshold:', GAP_SCORE_THRESHOLD, 'weights:', GAP_TYPE_WEIGHTS)"`

Expected:
```
threshold: 0.65 weights: {'domain_specialization': 1.0, 'compositional': 0.6, 'novel': 1.0}
```

- [ ] **Step 4: Final commit if any fixups were needed**

```bash
git add -A
git commit -m "fix: address test suite issues from coverage gap integration"
```
