# Structural Context for Risk Embeddings

**Date**: 2026-04-16
**Status**: Draft

## Problem

The risk index in `nexus-mcp` embeds risks using only lexical content: `"{name}: {description}. Concern: {concern}"`. This ignores structural signals from the knowledge graph — group membership, cross-framework mappings, sibling risks, and related actions.

AIR 2024 is the largest framework (314/546 risks, 57% of the knowledge graph) and has **zero** cross-mappings, zero actions. Its only structural signal is group membership (43 groups). It also produces the worst search distances:

| Framework | Risks | Cross-mapped | Mean distance | % above 0.6 |
|---|---|---|---|---|
| AIR 2024 | 314 | 0% | 0.5625 | 35% |
| IBM Risk Atlas | 99 | 92% | 0.4884 | 6% |
| Credo AI | 49 | 100% | 0.4545 | 3% |
| NIST AI RMF | 12 | 100% | 0.4649 | 10% |

Overall, 48.5% of matches have distance > 0.5 and 18.4% > 0.6. AIR 2024 accounts for 68% of all weak matches.

## Approach

Text-enrichment of embedding documents, following the proven pattern from `ontoquery/src/ontoquery/index.py:build_structural_context()`. A standalone function builds a structural context string for each risk from knowledge graph relationships, and the index appends it to the document text before ChromaDB embeds it.

No custom embedding models, no new dependencies, no changes to pipeline stages or response models.

## Design

### `build_structural_context(risks_by_id, groups, actions_by_id)`

New function in `nexus-mcp/src/nexus_mcp/risk_index.py`.

**Inputs**:
- `risks_by_id: dict[str, Risk]` — full risk inventory
- `groups: list` — risk group objects (with `id`, `name`, `isDefinedByTaxonomy`)
- `actions_by_id: dict[str, Action] | None` — action objects for resolving `hasRelatedAction` references

**Output**: `dict[str, str]` — `{risk_id: context_string}`

**Context string structure** (sections only appear when data exists):

```
PartOf: Fraud. Siblings: Spam, Phishing/Catfishing, Multi-level marketing.
Exact: Credo-Fraud-Scams. Close: NIST-Deception.
Related: OWASP-Social-Engineering, MIT-Manipulation.
Actions: Bias Testing, Fairness Metrics.
```

**Implementation details**:
- Group lookup: build `{group_id: group_name}` from `groups` list, and `{group_id: [risk]}` from `risks_by_id`
- Siblings: other risks in the same group, referenced by name (not ID). Capped at 8 entries with `(+N more)` overflow to avoid blowing up document length for large groups (e.g., "Discrimination/Protected Characteristics" has 60 risks)
- Cross-mappings: traverse `exact_mappings`, `close_mappings`, `broad_mappings`, `narrow_mappings`, `related_mappings` attributes. Resolve target IDs to risk names via `risks_by_id`. Group by mapping type in the context string
- Actions: traverse `hasRelatedAction`, resolve via a passed-in `actions_by_id` dict (or accept action names directly). Include action names only (not descriptions) to keep context concise

**Revised signature** (actions needed too):

```python
def build_structural_context(
    risks_by_id: dict[str, Any],
    groups: list,
    actions_by_id: dict[str, Any] | None = None,
    *,
    max_siblings: int = 8,
) -> dict[str, str]:
```

Risks with no structural signals at all (no group, no mappings, no actions) are omitted from the output dict.

### Changes to `RiskIndex.index_risks()`

Add one optional parameter:

```python
def index_risks(self, risks: list, structural_context: dict[str, str] | None = None) -> None:
```

Document text construction becomes:

```python
doc_parts = [f"{risk.name}: {risk.description}"]
if risk.concern:
    doc_parts.append(f"Concern: {risk.concern}")
doc = ". ".join(doc_parts)
if structural_context and risk.id in structural_context:
    doc = f"{doc}. {structural_context[risk.id]}"
```

Backward compatible — callers that don't pass `structural_context` get identical behavior.

### Schema version for reindex trigger

`needs_reindex()` currently only checks `collection.count()`. Since this change alters *what* gets embedded without changing the count, a version check is needed.

Add a module-level constant:

```python
SCHEMA_VERSION = 2  # bumped when document format changes
```

Store it in collection metadata at creation time. `needs_reindex()` checks both count and version:

```python
def needs_reindex(self, expected_count: int) -> bool:
    try:
        collection = self._client.get_collection(name=COLLECTION_NAME)
        if collection.count() != expected_count:
            return True
        version = collection.metadata.get("schema_version", 1)
        return version != SCHEMA_VERSION
    except Exception:
        return True
```

### Caller changes

Two call sites pass structural context to `index_risks()`:

1. **`_get_handlers()` in `nexus-mcp/src/nexus_mcp/server.py`** (MCP server startup):
   ```python
   ctx = build_structural_context(risks_by_id, groups, actions_by_id)
   if idx.needs_reindex(len(all_risks)):
       idx.index_risks(all_risks, structural_context=ctx)
   ```

2. **`_create_risk_handlers()` in `refiner/src/refiner/cli.py`** (pipeline CLI):
   Same pattern — build context, pass to `index_risks()`.

## Testing

### Unit tests for `build_structural_context()`

In `nexus-mcp/tests/`:

- Risk with group + siblings → `PartOf: X. Siblings: A, B, C`
- Risk with cross-mappings → `Exact: ...` / `Close: ...` etc.
- Risk with actions → `Actions: ...`
- Risk with all signals → full context string with all sections
- Risk with no structural data → omitted from output dict
- Sibling cap at 8 → overflow produces `(+N more)`
- Large group (60 siblings) → correctly capped

### Integration tests

- `index_risks()` with `structural_context` → collection count correct, search results return expected fields
- `needs_reindex()` returns `True` when schema version mismatches

### Existing tests

`nexus-mcp/tests/` and `refiner/tests/test_map_risks.py` pass unchanged — `structural_context` is optional, mock-based tests don't hit real ChromaDB.

## Evaluation

After implementation, reindex and re-run the SWB policy (worst match distances) to compare:

- Match distances before vs after
- Whether weak match count decreases
- Whether cross-framework risks surface in search results that previously didn't appear in top-5

## Files modified

- `nexus-mcp/src/nexus_mcp/risk_index.py` — `build_structural_context()`, `index_risks()` signature, `needs_reindex()` version check, `SCHEMA_VERSION` constant
- `nexus-mcp/src/nexus_mcp/server.py` — `_get_handlers()` passes structural context
- `refiner/src/refiner/cli.py` — `_create_risk_handlers()` passes structural context
- `nexus-mcp/tests/test_risk_index.py` (or new test file) — unit tests for `build_structural_context()`
