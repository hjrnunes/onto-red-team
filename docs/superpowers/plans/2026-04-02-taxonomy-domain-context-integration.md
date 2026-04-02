# Taxonomy-Domain Context Integration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deepen integration between risk taxonomy and domain context ontology classes by widening the ontology search funnel, enriching LLM context, and linking outputs structurally.

**Architecture:** Four changes compose into one improvement: (1) `expand_candidates()` in anchor runs multiple ontology searches (description, concern, actions, cross-mapped descriptions) and merges with frequency signal, (2) `map_risks` collects risk actions and threads them through, (3) contextualize receives risk description/concern for informed enumeration filtering, (4) structure embeds domain context summary in taxonomy entries. No new LLM calls or pipeline stages.

**Tech Stack:** Python, Pydantic, Instructor, pytest, existing ontoquery/nexus-mcp handler dicts

**Spec:** `docs/superpowers/specs/2026-04-02-taxonomy-domain-context-integration-design.md`

---

### Task 1: `expand_candidates()` function in anchor

Pure function with no dependencies on other tasks. Replaces the single-search-then-slice pattern.

**Files:**
- Modify: `refiner/src/refiner/stages/anchor.py`
- Test: `refiner/tests/test_anchor.py`

- [ ] **Step 1: Write failing tests for `expand_candidates()`**

Add to `refiner/tests/test_anchor.py`:

```python
from refiner.stages.anchor import expand_candidates


def test_expand_candidates_single_query(mock_onto_handlers):
    """With only a description, behaves like current single search."""
    mock_onto_handlers["search_classes"].return_value = [
        {"uri": "http://example.org/A", "label": "A", "distance": 0.2},
        {"uri": "http://example.org/B", "label": "B", "distance": 0.4},
    ]
    candidates, stats = expand_candidates(
        description="Fraud risk",
        concern="",
        action_descriptions=[],
        cross_mapped_descriptions=[],
        onto_handlers=mock_onto_handlers,
        selected_domains=None,
    )
    assert len(candidates) == 2
    assert candidates[0]["uri"] == "http://example.org/A"
    assert stats["queries_run"] == 1
    mock_onto_handlers["search_classes"].assert_called_once()


def test_expand_candidates_multi_query_dedup(mock_onto_handlers):
    """Same URI from multiple queries gets hit_count > 1."""
    mock_onto_handlers["search_classes"].side_effect = [
        # description query
        [{"uri": "http://example.org/A", "label": "A", "distance": 0.3},
         {"uri": "http://example.org/B", "label": "B", "distance": 0.5}],
        # concern query
        [{"uri": "http://example.org/A", "label": "A", "distance": 0.2},
         {"uri": "http://example.org/C", "label": "C", "distance": 0.4}],
    ]
    candidates, stats = expand_candidates(
        description="Fraud risk",
        concern="Financial loss",
        action_descriptions=[],
        cross_mapped_descriptions=[],
        onto_handlers=mock_onto_handlers,
        selected_domains=None,
    )
    assert stats["queries_run"] == 2
    assert stats["unique_after_dedup"] == 3  # A, B, C
    # A appears in both queries — should be ranked first
    a = next(c for c in candidates if c["uri"] == "http://example.org/A")
    assert a["hit_count"] == 2
    assert a["best_distance"] == 0.2  # min of 0.3 and 0.2


def test_expand_candidates_with_actions(mock_onto_handlers):
    """Action descriptions generate additional search queries."""
    mock_onto_handlers["search_classes"].side_effect = [
        [{"uri": "http://example.org/A", "label": "A", "distance": 0.3}],  # description
        [{"uri": "http://example.org/B", "label": "B", "distance": 0.4}],  # action 1
        [{"uri": "http://example.org/C", "label": "C", "distance": 0.5}],  # action 2
    ]
    candidates, stats = expand_candidates(
        description="Fraud risk",
        concern="",
        action_descriptions=["Monitor transactions", "Verify identity"],
        cross_mapped_descriptions=[],
        onto_handlers=mock_onto_handlers,
        selected_domains=None,
    )
    assert stats["queries_run"] == 3
    assert len(candidates) == 3


def test_expand_candidates_with_cross_mappings(mock_onto_handlers):
    """Cross-mapped descriptions generate additional search queries."""
    mock_onto_handlers["search_classes"].side_effect = [
        [{"uri": "http://example.org/A", "label": "A", "distance": 0.3}],  # description
        [{"uri": "http://example.org/A", "label": "A", "distance": 0.1}],  # cross-mapped
    ]
    candidates, stats = expand_candidates(
        description="Fraud risk",
        concern="",
        action_descriptions=[],
        cross_mapped_descriptions=["Financial fraud and scams"],
        onto_handlers=mock_onto_handlers,
        selected_domains=None,
    )
    assert stats["queries_run"] == 2
    a = next(c for c in candidates if c["uri"] == "http://example.org/A")
    assert a["hit_count"] == 2
    assert a["best_distance"] == 0.1


def test_expand_candidates_domain_filter(mock_onto_handlers):
    """Domain filtering is applied after merge."""
    mock_onto_handlers["search_classes"].return_value = [
        {"uri": "http://purl.obolibrary.org/obo/MAXO_001", "label": "MaxO1", "distance": 0.1},
        {"uri": "https://spec.edmcouncil.org/fibo/ontology/FND/Foo", "label": "Foo", "distance": 0.2},
    ]
    candidates, stats = expand_candidates(
        description="Fraud risk",
        concern="",
        action_descriptions=[],
        cross_mapped_descriptions=[],
        onto_handlers=mock_onto_handlers,
        selected_domains=["CCO", "Commons", "FIBO", "D3FEND", "CSO"],
    )
    # OBO candidate should be filtered out
    assert all(c["uri"] != "http://purl.obolibrary.org/obo/MAXO_001" for c in candidates)
    assert stats["kept_after_filter"] == 1


def test_expand_candidates_max_candidates(mock_onto_handlers):
    """Results are capped at max_candidates."""
    mock_onto_handlers["search_classes"].return_value = [
        {"uri": f"http://example.org/{i}", "label": f"C{i}", "distance": i * 0.1}
        for i in range(10)
    ]
    candidates, stats = expand_candidates(
        description="Fraud risk",
        concern="",
        action_descriptions=[],
        cross_mapped_descriptions=[],
        onto_handlers=mock_onto_handlers,
        selected_domains=None,
        max_candidates=5,
    )
    assert len(candidates) == 5


def test_expand_candidates_sorts_by_hit_count_then_distance(mock_onto_handlers):
    """Candidates sorted by hit_count desc, then best_distance asc."""
    mock_onto_handlers["search_classes"].side_effect = [
        # description
        [{"uri": "http://example.org/A", "label": "A", "distance": 0.5},
         {"uri": "http://example.org/B", "label": "B", "distance": 0.1}],
        # concern
        [{"uri": "http://example.org/A", "label": "A", "distance": 0.4}],
    ]
    candidates, _ = expand_candidates(
        description="Fraud",
        concern="Loss",
        action_descriptions=[],
        cross_mapped_descriptions=[],
        onto_handlers=mock_onto_handlers,
        selected_domains=None,
    )
    # A has hit_count=2, B has hit_count=1 → A first
    assert candidates[0]["uri"] == "http://example.org/A"
    assert candidates[1]["uri"] == "http://example.org/B"


def test_expand_candidates_skips_empty_queries(mock_onto_handlers):
    """Empty strings are not searched."""
    mock_onto_handlers["search_classes"].return_value = [
        {"uri": "http://example.org/A", "label": "A", "distance": 0.3},
    ]
    candidates, stats = expand_candidates(
        description="Fraud risk",
        concern="",
        action_descriptions=["", "  "],
        cross_mapped_descriptions=[],
        onto_handlers=mock_onto_handlers,
        selected_domains=None,
    )
    assert stats["queries_run"] == 1  # only description, not empty strings


def test_expand_candidates_tracks_query_sources(mock_onto_handlers):
    """Each candidate tracks which query sources found it."""
    mock_onto_handlers["search_classes"].side_effect = [
        [{"uri": "http://example.org/A", "label": "A", "distance": 0.3}],  # description
        [{"uri": "http://example.org/A", "label": "A", "distance": 0.2}],  # concern
        [{"uri": "http://example.org/A", "label": "A", "distance": 0.4}],  # action
    ]
    candidates, _ = expand_candidates(
        description="Fraud",
        concern="Loss",
        action_descriptions=["Monitor"],
        cross_mapped_descriptions=[],
        onto_handlers=mock_onto_handlers,
        selected_domains=None,
    )
    a = candidates[0]
    assert "description" in a["query_sources"]
    assert "concern" in a["query_sources"]
    assert "action" in a["query_sources"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd refiner && uv run pytest tests/test_anchor.py -k "expand_candidates" -v`
Expected: FAIL — `expand_candidates` not importable

- [ ] **Step 3: Implement `expand_candidates()` in anchor.py**

Add to `refiner/src/refiner/stages/anchor.py`, before the `anchor()` function:

```python
def expand_candidates(
    description: str,
    concern: str,
    action_descriptions: list[str],
    cross_mapped_descriptions: list[str],
    onto_handlers: dict,
    selected_domains: list[str] | None,
    top_k_per_query: int = 10,
    max_candidates: int = 5,
) -> tuple[list[dict], dict]:
    """Run multiple ontology searches, merge by URI, annotate with hit count."""
    queries: list[tuple[str, str]] = []  # (query_text, source_label)
    if description.strip():
        queries.append((description, "description"))
    if concern.strip():
        queries.append((concern, "concern"))
    for a in action_descriptions:
        if a.strip():
            queries.append((a, "action"))
    for d in cross_mapped_descriptions:
        if d.strip():
            queries.append((d, "cross_mapping"))

    # Run all queries and collect results
    by_uri: dict[str, dict] = {}  # uri -> merged candidate
    raw_total = 0
    for query_text, source_label in queries:
        results = onto_handlers["search_classes"](query_text, top_k=top_k_per_query)
        raw_total += len(results)
        for r in results:
            uri = r.get("uri", "")
            if not uri:
                continue
            if uri not in by_uri:
                by_uri[uri] = {
                    "uri": uri,
                    "label": r.get("label", ""),
                    "hit_count": 0,
                    "best_distance": float("inf"),
                    "query_sources": [],
                }
            entry = by_uri[uri]
            entry["hit_count"] += 1
            dist = r.get("distance", 1.0)
            if dist < entry["best_distance"]:
                entry["best_distance"] = dist
            if source_label not in entry["query_sources"]:
                entry["query_sources"].append(source_label)

    # Domain filter
    if selected_domains:
        filtered = {
            uri: c for uri, c in by_uri.items()
            if derive_source_ontology(uri) in selected_domains
        }
    else:
        filtered = by_uri

    # Sort: hit_count desc, best_distance asc
    sorted_candidates = sorted(
        filtered.values(),
        key=lambda c: (-c["hit_count"], c["best_distance"]),
    )
    kept = sorted_candidates[:max_candidates]

    stats = {
        "queries_run": len(queries),
        "raw_total": raw_total,
        "unique_after_dedup": len(by_uri),
        "kept_after_filter": len(kept),
    }

    return kept, stats
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd refiner && uv run pytest tests/test_anchor.py -k "expand_candidates" -v`
Expected: All PASS

- [ ] **Step 5: Run full anchor test suite to check no regressions**

Run: `cd refiner && uv run pytest tests/test_anchor.py -v`
Expected: All existing tests still PASS

- [ ] **Step 6: Commit**

```bash
cd refiner && git add src/refiner/stages/anchor.py tests/test_anchor.py
git commit -m "feat(refiner): add expand_candidates() for multi-query ontology search"
```

---

### Task 2: Action collection in map_risks

Adds `get_related_actions()` calls and returns actions as 5th tuple element.

**Files:**
- Modify: `refiner/src/refiner/stages/map_risks.py`
- Test: `refiner/tests/test_map_risks.py`

**Dependencies:** None (independent of Task 1)

- [ ] **Step 1: Write failing tests for action collection**

Add to `refiner/tests/test_map_risks.py`:

```python
def test_map_risks_returns_risk_actions(mock_client, mock_config, mock_risk_handlers):
    """map_risks collects action descriptions from get_related_actions."""
    classifications = [_make_classification()]
    mock_risk_handlers["search_risks"].return_value = [
        {"id": "atlas-fraud", "name": "Fraud", "description": "Fraud risk", "distance": 0.2},
    ]
    mock_risk_handlers["get_risk_details"].return_value = {
        "id": "atlas-fraud", "name": "Fraud", "description": "d", "concern": "c",
        "risk_type": "output", "taxonomy": "ibm-risk-atlas",
    }
    mock_risk_handlers["get_related_risks"].return_value = []
    mock_risk_handlers["get_related_actions"].return_value = [
        {"id": "action-1", "name": "Monitor transactions", "description": "Monitor financial transactions for anomalies"},
        {"id": "action-2", "name": "Verify identity", "description": "Verify user identity before sensitive operations"},
    ]
    mock_client.chat.completions.create.return_value = _RiskSelection(
        matched_risks=[_SlimRiskMatch(risk_index=1, risk_name="Fraud", relevance="primary", justification="j")],
    )
    mappings, details, seen_ids, related, risk_actions = map_risks(
        classifications, mock_client, mock_config, mock_risk_handlers,
    )
    assert "atlas-fraud" in risk_actions
    assert len(risk_actions["atlas-fraud"]) == 2
    assert "Monitor financial transactions for anomalies" in risk_actions["atlas-fraud"]


def test_map_risks_actions_empty_when_none(mock_client, mock_config, mock_risk_handlers):
    """When get_related_actions returns empty, risk_actions has empty list."""
    classifications = [_make_classification()]
    mock_risk_handlers["search_risks"].return_value = [
        {"id": "atlas-fraud", "name": "Fraud", "description": "d", "distance": 0.2},
    ]
    mock_risk_handlers["get_risk_details"].return_value = {
        "id": "atlas-fraud", "name": "Fraud", "description": "d", "concern": "c",
        "risk_type": "output", "taxonomy": "ibm-risk-atlas",
    }
    mock_risk_handlers["get_related_risks"].return_value = []
    mock_risk_handlers["get_related_actions"].return_value = []
    mock_client.chat.completions.create.return_value = _RiskSelection(
        matched_risks=[_SlimRiskMatch(risk_index=1, risk_name="Fraud", relevance="primary", justification="j")],
    )
    _, _, _, _, risk_actions = map_risks(
        classifications, mock_client, mock_config, mock_risk_handlers,
    )
    assert risk_actions.get("atlas-fraud") == []


def test_map_risks_actions_skips_empty_descriptions(mock_client, mock_config, mock_risk_handlers):
    """Actions without descriptions are not included."""
    classifications = [_make_classification()]
    mock_risk_handlers["search_risks"].return_value = [
        {"id": "atlas-fraud", "name": "Fraud", "description": "d", "distance": 0.2},
    ]
    mock_risk_handlers["get_risk_details"].return_value = {
        "id": "atlas-fraud", "name": "Fraud", "description": "d", "concern": "c",
        "risk_type": "output", "taxonomy": "ibm-risk-atlas",
    }
    mock_risk_handlers["get_related_risks"].return_value = []
    mock_risk_handlers["get_related_actions"].return_value = [
        {"id": "action-1", "name": "No desc", "description": ""},
        {"id": "action-2", "name": "Has desc", "description": "Real description"},
    ]
    mock_client.chat.completions.create.return_value = _RiskSelection(
        matched_risks=[_SlimRiskMatch(risk_index=1, risk_name="Fraud", relevance="primary", justification="j")],
    )
    _, _, _, _, risk_actions = map_risks(
        classifications, mock_client, mock_config, mock_risk_handlers,
    )
    assert risk_actions["atlas-fraud"] == ["Real description"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd refiner && uv run pytest tests/test_map_risks.py -k "actions" -v`
Expected: FAIL — `map_risks` returns 4-tuple, not 5

- [ ] **Step 3: Implement action collection in map_risks**

In `refiner/src/refiner/stages/map_risks.py`:

Add `risk_actions_cache: dict[str, list[str]] = {}` at the top of the function alongside the other caches.

Inside the `for c in candidates` loop, after the `get_related_risks` call, add:

```python
actions = risk_handlers["get_related_actions"](c["id"])
risk_actions_cache[c["id"]] = [a.get("description", "") for a in actions if a.get("description")]
```

Update the **early return** for empty classifications (line 49-50 of `map_risks.py`) from:
```python
return [], {}, set(), {}
```
to:
```python
return [], {}, set(), {}, {}
```

Change the **main return** at the end from:
```python
return mappings, risk_details_cache, seen_risk_ids, related_risks
```
to:
```python
return mappings, risk_details_cache, seen_risk_ids, related_risks, risk_actions_cache
```

- [ ] **Step 4: Update all existing test unpackings from 4-tuple to 5-tuple**

In `refiner/tests/test_map_risks.py`, update all lines that unpack `map_risks` results. Every occurrence of:
```python
mappings, details, seen_ids, related = map_risks(...)
```
becomes:
```python
mappings, details, seen_ids, related, _ = map_risks(...)
```

And every occurrence of:
```python
_, details, _, _ = map_risks(...)
_, _, seen_ids, _ = map_risks(...)
_, _, _, related_risks = map_risks(...)
mappings, _, _, _ = map_risks(...)
```
adds the 5th `_` placeholder.

Also update `test_map_risks_empty_classifications` assertions to include the 5th element:
```python
mappings, details, seen_ids, related, risk_actions = map_risks([], ...)
assert risk_actions == {}
```

- [ ] **Step 5: Run tests to verify all pass**

Run: `cd refiner && uv run pytest tests/test_map_risks.py -v`
Expected: All PASS (old and new)

- [ ] **Step 6: Commit**

```bash
cd refiner && git add src/refiner/stages/map_risks.py tests/test_map_risks.py
git commit -m "feat(refiner): collect risk actions in map_risks (5-tuple return)"
```

---

### Task 3: Pipeline wiring and anchor integration

Connects `expand_candidates()` into the anchor stage and threads new data through the pipeline.

**Files:**
- Modify: `refiner/src/refiner/pipeline.py` — `PipelineState` + `run_pipeline()` wiring
- Modify: `refiner/src/refiner/stages/anchor.py` — use `expand_candidates()` in `anchor()`
- Modify: `refiner/src/refiner/cli.py` — update `map_risks` unpacking (if any direct calls)
- Modify: `refiner/tests/test_pipeline.py` — update mock return (5-tuple), anchor/contextualize call assertions
- Test: `refiner/tests/test_anchor.py`

**Dependencies:** Task 1 (`expand_candidates`), Task 2 (5-tuple return)

**Note:** Task 4 also modifies `pipeline.py` (contextualize wiring). Execute Task 4 after Task 3 to avoid merge conflicts.

- [ ] **Step 1: Add `risk_actions` field to `PipelineState`**

In `refiner/src/refiner/pipeline.py`, add to the `PipelineState` dataclass:

```python
risk_actions: dict[str, list[str]] | None = None
```

- [ ] **Step 2: Update `run_pipeline()` to capture 5-tuple and pass new params**

In `refiner/src/refiner/pipeline.py`, change the `map_risks` call unpacking from:
```python
state.risk_mappings, state.risk_details, state.seen_risk_ids, state.related_risks = map_risks(...)
```
to:
```python
state.risk_mappings, state.risk_details, state.seen_risk_ids, state.related_risks, state.risk_actions = map_risks(...)
```

Change the `anchor` call from:
```python
state.variation_axes = anchor(
    state.risk_mappings, state.risk_details, client, config, onto_handlers,
    selected_domains=state.selected_domains, report=report,
)
```
to:
```python
state.variation_axes = anchor(
    state.risk_mappings, state.risk_details, client, config, onto_handlers,
    selected_domains=state.selected_domains,
    risk_actions=state.risk_actions,
    related_risks=state.related_risks,
    report=report,
)
```

- [ ] **Step 3: Update `anchor()` to accept and use new params**

In `refiner/src/refiner/stages/anchor.py`, change anchor signature:

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
    report=None,
) -> list[RiskVariationAxes]:
```

Replace the existing candidate search block:
```python
raw_candidates = onto_handlers["search_classes"](description, top_k=10)
if selected_domains:
    candidates = [c for c in raw_candidates
                  if derive_source_ontology(c.get("uri", "")) in selected_domains][:3]
    ...
else:
    candidates = raw_candidates[:3]
```

With:
```python
actions = risk_actions.get(rm.risk_id, []) if risk_actions else []
cross_mapped_descs = []
if related_risks:
    for rel in related_risks.get(rm.risk_id, []):
        desc = rel.get("description", "")
        if desc:
            cross_mapped_descs.append(desc)

candidates, expansion_stats = expand_candidates(
    description=description,
    concern=concern,
    action_descriptions=actions,
    cross_mapped_descriptions=cross_mapped_descs,
    onto_handlers=onto_handlers,
    selected_domains=selected_domains,
)

if report:
    report.events.append({
        "stage": "anchor", "event": "candidate_expansion",
        "risk_id": rm.risk_id, **expansion_stats,
    })
    for c in candidates:
        report.events.append({
            "stage": "anchor", "event": "multi_query_hit",
            "risk_id": rm.risk_id,
            "uri": c["uri"],
            "hit_count": c["hit_count"],
            "best_distance": c["best_distance"],
            "query_sources": c["query_sources"],
        })
```

Remove the old `domain_filtered` event emission (domain filtering now happens inside `expand_candidates`).

Update the enrichment loop to use the new candidate format — candidates from `expand_candidates()` have `uri`, `label`, `hit_count`, `best_distance`, `query_sources`. The enrichment loop uses `c["uri"]` (unchanged).

Update the LLM prompt to include frequency annotation:
```python
for ec in enriched:
    hit_info = ""
    cand = next((c for c in candidates if c["uri"] == ec["uri"]), None)
    if cand and cand.get("hit_count", 1) > 1:
        hit_info = f" [found by {cand['hit_count']}/{expansion_stats['queries_run']} queries]"
    line = f"- {ec['uri']}: {ec.get('label', '')} — {ec.get('definition', '')}{hit_info}"
    ...
```

- [ ] **Step 4: Update `test_pipeline.py`**

In `refiner/tests/test_pipeline.py`:

1. Update the mock `map_risks` return value from 4-tuple to 5-tuple — add `{}` (empty risk_actions) as 5th element.

2. Update the `anchor` call assertion to include the new kwargs:
```python
m_anchor.assert_called_once_with(
    map_result[0], map_result[1], mock_client, mock_config, mock_onto_handlers,
    selected_domains=domains_result,
    risk_actions=state.risk_actions,
    related_risks=state.related_risks,
    report=report,
)
```
(Adjust exact variable names to match what the test file uses.)

3. The `contextualize` call assertion update will be done in Task 4.

- [ ] **Step 5: Fix existing anchor tests broken by `expand_candidates`**

After `expand_candidates` integration, `search_classes` is called for each non-empty query string (description + concern). Since `_make_risk_details()` sets `concern="Financial loss and trust erosion"`, all existing anchor tests that use `_make_risk_details()` will now have 2 `search_classes` calls instead of 1.

**Fix these specific tests:**

In `test_anchor_searches_ontology` (line 60): change `assert_called_once()` to `assert mock_onto_handlers["search_classes"].call_count >= 1`

In `test_anchor_filters_candidates_by_domain` (line 114): change `assert_called_once()` to `assert mock_onto_handlers["search_classes"].call_count >= 1`

Also: these tests use `return_value` on `search_classes`, which only works for the first call. Since `expand_candidates` will call `search_classes` for concern too, the second call will return the same value (which is fine — dedup will merge them). No change needed for `return_value` tests. But tests using `side_effect` (list of returns) need enough return values for all queries — add extra returns as needed.

- [ ] **Step 6: Write tests for anchor with expanded candidates**

Add to `refiner/tests/test_anchor.py`:

```python
def test_anchor_uses_expand_candidates_with_actions(mock_client, mock_config, mock_onto_handlers):
    """When risk_actions are provided, expand_candidates uses them."""
    mappings = [_make_mapping()]
    risk_details = _make_risk_details()
    risk_actions = {"atlas-fraud": ["Monitor financial transactions"]}
    # search_classes called 3 times: description, concern (from _make_risk_details), action
    mock_onto_handlers["search_classes"].side_effect = [
        [{"uri": "http://example.org/Person", "label": "Person", "distance": 0.3}],  # description
        [{"uri": "http://example.org/Person", "label": "Person", "distance": 0.4}],  # concern
        [{"uri": "http://example.org/Transaction", "label": "Transaction", "distance": 0.2}],  # action
    ]
    mock_onto_handlers["get_class_definition"].side_effect = lambda uri: {
        "uri": uri, "label": uri.split("/")[-1], "definition": "d", "superclasses": [],
    }
    mock_onto_handlers["get_siblings"].return_value = []
    mock_onto_handlers["get_superclasses"].return_value = []
    mock_client.chat.completions.create.return_value = _AnchorResponse(
        axes=[_SlimAxis(
            cco_class_uri="http://example.org/Transaction",
            cco_class_label="Transaction", role="object", rationale="r",
        )],
    )
    result = anchor(mappings, risk_details, mock_client, mock_config, mock_onto_handlers,
                    risk_actions=risk_actions)
    assert result[0].axes[0].cco_class_uri == "http://example.org/Transaction"
    # search_classes called 3 times (description + concern + action)
    assert mock_onto_handlers["search_classes"].call_count == 3


def test_anchor_uses_cross_mapped_descriptions(mock_client, mock_config, mock_onto_handlers):
    """When related_risks have descriptions, they drive additional searches."""
    mappings = [_make_mapping()]
    risk_details = _make_risk_details()
    related_risks = {
        "atlas-fraud": [
            {"id": "owasp-fraud", "mapping_type": "close", "description": "Social engineering attacks"},
        ],
    }
    mock_onto_handlers["search_classes"].side_effect = [
        [{"uri": "http://example.org/Person", "label": "Person", "distance": 0.3}],  # description
        [{"uri": "http://example.org/Person", "label": "Person", "distance": 0.4}],  # concern
        [{"uri": "http://example.org/SocialEngineer", "label": "Social Engineer", "distance": 0.2}],  # cross-mapped
    ]
    mock_onto_handlers["get_class_definition"].side_effect = lambda uri: {
        "uri": uri, "label": uri.split("/")[-1], "definition": "d", "superclasses": [],
    }
    mock_onto_handlers["get_siblings"].return_value = []
    mock_onto_handlers["get_superclasses"].return_value = []
    mock_client.chat.completions.create.return_value = _AnchorResponse(
        axes=[_SlimAxis(
            cco_class_uri="http://example.org/SocialEngineer",
            cco_class_label="Social Engineer", role="agent", rationale="r",
        )],
    )
    result = anchor(mappings, risk_details, mock_client, mock_config, mock_onto_handlers,
                    related_risks=related_risks)
    assert result[0].axes[0].cco_class_uri == "http://example.org/SocialEngineer"


def test_anchor_emits_candidate_expansion(mock_client, mock_config, mock_onto_handlers):
    """Anchor emits candidate_expansion event with stats."""
    mappings = [_make_mapping()]
    risk_details = _make_risk_details()
    mock_onto_handlers["search_classes"].return_value = [
        {"uri": "http://example.org/A", "label": "A", "distance": 0.3},
    ]
    mock_onto_handlers["get_class_definition"].return_value = {
        "uri": "http://example.org/A", "label": "A", "definition": "d", "superclasses": [],
    }
    mock_onto_handlers["get_siblings"].return_value = []
    mock_onto_handlers["get_superclasses"].return_value = []
    mock_client.chat.completions.create.return_value = _AnchorResponse(
        axes=[_SlimAxis(cco_class_uri="http://example.org/A", cco_class_label="A", role="agent", rationale="r")],
    )
    report = RunReport(model="m", policy_set="p", timestamp="t")
    anchor(mappings, risk_details, mock_client, mock_config, mock_onto_handlers, report=report)
    expansion = [e for e in report.events if e["event"] == "candidate_expansion"]
    assert len(expansion) == 1
    assert expansion[0]["queries_run"] >= 1


def test_anchor_emits_multi_query_hit(mock_client, mock_config, mock_onto_handlers):
    """Anchor emits multi_query_hit per kept candidate."""
    mappings = [_make_mapping()]
    risk_details = _make_risk_details()
    mock_onto_handlers["search_classes"].side_effect = [
        [{"uri": "http://example.org/A", "label": "A", "distance": 0.3}],
        [{"uri": "http://example.org/A", "label": "A", "distance": 0.2}],
    ]
    mock_onto_handlers["get_class_definition"].return_value = {
        "uri": "http://example.org/A", "label": "A", "definition": "d", "superclasses": [],
    }
    mock_onto_handlers["get_siblings"].return_value = []
    mock_onto_handlers["get_superclasses"].return_value = []
    mock_client.chat.completions.create.return_value = _AnchorResponse(
        axes=[_SlimAxis(cco_class_uri="http://example.org/A", cco_class_label="A", role="agent", rationale="r")],
    )
    report = RunReport(model="m", policy_set="p", timestamp="t")
    anchor(mappings, risk_details, mock_client, mock_config, mock_onto_handlers, report=report)
    hits = [e for e in report.events if e["event"] == "multi_query_hit"]
    assert len(hits) >= 1
    assert hits[0]["hit_count"] >= 1
```

- [ ] **Step 7: Run all anchor tests**

Run: `cd refiner && uv run pytest tests/test_anchor.py -v`
Expected: All PASS (including updated existing tests from Step 5)

- [ ] **Step 8: Run full test suite (including pipeline tests)**

Run: `cd refiner && uv run pytest tests/ -v`
Expected: All PASS

- [ ] **Step 9: Commit**

```bash
cd refiner && git add src/refiner/stages/anchor.py src/refiner/pipeline.py src/refiner/cli.py tests/test_anchor.py tests/test_pipeline.py
git commit -m "feat(refiner): integrate expand_candidates into anchor with action/cross-mapping threading"
```

---

### Task 4: Risk context in contextualize

Threads risk description/concern into the contextualize LLM prompt.

**Files:**
- Modify: `refiner/src/refiner/stages/contextualize.py`
- Modify: `refiner/src/refiner/pipeline.py` — wire `risk_details` to `contextualize()`
- Test: `refiner/tests/test_contextualize.py`

**Dependencies:** None (independent, but pipeline wiring in Task 3 may touch same lines in `pipeline.py`)

- [ ] **Step 1: Write failing test for risk context in prompt**

Add to `refiner/tests/test_contextualize.py`:

```python
def test_contextualize_includes_risk_description_in_prompt(mock_client, mock_config, mock_onto_handlers):
    """When risk_details provided, description and concern appear in LLM prompt."""
    axes = [RiskVariationAxes(
        risk_id="atlas-fraud", risk_name="Fraud", policy_concept="Fraud",
        axes=[VariationAxis(
            cco_class_uri="http://example.org/Person", cco_class_label="Person",
            roles=["agent"], rationale="r",
        )],
    )]
    risk_details = {
        "atlas-fraud": {
            "description": "Fraudulent activities targeting financial systems",
            "concern": "Financial loss and trust erosion",
        },
    }
    mock_onto_handlers["get_subclasses"].return_value = [
        {"uri": "http://example.org/Employee", "label": "Employee", "depth": 1},
    ]
    mock_client.chat.completions.create.return_value = _ContextResponse(axes=[
        _AxisResponse(cco_class_uri="http://example.org/Person", enumerations=[
            _EnumResponse(class_uri="http://example.org/Employee", class_label="Employee", relevance="high"),
        ]),
    ])
    mock_onto_handlers["get_class_definition"].return_value = {
        "uri": "http://example.org/Employee", "label": "Employee", "definition": "d", "superclasses": [],
    }
    result = contextualize(axes, mock_client, mock_config, mock_onto_handlers,
                           risk_details=risk_details)
    # Check the LLM was called with description and concern in the prompt
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    messages = call_kwargs["messages"]
    user_msg = messages[1]["content"]
    assert "Fraudulent activities targeting financial systems" in user_msg
    assert "Financial loss and trust erosion" in user_msg


def test_contextualize_works_without_risk_details(mock_client, mock_config, mock_onto_handlers):
    """Backward compat: risk_details=None still works."""
    axes = [RiskVariationAxes(
        risk_id="atlas-fraud", risk_name="Fraud", policy_concept="Fraud",
        axes=[VariationAxis(
            cco_class_uri="http://example.org/Person", cco_class_label="Person",
            roles=["agent"], rationale="r",
        )],
    )]
    mock_onto_handlers["get_subclasses"].return_value = []
    mock_onto_handlers["get_siblings"].return_value = []
    mock_client.chat.completions.create.return_value = _ContextResponse(axes=[])
    result = contextualize(axes, mock_client, mock_config, mock_onto_handlers)
    assert len(result) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd refiner && uv run pytest tests/test_contextualize.py -k "risk_description" -v`
Expected: FAIL — `contextualize()` doesn't accept `risk_details` parameter

- [ ] **Step 3: Implement risk context in contextualize**

In `refiner/src/refiner/stages/contextualize.py`:

Add `risk_details: dict[str, dict] | None = None` parameter to `contextualize()` signature, before `report`:

```python
def contextualize(
    variation_axes: list[RiskVariationAxes],
    client: instructor.Instructor,
    config: LLMConfig,
    onto_handlers: dict,
    selected_domains: list[str] | None = None,
    risk_details: dict[str, dict] | None = None,
    report: RunReport | None = None,
) -> list[DomainContextProfile]:
```

Inside the loop, before building `user_content`, add:

```python
details = risk_details.get(rva.risk_id, {}) if risk_details else {}
description = details.get("description", "")
concern = details.get("concern", "")
```

Change the `user_content` building from:
```python
user_content = (
    f"Risk: {rva.risk_name} (ID: {rva.risk_id})\n"
    f"Policy: {rva.policy_concept}\n\n"
    + "\n\n".join(axis_context)
)
```
to:
```python
user_content = (
    f"Risk: {rva.risk_name} (ID: {rva.risk_id})\n"
    f"Description: {description}\n"
    f"Concern: {concern}\n"
    f"Policy: {rva.policy_concept}\n\n"
    + "\n\n".join(axis_context)
)
```

- [ ] **Step 4: Wire `risk_details` in `run_pipeline()`**

In `refiner/src/refiner/pipeline.py`, update the `contextualize` call:

```python
state.domain_context = contextualize(
    state.variation_axes, client, config, onto_handlers,
    selected_domains=state.selected_domains,
    risk_details=state.risk_details,
    report=report,
)
```

- [ ] **Step 5: Run tests**

Run: `cd refiner && uv run pytest tests/test_contextualize.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
cd refiner && git add src/refiner/stages/contextualize.py src/refiner/pipeline.py tests/test_contextualize.py
git commit -m "feat(refiner): thread risk description/concern into contextualize prompt"
```

---

### Task 5: Structural output integration

Adds `domain_context_summary` to taxonomy entries.

**Files:**
- Modify: `refiner/src/refiner/stages/structure.py`
- Test: `refiner/tests/test_structure.py`

**Dependencies:** None

- [ ] **Step 1: Write failing tests for domain_context_summary**

Add to `refiner/tests/test_structure.py`:

```python
def test_structure_includes_domain_context_summary():
    """Taxonomy entries include domain_context_summary from matching profiles."""
    classifications, risk_mappings, related_risks, domain_context = _make_state_data()
    taxonomy, _ = structure("swb", classifications, risk_mappings, domain_context,
                            related_risks=related_risks)
    fraud_entry = next(e for e in taxonomy["entries"] if "fraud" in e["id"])
    assert "domain_context_summary" in fraud_entry
    summary = fraud_entry["domain_context_summary"]
    assert summary["axis_count"] == 1
    assert summary["enumeration_count"] == 1
    assert "CCO" in summary["source_ontologies"]
    assert len(summary["axes"]) == 1
    assert summary["axes"][0]["class"] == "Person"


def test_structure_no_summary_when_no_matching_profile():
    """Entries without matching domain context profiles have no summary."""
    classifications, risk_mappings, related_risks, domain_context = _make_state_data()
    taxonomy, _ = structure("swb", classifications, risk_mappings, domain_context,
                            related_risks=related_risks)
    disclosure_entry = next(e for e in taxonomy["entries"] if "data-disclosure" in e["id"])
    # No domain context profile for atlas-data-disclosure in _make_state_data
    assert "domain_context_summary" not in disclosure_entry


def test_structure_summary_with_multiple_axes():
    """Summary correctly aggregates across multiple axes."""
    classifications = [
        PolicyClassification(
            policy_concept="Fraud", concept_definition="d", policy_type="A", justification="j",
        ),
    ]
    risk_mappings = [
        PolicyRiskMapping(
            policy_concept="Fraud", policy_type="A",
            matched_risks=[RiskMatch(risk_id="atlas-fraud", risk_name="Fraud", relevance="primary", justification="j")],
        ),
    ]
    domain_context = [
        DomainContextProfile(
            risk_id="atlas-fraud", risk_name="Fraud", policy_concept="Fraud",
            axes=[
                DomainContextAxis(
                    cco_class_uri="http://example.org/Person", cco_class_label="Person", roles=["agent"],
                    enumerations=[
                        AxisEnumeration(class_uri="http://example.org/E1", class_label="E1", source_ontology="CCO", relevance="high"),
                        AxisEnumeration(class_uri="http://example.org/E2", class_label="E2", source_ontology="CCO", relevance="medium"),
                    ],
                ),
                DomainContextAxis(
                    cco_class_uri="http://example.org/Instrument", cco_class_label="Instrument", roles=["instrument"],
                    enumerations=[
                        AxisEnumeration(class_uri="http://example.org/E3", class_label="E3", source_ontology="FIBO", relevance="high"),
                    ],
                ),
            ],
        ),
    ]
    taxonomy, _ = structure("swb", classifications, risk_mappings, domain_context)
    fraud_entry = next(e for e in taxonomy["entries"] if "fraud" in e["id"])
    summary = fraud_entry["domain_context_summary"]
    assert summary["axis_count"] == 2
    assert summary["enumeration_count"] == 3
    assert sorted(summary["source_ontologies"]) == ["CCO", "FIBO"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd refiner && uv run pytest tests/test_structure.py -k "summary" -v`
Expected: FAIL — no `domain_context_summary` key in entries

- [ ] **Step 3: Implement domain_context_summary in structure()**

In `refiner/src/refiner/stages/structure.py`:

At the top of `structure()`, after the function signature, build a lookup from risk_id to domain context profile:

```python
dc_by_risk_id: dict[str, DomainContextProfile] = {}
for p in domain_context:
    if p.risk_id not in dc_by_risk_id:
        dc_by_risk_id[p.risk_id] = p
```

Inside the existing entry-building loop, after the cross-mappings block (after the `entry = entries_by_id[entry_id]` and `if related_risks:` block), add the summary lookup using `rm.risk_id` which is already available in scope:

```python
            # Attach domain context summary (only on first encounter of this entry)
            if "domain_context_summary" not in entry:
                profile = dc_by_risk_id.get(rm.risk_id)
                if profile and profile.axes:
                    axes_summary = []
                    all_ontologies: set[str] = set()
                    total_enums = 0
                    for axis in profile.axes:
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

This uses the in-loop approach (matching by `rm.risk_id` which is available in the loop body), avoiding a fragile second-pass reverse lookup.

- [ ] **Step 4: Run tests**

Run: `cd refiner && uv run pytest tests/test_structure.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
cd refiner && git add src/refiner/stages/structure.py tests/test_structure.py
git commit -m "feat(refiner): add domain_context_summary to taxonomy entries"
```

---

### Task 6: Evaluation metrics for expansion effectiveness

Adds metrics that measure the impact of the multi-query expansion.

**Files:**
- Modify: `refiner/src/refiner/evaluate.py`
- Test: `refiner/tests/test_evaluate.py`

**Dependencies:** Task 3 (pipeline events exist)

- [ ] **Step 1: Write failing tests for new metrics**

Add to `refiner/tests/test_evaluate.py`:

```python
from refiner.evaluate import (
    compute_candidate_expansion_effectiveness,
    compute_query_source_contribution,
)


def test_compute_candidate_expansion_effectiveness():
    events = [
        {"stage": "anchor", "event": "candidate_expansion",
         "risk_id": "r1", "queries_run": 4, "raw_total": 15, "unique_after_dedup": 8, "kept_after_filter": 5},
        {"stage": "anchor", "event": "candidate_expansion",
         "risk_id": "r2", "queries_run": 2, "raw_total": 10, "unique_after_dedup": 6, "kept_after_filter": 3},
        {"stage": "anchor", "event": "multi_query_hit",
         "risk_id": "r1", "uri": "http://example.org/A", "hit_count": 3, "best_distance": 0.1, "query_sources": ["description", "concern", "action"]},
        {"stage": "anchor", "event": "multi_query_hit",
         "risk_id": "r1", "uri": "http://example.org/B", "hit_count": 1, "best_distance": 0.4, "query_sources": ["description"]},
    ]
    result = compute_candidate_expansion_effectiveness(events)
    assert result["mean_queries_run"] == 3.0  # (4 + 2) / 2
    assert result["mean_unique_candidates"] == 7.0  # (8 + 6) / 2
    assert result["multi_hit_fraction"] == 0.5  # 1 of 2 multi_query_hit events has hit_count > 1


def test_compute_candidate_expansion_effectiveness_empty():
    result = compute_candidate_expansion_effectiveness([])
    assert result["mean_queries_run"] == 0
    assert result["multi_hit_fraction"] == 0


def test_compute_query_source_contribution():
    events = [
        {"stage": "anchor", "event": "multi_query_hit",
         "risk_id": "r1", "uri": "a", "hit_count": 3, "best_distance": 0.1,
         "query_sources": ["description", "concern", "action"]},
        {"stage": "anchor", "event": "multi_query_hit",
         "risk_id": "r1", "uri": "b", "hit_count": 1, "best_distance": 0.4,
         "query_sources": ["description"]},
        {"stage": "anchor", "event": "multi_query_hit",
         "risk_id": "r2", "uri": "c", "hit_count": 2, "best_distance": 0.2,
         "query_sources": ["concern", "cross_mapping"]},
    ]
    result = compute_query_source_contribution(events)
    # description appears in 2 of 3 hits
    assert result["description"] == 2
    assert result["concern"] == 2
    assert result["action"] == 1
    assert result["cross_mapping"] == 1


def test_compute_query_source_contribution_empty():
    result = compute_query_source_contribution([])
    assert result == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd refiner && uv run pytest tests/test_evaluate.py -k "expansion or query_source" -v`
Expected: FAIL — functions not importable

- [ ] **Step 3: Implement the metrics**

Add to `refiner/src/refiner/evaluate.py`:

```python
def compute_candidate_expansion_effectiveness(events: list[dict]) -> dict:
    expansion_events = [e for e in events if e.get("event") == "candidate_expansion"]
    hit_events = [e for e in events if e.get("event") == "multi_query_hit"]

    if not expansion_events:
        return {"mean_queries_run": 0, "mean_unique_candidates": 0, "multi_hit_fraction": 0}

    mean_queries = sum(e["queries_run"] for e in expansion_events) / len(expansion_events)
    mean_unique = sum(e["unique_after_dedup"] for e in expansion_events) / len(expansion_events)

    multi_hit_count = sum(1 for e in hit_events if e.get("hit_count", 1) > 1)
    multi_hit_fraction = multi_hit_count / len(hit_events) if hit_events else 0

    return {
        "mean_queries_run": mean_queries,
        "mean_unique_candidates": mean_unique,
        "multi_hit_fraction": multi_hit_fraction,
    }


def compute_query_source_contribution(events: list[dict]) -> dict:
    hit_events = [e for e in events if e.get("event") == "multi_query_hit"]
    if not hit_events:
        return {}

    counts: dict[str, int] = {}
    for e in hit_events:
        for source in e.get("query_sources", []):
            counts[source] = counts.get(source, 0) + 1
    return counts
```

- [ ] **Step 4: Wire into `run_evaluation()`**

In `refiner/src/refiner/evaluate.py`, inside `run_evaluation()`, find where `aggregate_stage_quality()` is called and add the new metrics. Guard against missing `stage_quality` key:

```python
if report_data:
    events = report_data.get("events", [])
    # ... existing stage_quality code ...
    if "stage_quality" not in result:
        result["stage_quality"] = {}
    result["stage_quality"]["candidate_expansion"] = compute_candidate_expansion_effectiveness(events)
    result["stage_quality"]["query_source_contribution"] = compute_query_source_contribution(events)
```

- [ ] **Step 5: Run tests**

Run: `cd refiner && uv run pytest tests/test_evaluate.py -v`
Expected: All PASS

- [ ] **Step 6: Run full test suite**

Run: `cd refiner && uv run pytest tests/ -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
cd refiner && git add src/refiner/evaluate.py tests/test_evaluate.py
git commit -m "feat(refiner): add candidate expansion and query source contribution metrics"
```

---

### Task 7: Final integration verification

Verify everything works together end-to-end.

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

Run: `cd refiner && uv run pytest tests/ -v --tb=short`
Expected: All tests PASS, no regressions

- [ ] **Step 2: Verify backward compatibility**

Check that `anchor()` and `contextualize()` still work with their original call signatures (no new required params):

Run: `cd refiner && uv run pytest tests/test_anchor.py::test_anchor_no_report_works tests/test_anchor.py::test_anchor_empty_mappings tests/test_contextualize.py::test_contextualize_no_report_works -v`
Expected: All PASS

- [ ] **Step 3: Verify `map_risks` 5-tuple return doesn't break pipeline tests**

Run: `cd refiner && uv run pytest tests/ -k "pipeline or map_risks" -v`
Expected: All PASS

- [ ] **Step 4: Final commit (if any fixups needed)**

```bash
git add -u && git commit -m "fix(refiner): integration fixups for taxonomy-domain context integration"
```
