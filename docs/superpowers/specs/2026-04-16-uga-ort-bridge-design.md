# UGA–ORT Semantic Bridge Design

**Date:** 2026-04-16  
**Status:** Draft  
**Context:** [UGA Paper Analysis](obsidian://open?vault=Red%20Hat&file=Red%20Hat%2FOnto%20Red-Teaming%2FUGA%20Paper%20Analysis%20%E2%80%94%20From%20Intent%20to%20AI%20Governance)

---

## Problem

UGA (Usage Governance Advisor, Daly et al. 2024) and ORT (Onto Red-Teaming / Taxonomy Refiner) operate on complementary phases of the AI governance lifecycle:

- **UGA**: intent → risk assessment → model selection → guardrail recommendation (pre-deployment)
- **ORT**: policy → risk taxonomy → domain context → adversarial prompts → evaluation (validation)

Both systems consume the same knowledge graph (AI Atlas Nexus), use SKOS predicates for cross-taxonomy mappings, use SSSOM for mapping provenance, and ground stakeholders in AIRO roles. Despite this shared foundation, there is no formal specification of how data flows between them.

**Goal:** Define a semantic bridge — SSSOM mapping artifacts plus a projection specification — that:

1. Makes a UGA-captured use-case a valid ORT pipeline input (replacing hand-authored policy JSON)
2. Makes ORT's outputs interpretable by UGA (enabling guardrail validation and risk recalibration)
3. Keeps both systems independent — the bridge is metadata, not coupling

## Approach: SSSOM Bridge Artifacts

The bridge follows the same pattern both systems already use for risk cross-mappings: SSSOM files with SKOS predicates and provenance metadata. No schema changes to either system.

**Why not extend the nexus LinkML schema?** The nexus is IBM-maintained. Adding ORT-specific classes would couple ORT's evolution to the nexus release cycle and require upstream buy-in. The bridge approach works with the nexus as-is.

**Why not JSON-LD?** Both systems already serialize to YAML/JSON. JSON-LD would add boilerplate without practical benefit — neither system requires SPARQL access, and LinkML's known limitation with nested `@type` directives would cause friction.

## Bridge Structure

Three artifacts, co-located with ORT's existing SSSOM files:

```
refiner/data/
  risk-to-vocabulary.sssom.tsv          # existing Layer 1
  vocabulary-to-ontology.sssom.tsv      # existing Layer 2
  ontology-to-bfo.sssom.tsv            # existing Layer 3
  uga-to-ort.sssom.tsv                 # new — input projection
  ort-to-uga.sssom.tsv                 # new — output alignment
```

This spec (the prose projection specification) serves as the third artifact.

---

## Layer A: UGA → ORT Input Projection

Maps UGA's use-case output (AiSystem + Questionnaire responses + Risk assessment) onto ORT's `PolicyProfile` input schema.

### Direct Mappings

| UGA (nexus LinkML) | SKOS Predicate | ORT (Pydantic) | Confidence | Notes |
|---|---|---|---|---|
| `AiSystem.name` | `skos:exactMatch` | `GovernedSystem.name` | 0.95 | |
| `AiSystem.description` | `skos:exactMatch` | `GovernedSystem.description` | 0.95 | |
| `AiSystem.hasPurpose` | `skos:exactMatch` | `GovernedSystem.purpose` | 0.95 | |
| `AiSystem.hasEuRiskCategory` | `skos:closeMatch` | `GovernedSystem.risk_level` | 0.80 | UGA: EU AI Act categories; ORT: high/limited/minimal/unclassified. Requires value normalization. |
| `AiSystem.isDevelopedBy` | `skos:exactMatch` | `PolicyProfile.organization` (role: `airo:AIProvider`) | 0.90 | |
| `AiSystem.isDeployedBy` | `skos:exactMatch` | `Stakeholder` (role: `airo:AIDeployer`) | 0.90 | |
| `AIUser` | `skos:exactMatch` | `Stakeholder` (role: `airo:AIUser`) | 0.95 | Same AIRO class |
| `AISubject` | `skos:exactMatch` | `Stakeholder` (role: `airo:AISubject`) | 0.95 | Same AIRO class |
| `AiSystem.isAppliedWithinDomain` | `skos:closeMatch` | `PolicyProfile.domain` | 0.75 | UGA: structured enum; ORT: free text string |
| `RiskControl` | `skos:relatedMatch` | `Policy.risk_controls` | 0.70 | UGA: structured entity with `hasRelatedAction`; ORT: string list |
| `Action.description` | `skos:closeMatch` | `Policy.risk_controls[]` | 0.80 | UGA's action descriptions map to ORT's control strings |
| `Prohibition` | `skos:closeMatch` | `Policy` | 0.75 | UGA's governance rules map to ORT policy concepts |
| `Obligation` | `skos:closeMatch` | `Policy` | 0.75 | |
| `AiSystem.hasRelatedRisk → Risk` | `skos:broadMatch` | `Policy.policy_concept` | 0.70 | Key semantic gap — see projection logic below |

### Risk → Policy Projection

UGA outputs prioritized `Risk` entities (with severity: High/Medium/Low). ORT expects `Policy` objects (`policy_concept` + `concept_definition`). These aren't equivalent — a risk describes what can go wrong; a policy describes what's prohibited.

**Projection logic:**

1. **Default:** Use `Risk.concern` as `Policy.concept_definition`. The concern field exists for every nexus risk and reads like a policy statement (e.g., "An AI model may generate content that could be used to manipulate individuals into revealing sensitive information").
2. **With questionnaire context:** When UGA provides filled questionnaire responses, use them to contextualize the risk into a domain-specific policy definition via a lightweight LLM pass.
3. **Mapping:** `Risk.name` → `Policy.policy_concept`, `Risk.concern` → `Policy.concept_definition`.

**Severity → Relevance:** UGA's High/Medium/Low severity does not map directly to ORT's primary/supporting/tangential relevance (which is determined by ORT's own risk matching). However, UGA severity can be carried as metadata to inform downstream prioritization — e.g., emit more prompts for High-severity risks.

### Cardinality Differences

| Aspect | UGA | ORT | Resolution |
|---|---|---|---|
| AI systems | Single `AiSystem` per use-case | `list[GovernedSystem]` | Wrap single system in list |
| Stakeholders | Class hierarchy (`AISubject`, `AIOperator` → `AIDeployer`, `AIDeveloper`, `AIUser`) | Flat `list[Stakeholder]` with role CURIEs | Flatten hierarchy, assign role CURIEs |
| Risks | `AiSystem.hasRelatedRisk` (multivalued) | `list[Policy]` (each with concept + definition) | One Policy per risk, projected via concern field |
| Regulations | Implicit via `hasEuAiSystemType`, `hasEuRiskCategory` | Explicit `list[RegulatoryReference]` | Extract from EU AI Act classification |

### What Doesn't Map (UGA → ORT)

These UGA elements have no ORT input equivalent:

- `AiSystem.isComposedOf` — model inventory/architecture. ORT tests behavior, not architecture.
- `AiEvalResult` / benchmark scores — ORT doesn't consume pre-existing evaluations as input.
- `LargeLanguageModel` intrinsics (numParameters, contextWindowSize) — irrelevant to adversarial prompt generation.
- `AiSystem.hasCapability` — ORT doesn't reason about model capabilities.

These are not semantic gaps to fix — they reflect the systems' different concerns. ORT tests policies, not models.

---

## Layer B: ORT → UGA Output Alignment

Maps ORT's outputs onto nexus schema classes. Where no nexus equivalent exists, the entry is omitted — the bridge exposes what aligns and explicitly documents what doesn't.

### RiskLandscape → nexus Risk

| ORT Output | SKOS Predicate | Nexus Class | Confidence | Notes |
|---|---|---|---|---|
| `RiskDetail.risk_id` | `skos:exactMatch` | `Risk.id` | 0.95 | Same identifiers — both sourced from nexus |
| `RiskDetail.risk_name` | `skos:exactMatch` | `Risk.name` | 0.95 | |
| `RiskDetail.cross_mappings` | `skos:exactMatch` | `Risk.related_mappings` / `exact_mappings` | 0.95 | Same SSSOM source |
| `RiskDetail.related_actions` | `skos:exactMatch` | `Risk.hasRelatedAction → Action` | 0.95 | Same data from same KG |
| `PolicyRiskMapping.relevance` | — | No equivalent | — | New information: primary/supporting/tangential classification |
| `PolicyRiskMapping.distance` | `skos:relatedMatch` | `AiEvalResult.value` (via `Fact`) | 0.70 | Semantic distance expressible as evaluation result |
| `WeakMatch` | — | No equivalent | — | Coverage gap signal — new for UGA |
| `RiskLandscape.framework_coverage` | `skos:relatedMatch` | Derivable from `Risk.isDefinedByTaxonomy` | 0.65 | Aggregate; nexus tracks per-risk |

### Evaluation → nexus AiEvalResult

| ORT Output | SKOS Predicate | Nexus Class | Confidence | Notes |
|---|---|---|---|---|
| Judge: `subtlety` score | `skos:closeMatch` | `AiEvalResult` (extends `Fact`) | 0.80 | `value` = score, `evidence` = judge rationale |
| Judge: `plausibility` score | `skos:closeMatch` | `AiEvalResult` | 0.80 | |
| Judge: `domain_grounding` score | `skos:closeMatch` | `AiEvalResult` | 0.80 | |
| Judge: `policy_relevance` score | `skos:closeMatch` | `AiEvalResult` | 0.80 | |
| Coverage: `risks_matched` | `skos:relatedMatch` | `AiEvalResult` | 0.65 | Aggregate metric |
| Coverage: `axes_with_enumerations` | — | No equivalent | — | ORT-specific |
| Prompt metrics: `semantic_diversity` | `skos:relatedMatch` | `AiEvalResult` | 0.60 | Expressible but no existing eval type matches |
| Prompt metrics: `jargon_leak_rate` | — | No equivalent | — | ORT-specific quality signal |
| Prompt metrics: `axis_fidelity` | — | No equivalent | — | ORT-specific |

### Emitted Prompts → nexus Fact

| ORT Output | SKOS Predicate | Nexus Class | Confidence | Notes |
|---|---|---|---|---|
| `EmittedPrompt` (full prompt) | `skos:broadMatch` | `Fact.value` | 0.60 | Generated artifact with provenance |
| `EmittedPrompt.risk_id` | `skos:exactMatch` | `Risk.id` | 0.95 | Links back to nexus risk |
| `EmittedPrompt.cross_mappings` | `skos:exactMatch` | `Risk.related_mappings` | 0.95 | Carried through from input |
| `EmittedPrompt.technique` | — | No equivalent | — | Adversarial technique taxonomy (ORT-specific) |
| `EmittedPrompt.sampled_axes` | — | No equivalent | — | Ontological grounding (ORT-specific) |

### DomainContext → Linked Artifact (Not Structurally Mapped)

ORT's DomainContext (axes, enumerations, BFO categories, vocabulary context, derivation paths) has no structural counterpart in the nexus schema. The ontological grounding is deeply ORT-specific.

**Convention:** DomainContext is referenced by URI from the bridge output, not mapped class-by-class. The YAML artifact is available for consumers that understand ORT's model (e.g., a future feedback pipeline). Individual axes can optionally be projected as nexus `Term` entries when lightweight cross-referencing is sufficient:

- `DomainContextAxis.cco_class_uri` → `Term.id`
- `DomainContextAxis.cco_class_label` → `Term.name`
- SKOS mappings linking the term to the risk it grounds

This is an enrichment, not a requirement.

### What's Genuinely New for UGA

These ORT outputs have no nexus schema equivalent. They represent new information that the bridge surfaces but cannot map:

- **`PolicyRiskMapping.relevance`** (primary/supporting/tangential) — risk prioritization beyond UGA's H/M/L severity
- **`WeakMatch`** — risks below the matching threshold that may indicate coverage gaps
- **Variation axes and enumerations** — ontological grounding of risks in domain-specific concepts
- **Prompt-level metrics** (jargon leak rate, axis fidelity, semantic diversity) — quality signals for generated adversarial content
- **Adversarial technique classification** — pretexting, authority impersonation, etc.

These are candidates for future nexus schema extension if the UGA–ORT integration matures.

---

## Closed-Loop Governance Cycle

The bridge enables the following data flow:

```
UGA Phase                          Bridge                         ORT Phase
─────────────────────────────────────────────────────────────────────────────

1. User describes intent           
   "medical triage chatbot"        
                                   
2. UGA auto-fills questionnaire    
   → AiSystem, Stakeholders,      
     Risk priorities (H/M/L)       
                                   
3. UGA recommends guardrails       
   → RiskControl, Action entities  
                                   uga-to-ort.sssom.tsv
                                   + Risk.concern → Policy projection
                                   ─────────────────────►
                                                          4. ORT ingests as PolicyProfile
                                                             (no hand-authored JSON needed)
                                                          
                                                          5. ORT runs pipeline:
                                                             map_risks → anchor →
                                                             contextualize → emit
                                                          
                                                          6. ORT evaluates:
                                                             coverage, judge scores,
                                                             guardrail pass/fail
                                   ort-to-uga.sssom.tsv
                                   + DomainContext linked by URI
                                   ◄─────────────────────
7. UGA consumes results:           
   a. Risk relevance signals       
      (primary/supporting/         
       tangential + weak matches)  
      → recalibrate severity       
                                   
   b. Judge scores                 
      (subtlety, plausibility)     
      → empirical validation of    
        guardrail effectiveness    
                                   
   c. Coverage gaps                
      → risks UGA missed or        
        underweighted              
```

### What This Achieves

- UGA's intent capture replaces hand-authored policy JSON as ORT's front door
- ORT's adversarial testing validates UGA's guardrail recommendations empirically
- Both systems remain independent — the bridge is metadata, not coupling
- The nexus KG is the shared reference point (same risk IDs, same SKOS predicates, same SSSOM conventions)

### What This Does Not Achieve (Future Work)

- **Automated feedback loop** — requires runtime adapter code, not just mappings
- **UGA re-scoring** — requires UGA-side consumption logic for ORT evaluation results
- **Shared provenance chain** — each system tracks provenance independently; a unified chain would require a common provenance model (e.g., PROV-O)
- **Model-aware testing** — ORT tests policies, not models; connecting UGA's model inventory to ORT's prompt generation would require a new pipeline mode

## Shared Semantic Foundation

Both systems already share:

| Aspect | UGA | ORT | Bridge Role |
|---|---|---|---|
| Knowledge graph | AI Atlas Nexus (LinkML) | AI Atlas Nexus (handler dicts) | Same risk IDs, no translation needed |
| Risk identifiers | `Risk.id` (e.g., `atlas-social-engineering`) | `RiskDetail.risk_id` | Identity mapping |
| Cross-mappings | SKOS on `Entity` base class (5 predicates) | SSSOM files with SKOS predicates | Same vocabulary, same conventions |
| Stakeholder roles | AIRO class hierarchy (`AISubject`, `AIUser`, etc.) | AIRO CURIEs on `Stakeholder.roles` | Same ontology, different encoding |
| Mapping provenance | SSSOM with `semapv:` justifications | SSSOM with `semapv:` justifications | Same provenance vocabulary |
| Risk taxonomies | 10 frameworks, 600+ risks | Same 10 frameworks via nexus | Same source |

The bridge does not create semantic alignment — it documents the alignment that already exists and specifies the projection logic for the gaps (primarily Risk → Policy).

## SSSOM File Specifications

### `uga-to-ort.sssom.tsv` Header

```
# curie_map:
#   nexus: https://ibm.github.io/ai-atlas-nexus/
#   ort: https://taxonomy-refiner.io/schema/
#   airo: https://delaramglp.github.io/airo#
#   skos: http://www.w3.org/2004/02/skos/core#
#   semapv: https://w3id.org/semapv/vocab/
#
# mapping_set_id: uga-to-ort-input-projection
# mapping_set_description: Maps UGA use-case capture (AI Atlas Nexus LinkML schema) to ORT PolicyProfile input schema
# mapping_set_version: 0.1
# mapping_date: 2026-04-16
# mapping_tool: manual
# license: https://creativecommons.org/licenses/by/4.0/
```

### `ort-to-uga.sssom.tsv` Header

```
# curie_map:
#   ort: https://taxonomy-refiner.io/schema/
#   nexus: https://ibm.github.io/ai-atlas-nexus/
#   airo: https://delaramglp.github.io/airo#
#   skos: http://www.w3.org/2004/02/skos/core#
#   semapv: https://w3id.org/semapv/vocab/
#
# mapping_set_id: ort-to-uga-output-alignment
# mapping_set_description: Maps ORT pipeline outputs to AI Atlas Nexus LinkML schema classes for UGA consumption
# mapping_set_version: 0.1
# mapping_date: 2026-04-16
# mapping_tool: manual
# license: https://creativecommons.org/licenses/by/4.0/
```

## References

- Daly et al. (2024). "Usage Governance Advisor: From Intent to AI Governance." arXiv:2412.01957v2
- Daly et al. (2025). "AI Risk Atlas: Taxonomy and Tooling." arXiv:2503.05780v2
- IBM/ai-atlas-nexus: https://github.com/IBM/ai-atlas-nexus
- SSSOM: https://mapping-commons.github.io/sssom/
- AIRO: https://delaramglp.github.io/airo
- DPV: https://w3id.org/dpv
- LinkML: https://linkml.io
