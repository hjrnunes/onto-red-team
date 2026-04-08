# Ontology Integration Redesign: Structural Navigation with SSSOM Seed Mappings

**Date:** 2026-04-04
**Status:** Draft
**Scope:** Anchor stage, contextualize stage, ontology discovery mechanism, nexus integration

## Problem Statement

The current pipeline discovers ontology classes via ChromaDB semantic search over class labels+definitions, using risk description text as queries. This has fundamental limitations:

1. **Textual similarity is a weak proxy for semantic relevance.** FIBO financial classes contaminate healthcare runs (33% in gen8) because insurance/billing language in healthcare policies is textually close to FIBO class embeddings.
2. **The nexus risk knowledge graph's thematic structure is unused.** Risks are organized into RiskGroups (Privacy, Fairness, Robustness, etc.) that naturally map to ontology domains/branches, but this structure never informs which ontology classes are relevant.
3. **No provenance for candidates.** The LLM selecting axes sees candidates with distance scores but no explanation of *why* they're relevant to the risk.
4. **Enumeration via subclass hierarchies is brittle.** Leaf nodes produce sibling fallback monocultures, ontology depth is wildly uneven across domains, and subclass enumerations don't correspond to the variation that makes adversarial prompts diverse.

## Design Principles

From 8 generations of pipeline runs, we've learned:

- **Ontologies are a concept relevance engine, not a diversity engine.** Their value is in finding the right variation axes (semantic structure, class hierarchies, restrictions, domain organization), not in enumerating instances.
- **Diversity should come from policy content**, informed by LLM generation and constrained by knowledge graph attributes.
- **Ontology integration is a filtering problem.** The ontologies provide too much; success comes from context-aware scoping.
- **Prompt quality correlates with role diversity** (agent+instrument+object), not axis count.
- **Ground-truth cross-mappings** from the knowledge graph must never be LLM-generated.

## Architecture Overview

Replace the current `text search → merge strategy → LLM picks` flow with a hybrid approach:

```
Risk → isPartOf → RiskGroup → SSSOM seed mappings → ontology branch URIs
                                         ↓
              ┌──────────────────────────┼──────────────────────────┐
              │                          │                          │
    Structural Navigation      Constrained Search         Structural Proximity
    (primary: graph traversal   (complementary: ChromaDB   Check (for search
     from seed URIs)            scoped to seed domains)    candidates)
              │                          │                          │
              └──────────┬───────────────┘──────────────────────────┘
                         │
                  Tiered Candidate Pool
                  (structural > search-connected > search-only)
                         │
                  LLM selects 2-3 axes (with provenance)
                         │
              Policy-Driven LLM Enumeration
              (replaces subclass expansion)
```

## 1. SSSOM Seed Mappings

### Format

Risk-to-ontology mappings use the SSSOM (Simple Standard for Sharing Ontological Mappings) format, consistent with the nexus's existing risk-to-risk cross-taxonomy mappings.

```tsv
# curie_map:
#   ibm-risk-atlas: https://www.ibm.com/docs/en/watsonx/saas?topic=
#   cso: http://taxonomy-refiner.io/ontologies/cso#
#   d3f: http://d3fend.mitre.org/ontologies/d3fend.owl#
#   cco: https://www.commoncoreontologies.org/
#   obo: http://purl.obolibrary.org/obo/
#   lkif: http://www.estrellaproject.org/lkif-core/
#   fibo: https://spec.edmcouncil.org/fibo/ontology/
#   semapv: https://w3id.org/semapv/vocab/
#   skos: http://www.w3.org/2004/02/skos/core#
# mapping_set_id: risk-to-ontology-branches
# mapping_set_description: Maps AI risk concepts to domain ontology branches for structural navigation
# license: https://www.apache.org/licenses/LICENSE-2.0.html
subject_id	subject_label	predicate_id	object_id	object_label	mapping_justification	confidence
```

### Predicate Semantics

The SKOS predicate determines how the seed is navigated:

| Predicate | Meaning | Navigation strategy |
|-----------|---------|-------------------|
| `skos:broadMatch` | Seed is a parent branch of relevant classes | Navigate DOWN: `get_subclasses(seed, depth=2)` |
| `skos:relatedMatch` | Seed is laterally related | Navigate AROUND: `get_siblings()`, `get_restrictions()`, `get_properties()` |
| `skos:exactMatch` | Seed IS a relevant class | Use directly as candidate, no navigation needed |
| `skos:closeMatch` | Seed is nearly equivalent | Use directly + shallow navigation (depth=1) |

### Confidence as Weight

The `confidence` field (0.0-1.0) weights candidates during tiered merge:
- High confidence (>0.8): candidates from these seeds get Tier 1 priority
- Medium confidence (0.5-0.8): Tier 1 but lower priority within tier
- Low confidence (<0.5): treated as Tier 2 (search-connected level)

### Mapping Granularity

Mappings exist at two levels:

1. **RiskGroup level** — `subject_id` is a RiskGroup from any nexus taxonomy (e.g.,
   `ibm-risk-atlas-privacy`, `ai-risk-taxonomy-fraud`, `credo-rg-malicious-use`). Inherited by all
   risks in the group. This is the primary mapping level (~91 groups, ~257 SSSOM rows across 7
   taxonomies).
2. **Risk level** — `subject_id` is a specific risk (e.g., `atlas-exposing-personal-info`). Overrides
   or supplements group-level seeds for specific risks that need finer-grained ontology targeting.

Risk-level mappings supplement RiskGroup-level ones. When both exist for the same ontology branch,
the risk-level confidence takes precedence.

### Multi-Taxonomy Direct Mapping (replaces IBM hub-and-spoke)

> **Design change (gen 8.3):** The original design used IBM Risk Atlas RiskGroups as a canonical hub,
> with non-IBM risks resolving through nexus cross-taxonomy mappings to IBM equivalents. This was
> abandoned after g8.2 analysis revealed three structural failures:
>
> 1. **AI Risk Taxonomy entries have zero nexus cross-mappings** — 314 entries exist as isolated nodes
>    with no `exact_mappings`, `close_mappings`, or `related_mappings` to any taxonomy. Fixing this
>    nexus-side would require 300+ new mapping rows.
> 2. **Some non-IBM risks cross-map to other non-IBM taxonomies but not IBM** — e.g., Credo risks
>    mapped to Granite Guardian and MIT but not to `atlas-*` entries. The fallback filtered for
>    IBM-only (`rel_id.startswith("atlas-")`), so these non-IBM paths were ignored.
> 3. **Fallback took first IBM match and broke** — if the first `atlas-*` hit happened to be in an
>    unmapped IBM group (e.g., `ibm-risk-atlas-data-laws`), the resolution failed even though later
>    matches would have succeeded.
>
> These three modes accounted for all 32 zero-seed risks in g8.2 (25 + 4 + 1, plus 2 IBM risks in
> unmapped groups that the fallback never triggers for).

Layer 1 now maps RiskGroups directly from all 7 risk taxonomies in the nexus. Thematically similar
groups across taxonomies share the same AIRO/DPV vocabulary concepts:

| Theme | Example groups | Shared vocabulary |
|-------|---------------|-------------------|
| Privacy & data | ibm-risk-atlas-privacy, ai-risk-taxonomy-privacy-violations/*, credo-rg-privacy | pd:Biometric, pd:MedicalHealth, eu-rights:T2-DataProtection |
| Fraud & crime | ibm-risk-atlas-misuse, ai-risk-taxonomy-fraud, credo-rg-malicious-use, mit-ai-risk-domain-4 | risk:Threat, sector-law:CriminalLawEnforcement |
| Discrimination | ibm-risk-atlas-fairness, ai-risk-taxonomy-discrimination/*, mit-ai-risk-domain-1 | pd:EthnicOrigin, pd:Gender, eu-rights:T3-Equality |
| System safety | ibm-risk-atlas-robustness, ai-risk-taxonomy-integrity, credo-rg-security, mit-ai-risk-domain-7 | risk:Vulnerability, risk:Threat, eu-aiact:AIProvider |

The cross-taxonomy fallback via `get_related_risks` is retained as a safety net but is no longer the
primary resolution path for non-IBM risks.

**Coverage by taxonomy:** IBM Risk Atlas (16 groups), AI Risk Taxonomy (44), Credo (13), MIT AI Risk
Repository (10), AILuminate (3), Granite Guardian (4), ShieldGemma (1).

### Two-Layer Architecture

The actual implementation splits the original single-layer risk→ontology mapping into two layers
via an intermediate AIRO/DPV vocabulary:

```
Layer 1: RiskGroup → AIRO/DPV vocabulary    (risk-to-vocabulary.sssom.tsv)
Layer 2: AIRO/DPV → Domain ontology classes  (vocabulary-to-ontology.sssom.tsv)
```

**Layer 1** maps risk groups to regulatory/AI vocabulary concepts (EU AI Act stakeholders, DPV
personal data categories, DPV rights and risk concepts, sector-specific purposes). These provide
both structured LLM context and act as keys into Layer 2.

**Layer 2** maps vocabulary concepts to domain ontology branch URIs for structural navigation
(CCO Person, OMRSE Human Social Role, HANCESTRO Ancestry, CSO DangerousInformation, etc.).

This indirection means adding a new risk group to Layer 1 automatically inherits all existing
ontology paths from Layer 2 — no need to manually specify ontology URIs for each new group.

### Example Layer 1 Mappings (risk-to-vocabulary.sssom.tsv)

```tsv
# IBM Risk Atlas group
ibm-risk-atlas-privacy	Privacy	skos:relatedMatch	pd:Biometric	Biometric	semapv:ManualMappingCuration	0.90
ibm-risk-atlas-privacy	Privacy	skos:relatedMatch	pd:MedicalHealth	Medical Health	semapv:ManualMappingCuration	0.85
ibm-risk-atlas-privacy	Privacy	skos:relatedMatch	eu-rights:T2-DataProtection	Data Protection	semapv:ManualMappingCuration	0.90
# AI Risk Taxonomy group (shares vocabulary with IBM Privacy)
ai-risk-taxonomy-privacy-violations/sensitive-data-combinations	Privacy Violations	skos:relatedMatch	pd:Biometric	Biometric	semapv:ManualMappingCuration	0.90
ai-risk-taxonomy-privacy-violations/sensitive-data-combinations	Privacy Violations	skos:relatedMatch	pd:MedicalHealth	Medical Health	semapv:ManualMappingCuration	0.85
ai-risk-taxonomy-privacy-violations/sensitive-data-combinations	Privacy Violations	skos:relatedMatch	eu-rights:T2-DataProtection	Data Protection	semapv:ManualMappingCuration	0.90
# Credo group (fraud theme)
credo-rg-malicious-use	Malicious Use	skos:relatedMatch	risk:Threat	Threat	semapv:ManualMappingCuration	0.90
credo-rg-malicious-use	Malicious Use	skos:relatedMatch	sector-law:CriminalLawEnforcement	Criminal Law Enforcement	semapv:ManualMappingCuration	0.85
```

### Example Layer 2 Mappings (vocabulary-to-ontology.sssom.tsv)

```tsv
pd:Biometric	Biometric	skos:relatedMatch	cco:ont00001262	Person	semapv:ManualMappingCuration	0.80
eu-rights:T2-DataProtection	Data Protection	skos:broadMatch	cso:PrivacyViolation	Privacy Violation	semapv:ManualMappingCuration	0.90
risk:Threat	Threat	skos:broadMatch	cso:DangerousInformation	Dangerous Information	semapv:ManualMappingCuration	0.90
risk:Threat	Threat	skos:broadMatch	cso:FraudAndDeception	Fraud and Deception	semapv:ManualMappingCuration	0.85
```

### Seed Resolution Algorithm

```python
def resolve_seeds(risk_id, risk_group_id, nexus_handlers, layer1_mappings, layer2_mappings):
    """Two-layer SSSOM seed resolution with cross-taxonomy fallback."""
    vocab_seeds = []

    # 1. Direct risk-level vocabulary seeds
    vocab_seeds += layer1_mappings.get_by_subject(risk_id)

    # 2. RiskGroup-level vocabulary seeds
    if risk_group_id:
        vocab_seeds += layer1_mappings.get_by_subject(risk_group_id)

    # 3. Cross-taxonomy fallback (safety net, rarely needed with full Layer 1)
    if not vocab_seeds and not risk_id.startswith("ibm-risk-atlas"):
        related = nexus_handlers["get_related_risks"](risk_id)
        for rel in related:
            if rel["id"].startswith("atlas-"):
                ibm_group = nexus_handlers["get_risk_details"](rel["id"])["group"]
                vocab_seeds += layer1_mappings.get_by_subject(ibm_group)
                break

    # Chain through Layer 2: vocabulary → ontology branches
    ontology_seeds = []
    for vs in vocab_seeds:
        for hit in layer2_mappings.get_by_subject(vs.object_id):
            ontology_seeds.append({...hit, effective_confidence: vs.confidence * hit.confidence})

    # Build structured vocabulary context for LLM prompt
    vocabulary_context = categorize_vocabulary(vocab_seeds)

    return vocabulary_context, deduplicate_seeds(ontology_seeds)
```

## 2. Structural Navigation (Primary Discovery)

### Algorithm

```python
def navigate_from_seeds(seed_mappings, onto_handlers, selected_domains):
    candidates = []
    for mapping in seed_mappings:
        seed_uri = mapping.object_id
        predicate = mapping.predicate_id
        confidence = mapping.confidence

        if predicate == "skos:broadMatch":
            # Navigate DOWN — seed is an ancestor
            discovered = onto_handlers["get_subclasses"](seed_uri, depth=2)
            for cls in discovered:
                candidates.append({
                    "uri": cls["uri"],
                    "label": cls["label"],
                    "source": "structural",
                    "path": build_path(seed_uri, cls),
                    "seed_uri": seed_uri,
                    "seed_confidence": confidence,
                    "predicate": predicate,
                })

        elif predicate == "skos:relatedMatch":
            # Navigate AROUND — seed is laterally related
            for r in onto_handlers["get_restrictions"](seed_uri):
                filler = r.get("filler", "")
                if filler and is_valid_candidate(filler, onto_handlers, selected_domains):
                    candidates.append({...with restriction provenance...})
            for s in onto_handlers["get_siblings"](seed_uri):
                if is_valid_candidate(s["uri"], onto_handlers, selected_domains):
                    candidates.append({...with sibling provenance...})
            # The seed itself is also a candidate
            candidates.append({...seed as direct candidate...})

        elif predicate in ("skos:exactMatch", "skos:closeMatch"):
            # Use directly + optional shallow navigation
            candidates.append({...seed as direct candidate...})
            if predicate == "skos:closeMatch":
                for sub in onto_handlers["get_subclasses"](seed_uri, depth=1):
                    candidates.append({...})

    # Domain filter, BFO/LKIF exclusion (reuse existing _is_excluded_uri)
    candidates = [c for c in candidates
                  if not _is_excluded_uri(c["uri"], generic_safety_uris)
                  and derive_source_ontology(c["uri"]) in selected_domains]

    return candidates
```

### Path Tracking

Every structurally-navigated candidate carries its derivation path:

```python
{
    "uri": "cso:CreditScoreExposure",
    "label": "Credit Score Exposure",
    "source": "structural",
    "path": ["cso:PrivacyViolation", "cso:FinancialDataExposure", "cso:CreditScoreExposure"],
    "path_labels": ["Privacy Violation", "Financial Data Exposure", "Credit Score Exposure"],
    "seed_uri": "cso:PrivacyViolation",
    "seed_confidence": 0.95,
    "predicate": "skos:broadMatch",
    "roles": ["object"],  # from derive_roles()
}
```

### Depth Control

- Start at depth=2 per `broadMatch` seed
- If total structural candidates < 3: increase depth to 3 for highest-confidence seeds
- If total structural candidates > 20: prune by shortest path first, then role diversity, then seed confidence
- `relatedMatch` seeds don't use depth — they navigate restrictions and siblings only

## 3. Constrained Search (Complementary Discovery)

### Scoping

ChromaDB search is scoped to domains containing the seed URIs, not all selected domains:

```python
def constrained_search(risk_description, seed_mappings, onto_handlers, selected_domains):
    seed_domains = {derive_domain(m.object_id) for m in seed_mappings}
    search_domains = list(seed_domains & set(selected_domains))

    queries = []
    queries.append((risk_description, "description"))
    # Also search using seed class labels (finds classes related to seeds)
    for m in seed_mappings:
        defn = onto_handlers["get_class_definition"](m.object_id)
        if defn and defn.get("label"):
            queries.append((defn["label"], "seed_label"))

    return search_per_domain(queries, onto_handlers, search_domains, top_k=8)
```

### Structural Proximity Check

For each search result not already found structurally, check whether it shares a common ancestor with any seed URI within 3 hops:

```python
def check_structural_connection(candidate_uri, seed_uris, onto_handlers, max_hops=3):
    candidate_ancestors = walk_superclasses(candidate_uri, onto_handlers, max_hops)
    for seed_uri in seed_uris:
        seed_ancestors = walk_superclasses(seed_uri, onto_handlers, max_hops)
        common = candidate_ancestors & seed_ancestors
        if common:
            return {"connected": True, "common_ancestor": next(iter(common))}
    return {"connected": False}
```

## 4. Tiered Candidate Pool

Three tiers with decreasing confidence:

| Tier | Source | Provenance | Priority |
|------|--------|-----------|----------|
| 1 | Structural navigation | Full derivation path from seed | Highest — included up to 8 |
| 2 | Search + structurally connected | Distance score + common ancestor with seed | Medium — fill to 10 |
| 3 | Search only, no structural connection | Distance score only | Lowest — fill to 12 |

Tier 3 candidates are kept (not discarded) because they may represent genuine ontology gaps — relevant classes not reachable from any seed. When a Tier 3 candidate is selected by the LLM, it's logged as a **curation signal** for future seed mapping.

### Merge Logic

```python
def merge_tiered(structural, search_connected, search_only, max_total=12):
    result = []
    seen = set()

    # Tier 1: structural candidates, sorted by seed confidence then path length
    for c in sorted(structural, key=lambda c: (-c["seed_confidence"], len(c["path"]))):
        if c["uri"] not in seen and len(result) < 8:
            result.append(c)
            seen.add(c["uri"])

    # Tier 2: search-connected, sorted by distance
    for c in sorted(search_connected, key=lambda c: c.get("best_distance", 1.0)):
        if c["uri"] not in seen and len(result) < 10:
            result.append(c)
            seen.add(c["uri"])

    # Tier 3: search-only, sorted by distance
    for c in sorted(search_only, key=lambda c: c.get("best_distance", 1.0)):
        if c["uri"] not in seen and len(result) < max_total:
            result.append(c)
            seen.add(c["uri"])

    # Role diversity check: ensure at least 2 role types represented
    roles_present = {r for c in result for r in c.get("roles", [])}
    if len(roles_present) < 2:
        # Scan all tiers for candidates with missing roles, promote up to 2
        missing_roles = {"agent", "object", "instrument"} - roles_present
        all_remaining = [c for pool in [structural, search_connected, search_only]
                         for c in pool if c["uri"] not in seen]
        for c in all_remaining:
            c_roles = set(c.get("roles", []))
            if c_roles & missing_roles:
                result.append(c)
                seen.add(c["uri"])
                roles_present |= c_roles
                if len(roles_present) >= 2:
                    break

    return result
```

## 5. LLM Prompt Format (Anchor)

The LLM sees candidates with explicit provenance:

```
Risk: Unauthorized PII disclosure
Description: Risk of personally identifiable information being exposed...
Concern: PII leakage via model outputs or training data extraction
Policy: Do not disclose personal health information

Candidate classes:

## C1: CreditScoreExposure [object] -- structural
Definition: Exposure of credit score data to unauthorized parties
Path: Privacy Violation > Financial Data Exposure > Credit Score Exposure
Restrictions: exposesDataType -> FinancialData

## C2: PrescriptionExposure [object] -- structural
Definition: Exposure of prescription medication data
Path: Privacy Violation > Medical Data Exposure > Prescription Exposure

## C3: ExfiltrationViaWebService [instrument] -- structural
Definition: Unauthorized transfer of data via web service channels
Path: Data Exfiltration > Exfiltration Via Web Service

## C4: Person [agent] -- structural
Definition: A human being
Path: Privacy Violation > (restriction: exposesDataOf) > Person

## C5: DataAnonymization [instrument] -- search (connected via d3f:DefensiveTechnique)
Definition: Process of removing identifying information from data
Distance: 0.31

## C6: BiometricIdentifier [object] -- search only
Definition: A measurable biological characteristic used for identification
Distance: 0.28
```

The `-- structural` / `-- search (connected via ...)` / `-- search only` tags give the LLM provenance for judging relevance. The path shows the semantic derivation chain.

## 6. Contextualize Stage Redesign

### Current Flow (Replaced)

```
get_subclasses(axis_uri) -> sibling fallback -> domain filter -> disjointness filter -> LLM filters
```

### New Flow: Policy-Driven LLM Generation

```
Policy content + knowledge graph constraints + optional ontology subclasses -> LLM generates concrete variations
```

### Context Assembly

For each selected axis, assemble:

1. **Policy context** (when available):
   - `boundary_examples` — "includes SSN, credit card numbers, dates of birth"
   - `acceptable_uses` — "aggregate statistical reporting"
   - `risk_controls` — "PII masking, data anonymization"

2. **Knowledge graph constraints**:
   - `related_actions` from nexus — "Implement differential privacy, test for memorization"
   - `cross_mapped_risks` — related risk descriptions from other frameworks
   - `concern` field — "PII leakage via model outputs or training data extraction"

3. **Ontology subclasses** (optional inspiration, not primary):
   - If `get_subclasses(axis_uri, depth=1)` returns values, include as reference
   - Labeled as "existing ontology subclasses for reference, not exhaustive"

### LLM Prompt

```
Generate 5-8 specific, concrete scenario variations for the following axis.

Axis: {axis_label} ({roles})
Risk: {risk_name} -- {risk_description}
Concern: {risk_concern}

Policy context:
- Boundaries: {boundary_examples}
- Acceptable uses: {acceptable_uses}
- Controls: {risk_controls}

Related mitigation actions: {actions}
Related risks from other frameworks: {cross_mapped_descriptions}

{if subclasses: "Existing ontology subclasses (for reference): {subclass_labels}"}

Each variation should be a specific, concrete instance that a red-team prompt
could be built around. Focus on instances relevant to this specific policy.
```

### Response Model

```python
class _Variation(BaseModel):
    instance: str       # e.g., "FICO score leaked in model explanation"
    relevance: str      # high / medium / low

class _ContextResponse(BaseModel):
    variations: list[_Variation]
```

### Fallback

When policy content is thin (no boundary_examples, no acceptable_uses):
- Knowledge graph constraints + ontology subclasses carry the weight
- LLM still generates variations but with less policy grounding
- Logged as "thin_policy_context" event for reporting

## 7. Changes by Component

| Component | Change | Notes |
|-----------|--------|-------|
| `refiner/data/risk-to-ontology.sssom.tsv` | NEW | Seed mappings in SSSOM format |
| `refiner/src/refiner/ontology_seeds.py` | NEW | SSSOM loader, seed resolution with cross-taxonomy fallback |
| `refiner/src/refiner/stages/anchor.py` | REWRITE `expand_candidates()` | Structural navigation + constrained search + tiered merge. Remove `WeightedMergeStrategy`, `GroupedMergeStrategy`, `LLMMergeStrategy` |
| `refiner/src/refiner/stages/anchor.py` | UPDATE prompt format | Add provenance tags and paths to candidate presentation |
| `refiner/src/refiner/stages/anchor.py` | KEEP | `derive_roles()`, `_CATEGORY_ROLES`, `_is_excluded_uri()`, `build_generic_safety_uris()` |
| `refiner/src/refiner/stages/contextualize.py` | REWRITE | Replace subclass enumeration with policy-driven LLM generation |
| `refiner/src/refiner/stages/map_risks.py` | ADD | Return RiskGroup info alongside risk matches |
| `refiner/src/refiner/pipeline.py` | UPDATE | Load SSSOM seeds at startup, pass through to anchor, pass policy content to contextualize |
| `nexus-mcp/src/nexus_mcp/server.py` | ADD handler | `get_risk_group(risk_id)` — return RiskGroup metadata |
| `ontoquery/` | NO CHANGES | Existing handlers sufficient for navigation |
| `refiner/src/refiner/models.py` | UPDATE | Axis enumeration model changes (LLM-generated instances vs ontology subclasses) |

## 8. What Gets Removed

- `WeightedMergeStrategy` — replaced by tiered merge with SSSOM-informed priority
- `GroupedMergeStrategy` — replaced by tiered merge
- `LLMMergeStrategy` — the LLM's role moves from merge to final axis selection (already present)
- Legacy single-collection search path (`search_classes`) — fully replaced by constrained per-domain search
- Sibling fallback in contextualize — unnecessary when LLM generates variations
- Disjointness filtering in contextualize — unnecessary when not enumerating subclasses
- `_normalize_distances()` / z-score logic — replaced by structural provenance as primary signal

## 9. What Gets Kept

- `derive_roles()` and `_CATEGORY_ROLES` — role derivation via superclass walk remains essential
- `_is_excluded_uri()` — BFO/LKIF normative exclusion still applies to structurally-navigated candidates
- `build_generic_safety_uris()` — CSO DangerousInformation filtering still needed for domain-specific runs
- Risk-level memoization (axes_cache) — same risk from multiple policies = one computation
- Per-domain ChromaDB collections — used by constrained search
- `derive_source_ontology()` / `derive_domain()` — domain filtering still applies
- Ground-truth cross-mappings from nexus — never LLM-generated

## 10. How This Solves Known Problems

| Problem | Solution |
|---------|----------|
| FIBO contamination in healthcare | Seeds for Privacy/Fairness don't include FIBO branches. FIBO only appears if explicitly seeded (Compliance risks). Constrained search scoped to seed domains. |
| Sibling fallback monocultures | Contextualize generates variations from policy content, not subclass hierarchies. No dependency on ontology depth. |
| Axis role imbalance | Tiered merge enforces role diversity across candidate tiers before LLM selection. |
| Enumeration concentration | LLM generates diverse instances informed by policy, not constrained to ontology enumerations. |
| OBO mismatch in non-healthcare | OBO seeds only for Fairness concept (GSSO/HANCESTRO/OMRSE). Biomedical classes won't appear for Robustness risks. |
| No provenance for candidates | Every candidate carries explicit source tag, derivation path, and seed confidence. |
| Text similarity as sole discovery | Structural navigation is primary; search is complementary and scoped. |
| Z-score normalization insufficient | Replaced by structural provenance as primary relevance signal. Distance becomes secondary. |

## 11. Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Seed mapping curation is manual effort | Bootstrap with LLM-based matching (same approach nexus uses for risk-to-risk mappings). ~30-40 RiskGroup mappings + ~50-100 risk-level mappings. |
| Structural navigation misses relevant classes not connected to seeds | Constrained search as complementary source. Tier 3 (search-only) candidates catch ontology gaps. |
| Non-IBM risks without IBM cross-mappings | Fallback to constrained search. ~18% of NIST risks lack IBM mappings but these are edge cases. Log as "unmapped_risk" for monitoring. |
| Policy-driven LLM enumeration may hallucinate | Knowledge graph constraints (actions, cross-mappings) validate. Ontology subclasses as optional reference. |
| Navigation depth tuning | Start conservative (depth=2), adjust per-domain based on run assessments. Adaptive depth based on candidate count. |
| New risks without seed mappings | Fallback to constrained search across all selected domains (degrades gracefully to current-like behavior). |
