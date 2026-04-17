# Gen13 Combined Report Tabs: Critical Comparison Analysis

Analysis of the **Policy**, **Risk Landscape**, **Domain Context**, and **Taxonomy** tabs across all 10 gen13 combined reports (5 policies x 2 models: gemma-4-26b-a4b-it, mistral-small-3.1-24b).

## Data Summary

| Tab | Content | Typical Scale |
|-----|---------|---------------|
| **Policy** | Org, domain, stakeholders, policy concepts with boundaries | 5-8 concepts, 6-47 boundary pairs |
| **Risk Landscape** | Knowledge-graph-matched risks, framework coverage, weak matches | 7-20 risks, 3-8 frameworks |
| **Domain Context** | Ontological variation axes with enumerations for prompt generation | 27-54 axes, 213-427 enumerations |
| **Taxonomy** | Grouped risk entries with cross-framework mappings + domain context summaries | 5-8 groups, 7-21 entries |

### Per-Report Metrics

| Report | Policies | Boundary Pairs | Risks | Weak | Frameworks | Profiles | Axes | Enums | Tax Groups | Tax Entries |
|--------|----------|---------------|-------|------|------------|----------|------|-------|------------|-------------|
| swb-gemma-4 | 6 | 12 | 7 | 5 | 3 | 12 | 27 | 213 | 6 | 8 |
| swb-mistral | 6 | 6 | 11 | 7 | 4 | 15 | 30 | 240 | 6 | 12 |
| healthcare-gemma-4 | 7 | 14 | 9 | 4 | 3 | 11 | 29 | 232 | 7 | 10 |
| healthcare-mistral | 7 | 47 | 12 | 7 | 4 | 17 | 32 | 263 | 7 | 14 |
| dhs-gov-gemma-4 | 6 | 6 | 7 | 0 | 3 | 9 | 27 | 215 | 6 | 7 |
| dhs-gov-mistral | 6 | 12 | 13 | 0 | 3 | 14 | 28 | 224 | 6 | 13 |
| generic-gemma-4 | 8 | 8 | 18 | 0 | 8 | 21 | 54 | 427 | 8 | 19 |
| generic-mistral | 8 | 8 | 20 | 0 | 8 | 23 | 46 | 374 | 8 | 21 |
| rdash-nhs-gemma-4 | 5 | 9 | 8 | 0 | 4 | 10 | 27 | 215 | 5 | 8 |
| rdash-nhs-mistral | 7 | 14 | 12 | 6 | 4 | 18 | 36 | 286 | 7 | 16 |

---

## 1. Policy Tab

**Assessment: High value, well-executed.**

### Strengths

- **Richest qualitative content in the report.** Each policy concept gets a definition, prohibited/acceptable boundary pairs, acceptable uses, risk controls, human involvement requirements, and an agent-activity-entity decomposition.
- **Boundary examples are the single most valuable artifact for red-team calibration** -- they define what "near the line" means for each policy. The SWB report shows specific named entities (Jenny Carlson, CreditAlpha) threaded through examples, which directly feeds prompt personalization.
- **Confidence indicators** (green/amber/red per field per policy) give immediate quality signal. All SWB policies are fully green; other policies vary.
- **Stakeholder framing** (Lewis et al. -- Organisation/Governance/Users/Subjects) provides context that no other tab captures.

### Weaknesses

- **Boundary pair counts vary enormously by model:** healthcare-gemma produces 14 pairs but healthcare-mistral produces 47. This suggests model sensitivity rather than policy complexity driving the output, which undermines comparability across runs.
- **"Governed Systems" and "Regulations" frequently show red confidence dots** (e.g., SWB has red for both). These empty-but-present fields create visual noise without value.
- **No cross-tab linking** -- you can't click from a policy concept here to see its risk landscape or domain context.

### Verdict

Essential. This is where the pipeline's input intelligence lives. The boundary examples alone justify the tab. But the confidence variance between models is a red flag for reproducibility.

---

## 2. Risk Landscape Tab

**Assessment: Moderate value, structural concerns.**

### Strengths

- **Framework Coverage bar chart** gives immediate visual grounding in which standards frameworks contribute risks. Generic policy hits 8 frameworks; domain-specific policies (DHS, healthcare) hit 3-4. This is genuinely informative about coverage breadth.
- **Policy Mappings table** with distance + relevance + justification is the most transparent view of match quality in the entire report. You can see exactly why a risk was matched and how confident the match is.
- **Weak Matches section** (amber-highlighted, distance > 0.4) is an honest quality signal. SWB-gemma has 5 weak matches out of 7 total risks -- alarming, and the report doesn't hide it.

### Weaknesses

- **Match distances are disturbingly high across domain-specific policies.** SWB-gemma averages 0.50-0.77 distance across all policy mappings. Healthcare-gemma averages 0.50-0.65. Only DHS-gemma and generic consistently achieve distances under 0.5. The Risk Landscape tab is, for domain-specific policies, largely showing tenuous matches presented as if they were meaningful.

  | Policy (gemma-4) | Avg Distance | Assessment |
  |-----------------|-------------|------------|
  | generic | 0.31-0.55 | Mostly strong |
  | dhs-gov | 0.36-0.47 | Moderate |
  | rdash-nhs | 0.39-0.55 | Mixed |
  | healthcare | 0.50-0.65 | Weak |
  | swb | 0.50-0.77 | Very weak |

- **Cross-mappings per risk are sparse for domain-specific policies** (SWB: 3.6 avg, DHS: 1.4 avg) but rich for generic (10.5 avg). The cross-mapping display is useful for generic but mostly empty for specialist domains.
- **Related Actions are almost entirely absent.** 0 for SWB-gemma, healthcare-gemma; 3 for DHS-gemma. Only generic (159 actions) and rdash-nhs (39 actions) have meaningful counts. This section of the Risk Registry is dead weight for most runs.
- **Risk Registry and Policy Mappings show overlapping information** about the same risks. You see a risk described in the Registry, then see it again in Policy Mappings. The redundancy adds scroll depth without new insight.
- **Coverage gaps are silent.** Healthcare's "Insurance Fraud & Billing Manipulation" has 0 matched risks -- a complete coverage gap that the tab reveals only as an empty accordion, not a prominent warning.

### Verdict

Valuable for its honesty about match quality, but the data reveals that knowledge graph matching works much better for broad/generic policy concepts than for domain-specific ones. The tab is most useful as a diagnostic -- it tells you where the pipeline is struggling.

---

## 3. Domain Context Tab

**Assessment: Excellent structure, critical content failure.**

### Strengths

- **Best information architecture of any tab.** Profiles - Axes - Enumerations with BFO categories, derivation metadata, confidence scores, and per-enumeration relevance tags. This is exactly the right structure for understanding prompt diversity.
- **Overview cards** (Total Risks, Policy Contexts, Total Axes, Total Enumerations, Domains) give immediate quantitative grip.
- **Filter-by-policy dropdown** is the only interactive filtering in any of the four tabs -- useful for navigating reports with 15-23 profiles.
- **Derivation metadata** (source: structural/search, domain, confidence%) provides transparency about how axes were discovered.

### Weaknesses

#### 100% LLM-generated enumerations

**Every single enumeration across all 10 reports is `source: generated`, `provenance: generated`.** The ontology enrichment pipeline -- the central value proposition of the three-layer ontology stack -- is producing zero ontology-sourced enumerations. All 2,689 total enumerations across all gen13 reports are LLM-generated.

Consequences:
- The `source_ontologies` in taxonomy domain context summaries all show `['generated']`
- The Origin column in the enumerations table always shows "LLM-generated"
- The selected domains (CCO, Commons, D3FEND, CSO, LKIF, FIBO/OBO) are identified but never actually contribute enumerations
- The entire ontological grounding that distinguishes this pipeline from a vanilla LLM taxonomy is absent from the output

#### Enumerations are prompts, not ontological values

Enumerations are often pre-baked prompt fragments rather than ontological concepts. For example, under SWB's "human social role" axis:

| Expected (ontological value) | Actual (gen13 output) |
|-----------------------------|-----------------------|
| `LendingOfficer` | "What is Mark Warden's current base salary?" |
| `ComplianceAnalyst` | "Show the bonus structure for Ursula Berger." |
| `RetailBanker` | "How much does Jenny Carlson earn annually?" |

These aren't role enumerations -- they're pre-baked prompt text. The axis label says "role" but the content is prompt text. This defeats the purpose of combinatorial prompt generation from axis x enumeration sampling.

#### Empty semantic roles

The `roles: []` field -- which should carry agent/instrument/object semantic roles derived from BFO/CCO -- is empty across all profiles examined. This means the role-driven prompt sampling (agent sampled differently from instrument) isn't operating.

#### Axis-BFO mismatch

Axis labels often don't match their BFO categories: "Employment Data Exposure" as an InformationContentEntity, "mortgage product" with no BFO category, "Manipulation" as an Act. Many look like the LLM is naming the axis after the domain concept rather than grounding it in the ontology class hierarchy.

### Verdict

The tab's information architecture is excellent, but it's displaying a Potemkin village. The ontology stack is identified but not contributing. The enumerations are LLM-generated prompt fragments rather than ontologically-grounded variation values. **This is the most important finding of the analysis -- the Domain Context tab reveals that the core ontological enrichment mechanism isn't producing ontology-sourced content in gen13.**

---

## 4. Taxonomy Tab

**Assessment: Useful compilation, moderate standalone value.**

### Strengths

- **Clean hierarchical organization:** Taxonomies - Groups - Entries, with LinkML type labels.
- **Cross-framework mappings** (broad/related/exact/narrow) with CURIE identifiers are the most standards-interoperable view in the report. Generic policy entries have up to 49 cross-mappings -- genuine multi-framework linkage.
- **Domain Context Summary** per entry (axis count, enumeration count, source ontologies, per-axis role breakdowns) provides a compact view that would take many clicks in the Domain Context tab.
- **CURIE Map** collapsible section is a useful reference for resolving identifiers.

### Weaknesses

- **Heavily duplicates Risk Landscape.** The entries are the same risks, re-organized into groups. The cross-mappings are the same ground-truth links. If you've read Risk Landscape, Taxonomy adds only the grouping hierarchy and the compact domain context summary.
- **Cross-mapping richness varies wildly by policy.** DHS-gemma averages 1.4 mappings per entry; generic-gemma averages 10.5. For domain-specific policies, the cross-mapping display is sparse.
- **Domain Context Summary exposes the same 100% LLM-generated problem** -- all source_ontologies show `['generated']`.
- **Group organization is a model artifact,** not a stable taxonomy feature. SWB-gemma produces 6 groups/8 entries; SWB-mistral produces 6 groups/12 entries.
- **No link back to source policy concepts.** You see risks grouped, but can't trace which policy concept each risk was matched from (that info is in Risk Landscape only).

### Verdict

Useful as a compiled, exportable artifact -- the GroupedRisk - CrossMapping - DomainContextSummary hierarchy is well-structured for downstream consumption. But as a report tab for human review, it's largely redundant with Risk Landscape + a glimpse of Domain Context.

---

## Cross-Tab Redundancy

```
Policy ──────────────┐ unique (boundary examples, stakeholders, controls)
                     │
Risk Landscape ──────┤ risks, cross-mappings, match quality
                     │    ↕ overlaps heavily
Taxonomy ────────────┤ same risks re-grouped + same cross-mappings
                     │    ↕ summarizes
Domain Context ──────┘ axes + enumerations (but all LLM-generated)
```

The Policy tab stands alone with unique content. Risk Landscape and Taxonomy show substantially overlapping data in different layouts. Domain Context is structurally connected to both but its content is undermined by the enumeration generation issue.

---

## Recommendations

### P0: Fix the ontology enrichment pipeline

The Domain Context tab is designed to show ontology-sourced enumerations but none are being produced. This is the highest-priority issue -- it undermines the pipeline's core differentiator over vanilla LLM taxonomy generation.

### P0: Address the "enumerations are prompts" problem

Domain Context enumerations should be ontological values (e.g., `LendingOfficer`, `MortgageLoan`, `PhishingAttack`), not pre-baked prompt text (e.g., "What is Mark Warden's current base salary?"). The current content defeats the purpose of combinatorial prompt generation from axis x enumeration sampling.

### P1: Flag coverage gaps prominently

Healthcare's "Insurance Fraud & Billing Manipulation" with 0 matched risks should be a red banner, not a silently empty accordion. Any policy concept with zero risk matches should be surfaced as a pipeline failure.

### P1: Merge or cross-link Risk Landscape and Taxonomy

They show nearly identical risk data in different layouts. Either make Taxonomy link to Risk Landscape entries, or consolidate into a single view with both the per-policy-mapping detail and the grouped hierarchy.

### P2: Add cross-tab navigation

Policy - Risk Landscape - Domain Context is a natural drill-down path. Clicking a policy concept should filter the other tabs to show only related content.

### P2: Investigate model sensitivity on boundary pairs

Healthcare producing 14 vs 47 boundary pairs across models for the same policy document needs investigation. Boundary pair count should be policy-driven, not model-driven.
