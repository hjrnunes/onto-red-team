# LLM Merge Strategy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace statistical distance-based candidate merging with LLM-judged contextual relevance selection, and make all merge strategies pure (no mutable state).

**Architecture:** New `LLMMergeStrategy` class implementing the existing `SearchMergeStrategy` protocol. The protocol gains `risk_context` and `generic_safety_uris` parameters to eliminate mutable state. A mechanical pre-filter (distance ceiling + safety URIs) reduces the pool before the LLM call. Fallback to distance-sorted order on LLM failure.

**Tech Stack:** instructor, pydantic, openai (existing dependencies)

**Spec:** `docs/superpowers/specs/2026-04-03-llm-merge-strategy-design.md`

---

### Task 1: Update SearchMergeStrategy Protocol Signature

**Files:**
- Modify: `refiner/src/refiner/stages/anchor.py:84-93`

- [ ] **Step 1: Write the failing test**

In `refiner/tests/test_anchor.py`, add a test that verifies the protocol accepts the new parameters:

```python
def test_strategy_protocol_new_signature():
    """Protocol accepts risk_context and generic_safety_uris parameters."""
    from refiner.stages.anchor import SearchMergeStrategy, WeightedMergeStrategy

    strategy = WeightedMergeStrategy()
    per_domain = {
        "CSO": [
            {"uri": "http://cso/X", "label": "X", "hit_count": 1, "best_distance": 0.1,
             "domain": "CSO", "query_sources": []},
        ],
    }
    risk_context = {"description": "fraud", "concern": "loss", "policy_concept": "Fraud"}
    result = strategy.merge(
        per_domain, ["CSO"], max_candidates=5,
        risk_context=risk_context, generic_safety_uris=set(),
    )
    assert isinstance(result, list)
    assert isinstance(strategy, SearchMergeStrategy)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd refiner && uv run pytest tests/test_anchor.py::test_strategy_protocol_new_signature -v`
Expected: FAIL — `merge()` got unexpected keyword arguments

- [ ] **Step 3: Update the protocol and WeightedMergeStrategy**

In `refiner/src/refiner/stages/anchor.py`, update the `SearchMergeStrategy` protocol:

```python
@runtime_checkable
class SearchMergeStrategy(Protocol):
    """Protocol for merging per-domain search results into a candidate list."""

    def merge(
        self,
        per_domain_candidates: dict[str, list[dict]],
        selected_domains: list[str],
        max_candidates: int,
        risk_context: dict,
        generic_safety_uris: set[str],
    ) -> list[dict]: ...
```

Update `WeightedMergeStrategy.__init__` — remove `generic_safety_uris` instance state:

```python
def __init__(self, always_included: list[str] | None = None):
    self._always_included = set(always_included or ALWAYS_INCLUDED)
```

Update `WeightedMergeStrategy.merge` signature and body — accept `generic_safety_uris` as parameter, pass to `_passes_threshold`:

```python
def merge(
    self,
    per_domain_candidates: dict[str, list[dict]],
    selected_domains: list[str],
    max_candidates: int,
    risk_context: dict,
    generic_safety_uris: set[str],
) -> list[dict]:
    selected_set = set(selected_domains)
    domain_selected = sorted(selected_set - self._always_included)

    for candidates in per_domain_candidates.values():
        self._normalize_distances(candidates)

    result: list[dict] = []
    seen: set[str] = set()
    remaining = max_candidates

    if domain_selected:
        quota_per = max(1, max_candidates // (len(domain_selected) + 1))
        for domain in domain_selected:
            for c in per_domain_candidates.get(domain, []):
                if (c["uri"] not in seen
                    and remaining > 0
                    and self._passes_threshold(c, generic_safety_uris)
                    and len([r for r in result if r.get("domain") == domain]) < quota_per):
                    result.append(c)
                    seen.add(c["uri"])
                    remaining -= 1

    pool = []
    for domain in sorted(self._always_included):
        if domain in selected_set:
            pool.extend(per_domain_candidates.get(domain, []))
    pool.sort(key=lambda c: (-c.get("hit_count", 0), c.get("normalized_distance", 0.0)))

    for c in pool:
        if c["uri"] not in seen and remaining > 0 and self._passes_threshold(c, generic_safety_uris):
            result.append(c)
            seen.add(c["uri"])
            remaining -= 1

    return result
```

Update `_passes_threshold` to take `generic_safety_uris` as a parameter:

```python
def _passes_threshold(self, c: dict, generic_safety_uris: set[str]) -> bool:
    if generic_safety_uris and c.get("uri", "") in generic_safety_uris:
        return False
    if c.get("best_distance", 1.0) >= self.DISTANCE_CEILING:
        return False
    if c.get("normalized_distance", 0.0) >= self.ZSCORE_THRESHOLD:
        return False
    return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd refiner && uv run pytest tests/test_anchor.py::test_strategy_protocol_new_signature -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd refiner && git add src/refiner/stages/anchor.py tests/test_anchor.py
git commit -m "refactor(anchor): add risk_context and generic_safety_uris to merge protocol"
```

---

### Task 2: Update GroupedMergeStrategy to New Signature

**Files:**
- Modify: `refiner/src/refiner/stages/anchor.py:194-228`

- [ ] **Step 1: Write the failing test**

In `refiner/tests/test_anchor.py`:

```python
def test_grouped_merge_new_signature():
    """GroupedMergeStrategy accepts new protocol parameters."""
    from refiner.stages.anchor import GroupedMergeStrategy, SearchMergeStrategy

    strategy = GroupedMergeStrategy()
    per_domain = {
        "CSO": [
            {"uri": "http://cso/X", "label": "X", "hit_count": 1, "best_distance": 0.1,
             "domain": "CSO", "query_sources": []},
        ],
    }
    risk_context = {"description": "fraud", "concern": "loss", "policy_concept": "Fraud"}
    result = strategy.merge(
        per_domain, ["CSO"], max_candidates=5,
        risk_context=risk_context, generic_safety_uris=set(),
    )
    assert isinstance(result, list)
    assert isinstance(strategy, SearchMergeStrategy)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd refiner && uv run pytest tests/test_anchor.py::test_grouped_merge_new_signature -v`
Expected: FAIL — `merge()` got unexpected keyword arguments

- [ ] **Step 3: Update GroupedMergeStrategy**

In `refiner/src/refiner/stages/anchor.py`, update `GroupedMergeStrategy`:

Remove `generic_safety_uris` from `__init__`:

```python
def __init__(self, always_included: list[str] | None = None):
    self._always_included = set(always_included or ALWAYS_INCLUDED)
```

Update `merge` signature and body:

```python
def merge(
    self,
    per_domain_candidates: dict[str, list[dict]],
    selected_domains: list[str],
    max_candidates: int,
    risk_context: dict,
    generic_safety_uris: set[str],
) -> list[dict]:
    active_domains = [d for d in selected_domains if d in per_domain_candidates]
    if not active_domains:
        return []

    per_domain_quota = max(1, max_candidates // len(active_domains))
    result: list[dict] = []
    seen: set[str] = set()

    for domain in active_domains:
        taken = 0
        for c in per_domain_candidates.get(domain, []):
            uri = c["uri"]
            if uri in seen:
                continue
            if generic_safety_uris and uri in generic_safety_uris:
                continue
            if taken < per_domain_quota:
                result.append(c)
                seen.add(uri)
                taken += 1

    return result[:max_candidates]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd refiner && uv run pytest tests/test_anchor.py::test_grouped_merge_new_signature -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd refiner && git add src/refiner/stages/anchor.py tests/test_anchor.py
git commit -m "refactor(anchor): update GroupedMergeStrategy to new protocol signature"
```

---

### Task 3: Fix All Existing Tests to Use New Signature

**Files:**
- Modify: `refiner/tests/test_anchor.py`

All existing tests that call `strategy.merge(...)` or set `strategy.generic_safety_uris = ...` need updating.

- [ ] **Step 1: Update all WeightedMergeStrategy tests**

Every call to `strategy.merge(per_domain, selected, max_candidates=N)` becomes:

```python
strategy.merge(per_domain, selected, max_candidates=N, risk_context={}, generic_safety_uris=set())
```

Every test that sets `strategy.generic_safety_uris = {…}` changes to pass the set as the `generic_safety_uris` parameter instead. Remove the instance attribute assignment.

Tests to update (search for `.merge(` and `.generic_safety_uris`):

- `test_weighted_merge_guarantees_domain_selected_slots` (line ~828)
- `test_weighted_merge_fills_with_always_included` (line ~842)
- `test_weighted_merge_no_domain_selected` (line ~856)
- `test_weighted_merge_deduplicates` (line ~868)
- `test_grouped_merge_equal_distribution` (line ~880)
- `test_grouped_merge_caps_at_max` (line ~895)
- `test_grouped_merge_skips_empty_domains` (line ~905)
- `test_strategy_protocol_compliance` (line ~915) — keep but note it only checks isinstance
- `test_weighted_merge_filters_poor_distance_candidate` (line ~1035)
- `test_weighted_merge_keeps_good_single_candidate` (line ~1054)
- `test_weighted_merge_filters_domain_outlier_by_zscore` (line ~1072)
- `test_weighted_merge_pool_filters_by_threshold` (line ~1093)
- `test_weighted_merge_filters_generic_safety_uris` (line ~1115) — change `strategy.generic_safety_uris = {…}` to parameter
- `test_weighted_merge_no_filter_when_generic_safety_empty` (line ~1141) — pass `generic_safety_uris=set()`
- `test_weighted_merge_generic_safety_filters_quota_pass` (line ~1156) — change to parameter
- `test_grouped_merge_filters_generic_safety_uris` (line ~1177) — change to parameter

Example — `test_weighted_merge_filters_generic_safety_uris` before:

```python
def test_weighted_merge_filters_generic_safety_uris():
    strategy = WeightedMergeStrategy(always_included=["CCO", "CSO"])
    strategy.generic_safety_uris = {"http://cso/arson", "http://cso/cbrn"}
    # ...
    result = strategy.merge(per_domain, ["CSO"], max_candidates=5)
```

After:

```python
def test_weighted_merge_filters_generic_safety_uris():
    strategy = WeightedMergeStrategy(always_included=["CCO", "CSO"])
    # ...
    result = strategy.merge(
        per_domain, ["CSO"], max_candidates=5,
        risk_context={}, generic_safety_uris={"http://cso/arson", "http://cso/cbrn"},
    )
```

- [ ] **Step 2: Run all anchor tests**

Run: `cd refiner && uv run pytest tests/test_anchor.py -v`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
cd refiner && git add tests/test_anchor.py
git commit -m "test(anchor): update all merge tests to new protocol signature"
```

---

### Task 4: Thread generic_safety_uris and policy_concept Through Pipeline

**Files:**
- Modify: `refiner/src/refiner/pipeline.py:43-110`
- Modify: `refiner/src/refiner/stages/anchor.py:333-362` (expand_candidates)
- Modify: `refiner/src/refiner/stages/anchor.py:477-530` (anchor)

- [ ] **Step 1: Write failing test for expand_candidates with new params**

In `refiner/tests/test_anchor.py`:

```python
def test_expand_candidates_passes_risk_context_to_strategy(mock_onto_handlers):
    """expand_candidates assembles risk_context and passes to merge strategy."""
    from unittest.mock import MagicMock
    from refiner.stages.anchor import expand_candidates

    mock_strategy = MagicMock()
    mock_strategy.merge.return_value = [
        {"uri": "http://cso/X", "label": "X", "hit_count": 1, "best_distance": 0.1,
         "domain": "CSO", "query_sources": ["description"]},
    ]
    mock_onto_handlers["search_domains"] = MagicMock(return_value={
        "CSO": [{"uri": "http://cso/X", "label": "X", "distance": 0.1}],
    })

    candidates, stats = expand_candidates(
        description="fraud risk",
        concern="financial loss",
        action_descriptions=[],
        cross_mapped_descriptions=[],
        onto_handlers=mock_onto_handlers,
        selected_domains=["CSO"],
        merge_strategy=mock_strategy,
        policy_concept="Fraud Prevention",
        generic_safety_uris={"http://cso/arson"},
    )

    mock_strategy.merge.assert_called_once()
    call_kwargs = mock_strategy.merge.call_args
    assert call_kwargs[1]["risk_context"] == {
        "description": "fraud risk",
        "concern": "financial loss",
        "policy_concept": "Fraud Prevention",
    }
    assert call_kwargs[1]["generic_safety_uris"] == {"http://cso/arson"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd refiner && uv run pytest tests/test_anchor.py::test_expand_candidates_passes_risk_context_to_strategy -v`
Expected: FAIL — `expand_candidates()` got unexpected keyword arguments

- [ ] **Step 3: Update expand_candidates signature and merge call**

In `refiner/src/refiner/stages/anchor.py`, update `expand_candidates`:

```python
def expand_candidates(
    description: str,
    concern: str,
    action_descriptions: list[str],
    cross_mapped_descriptions: list[str],
    onto_handlers: dict,
    selected_domains: list[str] | None,
    merge_strategy: SearchMergeStrategy | None = None,
    top_k_per_query: int = 10,
    max_candidates: int = 5,
    policy_concept: str = "",
    generic_safety_uris: set[str] | None = None,
) -> tuple[list[dict], dict]:
```

Update the merge call site (inside the `if merge_strategy ...` branch):

```python
        kept = merge_strategy.merge(
            per_domain, selected_domains, max_candidates,
            risk_context={
                "description": description,
                "concern": concern,
                "policy_concept": policy_concept,
            },
            generic_safety_uris=generic_safety_uris or set(),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd refiner && uv run pytest tests/test_anchor.py::test_expand_candidates_passes_risk_context_to_strategy -v`
Expected: PASS

- [ ] **Step 5: Update anchor() to thread policy_concept and generic_safety_uris**

In `refiner/src/refiner/stages/anchor.py`, update `anchor` signature:

```python
def anchor(
    risk_mappings: list[PolicyRiskMapping],
    risk_details: dict[str, dict],
    client: instructor.Instructor,
    config: LLMConfig,
    onto_handlers: dict,
    selected_domains: list[str] | None = None,
    risk_actions: dict[str, list[str]] | None = None,
    related_risks: dict[str, list[dict]] | None = None,
    merge_strategy: SearchMergeStrategy | None = None,
    report=None,
    generic_safety_uris: set[str] | None = None,
) -> list[RiskVariationAxes]:
```

Update the `expand_candidates` call inside `anchor()` (line ~522):

```python
            candidates, expansion_stats = expand_candidates(
                description=description,
                concern=concern,
                action_descriptions=actions,
                cross_mapped_descriptions=cross_mapped_descs,
                onto_handlers=onto_handlers,
                selected_domains=selected_domains,
                merge_strategy=merge_strategy,
                policy_concept=mapping.policy_concept,
                generic_safety_uris=generic_safety_uris,
            )
```

- [ ] **Step 6: Update pipeline.py to compute and pass generic_safety_uris**

In `refiner/src/refiner/pipeline.py`, replace the mutable state block (lines 65-75) with:

```python
    # Compute CSO DangerousInformation filter for domain-specific runs
    generic_safety_uris: set[str] = set()
    if state.selected_domains:
        domain_specific = set(state.selected_domains) - set(ALWAYS_INCLUDED)
        if domain_specific:
            uris = build_generic_safety_uris(onto_handlers)
            if uris:
                generic_safety_uris = uris
                logger.info(
                    "Filtering %d CSO generic-safety URIs (domain-specific: %s)",
                    len(uris), ", ".join(sorted(domain_specific)),
                )
```

Update the `anchor()` call (lines 88-95):

```python
    state.variation_axes = anchor(
        state.risk_mappings, state.risk_details, client, config, onto_handlers,
        selected_domains=state.selected_domains,
        risk_actions=state.risk_actions,
        related_risks=state.related_risks,
        merge_strategy=merge_strategy,
        report=report,
        generic_safety_uris=generic_safety_uris,
    )
```

- [ ] **Step 7: Run all tests**

Run: `cd refiner && uv run pytest tests/ -v`
Expected: ALL PASS (some existing `expand_candidates` tests may need `policy_concept`/`generic_safety_uris` added — these have defaults so should be fine)

- [ ] **Step 8: Commit**

```bash
cd refiner && git add src/refiner/stages/anchor.py src/refiner/pipeline.py tests/test_anchor.py
git commit -m "refactor(anchor): thread generic_safety_uris and policy_concept as parameters"
```

---

### Task 5: Implement LLMMergeStrategy

**Files:**
- Modify: `refiner/src/refiner/stages/anchor.py`

- [ ] **Step 1: Write the failing test — pre-filter removes bad candidates**

In `refiner/tests/test_anchor.py`:

```python
def test_llm_merge_prefilter_removes_high_distance():
    """Pre-filter removes candidates above distance ceiling before LLM call."""
    from refiner.stages.anchor import LLMMergeStrategy

    client = MagicMock()
    config = LLMConfig(base_url="http://localhost:8000/v1", model="test-model")
    strategy = LLMMergeStrategy(client, config)

    per_domain = {
        "CSO": [
            {"uri": "http://cso/good", "label": "Good", "hit_count": 2, "best_distance": 0.1,
             "domain": "CSO", "query_sources": ["description"]},
            {"uri": "http://cso/bad", "label": "Bad", "hit_count": 1, "best_distance": 0.7,
             "domain": "CSO", "query_sources": ["description"]},
        ],
    }
    # LLM selects index 0 (only candidate after pre-filter)
    client.chat.completions.create.return_value = MagicMock(selected=[0])

    result = strategy.merge(
        per_domain, ["CSO"], max_candidates=5,
        risk_context={"description": "fraud", "concern": "", "policy_concept": "Fraud"},
        generic_safety_uris=set(),
    )
    uris = [c["uri"] for c in result]
    assert "http://cso/good" in uris
    assert "http://cso/bad" not in uris
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd refiner && uv run pytest tests/test_anchor.py::test_llm_merge_prefilter_removes_high_distance -v`
Expected: FAIL — `LLMMergeStrategy` not found

- [ ] **Step 3: Write the failing test — pre-filter removes safety URIs**

In `refiner/tests/test_anchor.py`:

```python
def test_llm_merge_prefilter_removes_safety_uris():
    """Pre-filter removes candidates in generic_safety_uris before LLM call."""
    from refiner.stages.anchor import LLMMergeStrategy

    client = MagicMock()
    config = LLMConfig(base_url="http://localhost:8000/v1", model="test-model")
    strategy = LLMMergeStrategy(client, config)

    per_domain = {
        "CSO": [
            {"uri": "http://cso/fraud", "label": "Fraud", "hit_count": 2, "best_distance": 0.1,
             "domain": "CSO", "query_sources": ["description"]},
            {"uri": "http://cso/arson", "label": "Arson", "hit_count": 3, "best_distance": 0.05,
             "domain": "CSO", "query_sources": ["description"]},
        ],
    }
    client.chat.completions.create.return_value = MagicMock(selected=[0])

    result = strategy.merge(
        per_domain, ["CSO"], max_candidates=5,
        risk_context={"description": "fraud", "concern": "", "policy_concept": "Fraud"},
        generic_safety_uris={"http://cso/arson"},
    )
    uris = [c["uri"] for c in result]
    assert "http://cso/fraud" in uris
    assert "http://cso/arson" not in uris
```

- [ ] **Step 4: Write the failing test — LLM selects from pool**

In `refiner/tests/test_anchor.py`:

```python
def test_llm_merge_selects_by_llm_judgment():
    """LLM merge selects candidates by LLM response indices."""
    from refiner.stages.anchor import LLMMergeStrategy

    client = MagicMock()
    config = LLMConfig(base_url="http://localhost:8000/v1", model="test-model")
    strategy = LLMMergeStrategy(client, config)

    per_domain = {
        "CSO": [
            {"uri": "http://cso/A", "label": "Fraud", "hit_count": 2, "best_distance": 0.1,
             "domain": "CSO", "query_sources": ["description"]},
            {"uri": "http://cso/B", "label": "Privacy", "hit_count": 1, "best_distance": 0.2,
             "domain": "CSO", "query_sources": ["description"]},
        ],
        "FIBO": [
            {"uri": "http://fibo/C", "label": "Lending", "hit_count": 1, "best_distance": 0.15,
             "domain": "FIBO", "query_sources": ["description"]},
            {"uri": "http://fibo/D", "label": "Federal Reserve", "hit_count": 1, "best_distance": 0.3,
             "domain": "FIBO", "query_sources": ["description"]},
        ],
    }
    # LLM picks indices 0 and 2 (Fraud and Lending, skipping Privacy and Federal Reserve)
    client.chat.completions.create.return_value = MagicMock(selected=[0, 2])

    result = strategy.merge(
        per_domain, ["CSO", "FIBO"], max_candidates=5,
        risk_context={"description": "fraud", "concern": "loss", "policy_concept": "Fraud"},
        generic_safety_uris=set(),
    )
    uris = [c["uri"] for c in result]
    assert uris == ["http://cso/A", "http://fibo/C"]
```

- [ ] **Step 5: Write the failing test — fallback on LLM failure**

In `refiner/tests/test_anchor.py`:

```python
def test_llm_merge_fallback_on_failure():
    """Falls back to distance-sorted order when LLM call fails."""
    from refiner.stages.anchor import LLMMergeStrategy

    client = MagicMock()
    config = LLMConfig(base_url="http://localhost:8000/v1", model="test-model")
    strategy = LLMMergeStrategy(client, config)

    per_domain = {
        "CSO": [
            {"uri": "http://cso/A", "label": "A", "hit_count": 1, "best_distance": 0.3,
             "domain": "CSO", "query_sources": ["description"]},
            {"uri": "http://cso/B", "label": "B", "hit_count": 2, "best_distance": 0.1,
             "domain": "CSO", "query_sources": ["description"]},
        ],
    }
    client.chat.completions.create.side_effect = Exception("LLM failed")

    result = strategy.merge(
        per_domain, ["CSO"], max_candidates=5,
        risk_context={"description": "fraud", "concern": "", "policy_concept": "Fraud"},
        generic_safety_uris=set(),
    )
    # Fallback: sorted by (-hit_count, best_distance)
    assert result[0]["uri"] == "http://cso/B"  # hit_count 2, distance 0.1
    assert result[1]["uri"] == "http://cso/A"  # hit_count 1, distance 0.3
```

- [ ] **Step 6: Write the failing test — truncation**

In `refiner/tests/test_anchor.py`:

```python
def test_llm_merge_truncates_to_max_candidates():
    """Result truncated to max_candidates even if LLM returns more."""
    from refiner.stages.anchor import LLMMergeStrategy

    client = MagicMock()
    config = LLMConfig(base_url="http://localhost:8000/v1", model="test-model")
    strategy = LLMMergeStrategy(client, config)

    per_domain = {
        "CSO": [
            {"uri": f"http://cso/{i}", "label": f"C{i}", "hit_count": 1, "best_distance": 0.1 + i * 0.01,
             "domain": "CSO", "query_sources": ["description"]}
            for i in range(10)
        ],
    }
    # LLM returns 8 indices
    client.chat.completions.create.return_value = MagicMock(selected=[0, 1, 2, 3, 4, 5, 6, 7])

    result = strategy.merge(
        per_domain, ["CSO"], max_candidates=3,
        risk_context={"description": "fraud", "concern": "", "policy_concept": "Fraud"},
        generic_safety_uris=set(),
    )
    assert len(result) == 3
```

- [ ] **Step 7: Write the failing test — empty pool skips LLM**

In `refiner/tests/test_anchor.py`:

```python
def test_llm_merge_empty_pool_no_llm_call():
    """Empty pre-filtered pool returns empty without calling LLM."""
    from refiner.stages.anchor import LLMMergeStrategy

    client = MagicMock()
    config = LLMConfig(base_url="http://localhost:8000/v1", model="test-model")
    strategy = LLMMergeStrategy(client, config)

    per_domain = {
        "CSO": [
            {"uri": "http://cso/bad", "label": "Bad", "hit_count": 1, "best_distance": 0.8,
             "domain": "CSO", "query_sources": ["description"]},
        ],
    }
    result = strategy.merge(
        per_domain, ["CSO"], max_candidates=5,
        risk_context={"description": "fraud", "concern": "", "policy_concept": "Fraud"},
        generic_safety_uris=set(),
    )
    assert result == []
    client.chat.completions.create.assert_not_called()
```

- [ ] **Step 8: Write the failing test — protocol compliance**

In `refiner/tests/test_anchor.py`:

```python
def test_llm_merge_protocol_compliance():
    """LLMMergeStrategy satisfies the SearchMergeStrategy protocol."""
    from refiner.stages.anchor import LLMMergeStrategy, SearchMergeStrategy

    client = MagicMock()
    config = LLMConfig(base_url="http://localhost:8000/v1", model="test-model")
    strategy = LLMMergeStrategy(client, config)
    assert isinstance(strategy, SearchMergeStrategy)
```

- [ ] **Step 9: Implement LLMMergeStrategy**

In `refiner/src/refiner/stages/anchor.py`, add after `GroupedMergeStrategy`:

```python
_MERGE_SYSTEM_PROMPT = """\
You are selecting ontology classes relevant to an AI risk.

Given a risk (with description, concern, and policy context) and a numbered list of candidate ontology classes, select the classes most relevant to this specific risk. Return their indices.

Select up to {max_candidates} classes. Prefer classes that directly relate to the risk over tangentially related ones."""


class _MergeSelection(BaseModel):
    selected: list[int]


class LLMMergeStrategy:
    """LLM-judged contextual relevance selection.

    Pre-filters by distance ceiling and generic safety URIs, then asks the LLM
    to select the most relevant candidates for the given risk context.
    Falls back to distance-sorted order on LLM failure.
    """

    DISTANCE_CEILING = 0.6

    def __init__(self, client: instructor.Instructor, config: LLMConfig):
        self._client = client
        self._config = config

    def merge(
        self,
        per_domain_candidates: dict[str, list[dict]],
        selected_domains: list[str],
        max_candidates: int,
        risk_context: dict,
        generic_safety_uris: set[str],
    ) -> list[dict]:
        # Pre-filter: distance ceiling + safety URIs
        pool: list[dict] = []
        for domain in sorted(per_domain_candidates):
            for c in per_domain_candidates[domain]:
                if c.get("best_distance", 1.0) >= self.DISTANCE_CEILING:
                    continue
                if generic_safety_uris and c.get("uri", "") in generic_safety_uris:
                    continue
                pool.append(c)

        pool.sort(key=lambda c: (-c.get("hit_count", 0), c.get("best_distance", 1.0)))

        if not pool:
            return []

        if len(pool) <= max_candidates:
            return pool[:max_candidates]

        # Build numbered candidate list for LLM
        lines = []
        for idx, c in enumerate(pool):
            lines.append(f"{idx}. {c.get('label', '')} [{c.get('domain', '')}]")

        user_content = (
            f"Risk: {risk_context.get('description', '')}\n"
            f"Concern: {risk_context.get('concern', '')}\n"
            f"Policy: {risk_context.get('policy_concept', '')}\n\n"
            f"Candidate classes:\n" + "\n".join(lines)
        )

        messages = [
            {"role": "system", "content": _MERGE_SYSTEM_PROMPT.format(max_candidates=max_candidates)},
            {"role": "user", "content": user_content},
        ]

        try:
            result = self._client.chat.completions.create(
                model=self._config.model,
                response_model=_MergeSelection,
                messages=messages,
                temperature=self._config.temperature,
                max_retries=self._config.max_retries,
                max_tokens=self._config.max_tokens,
            )
            debug.log_call("merge", messages, result, context={
                "policy_concept": risk_context.get("policy_concept", ""),
                "pool_size": len(pool),
                "selected_count": len(result.selected),
            })

            selected = []
            for idx in result.selected:
                if 0 <= idx < len(pool):
                    selected.append(pool[idx])
            return selected[:max_candidates]

        except Exception:
            logger.warning("LLM merge failed, falling back to distance-sorted order", exc_info=True)
            return pool[:max_candidates]
```

- [ ] **Step 10: Run all new LLM merge tests**

Run: `cd refiner && uv run pytest tests/test_anchor.py -k "llm_merge" -v`
Expected: ALL PASS

- [ ] **Step 11: Commit**

```bash
cd refiner && git add src/refiner/stages/anchor.py tests/test_anchor.py
git commit -m "feat(anchor): add LLMMergeStrategy with pre-filter and fallback"
```

---

### Task 6: Wire LLMMergeStrategy into CLI

**Files:**
- Modify: `refiner/src/refiner/cli.py:199-205`

- [ ] **Step 1: Update CLI strategy map**

In `refiner/src/refiner/cli.py`, update the strategy instantiation block (around line 199-205):

```python
    from refiner.stages.anchor import WeightedMergeStrategy, GroupedMergeStrategy, LLMMergeStrategy
    strategy_map = {
        "weighted": lambda: WeightedMergeStrategy(),
        "grouped": lambda: GroupedMergeStrategy(),
        "llm": lambda: LLMMergeStrategy(client, config),
    }
    if search_strategy not in strategy_map:
        typer.echo(f"Error: --search-strategy must be one of: {', '.join(strategy_map)}", err=True)
        raise typer.Exit(1)
    merge_strategy_obj = strategy_map[search_strategy]()
```

- [ ] **Step 2: Remove the mutable state block in pipeline.py**

In `refiner/src/refiner/pipeline.py`, the block that sets `merge_strategy.generic_safety_uris` (lines 66-75) should already have been replaced in Task 4 Step 6. Verify the old `hasattr(merge_strategy, "generic_safety_uris")` block is gone and the new `generic_safety_uris` computation is in place.

- [ ] **Step 3: Run full test suite**

Run: `cd refiner && uv run pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
cd refiner && git add src/refiner/cli.py src/refiner/pipeline.py
git commit -m "feat(cli): add --search-strategy llm option"
```

---

### Task 7: Integration Test

**Files:**
- Modify: `refiner/tests/test_anchor.py`

- [ ] **Step 1: Write integration test**

In `refiner/tests/test_anchor.py`:

```python
def test_expand_candidates_with_llm_strategy(mock_onto_handlers):
    """expand_candidates uses LLMMergeStrategy end-to-end."""
    from refiner.stages.anchor import LLMMergeStrategy, expand_candidates

    mock_client = MagicMock()
    config = LLMConfig(base_url="http://localhost:8000/v1", model="test-model")
    strategy = LLMMergeStrategy(mock_client, config)

    mock_onto_handlers["search_domains"] = MagicMock(return_value={
        "CSO": [
            {"uri": "http://cso/fraud", "label": "Fraud", "distance": 0.1},
            {"uri": "http://cso/privacy", "label": "Privacy", "distance": 0.2},
        ],
        "FIBO": [
            {"uri": "http://fibo/lending", "label": "Lending", "distance": 0.15},
        ],
    })

    # LLM selects index 0 and 2 (Fraud and Lending)
    mock_client.chat.completions.create.return_value = MagicMock(selected=[0, 2])

    candidates, stats = expand_candidates(
        description="fraud risk in banking",
        concern="financial loss",
        action_descriptions=[],
        cross_mapped_descriptions=[],
        onto_handlers=mock_onto_handlers,
        selected_domains=["CSO", "FIBO"],
        merge_strategy=strategy,
        policy_concept="Fraud Prevention",
        generic_safety_uris=set(),
    )

    assert stats["search_strategy"] == "LLMMergeStrategy"
    assert len(candidates) >= 1
    mock_client.chat.completions.create.assert_called_once()
```

- [ ] **Step 2: Run the test**

Run: `cd refiner && uv run pytest tests/test_anchor.py::test_expand_candidates_with_llm_strategy -v`
Expected: PASS

- [ ] **Step 3: Run full test suite one final time**

Run: `cd refiner && uv run pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
cd refiner && git add tests/test_anchor.py
git commit -m "test(anchor): add LLMMergeStrategy integration test"
```
