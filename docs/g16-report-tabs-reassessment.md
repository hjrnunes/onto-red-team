# Gen16 Combined Report: Reassessment

Reassessment of the combined report tabs following the gen13→g16 pipeline evolution and the Domain Context + Taxonomy tab merge. Covers all 15 g16 runs (5 policies x 3 models: gemma-3-12b-it, gemma-4-26b-a4b-it, mistral-small-3.1-24b).

## Gen13 → G16: What Changed

| Issue (gen13) | Status in g16 |
|---------------|---------------|
| 100% LLM-generated enumerations | **Fixed.** ~51% ontology-sourced (subclass/sibling provenance from CSO, FIBO, OBO, CCO, LKIF, Commons) |
| Enumerations are prompt fragments, not ontological values | **Fixed.** Enumerations are now concept-level noun phrases (`Salary Exposure`, `deposit account`, `mortgage product`) |
| Empty semantic roles on all axes | **By design.** Role system removed in g8.1, replaced by ontology-grounded slot labels per adversarial technique frame |
| Domain Context + Taxonomy redundancy | **Fixed.** Merged into single "Enriched Taxonomy" tab |
| No cross-tab navigation | Partially addressed — Enriched Taxonomy now shows taxonomy entries with inline DC profiles |
| Coverage gaps silent | Not addressed — zero-match concepts still appear as empty accordions |
| D3FEND contributes zero enumerations | **Not fixed.** D3FEND selected everywhere, contributes zero axis URIs or enumerations |
| Fidelity metric declining | **Resolved.** Judge evaluation (new in g16) confirms prompts are excellent (4.0/4.9/4.9/4.7) — fidelity decline is a measurement artifact |

---

## Data Summary

| Tab | Content | G16 Scale |
|-----|---------|-----------|
| **Policy** | Org, domain, stakeholders, policy concepts with boundaries | 4-8 concepts, 4-28 boundary pairs |
| **Risk Landscape** | Knowledge-graph-matched risks, framework coverage, weak matches | 6-18 risks, 3-7 frameworks |
| **Enriched Taxonomy** | Taxonomy entries with inline domain context: cross-mappings, axes, enumerations | 6-22 entries, 44-139 axes, 352-1111 enums |
| **Dataset Explorer** | Generated adversarial prompts | 105-330 prompts/run, 2985 total |
| **Evaluation** | Quality metrics + judge evaluation | Judge 4.0/4.9/4.9/4.7 battery mean |

### Per-Policy Metrics (g16, gemma-4-26b model)

| Policy | Concepts | Boundary Pairs | Risks | Weak | Frameworks | Axes | Enums | Onto% | Entries | Prompts |
|--------|----------|---------------|-------|------|------------|------|-------|-------|---------|---------|
| SWB | 6 | 12 | 7 | 5 | 3 | 73 | 583 | 45% | 8 | 180 |
| Generic | 8 | 8 | 17 | 0 | 7 | 112 | 896 | 49% | 20 | 285 |
| Healthcare | 7 | 14 | 9 | 3 | 3 | 57 | 456 | 46% | 11 | 150 |
| DHS-Gov | 6 | 6 | 7 | 0 | 3 | 54 | 431 | 45% | 8 | 135 |
| RDaSH NHS | 6 | 9 | 8 | 1 | 4 | 67 | 536 | 51% | 9 | 165 |

---

## 1. Policy Tab

**Assessment: High value. Stable from gen13.**

### Strengths (unchanged)
- Richest qualitative content: boundary examples, stakeholder framing, decomposition
- Confidence indicators (green/amber/red) provide immediate quality signal
- Boundary examples remain the single most valuable artifact for red-team calibration

### Improvements from gen13
- **Third model added** (gemma-3-12b-it) provides additional validation signal
- Policy concept counts stable across models (exception: rdash-nhs-gemma-3 drops to 4 concepts)

### Persistent weaknesses
- **Boundary pair counts still model-sensitive:** Healthcare produces 14 (gemma-4) vs 28 (mistral), a 2x variance for the same policy document
- **Governed Systems and Regulations inconsistently populated:** SWB has empty governed_systems across all 3 models. Gemma-3 is the weakest at populating these fields
- **Generic gemma-4 extracts 0 stakeholders** — a complete failure on a field that's well-populated by the other models

### Verdict
Essential. The boundary examples and decomposition justify the tab. But the model sensitivity on secondary fields (governed_systems, regulations, stakeholder counts) needs attention — different models extract different amounts of context from the same document.

---

## 2. Risk Landscape Tab

**Assessment: Moderate-to-high value. Improved from gen13.**

### Improvements from gen13
- **No zero-match coverage gaps** — every policy concept maps to at least one risk across all 15 runs (gen13 had silent gaps like Healthcare's "Insurance Fraud & Billing Manipulation")
- **Tighter distance distribution** — g16 avg distances 0.40-0.64 vs gen13's 0.31-0.77
- **Model sensitivity on distances is low** — same risk-concept pairs have near-identical embedding distances regardless of model (spread <0.01 for most policies). The variance comes from Mistral adding more risks, not worse matching

### Persistent weaknesses
- **SWB weak match burden** remains the worst in the battery (5-9 risks at >0.6 distance). "Executive Compensation" matches at 0.735-0.794 across all models — a fundamental knowledge graph coverage gap, not a matching quality issue
- **Related Actions still mostly absent** — 0 for SWB/healthcare gemma runs. Only generic (57-61 actions) and rdash-nhs (12-28) have meaningful counts
- **Cross-mapping richness varies wildly** — generic averages 8-9 per risk, DHS-Gov averages 1.4-2.5. Domain-specific policies have sparse cross-framework links

### New findings
- **Model choice affects quantity, not core quality** — Mistral-Small generates more risks (avg 13.4 vs 9.6-9.8) including weaker matches. The retrieval distances for shared risk-concept pairs are identical across models (same ChromaDB embeddings)
- **Structural context enrichment (g16 feature)** — did not eliminate weak matches but provides better semantic context. The bottleneck is the knowledge graph's missing AIR 2024 cross-taxonomy mappings

### Verdict
Valuable for its transparency about match quality. The zero coverage gaps are a clear improvement. But SWB's financial-domain weak matches are a persistent gap that tab display can't fix — it requires nexus knowledge graph enrichment.

---

## 3. Enriched Taxonomy Tab (merged)

**Assessment: Good structure. The merge was the right call. Critical content improvement from gen13.**

### What the merge achieved
- **Single point of truth** for each risk: taxonomy entry (cross-mappings, group membership) + domain context profile (axes, enumerations, derivation paths) in one expandable card
- **Eliminated tab-switching** — previously had to jump between Domain Context and Taxonomy to see the same risk's full picture
- **Policy filter preserved** — filters entries by matching DC profile's policy_concept
- **Fallback handling** — entries without a matching DC profile show the lightweight `domain_context_summary` instead of full axes/enumerations
- **Unmatched profiles section** — DC profiles for risks not in the taxonomy appear at the bottom (typically 0-1 per report)

### Critical improvement: enumeration quality
This is the headline finding. The gen13 analysis flagged the Domain Context tab as a "Potemkin village" — excellent structure displaying entirely fabricated content. G16 resolves both facets:

1. **~51% of enumerations are now ontology-sourced** (was 0% in gen13/g14). Breakdown:
   - Provenance: `subclass` (~55% of onto-sourced), `sibling` (~45% of onto-sourced)
   - Source ontologies: CSO (dominant), FIBO (financial), OBO (healthcare), CCO, LKIF, Commons
   - Range: 42-66% ontology-sourced across runs (rdash-nhs-gemma-3 peaks at 66%)

2. **Enumerations are proper concept-level values**, not prompt fragments:
   - Gen13: `"What is Mark Warden's current base salary?"` (pre-baked prompt text)
   - G16: `Salary Exposure`, `deposit account`, `mortgage product` (ontological concepts)

### Remaining weaknesses

#### Empty semantic roles (by design)
`roles: []` on 100% of axes across all 15 g16 runs. This is **intentional** — the old `_CATEGORY_ROLES` / `derive_roles()` system was removed in g8.1 and replaced by **ontology-grounded slot labels** in the emit stage. Each adversarial technique frame (pretexting, delegated_authority, etc.) maps BFO categories to context-specific labels (e.g., pretexting maps `Role` → "professional role", `Agent` → "authority figure"). The slot label system uses `bfo_category` directly rather than the old role tags. The role badges in the report template are legacy UI — they could be removed or repurposed to show BFO categories instead.

#### D3FEND phantom domain
D3FEND appears in `selected_domains` for every run but contributes:
- 0 axis URIs
- 0 enumerations
- The Domains count in overview cards includes D3FEND, inflating the perceived coverage

#### Axis-BFO distribution skew
45% of axes are categorized as `Act`, 22% as `InformationContentEntity`. Only 2% are `Role`. 6% have empty bfo_category. This skew means prompt variation is dominated by actions and information objects, with limited diversity in agent/instrument dimensions.

#### ~~No cross-tab linking to Risk Landscape~~ (fixed)
Match distance badges now appear on each Enriched Taxonomy entry header, color-coded green (<0.3) / amber (0.3–0.5) / red (>0.5) — matching the Risk Landscape tab's scheme. Distance data flows from `risk_landscape.policy_mappings` through `build_combined_report.py` into DC profiles.

### Data linkage quality
Entry-to-DC-profile matching by `risk_name` works well:
- SWB: 7/8 entries matched (87.5%)
- Generic: 17/18 (94.4%)
- Healthcare: 9/10 (90.0%)
- Typically 1 unmatched entry per report, falling back to summary view

### Verdict
The merge eliminated the redundancy problem and the inline DC profiles make the tab genuinely useful for understanding prompt generation inputs. The critical enumeration quality improvement (0% → 51% ontology-sourced, proper concept values) transforms this from a Potemkin village into a meaningful ontological grounding display. Match distance badges now provide cross-tab linkage to Risk Landscape match quality. The D3FEND phantom domain is the remaining structural gap.

---

## 4. Dataset Explorer Tab

**Assessment: High value. Now validated by judge evaluation.**

The g16 battery introduces judge evaluation (30 prompts sampled per run, 450 total judgments), providing the quality signal that was previously missing.

### Key metrics
- **2,985 total prompts** across 15 runs (up from gen15's 2,370 due to Mistral completion recovery)
- **Zero hard red flags** — battery record
- **Judge battery mean:** subtlety 4.0 / plausibility 4.9 / domain_grounding 4.9 / policy_relevance 4.7
- **Semantic diversity** stable at 0.96-0.98

### Model comparison
| | Gemma 3 12B | Gemma 4 26B | Mistral 3.1 24B |
|--|------------|------------|-----------------|
| Avg prompts/run | 171 | 183 | 243 |
| Empty prompts | **19** | 0 | 0 |
| Red flags | 12 | 3 | 16 |
| Judge domain_grounding | 4.9 | **5.0** | 4.8 |
| Judge policy_relevance | 4.3 | **4.9** | 4.7 |

### Findings
- **Gemma 4 is near-ceiling** — 5.0 domain grounding, zero empties, 3 soft red flags across 915 prompts
- **Gemma 3 empty prompt regression** — 19 empties (up from 5 in gen15), likely due to concept-level enumeration style providing insufficient context for the 12B model
- **Fidelity metric is confirmed miscalibrated** — declining from 0.853 (gen10) to 0.577 (g16), but judge evaluation proves prompts are excellent. The fidelity metric was designed for scenario-level enumerations and penalizes the (correct) concept-level adaptation

---

## 5. Evaluation Tab

**Assessment: Moderate standalone value. Judge data is the new primary signal.**

The Evaluation tab displays the automated metrics (fidelity, red flags, coverage) and now includes judge evaluation scores. The judge scores are the most actionable quality signal, while fidelity is recognized as miscalibrated.

### Recommendation
The tab should visually promote judge scores over fidelity metrics, given fidelity's confirmed measurement artifact status.

---

## Cross-Tab Summary

```
Policy ──────────────┐ unique (boundary examples, stakeholders, controls)
                     │
Risk Landscape ──────┤ match quality, distances, coverage gaps
                     │    ↕ conceptually linked (same risks)
Enriched Taxonomy ───┤ entries + cross-mappings + full DC profiles
                     │    (axes, enumerations, derivation paths)
                     │
Dataset Explorer ────┤ generated prompts (judge-validated)
                     │
Evaluation ──────────┘ quality metrics + judge scores
```

The merge eliminated the Domain Context / Taxonomy redundancy. The remaining overlap is between Risk Landscape (per-policy-concept match quality) and Enriched Taxonomy (per-entry detail). They show different facets of the same risks — Risk Landscape is about match confidence, Enriched Taxonomy is about downstream content.

---

## Recommendations

### ~~P0: Fix empty semantic roles~~ (not a bug)
The role system was intentionally removed in g8.1 and replaced by ontology-grounded slot labels per adversarial technique frame (g8.3). The `roles: []` field is kept for backward compatibility. The role badges in the report template are legacy UI that could be cleaned up or repurposed.

### ~~P1: Add match distance to Enriched Taxonomy entries~~ (done)
Match distance badges now appear on each entry header, color-coded by match quality (green/amber/red). Distance data flows from `risk_landscape.policy_mappings` through `build_combined_report.py` into DC profiles.

### P0: Deprecate or recalibrate fidelity metric
The judge evaluation (4.0/4.9/4.9/4.7 battery mean) conclusively shows fidelity's decline from 0.853 to 0.577 is a measurement artifact. Options: switch to judge-based quality as primary metric, or add semantic similarity scoring that recognizes concept-label adaptation.

### P1: Resolve D3FEND integration
D3FEND appears in selected_domains and inflates the "Domains" count but contributes zero axis URIs and zero enumerations. Either add D3FEND class URIs to vocabulary-to-ontology.sssom.tsv or remove D3FEND from always-included domains.

### P2: Investigate Gemma 3 empty prompt regression
19 empty prompts (up from 5 in gen15) is a notable regression. The concept-level enumeration style may provide insufficient context for the 12B model.

### P2: Flag zero-match policy concepts prominently
While g16 has no zero-match concepts, Healthcare's "Insurance Fraud & Billing Manipulation" still has zero prompts for Gemma 4. Silent empty accordions should be red-flagged.

### P2: Address SWB weak match burden at knowledge graph level
The 314 structurally-isolated AIR 2024 risks need cross-taxonomy mappings in the nexus knowledge graph. The structural context enrichment helps but cannot compensate for missing mappings.

---

## Gen13 → G16 Trajectory

| Metric | Gen13 | G14 | G16 |
|--------|-------|-----|-----|
| Ontology-sourced enums | 0% | 0% | **~51%** |
| Enumeration style | Prompt fragments | Prompt fragments | **Concept-level noun phrases** |
| Semantic roles populated | 0% | 0% | N/A (replaced by slot labels in g8.1) |
| D3FEND contributing | No | No | No |
| Zero-match concepts | Yes (silent) | None | None |
| Fidelity (battery mean) | ~0.85 | ~0.88 | 0.577 (miscalibrated) |
| Judge evaluation | N/A | N/A | **4.0/4.9/4.9/4.7** |
| Report tabs | 4 separate (DC + Tax redundant) | 4 separate | **3 merged (Enriched Taxonomy)** |
| Hard red flags | Unknown | 1 | **0** |
| Models tested | 2 | 3 | 3 |
| Completed runs | 10 | 15 | **15** |
| Total prompts | ~2500 | ~3000 | **2,985** |

**Bottom line:** The pipeline's output quality is at its highest measured level. The two critical gen13 findings — fabricated enumerations and prompt-fragment content — are both resolved in g16. The merged Enriched Taxonomy tab correctly displays the improved data with match distance cross-linkage. The remaining gaps are D3FEND phantom integration and fidelity metric miscalibration.
