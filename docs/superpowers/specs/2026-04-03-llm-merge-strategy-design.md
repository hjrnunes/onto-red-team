# LLM Merge Strategy Design

## Problem

The `WeightedMergeStrategy` uses z-score normalization and distance thresholds to merge per-domain
ontology search results into a candidate list for the anchor stage. This approach cannot distinguish
semantically relevant candidates from irrelevant ones that happen to be close in embedding space.
The primary symptom is FIBO contamination in healthcare runs (27-32%), where US financial regulatory
classes (Federal Reserve district, automated underwriting system) pass distance thresholds because
healthcare policies mention insurance/billing.

## Solution

A new `LLMMergeStrategy` that replaces the statistical merge with an LLM call. The LLM receives the
pre-filtered candidate pool and risk context, and selects the most relevant candidates. This
addresses FIBO contamination at the root — semantic relevance judged in context, not by distance proxy.

## Protocol Changes

### Updated `SearchMergeStrategy` signature

```python
class SearchMergeStrategy(Protocol):
    def merge(
        self,
        per_domain_candidates: dict[str, list[dict]],
        selected_domains: list[str],
        max_candidates: int,
        risk_context: dict,
        generic_safety_uris: set[str],
    ) -> list[dict]: ...
```

`risk_context` shape:

```python
{"description": str, "concern": str, "policy_concept": str}
```

`generic_safety_uris` moves from mutable instance state to a function parameter. This makes all
strategies stateless after construction, keeping `merge()` a pure function.

### Existing strategies

`WeightedMergeStrategy` and `GroupedMergeStrategy` updated to accept the new parameters. They ignore
`risk_context` and use `generic_safety_uris` in their filtering logic (moved from `_passes_threshold`
instance state to parameter). `__init__` no longer stores `generic_safety_uris`.

## LLMMergeStrategy

```python
class LLMMergeStrategy:
    DISTANCE_CEILING = 0.6

    def __init__(self, client: instructor.Instructor, config: LLMConfig):
        self._client = client
        self._config = config
```

### Pre-filter (mechanical, before LLM)

1. Remove candidates in `generic_safety_uris`
2. Remove candidates with `best_distance >= DISTANCE_CEILING` (0.6)
3. Flatten all domains into a single pool, sorted by `(-hit_count, best_distance)`

### LLM call

The surviving candidates (typically 10-25) are presented as a numbered list with label and domain.
The LLM receives risk context (description, concern, policy_concept) and selects up to
`max_candidates` by index, ranked by relevance.

Response model (no docstring, per project convention):

```python
class _MergeSelection(BaseModel):
    selected: list[int]
```

Prompt is compact — labels and domains only, no definitions or siblings. This keeps the prompt small
for the target models (Gemma 3 12B, Gemma 4 26B, Mistral 24B). If label-only selection proves
insufficient, definitions can be added as a follow-up iteration.

### Post-processing

- Map selected indices back to candidate dicts
- Truncate to `max_candidates` if the LLM returns more
- If the LLM returns fewer, accept as-is

### Fallback

If the LLM call fails after retries, fall back to distance-sorted order: return the top
`max_candidates` from the pre-filtered pool. No pipeline crash.

### Debug logging

The LLM merge call is logged via `debug.log_call()` with stage `"merge"`.

## Call Chain Changes

### `cli.py`

`--search-strategy` gains `"llm"` as a valid value:

```python
strategy_map = {
    "weighted": lambda: WeightedMergeStrategy(),
    "grouped": lambda: GroupedMergeStrategy(),
    "llm": lambda: LLMMergeStrategy(client, config),
}
```

### `pipeline.py`

`generic_safety_uris` computed as a value, not set as state on the strategy:

```python
generic_safety_uris = set()
if state.selected_domains:
    domain_specific = set(state.selected_domains) - set(ALWAYS_INCLUDED)
    if domain_specific:
        generic_safety_uris = build_generic_safety_uris(onto_handlers)

state.variation_axes = anchor(
    ...,
    generic_safety_uris=generic_safety_uris,
)
```

### `anchor()`

Gains `generic_safety_uris: set[str]` parameter. Passes it and a `risk_context` dict through to
`expand_candidates()`.

### `expand_candidates()`

Gains `policy_concept: str` parameter (threaded from `anchor()` via `mapping.policy_concept`).
Assembles `risk_context` dict and passes both it and `generic_safety_uris` to `merge()`:

```python
risk_context = {
    "description": description,
    "concern": concern,
    "policy_concept": policy_concept,
}
kept = merge_strategy.merge(
    per_domain, selected_domains, max_candidates,
    risk_context=risk_context,
    generic_safety_uris=generic_safety_uris,
)
```

## Testing

All tests in existing `test_anchor.py`.

### LLMMergeStrategy unit tests

- Mock instructor client, verify prompt contains risk context and candidate labels
- Verify pre-filter removes candidates above distance ceiling and in `generic_safety_uris`
- Verify fallback to distance-sorted order when LLM call raises
- Verify truncation when LLM returns more than `max_candidates`
- Verify empty pre-filtered pool returns empty (no LLM call)

### Updated existing tests

- `WeightedMergeStrategy` and `GroupedMergeStrategy`: update all calls to pass new parameters,
  remove tests that set `generic_safety_uris` as instance state
- `expand_candidates` and `anchor`: thread `policy_concept` and `generic_safety_uris` through calls,
  verify `risk_context` dict assembly

### Integration test

- Mock LLM returning specific indices, verify correct candidates survive through to anchor stage
