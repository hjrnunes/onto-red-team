# Changelog

All notable changes to this project will be documented in this file.

## Gen 8.3 — Multi-Taxonomy SSSOM Coverage (current)

### Changed

- **SSSOM Layer 1 expanded from 11 IBM groups to 91 groups across 7 taxonomies** — The original
  design used IBM Risk Atlas RiskGroups as a hub-and-spoke: non-IBM risks resolved to IBM equivalents
  via nexus cross-taxonomy mappings (`get_related_risks`), then used the IBM group's vocabulary seeds.
  Investigation of g8.2 zero-seed risks revealed three failure modes:

  1. **AI Risk Taxonomy entries have no nexus cross-mappings at all** (25 of 32 zero-seed risks).
     These 314 entries exist as isolated nodes — the nexus knowledge graph simply doesn't link them
     to IBM equivalents. Fixing this nexus-side would require 300+ new mapping rows.

  2. **Some Credo risks cross-map to Granite/MIT/NIST but not IBM** (4 of 32). The fallback
     specifically filters for `atlas-*` IDs, so non-IBM cross-mappings are ignored. The working
     Credo risks (e.g., `credo-risk-013` → `atlas-spreading-toxicity`) happen to have IBM links.

  3. **Fallback takes first IBM match and breaks** (1 of 32). `mit-ai-risk-subdomain-7.3` maps to
     9 IBM risks, but the first hit (`atlas-data-acquisition`) was in the unmapped `ibm-risk-atlas-
     data-laws` group. Had it hit `atlas-data-curation` (mapped group) instead, it would have worked.

  Rather than building 300+ nexus cross-mappings to make hub-and-spoke work, Layer 1 now maps risk
  groups directly: `risk-to-vocabulary.sssom.tsv` expanded from 37 rows / 11 groups to 257 rows /
  91 groups. Thematically similar groups across taxonomies share vocabulary concepts (e.g.,
  ai-risk-taxonomy-fraud, credo-rg-malicious-use, and mit-ai-risk-domain-4 all map to `risk:Threat`
  + `sector-law:CriminalLawEnforcement`).

  Coverage by taxonomy: IBM Risk Atlas (16, was 11), AI Risk Taxonomy (44), Credo (13), MIT (10),
  AILuminate (3), Granite Guardian (4), ShieldGemma (1).

- **SSSOM Layer 2 expanded with 7 new vocabulary→ontology paths** — `vocabulary-to-ontology.sssom.tsv`
  expanded from 22 to 29 rows. Previously, vocabulary concepts `eu-aiact:AIUser`, `eu-aiact:DeepFake`,
  `eu-aiact:MarketSurveillanceAuthority`, and `pd:Biometric` had no Layer 2 paths — they contributed
  structured LLM context but produced zero ontology seeds. New mappings:
  - `eu-aiact:AIUser` → CCO Person + OMRSE Human Social Role
  - `eu-aiact:DeepFake` → CSO Fraud and Deception
  - `eu-aiact:MarketSurveillanceAuthority` → FIBO Government Body + LKIF Regulation
  - `pd:Biometric` → CCO Person + OMRSE Human Social Role

- **All 32 g8.2 zero-seed risks now resolve** — Every previously zero-seed risk produces 3–7
  ontology seeds. This should eliminate zero-axis profiles for these risks in the next battery.

## Gen 8.2 — Policy Context Injection

Second battery on the SSSOM pipeline. 1,890 prompts across 15 runs. Anchor prompt now receives
policy concept_definition and boundary examples (PROHIBITED/ACCEPTABLE pairs).

### Battery Results (g8.2 vs g8.1)

- Inappropriate demographic axes eliminated: Healthcare Gemma 4 Oceanian ancestry 45x → 0
- DHS-Gov volume recovered: 225 → 270 (+20%), reversing g8.1 regression
- More specific axis classes: Health Data Exposure, Employment Data Exposure, Direct Identifier Exposure
  replace broad Person/Organization defaults
- RDaSH Gemma 4 achieves 0 zero-axis profiles (full coverage milestone)
- Red flags: 21 → 19
- SWB volume regression: 195 → 120 (38% drop, SSSOM seed gap — not policy context related)
- Axis concentration persists: Act of Violence 135x, human social role 135x (upstream of selection)
- New metric: axis fidelity 0.58–0.97 (Gemma 4 best, Mistral worst)
- Domain term hit rate slight recovery: 0.0–0.059 (was 0.0–0.037)

## Gen 8.1 — SSSOM Redesign

First battery on the SSSOM-redesigned pipeline. 1,950 prompts across 15 runs.

### Fixed

- **Anchor label suffix leakage** — LLM responses echoed candidate heading tags (`-- structural`,
  `-- search`, `[Role]`, `[InformationContentEntity]`) into axis labels, affecting 180/1,950 prompts
  (9.2%). Post-processing now uses the authoritative label from the enriched candidate dict. A
  `_strip_label_suffix` fallback handles edge cases where no enriched match exists.

- **Debug anchor response rendering** — `_render_anchor_response` in `debug.py` referenced wrong
  field names (`cco_class_label`, `role`) instead of the actual `_AnchorResponse` fields (`class_id`,
  `class_label`, `rationale`), producing empty Class/Role columns in `debug.md`.

- **Opaque path labels in anchor prompt** — Path display showed raw CCO numeric URIs
  (`ont00001180 > ont00001239`) instead of human-readable class names. Path URIs are now resolved
  via `get_class_definition` during candidate enrichment, producing labels like `Agent > Legal Entity`.

### Added

- **Policy context in anchor prompt** — Anchor LLM now receives `concept_definition` and up to 3
  boundary examples (PROHIBITED/ACCEPTABLE pairs) from the enriched policy, giving the LLM explicit
  knowledge of what behavior is prohibited and where the boundary lies. System prompt updated to
  instruct axis selection toward the gray zone between prohibited and acceptable behavior. Threaded
  via a new `policies` parameter from the pipeline. Future option: pass full `Policy` objects
  (acceptable_uses, risk_controls) if boundary examples alone prove insufficient.

- **Anchor candidate tier reporting** — Anchor stage emits a `candidate_tiers` event per risk with
  seed count, per-tier candidate counts (structural, search_connected, search_only), merged total,
  and the actual seed URIs with labels and predicates.

- **Two-layer SSSOM seed mapping files** — Ontology integration now driven by SSSOM (Simple Standard for
  Sharing Ontological Mappings) seed files instead of ChromaDB distance-based retrieval. Two layers:
  a risk-to-ontology mapping layer and an ontology-to-ontology bridge layer. Seed resolution replaces
  the old `SearchMergeStrategy` hierarchy.

- **SSSOM loader and seed resolution** (`refiner/src/refiner/ontology_seeds.py`) — Loads two-layer seed
  files, resolves risk IDs to ontology class sets via structural navigation of ontology hierarchies.
  Replaces the ChromaDB-based candidate pool construction.

- **Policy-driven LLM enumeration generation** — Contextualize stage rewritten to generate scenario
  descriptions via LLM rather than sampling from ontology subclass pools. Enumerations are now
  `source_ontology: "generated"` with scenario-specific descriptions (e.g., "step-by-step guide to
  committing credit card fraud") instead of ontology class labels (e.g., "Pretexting", "Confidence Trick").

- **Vocabulary context per axis** — Each axis carries structured regulatory metadata with stakeholders
  (EU AI Act subject types), data_sensitivity (GDPR categories), and rights (EU Charter of Fundamental
  Rights) sourced from regulatory ontologies.

- **Enriched policy files** — All policy sets updated to `-enriched.json` variants with explicit
  PROHIBITED/ACCEPTABLE boundary examples and permitted-use specifications in the generation prompt.

- **`get_risk_group` nexus-mcp handler** — New handler for retrieving risk group metadata from the
  AI Atlas Nexus knowledge graph.

### Changed

- **Anchor stage rewritten** — `anchor()` now uses SSSOM seed path with structural navigation (parent/
  sibling/child traversal), tiered merge, and BFO category derivation. Backward-compatible legacy
  fallback retained for non-SSSOM runs. Old `_CATEGORY_ROLES` (29 entries) and `derive_roles()` removed.

- **Role system removed** — Sampled axes no longer carry agent/object/instrument/context/location role
  tags (`roles: []`). The old role-based compositional guidance is replaced by the LLM-generated
  scenario descriptions.

- **Old merge strategies removed** — `WeightedMergeStrategy`, `GroupedMergeStrategy`, and
  `LLMMergeStrategy` removed from anchor stage. Candidate selection now handled by SSSOM seed
  resolution + structural navigation.

- **Data models updated** — Pipeline models extended with vocabulary_context fields, SSSOM seed
  references, and generated-enumeration provenance tracking.

### Battery Results (g8.1 vs g8)

- Value-level concentration eliminated: max 13x (down from 53x)
- Empty prompts: 6 (down from 7), still Gemma 3 only
- RDaSH coverage doubled: 246 → 510 prompts
- Domain term hit rate regressed: 0.15-0.33 → 0.0-0.037 (LLM-generated enums lack ontology vocabulary)
- New issue: axis class over-concentration (Person 165x, GSSO 135x, Organization 120x)
- SWB volume halved: 365 → 195 (fewer SSSOM seed matches)

## Gen 8

### Added

- **LKIF normative class exclusion** — 13 URIs (9 deontic meta-labels + 4 upper-ontology primitives)
  excluded from candidate pools via `_is_excluded_uri()`. Eliminates Disallowed Intention, Strictly
  Disallowed, Allowed And Disallowed, Observation of Violation, Belief In Violation, and Obliged from
  all prompts. Also excludes LKIF upper-ontology primitives (Intention, Belief, Agent from
  expression/action.owl, Mental Process).

- **Empty enumeration guard** — Axes with zero enumerations after filtering excluded from profiles in
  contextualize stage, preventing dead-zone axes and downstream generation failures.

- **Role-diversity guidance in LLM merge prompt** — Candidates tagged with roles, prompt instructs
  diverse role selection across agent/object/instrument/context.

- **Enumeration concentration soft cap** — `max(3, effective_n // unique_values)` per axis limits
  oversampling of any single enumeration value within a risk.

- **LKIF domain display name** — "legal/regulatory" instead of raw "LKIF" in merge prompts.

## Gen 7

### Added

- **LKIF Core ontology** (~208 classes) — Legal Knowledge Interchange Format loaded from
  [RinkeHoekstra/lkif-core](https://github.com/RinkeHoekstra/lkif-core). 15 OWL modules covering
  norms (Obligation, Prohibition, Permission, Right), legal sources (Statute, Regulation, Directive,
  Contract, Treaty, Decree), legal entities (Corporation, Legal Person, Public Body), and temporal
  modifications (Repeal, Amendment, Suspension, Retroactivity). Fills Cross-Cutting Gap §2
  (Regulatory Text Structure) — FIBO models regulatory *entities* but not regulatory *text*. LKIF
  added to `ALWAYS_INCLUDED` domains since regulatory structure is cross-domain.

- **CCO→LKIF bridge** (`bridges/cco-lkif.ttl`, 11 axioms) — Maps LKIF classes into the BFO
  hierarchy via conservative `rdfs:subClassOf` axioms: 4 entity bridges (Agent, Person, Organisation,
  Action), 5 normative bridges (Norm→Process Regulation, Prohibition→Process Prohibition,
  Obligation→Process Requirement, Legal Source→Prescriptive ICE, Legal Document→Document Content
  Entity), 2 expression bridges (Expression→ICE, Proposition→ICE).

- **LKIF label generation** (`bridges/lkif-labels.ttl`, 205 labels) — LKIF uses URI fragments as
  class names without `rdfs:label` annotations. A generated labels file provides `rdfs:label` triples
  derived from URI fragments (e.g. `norm.owl#Customary_Law` → "Customary Law"). Generation is
  automated in `scripts/fetch_ontologies.sh` after clone.

- **DUO ontology** (~45 classes) — Data Use Ontology from OBO Foundry. Models data use conditions
  ("no restriction", "disease-specific research only", "geographical restriction", "user specific
  restriction"). Relevant for privacy/data governance risk scenarios across all domains.

- **Domain pattern: LKIF** — `DOMAIN_PATTERNS` in `ontoquery/index.py` extended with
  `"LKIF": "estrellaproject.org/lkif-core"`. Index: 100,313 → 100,561 classes.

### Changed

- **BFO upper-ontology exclusion** — All BFO classes (`http://purl.obolibrary.org/obo/BFO_*`) are now
  excluded from candidate pools in all three merge strategies (Weighted, Grouped, LLM) and from
  restriction/equivalence expansion. BFO classes like `material entity`, `generically dependent
  continuant`, and `process` are maximally abstract ontological primitives that produce vague,
  jargon-laden scenarios when selected as variation axes. Filtering uses a URI prefix check via a
  shared `_is_excluded_uri()` helper that also handles `generic_safety_uris`. BFO entries in
  `_CATEGORY_ROLES` are preserved — they remain necessary for role derivation via superclass chains.
  Addresses ~8% BFO jargon rate observed in gen6 DHS-Gov Gemma 3 runs.

- **LLMMergeStrategy prompt improvements** — Three changes to the merge prompt that improve LLM
  relevance judgment quality:
  - **Class definitions**: Pool candidates are enriched with truncated ontology definitions (≤25 words)
    via `onto_handlers["get_class_definition"]`. The LLM now sees *"Attitude Control Artifact Function
    [cyber defense] — the function of controlling spacecraft orientation..."* instead of just the label,
    making domain mismatch obvious. `LLMMergeStrategy.__init__` accepts optional `onto_handlers` param.
  - **Readable domain names**: Domain abbreviations replaced with human-readable descriptors via
    `_DOMAIN_DISPLAY` mapping (D3FEND → "cyber defense", FIBO → "financial industry", OBO →
    "biomedical/social", etc.).
  - **Conditional concern**: `Concern: None` no longer appears in prompts when the risk has no concern
    defined in the nexus ontology. The line is omitted entirely for None/empty values.

- **ALWAYS_INCLUDED domains** — LKIF added to always-included set: `["CCO", "Commons", "D3FEND",
  "CSO", "LKIF"]`. Regulatory text concepts are cross-domain (benefits banking, insurance,
  government, telecom policies that cite specific statutes and obligations).

## Gen 6

### Added

- **LLMMergeStrategy** — New merge strategy (`--search-strategy llm`) that replaces statistical
  distance-based candidate merging with LLM-judged contextual relevance selection. A mechanical
  pre-filter (distance ceiling 0.6 + CSO DangerousInformation URIs) reduces the pool, then the LLM
  selects the most relevant candidates given the risk description, concern, and policy context.
  Falls back to distance-sorted order on LLM failure. Addresses FIBO contamination in healthcare
  runs (27-32% in gen5) at the root — semantic relevance judged in context, not by distance proxy.

- **OBO ontology expansion** — Three new ontologies added to the OBO domain stack:
  - **GSSO** (~13k classes) — gender, sex, sexual orientation
  - **HANCESTRO** (~1.3k classes) — human ancestry
  - **OMRSE** (~600 classes) — social entities, insurance/healthcare roles
  
  OMRSE provides OBO-native insurance/healthcare role classes that may displace irrelevant FIBO
  financial regulatory classes in healthcare runs. GSSO and HANCESTRO add bias/discrimination
  dimensions for red-team testing.

### Changed

- **SearchMergeStrategy protocol** — `merge()` signature extended with `risk_context: dict` and
  `generic_safety_uris: set[str]` parameters. All strategies are now stateless after construction
  (`generic_safety_uris` moved from mutable instance state to function parameter). Both
  `WeightedMergeStrategy` and `GroupedMergeStrategy` updated to the new signature.

- **Pipeline parameter threading** — `generic_safety_uris` computed in `pipeline.py` and passed
  through `anchor()` → `expand_candidates()` → `merge()` as explicit parameters.
  `policy_concept` threaded from `anchor()` into `expand_candidates()` for risk context assembly.

## Gen 5

### Fixed

- **WeightedMergeStrategy: per-domain distance normalization + dual threshold** — Candidates are
  now z-score normalized per domain before merging, making distances comparable across ontology
  collections with different embedding distributions (e.g. CSO plain English vs OBO technical
  jargon). A dual threshold rejects candidates that fail either a raw distance ceiling (0.6) or a
  z-score threshold (1.0 std above domain mean). Applied to both the domain-selected quota loop and
  the always-included pool. Fixes three gen4 regressions caused by the per-domain search
  introduction:
  - FIBO domain contamination in healthcare/RDaSH (FIBO 1.4% → 13.9% of axis samples)
  - CSO harm axis explosion in banking (12 → 48 CSO harm samples, 4x increase)
  - Empty prompts from incoherent axis combinations (7 null prompts in SWB Gemma 3)

  See `docs/anchor-search-mechanics.md` for full analysis.

- **Pipeline prompt improvements across map_risks, anchor, contextualize** — Reduced token waste and
  improved LLM comprehension for small models (Gemma 2 9B, Phi-4):
  - **map_risks:** Removed `Policy Type:` line (internal classification, not useful for risk matching)
    and cross-mapping display from prompt (cross-mappings serve downstream structure stage, not risk
    selection). Cross-mapping data still fetched and stored for structure.
  - **anchor:** Replaced full URIs with short candidate IDs (C1, C2, ...) in prompts. Raw hit counts
    (`[found by 5/8 queries]`) replaced with relevance labels (high/medium). Switched to Markdown
    format with `## C1: ClassName` headers. Post-processing maps short IDs back to URIs.
  - **contextualize:** Replaced full URIs with short axis IDs (A1) and enum IDs (E1, E2, ...).
    Added `get_class_definition()` calls for each subclass/sibling candidate so the LLM sees
    definitions, not just labels. Switched to Markdown format with `### Axis A1: Label` headers.
    Post-processing maps IDs back to URIs before existing filters.
  - **emit:** Extended `_strip_framework_suffix()` to also remove OBO metadata suffixes (AE, HP, GO)
    from class labels before they reach the generation prompt. Fixes "Phobia AE", "Somnambulism AE"
    appearing as literal text in Gemma 2 healthcare prompts (27% contamination rate in gen4).

- **CSO DangerousInformation filtering for domain-specific runs** — CSO physical harm classes
  (Arson Methods, Sabotage Instructions, Drug Synthesis, CBRN, Weapons Manufacturing, Lock Picking,
  etc.) are now filtered from merge results when the pipeline selects domain-specific ontologies
  (FIBO, OBO, IOF). The URI set is derived from the ontology graph at runtime via
  `build_generic_safety_uris()` using `get_subclasses` on `cso#DangerousInformation` (18 classes,
  depth 3) — not hardcoded. Generic-only runs (no domain-specific selection) retain full CSO
  coverage. Applied to both `WeightedMergeStrategy` and `GroupedMergeStrategy`. Fixes CSO
  contamination in banking/healthcare/energy runs (15-25% of prompts affected in gen4).

  See `docs/anchor-search-mechanics.md` for full analysis.


