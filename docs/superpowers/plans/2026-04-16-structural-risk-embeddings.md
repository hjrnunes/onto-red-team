# Structural Risk Embeddings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enrich risk embedding documents with structural context (group membership, sibling risks, cross-framework mappings, related actions) to improve search quality, especially for the 314 structurally-isolated AIR 2024 risks.

**Architecture:** A new `build_structural_context()` function in `risk_index.py` builds a context string per risk from knowledge graph relationships. The existing `index_risks()` method appends this context to each document before ChromaDB embeds it. A schema version constant triggers automatic reindexing when the document format changes.

**Tech Stack:** Python, ChromaDB, existing nexus-mcp + refiner infrastructure. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-04-16-structural-risk-embeddings-design.md`

---

### Task 1: `build_structural_context()` — group and sibling context

**Files:**
- Modify: `nexus-mcp/src/nexus_mcp/risk_index.py` (add function, ~50 lines)
- Test: `nexus-mcp/tests/test_risk_index.py` (add tests)

- [ ] **Step 1: Write failing test — risk with group and siblings**

Add to `nexus-mcp/tests/test_risk_index.py`:

```python
from nexus_mcp.risk_index import build_structural_context


def test_structural_context_group_and_siblings(mock_risks, mock_groups, mock_actions):
    risks_by_id = {r.id: r for r in mock_risks}
    actions_by_id = {a.id: a for a in mock_actions}
    ctx = build_structural_context(risks_by_id, mock_groups, actions_by_id)

    # atlas-prompt-injection is in Robustness group (only member in that group)
    assert "atlas-prompt-injection" in ctx
    assert "PartOf: Robustness" in ctx["atlas-prompt-injection"]

    # llm01-prompt-injection shares owasp-llm-top-10-group with llm02
    owasp_ctx = ctx["llm01-prompt-injection"]
    assert "PartOf: OWASP LLM Top 10" in owasp_ctx
    assert "Siblings:" in owasp_ctx
    assert "LLM02: Sensitive Information Disclosure" in owasp_ctx
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd nexus-mcp && uv run pytest tests/test_risk_index.py::test_structural_context_group_and_siblings -v`
Expected: FAIL — `ImportError: cannot import name 'build_structural_context'`

- [ ] **Step 3: Implement `build_structural_context()` with group/sibling logic**

Add to `nexus-mcp/src/nexus_mcp/risk_index.py` before the `RiskIndex` class:

```python
from collections import defaultdict
from typing import Any


def build_structural_context(
    risks_by_id: dict[str, Any],
    groups: list,
    actions_by_id: dict[str, Any] | None = None,
    *,
    max_siblings: int = 8,
) -> dict[str, str]:
    """Build structural context strings for risk embeddings.

    Returns {risk_id: context_string} for risks that have structural signals.
    """
    # Build group lookup: group_id -> group_name
    group_names: dict[str, str] = {}
    for g in groups:
        g_type = getattr(g, "type", "")
        if g_type == "RiskGroup" or hasattr(g, "isDefinedByTaxonomy"):
            group_names[g.id] = g.name

    # Build group membership: group_id -> [risk]
    group_members: dict[str, list] = defaultdict(list)
    for risk in risks_by_id.values():
        group_id = getattr(risk, "isPartOf", "")
        if group_id:
            group_members[group_id].append(risk)

    result: dict[str, str] = {}
    for risk_id, risk in risks_by_id.items():
        parts: list[str] = []

        # Group + siblings
        group_id = getattr(risk, "isPartOf", "")
        if group_id and group_id in group_names:
            parts.append(f"PartOf: {group_names[group_id]}")
            siblings = [r.name for r in group_members[group_id] if r.id != risk_id]
            if siblings:
                siblings.sort()
                if len(siblings) <= max_siblings:
                    parts.append(f"Siblings: {', '.join(siblings)}")
                else:
                    shown = siblings[:max_siblings]
                    parts.append(
                        f"Siblings: {', '.join(shown)} (+{len(siblings) - max_siblings} more)"
                    )

        # Cross-mappings
        mapping_attrs = [
            ("exact_mappings", "Exact"),
            ("close_mappings", "Close"),
            ("broad_mappings", "Broad"),
            ("narrow_mappings", "Narrow"),
            ("related_mappings", "Related"),
        ]
        for attr, label in mapping_attrs:
            target_ids = getattr(risk, attr, [])
            if not target_ids:
                continue
            names = []
            for tid in target_ids:
                target = risks_by_id.get(tid)
                if target:
                    names.append(target.name)
            if names:
                parts.append(f"{label}: {', '.join(names)}")

        # Actions
        if actions_by_id:
            action_ids = getattr(risk, "hasRelatedAction", [])
            action_names = []
            for aid in action_ids:
                action = actions_by_id.get(aid)
                if action:
                    action_names.append(action.name)
            if action_names:
                parts.append(f"Actions: {', '.join(action_names)}")

        if parts:
            result[risk_id] = ". ".join(parts)

    return result
```

Also add the import at the top of the file:

```python
from collections import defaultdict
from typing import Any
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd nexus-mcp && uv run pytest tests/test_risk_index.py::test_structural_context_group_and_siblings -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add nexus-mcp/src/nexus_mcp/risk_index.py nexus-mcp/tests/test_risk_index.py
git commit -m "feat(nexus): add build_structural_context with group/sibling support"
```

---

### Task 2: Cross-mapping and action context

**Files:**
- Modify: `nexus-mcp/tests/test_risk_index.py` (add tests)

Cross-mapping and action logic is already in the implementation from Task 1. This task adds the test coverage.

- [ ] **Step 1: Write failing test — cross-mappings**

Add to `nexus-mcp/tests/test_risk_index.py`:

```python
def test_structural_context_cross_mappings(mock_risks, mock_groups, mock_actions):
    risks_by_id = {r.id: r for r in mock_risks}
    actions_by_id = {a.id: a for a in mock_actions}
    ctx = build_structural_context(risks_by_id, mock_groups, actions_by_id)

    # atlas-prompt-injection has exact_mappings=["llm01-prompt-injection"]
    # and related_mappings=["atlas-jailbreaking"] (not in mock_risks, so skipped)
    pi_ctx = ctx["atlas-prompt-injection"]
    assert "Exact: LLM01: Prompt Injection" in pi_ctx

    # atlas-confidential-data-in-prompt has close_mappings=["llm022025-..."]
    cd_ctx = ctx["atlas-confidential-data-in-prompt"]
    assert "Close: LLM02: Sensitive Information Disclosure" in cd_ctx
```

- [ ] **Step 2: Run test to verify it passes**

Run: `cd nexus-mcp && uv run pytest tests/test_risk_index.py::test_structural_context_cross_mappings -v`
Expected: PASS (logic already implemented in Task 1)

- [ ] **Step 3: Write test — actions**

Add to `nexus-mcp/tests/test_risk_index.py`:

```python
def test_structural_context_actions(mock_risks, mock_groups, mock_actions):
    risks_by_id = {r.id: r for r in mock_risks}
    actions_by_id = {a.id: a for a in mock_actions}
    ctx = build_structural_context(risks_by_id, mock_groups, actions_by_id)

    # atlas-prompt-injection has hasRelatedAction=["action-input-validation"]
    assert "Actions: Input validation" in ctx["atlas-prompt-injection"]

    # atlas-confidential-data-in-prompt has hasRelatedAction=["action-output-filtering"]
    assert "Actions: Output filtering" in ctx["atlas-confidential-data-in-prompt"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd nexus-mcp && uv run pytest tests/test_risk_index.py::test_structural_context_actions -v`
Expected: PASS

- [ ] **Step 5: Write test — no structural data means omitted from output**

Add to `nexus-mcp/tests/test_risk_index.py`:

```python
def test_structural_context_empty_risk_omitted():
    """A risk with no group, no mappings, no actions is omitted."""
    from tests.conftest import MockRisk
    bare_risk = MockRisk(id="bare", name="Bare Risk")
    ctx = build_structural_context({"bare": bare_risk}, [], None)
    assert "bare" not in ctx
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd nexus-mcp && uv run pytest tests/test_risk_index.py::test_structural_context_empty_risk_omitted -v`
Expected: PASS

- [ ] **Step 7: Write test — full context string with all signals**

Add to `nexus-mcp/tests/test_risk_index.py`:

```python
def test_structural_context_full_string(mock_risks, mock_groups, mock_actions):
    risks_by_id = {r.id: r for r in mock_risks}
    actions_by_id = {a.id: a for a in mock_actions}
    ctx = build_structural_context(risks_by_id, mock_groups, actions_by_id)

    # atlas-prompt-injection has group, exact mapping, related mapping (unresolved), and action
    pi_ctx = ctx["atlas-prompt-injection"]
    assert "PartOf: Robustness" in pi_ctx
    assert "Exact: LLM01: Prompt Injection" in pi_ctx
    assert "Actions: Input validation" in pi_ctx
    # atlas-jailbreaking not in risks_by_id, so Related section should not appear
    assert "Related:" not in pi_ctx
```

- [ ] **Step 8: Run test to verify it passes**

Run: `cd nexus-mcp && uv run pytest tests/test_risk_index.py::test_structural_context_full_string -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add nexus-mcp/tests/test_risk_index.py
git commit -m "test(nexus): add coverage for cross-mappings, actions, and edge cases"
```

---

### Task 3: Sibling cap overflow

**Files:**
- Modify: `nexus-mcp/tests/test_risk_index.py` (add test)

- [ ] **Step 1: Write failing test — sibling cap at max_siblings**

Add to `nexus-mcp/tests/test_risk_index.py`:

```python
def test_structural_context_sibling_cap():
    from tests.conftest import MockRisk, MockGroup

    group = MockGroup(id="big-group", name="Big Group")
    risks = [
        MockRisk(id=f"r-{i}", name=f"Risk {i:02d}", isPartOf="big-group")
        for i in range(12)
    ]
    risks_by_id = {r.id: r for r in risks}

    ctx = build_structural_context(risks_by_id, [group], None, max_siblings=8)

    # r-0 has 11 siblings, cap at 8 with overflow
    r0_ctx = ctx["r-0"]
    assert "PartOf: Big Group" in r0_ctx
    assert "(+3 more)" in r0_ctx
    # Should show exactly 8 sibling names
    siblings_part = r0_ctx.split("Siblings: ")[1]
    names_str = siblings_part.split(" (+")[0]
    assert len(names_str.split(", ")) == 8
```

- [ ] **Step 2: Run test to verify it passes**

Run: `cd nexus-mcp && uv run pytest tests/test_risk_index.py::test_structural_context_sibling_cap -v`
Expected: PASS (logic already in Task 1 implementation)

- [ ] **Step 3: Commit**

```bash
git add nexus-mcp/tests/test_risk_index.py
git commit -m "test(nexus): add sibling cap overflow test"
```

---

### Task 4: Schema version and `needs_reindex()` update

**Files:**
- Modify: `nexus-mcp/src/nexus_mcp/risk_index.py` (add `SCHEMA_VERSION`, update `index_risks`, update `needs_reindex`)
- Modify: `nexus-mcp/tests/test_risk_index.py` (add version tests)

- [ ] **Step 1: Write failing test — `needs_reindex` detects version mismatch**

Add to `nexus-mcp/tests/test_risk_index.py`:

```python
from nexus_mcp.risk_index import SCHEMA_VERSION


def test_needs_reindex_version_mismatch(chroma_dir, mock_risks):
    idx = RiskIndex(chroma_dir)
    idx.index_risks(mock_risks)
    assert idx.needs_reindex(len(mock_risks)) is False

    # Simulate old schema by overwriting collection metadata
    collection = idx._client.get_collection(name="risk_entries")
    # Delete and recreate with old version
    idx._client.delete_collection("risk_entries")
    old_col = idx._client.create_collection(
        name="risk_entries",
        metadata={"hnsw:space": "cosine", "schema_version": SCHEMA_VERSION - 1},
    )
    # Add a dummy doc so count matches
    old_col.upsert(
        ids=[r.id for r in mock_risks],
        documents=[r.name for r in mock_risks],
        metadatas=[{"id": r.id, "name": r.name, "description": "", "concern": "",
                     "taxonomy": "", "risk_type": "", "group": ""} for r in mock_risks],
    )
    assert idx.needs_reindex(len(mock_risks)) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd nexus-mcp && uv run pytest tests/test_risk_index.py::test_needs_reindex_version_mismatch -v`
Expected: FAIL — `ImportError: cannot import name 'SCHEMA_VERSION'`

- [ ] **Step 3: Add `SCHEMA_VERSION` constant and update `index_risks` and `needs_reindex`**

In `nexus-mcp/src/nexus_mcp/risk_index.py`, add at the top (after `COLLECTION_NAME`):

```python
SCHEMA_VERSION = 2  # bump when document format changes
```

Update `index_risks` method:

```python
def index_risks(self, risks: list, structural_context: dict[str, str] | None = None) -> None:
    """Index risk entries into ChromaDB. Overwrites existing collection."""
    try:
        self._client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    collection = self._client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine", "schema_version": SCHEMA_VERSION},
    )

    if not risks:
        return

    ids = []
    documents = []
    metadatas = []
    for risk in risks:
        doc_parts = [f"{risk.name}: {risk.description}"]
        if risk.concern:
            doc_parts.append(f"Concern: {risk.concern}")
        doc = ". ".join(doc_parts)
        if structural_context and risk.id in structural_context:
            doc = f"{doc}. {structural_context[risk.id]}"

        ids.append(risk.id)
        documents.append(doc)
        metadatas.append({
            "id": risk.id,
            "name": risk.name,
            "description": risk.description or "",
            "concern": risk.concern or "",
            "taxonomy": risk.isDefinedByTaxonomy or "",
            "risk_type": risk.risk_type or "",
            "group": risk.isPartOf or "",
        })

    batch_size = 5000
    for i in range(0, len(ids), batch_size):
        collection.upsert(
            ids=ids[i:i + batch_size],
            documents=documents[i:i + batch_size],
            metadatas=metadatas[i:i + batch_size],
        )
```

Update `needs_reindex` method:

```python
def needs_reindex(self, expected_count: int) -> bool:
    """Check if the index needs rebuilding."""
    try:
        collection = self._client.get_collection(name=COLLECTION_NAME)
        if collection.count() != expected_count:
            return True
        version = collection.metadata.get("schema_version", 1)
        return version != SCHEMA_VERSION
    except Exception:
        return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd nexus-mcp && uv run pytest tests/test_risk_index.py::test_needs_reindex_version_mismatch -v`
Expected: PASS

- [ ] **Step 5: Run all existing tests to verify no regressions**

Run: `cd nexus-mcp && uv run pytest -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add nexus-mcp/src/nexus_mcp/risk_index.py nexus-mcp/tests/test_risk_index.py
git commit -m "feat(nexus): add schema version to risk index, update needs_reindex"
```

---

### Task 5: Integration test — structural context in search results

**Files:**
- Modify: `nexus-mcp/tests/test_risk_index.py` (add integration test)

- [ ] **Step 1: Write integration test — indexing with structural context produces valid search results**

Add to `nexus-mcp/tests/test_risk_index.py`:

```python
def test_index_with_structural_context(chroma_dir, mock_risks, mock_groups, mock_actions):
    risks_by_id = {r.id: r for r in mock_risks}
    actions_by_id = {a.id: a for a in mock_actions}
    ctx = build_structural_context(risks_by_id, mock_groups, actions_by_id)

    idx = RiskIndex(chroma_dir)
    idx.index_risks(mock_risks, structural_context=ctx)

    assert idx.count() == len(mock_risks)

    # Search should still return valid results with expected fields
    results = idx.search("prompt injection attack", top_k=3)
    assert len(results) <= 3
    for r in results:
        assert "id" in r
        assert "name" in r
        assert "distance" in r
```

- [ ] **Step 2: Run test to verify it passes**

Run: `cd nexus-mcp && uv run pytest tests/test_risk_index.py::test_index_with_structural_context -v`
Expected: PASS

- [ ] **Step 3: Write test — backward compatibility without structural context**

Add to `nexus-mcp/tests/test_risk_index.py`:

```python
def test_index_without_structural_context(chroma_dir, mock_risks):
    """Calling index_risks without structural_context still works."""
    idx = RiskIndex(chroma_dir)
    idx.index_risks(mock_risks)
    assert idx.count() == len(mock_risks)

    results = idx.search("prompt injection", top_k=3)
    assert len(results) > 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd nexus-mcp && uv run pytest tests/test_risk_index.py::test_index_without_structural_context -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add nexus-mcp/tests/test_risk_index.py
git commit -m "test(nexus): add integration tests for structural context in indexing"
```

---

### Task 6: Wire up callers — `server.py` and `cli.py`

**Files:**
- Modify: `nexus-mcp/src/nexus_mcp/server.py:256-261`
- Modify: `refiner/src/refiner/cli.py:123-138`

- [ ] **Step 1: Update `_get_handlers()` in `server.py`**

In `nexus-mcp/src/nexus_mcp/server.py`, update the `_get_handlers()` function. Change the indexing block (around lines 257-261) from:

```python
    idx = RiskIndex(chroma_dir)
    if idx.needs_reindex(len(all_risks)):
        idx.index_risks(all_risks)
```

to:

```python
    from nexus_mcp.risk_index import build_structural_context

    idx = RiskIndex(chroma_dir)
    if idx.needs_reindex(len(all_risks)):
        ctx = build_structural_context(risks_by_id, groups, actions_by_id)
        idx.index_risks(all_risks, structural_context=ctx)
```

- [ ] **Step 2: Update `_create_risk_handlers()` in `cli.py`**

In `refiner/src/refiner/cli.py`, update the function (around lines 136-138) from:

```python
    idx = RiskIndex(chroma_dir)
    if idx.needs_reindex(len(all_risks)):
        idx.index_risks(all_risks)
```

to:

```python
    from nexus_mcp.risk_index import build_structural_context

    idx = RiskIndex(chroma_dir)
    if idx.needs_reindex(len(all_risks)):
        ctx = build_structural_context(risks_by_id, groups, actions_by_id)
        idx.index_risks(all_risks, structural_context=ctx)
```

- [ ] **Step 3: Run all nexus-mcp tests**

Run: `cd nexus-mcp && uv run pytest -v`
Expected: All tests PASS

- [ ] **Step 4: Run refiner tests to check for regressions**

Run: `cd refiner && uv run pytest tests/test_map_risks.py -v`
Expected: All tests PASS (mock-based, don't hit real indexing)

- [ ] **Step 5: Commit**

```bash
git add nexus-mcp/src/nexus_mcp/server.py refiner/src/refiner/cli.py
git commit -m "feat: wire structural context into risk indexing callers"
```

---

### Task 7: Full test suite verification

**Files:** None (verification only)

- [ ] **Step 1: Run full nexus-mcp test suite**

Run: `cd nexus-mcp && uv run pytest -v`
Expected: All ~19+ tests PASS

- [ ] **Step 2: Run full refiner test suite**

Run: `cd refiner && uv run pytest -v`
Expected: All ~350 tests PASS

- [ ] **Step 3: Commit if any fixups were needed**

Only commit if fixes were applied. Otherwise, mark task complete.
