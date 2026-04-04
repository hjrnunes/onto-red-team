# Changelog

All notable changes to this project will be documented in this file.

## Gen 7 (current)

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


