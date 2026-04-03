# Pipeline Quality Issues — Post Live Testing

**Date:** 2026-04-01
**Model:** Gemma 2 9B IT Abliterated (vLLM, 8K context)
**Policy set:** South West Bank (`swb.json`, 6 policies)
**Run output:** `/tmp/refiner-output-11/`

## Issue 1: Semantic Role Assignment — FIXED

**Stage:** Anchor (Stage 4)
**Fix:** Programmatic role derivation from BFO/CCO superclass chain. `derive_roles()` walks `get_superclasses()` looking for known BFO/CCO category URIs mapped to role lists. CCO categories (Agent, Material Artifact, Act, Information Content Entity) checked first for specificity, then broader BFO categories (material entity, process, role, site, temporal region, etc.). When found, derived roles override the LLM's assignment. For non-BFO classes (FIBO, Commons) where the walk doesn't hit known categories, falls back to the LLM's single role wrapped in a list.

Changed `VariationAxis.role: str` → `VariationAxis.roles: list[str]` (and `DomainContextAxis`, `SampledAxis`). Multiple roles express ambiguity — prompt generation picks the appropriate one at runtime. Added `_SlimAxis` model for LLM response (keeps single `role: str`).

## Issue 2: Risk ID Truncation — FIXED

**Stage:** Map Risks (Stage 3)
**Fix:** Sequential indices. Candidates shown as numbered list (1, 2, 3...). LLM returns `risk_index: int` via `_SlimRiskMatch`, post-processing maps back to actual IDs. Also relaxed match count from forced 2-3 to 1-3 with "1 strong match > 3 weak ones" guidance (Issue 3).

## Issue 3: Slug Sanitization — FIXED

**Stage:** Structure (Stage 6)
**Fix:** Added `re.sub(r"-+", "-", slug)` to `slugify()`. Collapses consecutive dashes.

## Issue 4: Money Laundering Coverage Gap — MITIGATED

**Stage:** Map Risks (Stage 3)
**Severity:** Low-Medium — data gap, not a pipeline issue

**Root cause:** No dedicated AML risk entry in the AI Atlas Nexus knowledge graph across all 10 frameworks.

**Fix:** Added `match_distance: float | None` to `RiskMatch` model, populated from semantic search distances. Logs warning when `match_distance > 0.4` (WEAK_MATCH_THRESHOLD). Downstream consumers can check this field to identify weak coverage. The pipeline accepts best-available matches but annotates them for visibility.

## Issue 5: Duplicate Risk Entries Across Policies — FIXED

**Stage:** Anchor (Stage 4) + Contextualize (Stage 5)
**Fix:** Added `axes_cache` dict in `anchor()` and `context_cache` dict in `contextualize()`, keyed by `risk_id`. First occurrence runs the LLM call; subsequent occurrences reuse the cached axes with the current `policy_concept`. Reduces LLM calls proportionally to risk overlap across policies.

**Note:** Option A (architectural cleanup — deduplicating at the pipeline level by collecting unique risk IDs before anchor, processing once, then fanning results back) would be a cleaner long-term design. The current approach (option B) works correctly but the deduplication logic is buried inside each stage function.

## Issue 6: Self-Reference in Sibling Enumerations — FIXED

**Stage:** Contextualize (Stage 5)
**Fix:** Added post-processing filter: `if enum.class_uri == input_axis.cco_class_uri: continue` skips enumerations that reference the axis class itself.
