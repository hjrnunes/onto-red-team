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

Three filtering layers, then two passes:

**Filtering layers** (applied to both passes via `_passes_threshold()`):
1. **Generic safety filter** — candidates whose URI is in `generic_safety_uris` are rejected.
   This set is built at runtime from `get_subclasses(cso#DangerousInformation, depth=3)` and
   contains 19 CSO physical harm classes (Arson, CBRN, Weapons, Drug Synthesis, etc.). Only
   active when domain-specific ontologies are selected (FIBO/OBO/IOF); generic-only runs keep
   full CSO coverage. Set by `pipeline.py` after `identify_domains`.
2. **Raw distance ceiling** (`DISTANCE_CEILING = 0.6`) — rejects obvious junk regardless of
   normalization.
3. **Z-score threshold** (`ZSCORE_THRESHOLD = 1.0`) — rejects within-domain outliers after
   per-domain z-score normalization via `_normalize_distances()`.

**Pass 1 — Quota for domain-selected ontologies.** FIBO, OBO, IOF (whichever the LLM selected)
get guaranteed slots. Formula: `quota_per = max(1, max_candidates // (len(domain_selected) + 1))`.
With `max_candidates=5` and 2 domain-selected ontologies, each gets 1 guaranteed slot.

**Pass 2 — Always-included fill remaining.** CCO, Commons, D3FEND, CSO candidates are pooled
and sorted by `(-hit_count, normalized_distance)`. They fill remaining slots.

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

## Fix: Per-Domain Distance Normalization + Dual Threshold

Implemented in `anchor.py` on `WeightedMergeStrategy`.

### Problem

Raw embedding distances aren't comparable across domain collections. A distance of 0.4 in CSO
(plain English labels) means something different from 0.4 in OBO (technical jargon). Any single
threshold applied to raw distances is unfair to some domains.

Additionally, with no threshold at all, candidates with poor relevance consume slots: FIBO gets
guaranteed quota with distance 0.7, and CSO harm classes fill pool slots despite being semantically
irrelevant to the policy context.

### Approach: Z-Score Normalization + Dual Threshold

**Normalization:** `_normalize_distances()` computes z-scores per domain. Each candidate gets a
`normalized_distance` field: negative means better than the domain average, positive means worse.
This makes distances comparable across domains with different embedding distributions.

Edge cases:
- Single candidate (n < 2): z-score = 0.0 (neutral — can't compute distribution)
- Uniform distances (std ≈ 0): z-score = 0.0 (all equally distant)

**Dual threshold:** `_passes_threshold()` applies two checks. A candidate must pass both:

1. `DISTANCE_CEILING = 0.6` — raw distance above which candidates are always rejected, regardless
   of normalization. Catches obvious junk (FIBO credit event notice at 0.7 for healthcare). Handles
   the n=1 edge case where z-score normalization is unavailable.

2. `ZSCORE_THRESHOLD = 1.0` — z-score above which candidates are rejected when per-domain
   normalization is available. Catches within-domain outliers (CSO arson at 0.55 in banking, where
   CSO's mean is ~0.3 and std ~0.12, giving z ≈ 2.0).

**Applied to both quota and pool:** The threshold applies in the quota loop (domain-selected
ontologies) and the always-included pool. Previously neither had any distance filtering.

**Sort order updated:** The always-included pool now sorts by `(-hit_count, normalized_distance)`
instead of `(-hit_count, best_distance)`, making the ranking domain-fair.

### Expected Impact

- **FIBO contamination**: single FIBO candidate at distance 0.7 → rejected by raw ceiling.
  Good FIBO match at 0.35 → passes both checks.
- **CSO harm explosion**: CSO harm classes with high z-scores (outliers within CSO's distribution)
  → rejected. Domain-relevant CSO classes (fraud, privacy) with low z-scores → kept.
- **Empty prompts**: fewer incoherent axis combinations → fewer null generation responses.

### Future Options

- **Cross-encoder reranker** between search and merge for subtle semantic mismatches (not needed
  yet — current failures are obvious distance outliers)
- **Extend generic safety filter to other CSO branches** — currently only `DangerousInformation`
  (18 classes) is filtered. `Violence`, `SelfHarm`, `SexualContent`, `SexualExploitation` could
  also be tagged if they surface as contamination in gen5 runs

## Fix: CSO DangerousInformation Context Filter

Implemented in `anchor.py` (`build_generic_safety_uris`, `WeightedMergeStrategy`,
`GroupedMergeStrategy`) and `pipeline.py`.

### Problem

CSO physical harm classes (Arson Methods, Sabotage Instructions, Drug Synthesis, CBRN Information,
Weapons Manufacturing, Lock Picking and Bypassing) are always-included and semantically close to
many risk descriptions. They get high hit counts (5-8 queries match them) and pass distance
thresholds because harm descriptions share vocabulary with many risk types ("unauthorized",
"exploit", "bypass"). The dual threshold reduces but doesn't eliminate this — a banking fraud risk
and "Lock Picking and Bypassing" are genuinely close in embedding space.

These classes are legitimate for generic AI safety testing but incoherent in banking, healthcare,
and energy contexts. 15-25% of prompts in gen4 domain-specific runs were contaminated.

### Approach: Graph-Derived URI Filter

**URI set derivation:** `build_generic_safety_uris(onto_handlers)` calls
`get_subclasses("cso#DangerousInformation", depth=3)` at runtime. Returns 19 URIs (the parent
+ 18 descendants). The set is derived from the ontology graph, not hardcoded — if CSO adds new
classes under DangerousInformation, re-indexing picks them up automatically.

**Activation signal:** `pipeline.py` checks the `identify_domains` result after that stage
completes. If domain-specific ontologies were selected (any of FIBO, OBO, IOF), the URI set is
computed and assigned to `merge_strategy.generic_safety_uris`. If only always-included domains
were selected (generic safety run), the set stays empty — no filtering.

**Filter application:** `_passes_threshold()` in `WeightedMergeStrategy` checks
`generic_safety_uris` before distance thresholds. Candidates whose URI is in the set are
rejected in both the domain-selected quota pass and the always-included pool pass.
`GroupedMergeStrategy` has the same filter in its `merge()` loop.

### CSO Hierarchy

```
ContentSafetyHazard (root)
├── Violence (29 classes)
├── HateAndDiscrimination (16 classes)
├── SelfHarm (13 classes)
├── SexualExploitation (15 classes)
├── SexualContent (9 classes)
├── FraudAndDeception (17 classes)        ← kept (relevant to banking, etc.)
├── DangerousInformation (18 classes)     ← FILTERED in domain-specific runs
│   ├── WeaponsManufacturing (4)
│   ├── DrugSynthesis (3)
│   ├── CBRNInformation (3)
│   ├── HarmfulHowTo (3: Arson, Sabotage, Lock Picking)
│   └── DualUseResearchConcern (1)
├── IntellectualProperty (18 classes)     ← kept
└── PrivacyViolation (16 classes)         ← kept
```

### Expected Impact

- **Banking/SWB:** CSO harm axes (Arson, CBRN, Lock Picking, Sabotage) eliminated. Fraud,
  Privacy, IP classes retained.
- **Healthcare:** CSO Drug Synthesis, Weapons Manufacturing eliminated. Privacy, Self-Harm
  (different branch) retained.
- **Generic safety:** No change — full CSO coverage including DangerousInformation.
- **Empty prompts:** fewer incoherent axis combinations → fewer null generation responses.
