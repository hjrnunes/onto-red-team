# Category-Aware Deep Semantics Design

**Date:** 2026-04-20
**Status:** Draft
**Motivation:** Peixoto et al. (2025) "Ontology-driven context engineering for semantically-aware chatbot responses" — empirical evidence that ontological nature-driven entity selection (Deep Semantics) outperforms graph-proximity-based selection (81% vs 28% correctness, with fewer entities extracted).

## Overview

Two related changes to make the refiner's ontology integration nature-aware:

1. **Category-aware `build_structural_context()`** — foreground constitutive relationships per BFO category in embedding documents, so the embedding space itself encodes ontological significance
2. **Category-aware navigation dispatch + revived semantic roles** — use BFO category to determine which relationships to follow during anchor-stage exploration, and derive contextual roles from the intersection of entity category and discovery relationship

Both are driven by a shared **category-property registry** (`CATEGORY_PATTERNS`) that maps BFO categories to their constitutive relationship patterns.

## Core Principle

> The ontological category of an entity determines which of its relationships are semantically load-bearing. Graph proximity treats all edges as equal. Ontological nature tells you which edges are constitutive and which are incidental.

A Process is undefined without its participants. A Quality cannot exist without its bearer. An ICE is meaningless without its aboutness. The category-property registry encodes these constitutive dependencies.

## Design

### 1. Category-Property Registry

A shared data structure in `ontoquery/bfo.py` (new module), consumed by both indexing and anchor stages.

```python
@dataclass
class ConstitutivePattern:
    role_prefix: str           # NL prefix for embedding context ("Participants", "About")
    property_patterns: list[str]  # URI fragments to match ("has_participant", "is_about")
    inverse: bool = False      # Also check reverse direction (object → subject)

CATEGORY_PATTERNS: dict[str, list[ConstitutivePattern]] = {
    "Process": [
        ConstitutivePattern("Participants", [
            "has_participant", "has_agent", "has_patient", "involves"]),
        ConstitutivePattern("Realizes", ["realizes", "is_realization_of"]),
        ConstitutivePattern("Inputs/Outputs", [
            "has_input", "has_output", "transforms"]),
    ],
    "Quality": [
        ConstitutivePattern("Characterizes", [
            "inheres_in", "bearer_of", "quality_of", "characterizes"],
            inverse=True),
    ],
    "Role": [
        ConstitutivePattern("Borne by", ["inheres_in", "role_of"], inverse=True),
        ConstitutivePattern("Realized in", ["realized_in", "realizes"]),
    ],
    "Disposition": [
        ConstitutivePattern("Borne by", [
            "inheres_in", "disposition_of"], inverse=True),
        ConstitutivePattern("Triggered by", ["realized_in", "has_realization"]),
    ],
    "InformationContentEntity": [
        ConstitutivePattern("About", [
            "is_about", "describes", "represents", "denotes"]),
        ConstitutivePattern("Carried by", [
            "generically_depends_on", "concretized_by"]),
    ],
    "MaterialEntity": [
        ConstitutivePattern("Parts", ["has_part", "has_component"]),
        ConstitutivePattern("Bears", [
            "bearer_of", "has_role", "has_disposition", "has_quality"]),
    ],
    "Agent": [
        ConstitutivePattern("Participates in", [
            "participates_in", "agent_in", "performs"]),
        ConstitutivePattern("Bears role", ["bearer_of", "has_role"]),
    ],
    "MaterialArtifact": [
        ConstitutivePattern("Parts", ["has_part", "has_component"]),
        ConstitutivePattern("Function", ["has_function", "has_disposition"]),
    ],
    "Act": [
        ConstitutivePattern("Participants", [
            "has_participant", "has_agent", "has_patient"]),
        ConstitutivePattern("Realizes", ["realizes"]),
    ],
    "Facility": [
        ConstitutivePattern("Located in", ["located_in", "has_site"]),
        ConstitutivePattern("Houses", ["has_part", "contains"]),
    ],
    "GenericallyDependentContinuant": [
        ConstitutivePattern("About", ["is_about", "describes"]),
        ConstitutivePattern("Concretized by", [
            "concretized_by", "generically_depends_on"]),
    ],
}
```

Property matching uses URI local name fragments — `"has_participant"` matches `d3fend.owl#has_participant` and any domain-specific variant whose local name (after `#` or `/`) contains the fragment. BFO numeric URIs (e.g., `BFO_0000057`) are handled by including their local names as additional patterns where needed (e.g., `"BFO_0000057"` for `has_participant`). Matching is case-insensitive and checks for whole-token containment (underscore/camelCase boundaries) to avoid false positives like `"has_part"` matching `"has_participant"` — the implementation should split on `_` and match token sequences.

The `inverse` flag covers cases where the constitutive relationship appears in the reverse direction (e.g., a Quality with an `inheres_in` restriction pointing to its bearer, vs a bearer with a `bearer_of` restriction pointing to the Quality).

### 2. Shared BFO Category Map

The existing `_BFO_CATEGORIES` dict in `anchor.py` moves to `ontoquery/bfo.py`:

```python
BFO_CATEGORY_MAP: dict[str, str] = {
    "http://purl.obolibrary.org/obo/BFO_0000040": "MaterialEntity",
    "http://purl.obolibrary.org/obo/BFO_0000015": "Process",
    "http://purl.obolibrary.org/obo/BFO_0000031": "GenericallyDependentContinuant",
    "http://purl.obolibrary.org/obo/BFO_0000020": "Quality",
    "http://purl.obolibrary.org/obo/BFO_0000023": "Role",
    "http://purl.obolibrary.org/obo/BFO_0000016": "Disposition",
    "http://purl.obolibrary.org/obo/BFO_0000017": "RealizableEntity",
    "http://purl.obolibrary.org/obo/BFO_0000029": "Site",
    "http://purl.obolibrary.org/obo/BFO_0000006": "SpatialRegion",
    "http://purl.obolibrary.org/obo/BFO_0000141": "ImmaterialEntity",
    "http://purl.obolibrary.org/obo/BFO_0000008": "TemporalRegion",
    "http://purl.obolibrary.org/obo/BFO_0000019": "Quality",
    # CCO shortcuts
    "https://www.commoncoreontologies.org/ont00000958": "InformationContentEntity",
    "https://www.commoncoreontologies.org/ont00001017": "Agent",
    "https://www.commoncoreontologies.org/ont00000995": "MaterialArtifact",
    "https://www.commoncoreontologies.org/ont00000192": "Facility",
    "https://www.commoncoreontologies.org/ont00000005": "Act",
    # CCO direct mappings
    "https://www.commoncoreontologies.org/ont00001262": "Agent",
    "https://www.commoncoreontologies.org/ont00001180": "Agent",
    "https://www.commoncoreontologies.org/ont00000740": "MaterialEntity",
}
```

### 3. BFO Classification at Indexing Time

New function in `ontoquery/bfo.py`:

```python
def classify_bfo_categories(
    projected_graph: ProjectedGraph,
    category_map: dict[str, str] = BFO_CATEGORY_MAP,
    max_depth: int = 10,
) -> dict[str, str]:
```

Walks SubClassOf edges in the projected graph to find the most specific BFO ancestor for each class. Returns `{uri: category_label}`. Same logic as `derive_bfo_category()` in anchor.py but operating on projected graph edges instead of `onto_handlers`.

The result is:
- Passed to `build_structural_context()` for category-aware embedding construction
- Saved as `bfo_categories.json` sidecar file next to the ChromaDB directory
- Loaded by the refiner at pipeline start

### 4. Category-Aware `build_structural_context()`

Modified signature:

```python
def build_structural_context(
    projected_graph,
    *,
    bfo_categories: dict[str, str] | None = None,
    max_children: int = 8,
    max_properties: int = 6,
) -> dict[str, str]:
```

When `bfo_categories` is provided, for each class:

1. Look up its BFO category
2. If it has patterns in `CATEGORY_PATTERNS`, partition properties:
   - **Constitutive:** property URI local name matches any `property_patterns` → grouped under the `role_prefix`
   - **Contextual:** everything else → listed normally
3. Output format:

```
[Process] Participants: Agent, DataSubject. Realizes: DataProtectionObligation.
SubClassOf: InformationProcessing. HasSubClass: DataCollection, DataErasure.
governed_by: Regulation. operates_on: PersonalData.
```

When `bfo_categories` is `None`, behavior is unchanged (backward compatible).

Properties are never dropped, only reordered and relabeled. Taxonomy (SubClassOf/HasSubClass) always appears regardless of category.

### 5. Category-Aware Navigation Dispatch

Inside the `relatedMatch` branch of `navigate_from_seeds()`, the uniform restriction + sibling expansion is replaced with a category-aware dispatch:

```python
def _expand_by_category(
    category: str,
    seed_uri: str,
    onto_handlers: dict,
    candidates: list[dict],
    bfo_categories: dict[str, str],
    *,
    seed_label: str,
    confidence: float,
    predicate: str,
    vocab_concept: str | None,
    vocab_label: str | None,
    safety: set[str],
    selected_domains: list[str] | None,
) -> None:
```

**Targeted restriction expansion:**

Restrictions whose property matches a constitutive pattern get confidence × 0.95. Non-constitutive restrictions get confidence × 0.8. All restrictions are still followed — constitutive ones just rank higher in tiered merging.

**Category-specific sibling behavior:**

| Category | Sibling Expansion | Confidence | Rationale |
|---|---|---|---|
| Quality, Role, Disposition | Aggressive | 0.85 | Sibling phases/roles share bearer kind (PHASE pattern) |
| Process, Act | Conditional (< 4 structural candidates) | 0.7 | Sibling processes don't participate in each other |
| MaterialEntity, Agent | Moderate | 0.8 | Default behavior |
| ICE, GDC | Skip | — | Sibling documents rarely relevant |

**Category-specific additional expansion:**

- **Role / Disposition:** Follow `inheres_in` restrictions to extract the bearer. Confidence × 0.9.
- **Process / Act:** Follow `realizes` restrictions to find realized dispositions/obligations. Confidence × 0.9.

**Fallback:** If category is empty or not in `CATEGORY_PATTERNS`, the existing uniform behavior applies unchanged.

**Scope:** Only applies to `relatedMatch` seeds. `broadMatch` (hierarchy downward) and `exactMatch`/`closeMatch` (direct reference) are unchanged.

### 6. Semantic Role Derivation

New function:

```python
def derive_role(
    candidate_category: str,
    seed_category: str,
    restriction_property: str,
    category_patterns: dict[str, list[ConstitutivePattern]] = CATEGORY_PATTERNS,
) -> str:
```

Roles are derived from the intersection of two things:
- The relationship through which the candidate was discovered (restriction property matched against the seed's constitutive patterns to find the `role_prefix`)
- The candidate's own BFO category (refines the role within that prefix)

**Relationship-derived roles (primary, when restriction context available):**

| Seed Category | Restriction Property | Candidate Category | Role |
|---|---|---|---|
| Process | `has_participant` | Agent | agent |
| Process | `has_participant` | MaterialEntity | patient |
| Process | `has_participant` | ICE | information |
| Process | `realizes` | Role/Disposition | obligation |
| Process | `has_input` | any | input |
| Process | `has_output` | any | output |
| Quality | `inheres_in` | any | bearer |
| Role | `inheres_in` | any | bearer |
| Role | `realized_in` | Process | realization |
| ICE | `is_about` | any | subject |
| ICE | `generically_depends_on` | any | medium |

**Category-only fallback roles (when discovered via siblings/search, no restriction context):**

| Candidate Category | Default Role |
|---|---|
| Agent | agent |
| Process, Act | process |
| ICE, GDC | information |
| Quality | quality |
| Role | role |
| Disposition | disposition |
| MaterialEntity, MaterialArtifact | object |
| Facility, Site | location |

### 7. New `semantic_role` Field

New field on `VariationAxis`:

```python
class VariationAxis(BaseModel):
    ...
    semantic_role: str = ""  # Derived from BFO category + discovery relationship
```

Separate from the old `roles: list[str]` field (which remains empty for backward compat). `semantic_role` is singular and derived, not a manually assigned list.

Appears in:
- LLM selection prompt: `[Process/agent]` alongside existing `[Process]` tag
- Contextualize stage: informs how domain context is framed for red-team prompt generation

## Data Flow

### Indexing Pipeline

```
ontology files
    → project_ontology(backend)
    → classify_bfo_categories(graph)          # NEW
    → build_structural_context(graph,         # MODIFIED
        bfo_categories=categories)
    → index_domain_classes(classes,
        structural_context=context)
    → save bfo_categories.json sidecar        # NEW
```

### Refiner Pipeline (anchor stage)

```
risk + policy + seed_mappings
    → load bfo_categories.json                # NEW
    → navigate_from_seeds(                    # MODIFIED: category dispatch
        ..., bfo_categories=categories)
    → constrained_search(...)                 # unchanged
    → merge_tiered(...)                       # unchanged (better confidence scores)
    → enrich candidates + derive_role()       # MODIFIED
    → LLM selection prompt                    # MODIFIED: [Process/agent] tags
    → VariationAxis with semantic_role        # NEW field
```

## Files Changed

| Subsystem | File | Change |
|---|---|---|
| ontoquery | `bfo.py` (new) | `BFO_CATEGORY_MAP`, `CATEGORY_PATTERNS`, `ConstitutivePattern`, `classify_bfo_categories()` |
| ontoquery | `index.py` | `build_structural_context()` gains `bfo_categories` param, category-aware property partitioning |
| ontoquery | CLI entry point | Call `classify_bfo_categories()`, pass to `build_structural_context()`, save sidecar |
| refiner | `anchor.py` | `_BFO_CATEGORIES` → import from `ontoquery.bfo`; `_expand_by_category()` dispatch; `derive_role()`; load sidecar |
| refiner | `models.py` | `VariationAxis.semantic_role` field |

## What Doesn't Change

- `owl2vec.py` — projection unchanged
- `constrained_search()` — unchanged, benefits from better embeddings
- `merge_tiered()` — unchanged, constitutive candidates rank higher via confidence
- Evaluation pipeline — unchanged, `semantic_role` is a new observation dimension
- Existing tests — should pass unchanged (backward compatible via `bfo_categories=None`)

## Backward Compatibility

- `build_structural_context(bfo_categories=None)` → existing uniform behavior
- `_expand_by_category(category="", ...)` → existing uniform restriction + sibling expansion
- `derive_role()` fallback → category-only default roles (similar to old `_CATEGORY_ROLES` but as fallback, not primary)
- `semantic_role` defaults to `""` — no impact on existing axes

## Requires Re-indexing

Yes, once: `just index-ontologies` with updated code.

## References

- Peixoto M, Silva G, Maddalena L, Baiao F (2025). Ontology-driven context engineering for semantically-aware chatbot responses. *Semantic Web Journal*.
- Design notes: Obsidian vault `Red Hat/Onto Red-Teaming/AI Atlas Nexus - Nature-Driven Entity Selection.md`
