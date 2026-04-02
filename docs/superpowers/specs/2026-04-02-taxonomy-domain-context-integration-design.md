# Taxonomy-Domain Context Integration Design

**Date:** 2026-04-02
**Status:** Draft

## Problem

The risk taxonomy and domain context ontology classes are weakly integrated. Four specific gaps reduce prompt quality and output coherence:

1. **Narrow ontology search funnel (A):** The anchor stage searches the ontology index with only the risk description. Risk concern text, mitigation action descriptions, and cross-mapped risk framings are all available but unused — leaving ontology classes undiscovered.

2. **Blind enumeration filtering (B1):** The contextualize stage filters subclass/sibling enumerations without knowing what the risk is about. It sees axis class names and candidates but not the risk description or concern, preventing informed relevance judgments.

3. **Disconnected outputs (C):** The taxonomy YAML and domain context YAML are parallel files with no structural references between them. Navigating from a taxonomy entry to its domain context requires an external join on risk_id.

4. **Unexploited cross-mappings (D):** Cross-mapped risks from other frameworks carry alternative descriptions of the same concern. These are passed through for traceability but never used to broaden ontology discovery.

Assessment data shows symptoms: Act of Propaganda in ~30% of prompts (axis concentration from narrow search), FIBO SecurityIdentifier matching infosec "security" (semantic collisions), and enumerations filtered without risk context.

## Approach

**Multi-query candidate expansion with frequency signal** (Approach 2 from brainstorming).

Combine gaps A and D into a single `expand_candidates()` function that runs multiple ontology search queries, deduplicates by URI, and annotates each candidate with how many queries surfaced it. The frequency count serves as a relevance signal for the LLM ("found by 3/4 queries") without adding LLM calls.

B1 and C are independent changes layered on top.

**No new pipeline stages. No new LLM calls.** The anchor LLM call gets a richer candidate set; the contextualize LLM call gets richer context. Same call count, better inputs.

## Design

### Data Flow Changes

```
Current:
  map_risks -> risk_details{description, concern}     -> anchor(search with description only)
            -> related_risks{id, mapping_type}         -> structure(cross-mapping IDs)
            -> (get_related_actions never called)

Proposed:
  map_risks -> risk_details{description, concern}      -> anchor(search with description + concern)
            -> risk_actions{risk_id -> [action descs]}  -> anchor(search with action text)
            -> related_risks{id, mapping_type, desc}    -> anchor(search with cross-mapped descriptions)
                                                        -> structure(cross-mapping IDs, unchanged)
            -> risk_details                             -> contextualize(risk description in LLM prompt)
```

### Component 1: Multi-Query Candidate Expansion (anchor.py)

New function replacing the current single-search-then-slice pattern:

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
    """Run multiple ontology searches, merge by URI, annotate with hit count.

    Returns (candidates, expansion_stats).
    """
```

**Query sources:**

| Source | Always present? | What it surfaces |
|--------|----------------|------------------|
| Risk description | Yes | Direct semantic matches (current behavior) |
| Risk concern | Usually | "What could go wrong" framing — different vocabulary |
| Action descriptions | 0-3 per risk | Agents, instruments, processes from mitigations |
| Cross-mapped descriptions | 0-5 per risk | Alternative framings from other frameworks |

**Merge logic:**

1. Run `search_classes(query, top_k=top_k_per_query)` for each non-empty query string
2. Group results by URI across all queries
3. For each unique URI: compute `hit_count` (number of queries that surfaced it) and `best_distance` (minimum distance across queries)
4. Apply domain filter (namespace-based, same as current)
5. Sort by `hit_count` desc, then `best_distance` asc
6. Take top `max_candidates` (raised from current 3 to 5)

**Candidate limit rationale:** Current limit is 3 from a single search. With multiple queries providing better signal, raising to 5 gives the LLM more to work with while the frequency annotation helps it prioritize. The LLM still returns 2-3 axes.

**Query count per risk:** Typically 2-10 ChromaDB searches per unique risk_id: 1 (description) + 0-1 (concern) + 0-3 (actions) + 0-5 (cross-mapped descriptions). With risk-level caching, each unique risk_id is expanded once regardless of how many policies match it. For a typical run (6 policies, ~10 unique risks), expect 20-60 total ChromaDB queries in the anchor stage, up from the current 10. ChromaDB queries are sub-millisecond on local collections of ~90k classes.

**LLM prompt change:** Each candidate line gains a frequency annotation:

```
- <uri>: <label> -- <definition> [found by 3/4 queries]
  Siblings: ...
```

Everything else in anchor stays the same: enrichment with definitions + siblings, LLM picks 2-3 axes, URI validation, BFO/CCO role derivation, cache by risk_id.

### Component 2: Action Threading (map_risks.py + pipeline.py)

**map_risks changes:**

After the existing `get_related_risks()` call for each candidate risk, add:

```python
actions = risk_handlers["get_related_actions"](c["id"])
risk_actions_cache[c["id"]] = [a.get("description", "") for a in actions if a.get("description")]
```

Return signature changes from 4-tuple to 5-tuple, adding `dict[str, list[str]]` for risk_actions.

**Eager collection note:** Actions are collected for all candidate risks (typically 5 per policy), not just the ones the LLM ultimately selects. This is intentional — LLM selection happens later in the `map_risks` flow, so pre-filtering is not possible. The `get_related_actions()` calls are local function calls (in-memory dict lookups), not network requests, so the overhead is negligible (~30 extra calls per pipeline run for 6 policies).

**PipelineState changes:**

```python
@dataclass
class PipelineState:
    # ... existing fields ...
    risk_actions: dict[str, list[str]] | None = None  # NEW
```

**Pipeline wiring:**

```python
state.risk_mappings, state.risk_details, state.seen_risk_ids, state.related_risks, state.risk_actions = map_risks(...)
```

**anchor() signature change:**

```python
def anchor(
    risk_mappings, risk_details, client, config, onto_handlers,
    selected_domains=None,
    risk_actions=None,       # NEW
    related_risks=None,      # NEW — for cross-mapped descriptions
    report=None,
) -> list[RiskVariationAxes]:
```

Inside the risk loop, gather inputs for `expand_candidates()`:

```python
actions = risk_actions.get(rm.risk_id, []) if risk_actions else []
cross_mapped_descs = []
if related_risks:
    for rel in related_risks.get(rm.risk_id, []):
        desc = rel.get("description", "")  # description is already on the related risk dict
        if desc:
            cross_mapped_descs.append(desc)
```

**Note:** Cross-mapped risk descriptions are read directly from the `related_risks` dicts, which already include a `description` field (populated by `get_related_risks()` in the nexus server). We do NOT look them up in `risk_details_cache`, which only contains the ~5 candidate risks per policy that were shown to the LLM — cross-mapped risks from other frameworks would not be found there.

### Component 3: Risk Context in Contextualize (contextualize.py)

**Signature change:**

```python
def contextualize(
    variation_axes, client, config, onto_handlers,
    selected_domains=None,
    risk_details=None,  # NEW
    report=None,
) -> list[DomainContextProfile]:
```

**Inside the loop:**

```python
details = risk_details.get(rva.risk_id, {}) if risk_details else {}
description = details.get("description", "")
concern = details.get("concern", "")
```

**Prompt change:**

```python
user_content = (
    f"Risk: {rva.risk_name} (ID: {rva.risk_id})\n"
    f"Description: {description}\n"
    f"Concern: {concern}\n"
    f"Policy: {rva.policy_concept}\n\n"
    + "\n\n".join(axis_context)
)
```

Same pattern anchor already uses. ~10 lines of change.

**Pipeline wiring:** One line in `run_pipeline()`:

```python
state.domain_context = contextualize(
    state.variation_axes, client, config, onto_handlers,
    selected_domains=state.selected_domains,
    risk_details=state.risk_details,  # NEW
    report=report,
)
```

### Component 4: Structural Output Integration (structure.py)

Add `domain_context_summary` to each taxonomy entry.

**In `structure()`:** Build a lookup from risk_id to domain context profiles. The `domain_context` parameter already receives `DomainContextProfile` model instances (not serialized dicts), so we can access `.risk_id`, `.axes`, etc. directly:

```python
dc_by_risk_id: dict[str, DomainContextProfile] = {}
for p in domain_context:
    dc_by_risk_id.setdefault(p.risk_id, p)
```

Inside the existing entry-building loop (which iterates `risk_mappings` and has access to `rm.risk_id`), look up the matching profile:

```python
profile = dc_by_risk_id.get(rm.risk_id)
```

For each taxonomy entry, attach a summary:

```python
if profile:
    axes_summary = []
    all_ontologies = set()
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

**Output example:**

```yaml
- id: client-swb-unauthorized-disclosure
  name: Unauthorized Disclosure
  type: Risk
  isPartOf: client-swb-confidentiality
  tag: unauthorized-disclosure
  close_mappings: [owasp-llm-06]
  domain_context_summary:
    axis_count: 3
    enumeration_count: 12
    source_ontologies: [CCO, FIBO]
    axes:
      - class: InformationBearingArtifact
        uri: https://www.commoncoreontologies.org/ont00000958
        roles: [object]
        enumeration_count: 5
      - class: DisclosureProvision
        uri: https://spec.edmcouncil.org/fibo/ontology/...
        roles: [object, instrument]
        enumeration_count: 4
      - class: Agent
        uri: https://www.commoncoreontologies.org/ont00001017
        roles: [agent]
        enumeration_count: 3
```

This is a summary for navigability. Full enumerations remain in the domain context file.

### Component 5: Pipeline Events and Evaluation Metrics

**New pipeline events:**

| Stage | Event | Fields |
|-------|-------|--------|
| `anchor` | `candidate_expansion` | `risk_id`, `queries_run`, `raw_total`, `unique_after_dedup`, `kept_after_filter` |
| `anchor` | `multi_query_hit` | `risk_id`, `uri`, `hit_count`, `best_distance`, `query_sources` |

`multi_query_hit` is emitted only for the final `max_candidates` candidates (after dedup, domain filtering, and ranking) — not for every deduplicated URI. This keeps event volume bounded at `max_candidates` (5) per risk.

Existing anchor events (`domain_filtered`, `cache_hit`, `empty_axes`, `role_derivation`) unchanged.

**New evaluation metrics (evaluate.py):**

1. **`compute_candidate_expansion_effectiveness`** — from pipeline events: mean queries_run, mean unique candidates after dedup, fraction of selected axes that were multi-hit (hit_count > 1). Answers: "is the expanded search finding axes the single-query search would miss?"

2. **`compute_query_source_contribution`** — from `multi_query_hit` events: breakdown of which query sources (description, concern, action, cross_mapping) contributed to axes actually selected by the LLM. Answers: "which signals are pulling their weight?"

Both derived from pipeline events only. They slot into the `stage_quality` section of the evaluation output.

**Existing metrics that will naturally reflect changes:**

- `single_value_axis_dominance` — should decrease (more diverse candidates)
- `enumeration_concentration` — Act of Propaganda dominance should decrease
- `semantic_diversity` — broader axes produce more diverse prompts
- `axis_fidelity` — risk context in contextualize improves enumeration filtering

## Files Changed

| File | Change |
|------|--------|
| `refiner/src/refiner/pipeline.py` | `PipelineState` gets `risk_actions` field. Thread `risk_actions`, `related_risks`, `risk_details` to anchor/contextualize |
| `refiner/src/refiner/stages/map_risks.py` | Add `get_related_actions()` call, return 5-tuple |
| `refiner/src/refiner/stages/anchor.py` | Add `expand_candidates()`, accept `risk_actions` + `related_risks` params |
| `refiner/src/refiner/stages/contextualize.py` | Accept `risk_details` param, include in LLM prompt |
| `refiner/src/refiner/stages/structure.py` | Build `domain_context_summary` on taxonomy entries |
| `refiner/src/refiner/evaluate.py` | Add `compute_candidate_expansion_effectiveness`, `compute_query_source_contribution` |
| `refiner/src/refiner/cli.py` | Update `map_risks` return unpacking (5-tuple). Wire `state.risk_actions` and `state.related_risks` to `anchor()` call, `state.risk_details` to `contextualize()` call |
| `refiner/tests/test_anchor.py` | Tests for `expand_candidates()`, multi-query, frequency annotation |
| `refiner/tests/test_map_risks.py` | Tests for action collection |
| `refiner/tests/test_contextualize.py` | Tests for risk description in prompt |
| `refiner/tests/test_structure.py` | Tests for domain_context_summary |
| `refiner/tests/test_evaluate.py` | Tests for new metrics |

## Backward Compatibility

- `expand_candidates()` degrades gracefully: if concern is empty and there are no actions or cross-mappings, it runs a single description query — identical to current behavior.
- `contextualize()` with `risk_details=None` behaves exactly as before (description/concern are empty strings in the prompt, a minor cosmetic change).
- `domain_context_summary` on taxonomy entries is additive — consumers that don't know about it ignore it.
- The `map_risks` return signature change requires updating callers (pipeline.py, cli.py, tests) — the main breaking change, contained to internal wiring.

## What This Does NOT Do

- **No feedback loop (B2):** Ontology context does not feed back into risk selection/weighting. The pipeline remains strictly forward.
- **No new LLM calls:** Same number of LLM calls as before. Richer inputs, not more calls.
- **No new stages:** All changes are within existing stages.
- **No schema changes to Pydantic models:** `VariationAxis`, `DomainContextProfile`, `AxisEnumeration` etc. are unchanged. Only `PipelineState` (a dataclass in `pipeline.py`, not a Pydantic model) gets a new field.
