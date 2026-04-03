# Anchor Search Mechanics

Deep-dive on the ontology search pipeline from `expand_candidates()` through prompt generation,
the gen3→gen4 regression caused by per-domain search, and the proposed fixes.

**Related:** `docs/refiner.md` (pipeline overview), `docs/superpowers/specs/2026-04-02-taxonomy-domain-context-integration-design.md` (design spec for multi-query expansion).

## Pipeline End-to-End

The refiner pipeline transforms client content policies into adversarial test prompts. The stages relevant to ontology search are:

### 1. identify_domains — picks which ontologies to search

The LLM reads the classified policies and selects which **domain ontologies** are relevant. There are two pools:

- **Always-included** (searched regardless): `CCO`, `Commons`, `D3FEND`, `CSO`
- **Domain options** (LLM picks): `FIBO` (financial), `OBO` (healthcare), `IOF` (manufacturing)

For a banking policy set, the LLM might return `["FIBO"]`. For healthcare, `["FIBO", "OBO"]` (FIBO because healthcare mentions billing/insurance). The final `selected_domains` list is always-included + LLM-selected, e.g. `["CCO", "Commons", "D3FEND", "CSO", "FIBO", "OBO"]`.

**Source:** `refiner/src/refiner/stages/identify_domains.py` — `ALWAYS_INCLUDED`, `DOMAIN_OPTIONS`.

### 2. anchor → expand_candidates() — finds ontology classes that ground each risk

Each risk concept (e.g. "Unauthorized Disclosure of Financial Records") needs to be grounded in concrete ontology classes that represent dimensions of variation — who does it, what's acted on, what tool is used, where it happens. These are **variation axes**.

`expand_candidates()` is the search function. It takes the risk's description, concern, action descriptions, and cross-mapping descriptions, and runs them as semantic queries against ChromaDB. The goal: find `max_candidates` (default 5) ontology classes that are semantically relevant to the risk.

**Source:** `refiner/src/refiner/stages/anchor.py:249-390`.

### 3. Ontology search infrastructure

Each ontology domain (CCO, FIBO, OBO, etc.) has its own ChromaDB collection. Every class in that ontology is embedded as a vector. Two search APIs exist:

- `search_classes(query, top_k=10)` — searches a **single merged collection** containing all domains together. Returns the globally best matches by vector distance.

- `search_domains(query, domains, top_k_per_domain=10)` — searches each domain's collection **independently**. Returns a dict: `{"CCO": [10 results], "FIBO": [10 results], "CSO": [10 results], ...}`.

**Source:** `ontoquery/src/ontoquery/index.py` — `search_raw()` and `search_domains()`. Exposed to the pipeline via `ontoquery/src/ontoquery/mcp_server.py` — `create_tool_handlers()` returns a dict of callables.

The pipeline calls these handlers directly (no MCP transport). The handler dict is created in `refiner/src/refiner/cli.py:128-130` via `_create_onto_handlers()`.

### 4. Path selection in expand_candidates()

`expand_candidates()` auto-detects which search path to use (`anchor.py:274`):

```python
if merge_strategy and onto_handlers.get("search_domains") and selected_domains:
    # Per-domain search → merge via strategy
else:
    # Legacy: single-collection search → sort by distance → take top N
```

**Legacy path (gen3):** Calls `search_classes(query, top_k=10)` per query. All results go into a single `by_uri` dict, deduplicated. Post-filtered by `selected_domains` (URI namespace check). Sorted by `(-hit_count, best_distance)`, top `max_candidates` kept.

**Per-domain path (gen4):** Calls `search_domains(query, selected_domains, top_k_per_domain=10)` per query. Results are grouped by domain in `_search_per_domain()`. Then `WeightedMergeStrategy.merge()` selects `max_candidates` from the per-domain pools.

### 5. WeightedMergeStrategy — merges per-domain results into N candidates

Two passes (`anchor.py:96-138`):

**Pass 1 — Quota for domain-selected ontologies.** FIBO, OBO, IOF (whichever the LLM selected) get guaranteed slots. Formula: `quota_per = max(1, max_candidates // (len(domain_selected) + 1))`. With `max_candidates=5` and 2 domain-selected ontologies, each gets 1 guaranteed slot. No distance threshold.

**Pass 2 — Always-included fill remaining.** CCO, Commons, D3FEND, CSO candidates are pooled and sorted by `(-hit_count, best_distance)`. They fill remaining slots. No distance threshold.

### 6. anchor LLM call — picks 2-3 axes from the candidates

The LLM receives the enriched candidates (with definitions, siblings, hit counts) and selects 2-3 as variation axes, assigning semantic roles (agent/object/instrument/location/temporal). Post-processing validates URIs and derives roles from the BFO/CCO hierarchy via `derive_roles()`.

**Source:** `anchor.py:497-535` (prompt construction), `anchor.py:543-563` (post-processing).

### 7. contextualize — populates each axis with enumeration values

For each chosen axis class, the pipeline gets its subclasses (or siblings as fallback) from the ontology graph. These become the **enumeration space** — the specific values that can be substituted when generating prompts. E.g., if the axis is `Lender`, enumerations might be `MortgageLender`, `PaydayLender`, `InstitutionalLender`.

The LLM filters irrelevant enumerations and assigns relevance ratings (high/medium/low). Post-processing validates URIs, filters by selected domains, and removes disjoint class conflicts.

**Source:** `refiner/src/refiner/stages/contextualize.py`.

### 8. emit → sample_axes() — samples axis combinations

For each risk, `sample_axes()` draws N random combinations from the enumeration spaces (weighted by relevance). Each combination is a concrete set of values — one per axis. E.g. `[MortgageLender (agent), FinancialRecord (object)]`.

**Source:** `refiner/src/refiner/emit.py:40-81`.

### 9. emit → build_prompt() + LLM — generates adversarial prompts

Each sampled combination becomes a generation prompt. The LLM writes a realistic-sounding professional request that would trigger the policy violation, incorporating the sampled domain vocabulary. The output is a JSONL dataset for red-team testing.

**Source:** `refiner/src/refiner/emit.py:100+`.

## Gen3 → Gen4 Regression

### What changed

Between gen3 and gen4, `search_domains` was added to ontoquery. This handler searches per-domain ChromaDB collections independently instead of the single merged collection. Once available in `onto_handlers`, `expand_candidates()` automatically switches to the per-domain path with `WeightedMergeStrategy`.

### Scale difference

- **Gen3 (legacy path):** `search_classes(query, top_k=10)` → 10 results per query, ranked purely by distance across all domains. Best matches win regardless of which domain they come from.
- **Gen4 (per-domain path):** `search_domains(query, domains, top_k_per_domain=10)` → 10 results × 5-6 domains = 50-60 raw candidates per query. `WeightedMergeStrategy` then selects 5.

### Three downstream effects

**1. FIBO domain contamination (healthcare, RDaSH NHS)**

Healthcare policies mention billing/insurance, so the LLM correctly selects FIBO. But the actual risks are clinical (medication errors, diagnosis disclosure). FIBO's best candidate for "Unauthorized PHI Disclosure" is something like `CreditEventNotice` at distance 0.7 (poor match). In gen3 this would never appear — it was ranked below dozens of better matches across all domains. In gen4 the quota guarantee forces it into the top 5. The LLM picks it as an axis, contextualize populates it with financial enumerations (equity announcements, bond issuance), and emit samples these into healthcare prompts — producing incoherent output like medication scenarios involving credit event notices.

Evidence: FIBO went from 1.4% → 13.9% of axis samples in healthcare Gemma 3.

**2. CSO harm axis explosion (SWB, cross-policy)**

CSO has physical harm classes (Arson Methods, Sabotage Instructions, CBRN Information, Weapons Manufacturing, Drug Synthesis, Lock Picking and Bypassing). These are legitimate for generic safety testing but incoherent in banking/healthcare contexts.

With 60 raw candidates instead of 10, more of these surface. They also get high hit-counts (5-8) because multiple queries (cross-mappings, actions) match them — harm descriptions are semantically close to many risk descriptions. High hit-count ranks them well in the always-included pool.

Evidence: SWB Gemma 3 CSO harm-axis samples went from 12 → 48 (4x increase). New classes `HarmfulHowTo`, `ContentSafetyHazard`, `DangerousInformation` all surfaced via cross-mapping and action queries.

**3. Empty prompts from incoherent axis combinations**

The CSO harm explosion feeds incoherent axis combinations to the generation LLM: "Sabotage Instructions + Weapons Manufacturing" for a banking scenario. The generation model correctly judges it can't compose a plausible banking request involving weapons manufacturing and returns `{"prompt": null}`.

Evidence: 7 empty prompts in SWB Gemma 3 (gen3 had 0). All 7 had incoherent CSO harm axis combinations.

## Proposed Fixes

### Fix 1: Distance threshold on WeightedMergeStrategy quota

Add a distance check to the quota loop (`anchor.py:120`). Domain-selected ontologies only get their guaranteed slot when their best candidate has a reasonable distance.

```python
QUOTA_DISTANCE_THRESHOLD = 0.5

for c in per_domain_candidates.get(domain, []):
    if (c["uri"] not in seen
        and remaining > 0
        and c.get("best_distance", 1.0) < QUOTA_DISTANCE_THRESHOLD  # NEW
        and len([r for r in result if r.get("domain") == domain]) < quota_per):
```

A healthcare billing concept at distance 0.35 qualifies. A credit event notice at distance 0.7 does not. The freed slot goes to always-included domains with better matches. Also indirectly helps CSO: when FIBO doesn't waste a slot, there's less room pressure.

### Fix 2: Distance threshold on always-included pool

Add the same threshold to the always-included pool loop (`anchor.py:132-136`). Currently no quality filter — any candidate fills a slot if there's room.

```python
for c in pool:
    if c["uri"] not in seen and remaining > 0 and c.get("best_distance", 1.0) < QUOTA_DISTANCE_THRESHOLD:
```

CSO harm classes that are semantically distant from banking/healthcare risks (distance > 0.5) are excluded. Only domain-relevant CSO classes (fraud, privacy violation — typically distance < 0.4) get through.

### How they fit together

Fix 1 handles the quota guarantee problem (FIBO gets free slots with poor relevance). Fix 2 handles the pool quality problem (CSO harm classes fill remaining slots despite poor relevance). Together they restore gen3's "only relevant classes surface" behavior while keeping gen4's architectural advantage of per-domain search preventing large ontologies from drowning out small ones.

### Alternative: CSO category blocklist

A more targeted option for CSO specifically — define CSO class URI fragments that are only valid for generic safety policies:

```python
CSO_GENERIC_ONLY = {
    "ArsonMethods", "SabotageInstructions", "DrugSynthesis",
    "CBRNInformation", "WeaponsManufacturing", "LockPickingAndBypassing",
}
```

Filter these out of the always-included pool when the policy set isn't generic. More targeted than a distance threshold but requires maintaining a blocklist.
