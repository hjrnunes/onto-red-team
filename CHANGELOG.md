# Changelog

All notable changes to this project will be documented in this file.

## Gen 12 (current)

### Added

- **RiskLandscape model** — New Pydantic envelope (`models.py`) that consolidates five scattered
  `PipelineState` caches (`risk_mappings`, `risk_details`, `related_risks`, `risk_actions`,
  `seen_risk_ids`) into a single serializable artifact. Contains `RiskDetail` (full risk metadata
  with cross-mappings and related actions), `WeakMatch` (distance-flagged matches above threshold),
  `PolicyRiskMapping` references, and `framework_coverage` counts. Serialized as
  `{slug}-risk-landscape.yaml` alongside the domain context document.

- **KnowledgeBaseRef model** — Provenance tracking for the knowledge graph state used during a run:
  nexus commit hash, risk count, ontology index hash, per-domain class counts, and indexing
  timestamp. Attached to both `DomainContextDocument` and `RiskLandscape` as an optional
  `knowledge_base` field.

- **`build_risk_landscape()` pure function** — New `refiner/stages/build_landscape.py` assembles a
  `RiskLandscape` from `map_risks()` outputs. Deduplicates risks across policy mappings, detects
  framework from risk ID prefixes (10 prefix patterns), flags weak matches above 0.6 distance
  threshold, and computes per-framework coverage counts. No LLM calls — pure data assembly.

- **Export layer** — New `refiner/export.py` wraps `structure()` with a `RiskLandscape`-aware API
  (`export_taxonomy()`). Extracts `risk_mappings`, `related_risks`, and `valid_risk_ids` from the
  landscape when provided. Taxonomy generation is now an export/projection of the domain context
  document, not a pipeline stage. Re-exports `slugify` for CLI use.

- **Independent CLI commands** — Two new commands for stage-level execution:
  - `refiner map-risks <policy-file>`: PolicyDocument → RiskLandscape YAML (runs identify_domains +
    map_risks + build_landscape, stops before ontology grounding)
  - `refiner ground <landscape> <policy-file>`: RiskLandscape + PolicyDocument → DomainContextDocument
    + taxonomy YAML (runs anchor + contextualize + export from a pre-built landscape)

- **PipelineState resolver properties** — Four `@property` methods (`risk_mappings_resolved`,
  `risk_details_resolved`, `risk_actions_resolved`, `related_risks_resolved`) that extract data from
  `risk_landscape` when the legacy cache fields are `None`. Enables backward-compatible access while
  the canonical source moves to `RiskLandscape`.

### Changed

- **Convergence-divergence diamond pattern** — Pipeline data flow restructured around two hub
  artifacts: `RiskLandscape` (risk identification convergence) and `DomainContextDocument` (ontology
  grounding convergence). Everything before `build_landscape` converges into `RiskLandscape`;
  everything after diverges into domain context and taxonomy projections. Each stage consumes
  serialized artifacts and produces new serializable artifacts, enabling independent tool extraction.

- **`anchor()` accepts `RiskLandscape`** — Optional `risk_landscape` parameter; when provided,
  `risk_mappings` and `risk_details` are extracted from it, making the dict parameters optional.

- **`contextualize()` accepts `RiskLandscape`** — Optional `risk_landscape` parameter; when provided,
  `selected_domains`, `risk_details`, `run_slug`, and `timestamp` are extracted from it.

- **CLI serializes RiskLandscape** — Both full (`run`) and partial (`--until`) execution paths write
  `{slug}-risk-landscape.yaml`. `PolicySourceRef` attached from `PolicyDocument` context when
  available.

### Refactored

- **Taxonomy is an export, not a stage** — `structure()` is no longer called directly from the
  pipeline. `export_taxonomy()` in `refiner/export.py` provides the public API, accepting either
  a `RiskLandscape` or raw dicts. CLI imports changed from `refiner.stages.structure` to
  `refiner.export`.

## Gen 10

### Removed

- **Classify stage** — Removed the A/B/C/D policy type classification stage entirely. The LLM-assigned
  types (Safety/Confidentiality/Scope/Routing) were inconsistent across models for the same policy set,
  and the only structural consumer (taxonomy grouping in `structure.py`) was never read by downstream
  stages (emit, evaluate, redteam). Saves one LLM call per run. `identify_domains` and `map_risks` now
  take `list[Policy]` directly instead of `list[PolicyClassification]`. Taxonomy groups are now
  deterministic — grouped by policy concept (from input) rather than LLM-assigned type.

- **`PolicyClassification` model** — Removed from `models.py` along with `policy_type` field from
  `PolicyRiskMapping`.

- **Type distribution in reports** — Removed `type_distribution` event from pipeline reports,
  evaluation aggregation, and both HTML report templates.

- **`ai_users`, `ai_subjects`, `named_entities` fields** — Replaced by unified `stakeholders:
  list[Stakeholder]` on `PolicyDocument`. The LLM extraction model (`_SlimContext`) still extracts
  users/subjects/entities separately; `_build_document()` consolidates them into typed `Stakeholder`
  objects with AIRO role CURIEs (`airo:AIUser`, `airo:AISubject`). Named entities carry their
  original role string (e.g. "CEO"). HTML report template renders a single Stakeholders section
  with role tooltips.

- **`ai_systems` field** — Replaced by `governed_systems: list[GovernedSystem]`. Each governed system
  carries name, description, purpose, and AI Act risk level. `_build_document()` wraps extracted
  system names into `GovernedSystem` objects.

- **`governing_regulations` field** — Replaced by `regulations: list[RegulatoryReference]`. Each
  reference carries name, jurisdiction, and URI. `_build_document()` wraps extracted regulation
  names into `RegulatoryReference` objects.

### Changed

- **Decomposition propagated to emit and provenance** — `build_prompt()` now includes a
  "The policy governs this configuration" block with agent/activity/entity when the policy has a
  decomposition. JSONL output rows carry a `decomposition` field. The PROV-O provenance sidecar
  includes agent/activity/entity on each prompt triple.

- **Enrichment pass populates PolicyDecomposition** — The ingest enrichment prompt now asks the LLM
  to identify the agent (who acts), activity (what is done), and entity (what is acted upon) for each
  policy. When provided, these are stored as `Policy.decomposition` — an Agent/Activity/Entity triple
  following the Lewis et al. 2021 ontology vocabulary. No extra LLM call; the decomposition fields
  are part of the existing enrichment response model.

### Added

- **AIRO-grounded PolicyDocument envelope** — `PolicyDocument.organization` is now a typed
  `Stakeholder` (name + AIRO role CURIEs + description) instead of a bare string. A `@field_validator`
  coerces plain strings for backward compatibility with existing JSON policy files. `domain` default
  changed from `""` to `None` (absent vs empty distinction).

- **Envelope type definitions** — New models `Stakeholder`, `GovernedSystem`, `RegulatoryReference`
  define the AIRO-grounded governance context. `GovernedSystem` captures AI system purpose and risk
  level (AI Act classification). `RegulatoryReference` captures regulation name, jurisdiction, and URI.
  These are available for future use by downstream stages.

- **Policy decomposition model** — New `PolicyDecomposition` (agent/activity/entity triple) on
  `Policy.decomposition` captures the Activity-Entity-Agent configuration a policy constraint governs,
  following the Lewis et al. 2021 ontology vocabulary. Optional — populated by future enrichment steps.

- **AIRO typing in structured output** — Taxonomy entries, groups, and the taxonomy itself now carry
  `class_uri` fields using AIRO CURIEs (`airo:Risk`, `airo:RiskConcept`). Taxonomy YAML output includes
  a top-level `curie_map` dict (21 prefixes) so downstream consumers can expand CURIEs to full URIs.

- **Shared CURIE registry** — New `refiner/src/refiner/curie_registry.py` provides a canonical
  `CURIE_MAP` plus `expand_curie()` and `compact_uri()` utilities. Convention: CURIEs in data
  structures and outputs, labels in LLM prompts, curie_map sidecar for URI expansion.

- **Provenance propagated to JSONL output** — `SampledAxis` now carries `provenance`
  (generated/subclass/sibling) from the source `AxisEnumeration`, so the emit-stage JSONL preserves
  how each sampled instance was discovered.

- **Vocabulary concept on SampledAxis** — `DomainContextAxis` and `SampledAxis` now carry
  `vocabulary_concept` and `vocabulary_label` from the source `VariationAxis`. The AIRO/DPV bridge
  concept (e.g., `eu-aiact:AISubject`) that explains why an axis was selected now survives through
  contextualize and emit to the final JSONL output.

- **CURIE map sidecar** — `emit` writes a `dataset.curie_map.json` alongside `dataset.jsonl`,
  providing the prefix-to-URI mapping for all CURIEs used in outputs.

- **Axis derivation provenance** — New `AxisDerivation` model captures how each variation axis was
  discovered: source (structural/search), seed URI, navigation path, effective confidence, and search
  distance. Carried from anchor through contextualize to the domain-context YAML output. Previously
  this data was computed but dropped after LLM axis selection.

- **Provenance sidecar** — New `refiner/src/refiner/provenance.py` writes `provenance.jsonl`
  alongside `dataset.jsonl`. PROV-O-style triples (wasGeneratedBy, wasDerivedFrom, wasAssociatedWith,
  used, partOf) capture the full derivation chain: profile → axis → enumeration → prompt. Queryable
  with jq, semantically compatible with PROV-O JSON-LD export.

- **Per-stage timestamps** — Pipeline events now include `started_at`, `completed_at`, and `model`
  for each stage, enabling temporal reconstruction and agent attribution at the stage level.

- **Agent attribution on enumerations** — `AxisEnumeration.generated_by` records which LLM model
  produced each enumeration instance.

## Gen 9.3

### Added

- **OWL2Vec\*-style ontology projection** — New `ontoquery/src/ontoquery/owl2vec.py` module implements
  the core projection rules from Chen et al. (2021): SubClassOf taxonomy (with bidirectional reverse
  edges), existential/universal restrictions → property edges, domain+range combination, atomic and
  complex equivalences, and annotation literal edges. Works against the existing pyoxigraph/rdflib
  backend via the `_query_triples` adapter — no Java/JVM dependency.

- **Random walks and Word2Vec embeddings** — DeepWalk-style random walks over the projected graph,
  interleaving entities and predicates. Word2Vec (skip-gram) training via gensim produces per-URI
  embeddings that capture pure structural similarity. Validated with 6 structural assertions on a
  9-class test ontology: hierarchy depth, branch clustering, sibling proximity, and hierarchy vs.
  property link discrimination all confirmed.

- **Context-augmented ChromaDB embeddings** — `build_structural_context()` serializes each class's
  projected edges into text (e.g., `SubClassOf: Person. worksFor: Organization. HasSubClass: Manager`)
  and appends it to the ChromaDB document at index time. The existing transformer embedding model now
  captures structural signals alongside lexical ones — no additional model or training step required.
  Wired into `ontoquery index` CLI and passed through `index_classes` / `index_domain_classes`.

- **gensim optional dependency** — Added as `[embeddings]` extra in ontoquery (`uv sync --extra
  embeddings`). Requires Python ≤3.13 (gensim C extensions don't build on 3.14 yet). The projection
  and context-augmented indexing work without gensim; only `train_embeddings()` / `owl2vec_embed()`
  require it.

## Gen 9.2 

### Added

- **BFO category fallback via SSSOM** — New `refiner/data/ontology-to-bfo.sssom.tsv` (63 mappings)
  maps domain ontology classes without BFO ancestry (CSO, LKIF, FIBO, Commons, OBO) to BFO categories.
  `derive_bfo_category()` uses these as fallback when the superclass walk returns empty. Projected
  coverage: 23% → ~88% of axes. Added `load_bfo_fallbacks()` loader in `ontology_seeds.py`, threaded
  through pipeline → anchor via `bfo_fallbacks` parameter.

- **Hard/soft red flag tiers** — Red flag patterns split into hard (overt jailbreak: `pretend you are`,
  `ignore previous instructions`, `jailbreak`, etc.) and soft (hedging language: `hypothetically`,
  `for educational purposes`, `as a test`, etc.). `compute_adversarial_metrics()` returns `red_flag_hard`
  and `red_flag_soft` alongside total `red_flag_count`. Combined report shows separate counts with
  distinct colors (red for hard, amber for soft). Explorer badges and modal detail view updated.
  g9.1 battery retroactively analyzed: 1 hard red flag, 39 soft across 3,030 prompts.

- **Technique diversity in evaluation output** — `compute_technique_diversity()` now wired into
  `run_evaluation()`. Shannon entropy, normalized entropy, and per-risk technique counts appear in
  the evaluation JSON under `generation_metrics.technique_diversity`.

- **Technique diversity card in combined report** — New card in Evaluation → Generation Metrics
  showing normalized entropy (color-coded), Shannon entropy in bits, and per-risk technique counts
  sorted ascending with coverage color coding.

- **Technique filter in explorer** — Dropdown filter in explorer sidebar filters prompts by
  adversarial technique frame.

### Fixed

- **Process Prohibition bypass via search path** — `constrained_search()` in anchor stage was not
  applying `_is_excluded_uri()` filter, allowing Process Prohibition to enter via ChromaDB semantic
  search even though the structural navigation path correctly excluded it. Added
  `generic_safety_uris` parameter and exclusion check. Eliminates the 10 residual Process
  Prohibition samples in DHS-Gov Mistral.

- **3 missing CCO URIs in `_BFO_CATEGORIES`** — Person (`ont00001262`), Organization (`ont00001180`),
  and Resource (`ont00000740`) were not in the BFO category mapping, causing 510 axes across the
  battery to miss BFO category assignment despite having direct CCO ancestry.

- **Combined report rendering issues** — Fixed 5 issues: (1) `candidate_expansion` and
  `query_source_contribution` rendered as empty stage quality cards — filtered from iteration.
  (2) 100% enumeration domain mismatch misleading for LLM-generated enumerations — replaced with
  informational "100% LLM-generated" block. (3) Empty role distribution — replaced with technique
  distribution (indigo badges), roles kept as conditional legacy. (4) `[object Object]` in Policy →
  named entities — fixed to render `{name, role}` objects correctly. (5) "Relevance Profile" and
  "Min Roles" renamed to "Axis Relevance" and "Min Axes".

## Gen 9.1

### Added

- **Multi-frame adversarial technique system** — Emit stage now selects from 5 adversarial technique
  frames instead of producing homogeneous pretexting prompts. Each frame provides a distinct social
  engineering strategy with soft LLM guidance (description paragraph + example prompts, not hard
  templates). Frames: `pretexting` (professional identity), `narrative_framing` (fiction/case study
  distancing), `analytical_reframing` (research/audit positioning), `delegated_authority` (urgency +
  chain of command), `comparative_benchmark` (harmful content as test data). Cross-validated against
  Galtea (26K prompts) and TUD-ARTS (282 prompts, 6 attack techniques) external datasets to confirm
  these families cover the observed attack surface beyond our own generation bias.

- **Ontology-grounded slot labels** — Each frame maps BFO categories to frame-specific human-readable
  labels (e.g., pretexting maps `Role`→"professional role", delegated_authority maps `Agent`→"authority
  figure"). When `bfo_category` is populated on a sampled axis, the scenario line uses the slot label
  (`- professional role: Financial Analyst (a type of Person)`) instead of the generic role prefix.
  Falls back to plain format when `bfo_category` is empty (~78% of current axes). As upstream SSSOM
  seed coverage improves, slot labels become more effective automatically.

- **Configurable technique distribution** — Frame selection uses weighted random choice with optional
  risk affinity boosting (2x weight when risk name/description matches frame keywords). Default:
  uniform across all 5 frames. Override via `--technique-weights` CLI option (JSON string) or
  `technique_weights` in `battery.yaml`. Affinity examples: fraud risks boost pretexting, bias risks
  boost analytical_reframing, privacy risks boost delegated_authority.

- **Technique diversity metrics** — `compute_technique_diversity()` in evaluate returns Shannon entropy,
  normalized entropy (0–1), per-technique counts, and per-risk unique technique counts. Also added
  `technique_distribution` to `compute_generation_metrics()` for backward-compatible technique counting
  (rows without `technique` field default to `"pretexting"`).

- **Technique metadata in emit output** — Each dataset.jsonl row now includes `technique` (frame name)
  and `technique_description` (frame description paragraph) fields.

### Fixed

- **`bfo_category` not propagated to SampledAxis** — Pre-existing gap: `bfo_category` existed on both
  `DomainContextAxis` and `SampledAxis` models but was never copied in `sample_axes()`. Added
  `bfo_category=axis.bfo_category` to the SampledAxis constructor. This was a prerequisite for slot
  labels to work.

## Gen 8.4

### Fixed

- **Garbled role prefix in generation prompts** — Since g8.1 removed the role system, every scenario
  line in the emit stage produced `- : a {label}` instead of `- {label}`. The empty `roles` list
  generated a dangling colon prefix on every generation prompt across the entire battery. Now omits
  the role prefix when `sa.roles` is empty.

- **CCO Process Prohibition excluded from candidate pools** — CCO Process Prohibition (`ont00000553`)
  and Process Requirement (`ont00001223`) are normative meta-concepts that describe "the act of
  prohibiting/requiring something" rather than substantive risk dimensions. They appeared as axes in
  11 profiles across RDaSH and DHS-Gov g8.3 runs. Added to `_is_excluded_uri` via `_CCO_NORMATIVE_URIS`.

### Added

- **Dedup saturation warnings** — Evaluation summary now warns when any risk reaches ≥70% dedup
  saturation (combinatorial space near-exhaustion), showing the risk ID, saturation percentage, and
  samples/space ratio.

- **Combined report contextual help** — Every section, metric, and badge in the combined HTML report
  now has tooltip explanations accessible on hover. Each tab (Evaluation, Explorer, Domain Context,
  Taxonomy, Policy) has a collapsible "Reading guide" that explains the tab's purpose, terminology,
  and how to interpret the data. Judge evaluation dimensions (subtlety, plausibility, domain grounding,
  policy relevance) have individual tooltips explaining the 1-5 scale. Intended for reviewers who are
  not familiar with the pipeline internals.

## Gen 8.3 — Multi-Taxonomy SSSOM Coverage

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

### Fixed

- **Slash characters in risk IDs causing debug file crash** — AI Risk Taxonomy risk IDs containing
  `/` (e.g., `ai-risk-taxonomy-phishing/catfishing`) caused `FileNotFoundError` in debug file
  writing. Slug generation now replaces `/` with `-`.

- **Contextualize debug.md rendering** — `_render_contextualize_response` expected the old
  `axes[].enumerations[]` response format. Updated to handle the current `variations[].{instance,
  relevance}` format with legacy fallback.

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


