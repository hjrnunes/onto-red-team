# Category-Aware Deep Semantics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the refiner's ontology integration nature-aware by foregrounding constitutive relationships per BFO category in embeddings and navigation, and deriving semantic roles from BFO patterns instead of a static table.

**Architecture:** A shared `ontoquery/bfo.py` module defines BFO category maps and constitutive property patterns. At indexing time, classes are classified by BFO category and their structural context is partitioned into constitutive (foregrounded) and contextual (normal) properties. At anchor time, navigation dispatch uses the same patterns to prioritize constitutive restrictions and derive semantic roles for each candidate.

**Tech Stack:** Python, dataclasses, pytest, ChromaDB (ontoquery), Pydantic (refiner models)

**Spec:** `docs/superpowers/specs/2026-04-20-category-aware-deep-semantics-design.md`

---

## File Map

| File | Responsibility |
|---|---|
| `ontoquery/src/ontoquery/bfo.py` (create) | `BFO_CATEGORY_MAP`, `ConstitutivePattern`, `CATEGORY_PATTERNS`, `classify_bfo_categories()`, `match_property()` |
| `ontoquery/tests/test_bfo.py` (create) | Tests for BFO classification, property matching, category patterns |
| `ontoquery/src/ontoquery/index.py` (modify) | `build_structural_context()` gains `bfo_categories` param |
| `ontoquery/tests/test_index.py` (modify) | Tests for category-aware structural context |
| `ontoquery/src/ontoquery/cli.py` (modify) | Wire up classification + sidecar save in `index` command |
| `refiner/src/refiner/models.py` (modify) | Add `semantic_role` to `VariationAxis` |
| `refiner/src/refiner/stages/anchor.py` (modify) | Import from `ontoquery.bfo`, add `_expand_by_category()`, `derive_role()`, load sidecar, update enrichment |
| `refiner/tests/test_structural_navigation.py` (modify) | Tests for category-aware navigation + role derivation |

---

### Task 1: Shared BFO Module — Data Structures and Property Matching

**Files:**
- Create: `ontoquery/src/ontoquery/bfo.py`
- Create: `ontoquery/tests/test_bfo.py`

- [ ] **Step 1: Write failing tests for `match_property()`**

```python
# ontoquery/tests/test_bfo.py
from ontoquery.bfo import match_property, ConstitutivePattern, CATEGORY_PATTERNS, BFO_CATEGORY_MAP


class TestMatchProperty:
    def test_exact_local_name_match(self):
        assert match_property("http://example.org/ont#has_participant", ["has_participant"]) is True

    def test_fragment_after_hash(self):
        assert match_property("http://d3fend.mitre.org/ontologies/d3fend.owl#has_participant", ["has_participant"]) is True

    def test_fragment_after_slash(self):
        assert match_property("http://example.org/ontology/has_participant", ["has_participant"]) is True

    def test_no_match(self):
        assert match_property("http://example.org/ont#worksFor", ["has_participant"]) is False

    def test_does_not_false_positive_has_part_vs_has_participant(self):
        assert match_property("http://example.org/ont#has_participant", ["has_part"]) is False

    def test_has_part_matches_has_part(self):
        assert match_property("http://example.org/ont#has_part", ["has_part"]) is True

    def test_case_insensitive(self):
        assert match_property("http://example.org/ont#Has_Participant", ["has_participant"]) is True

    def test_bfo_numeric_uri(self):
        assert match_property("http://purl.obolibrary.org/obo/BFO_0000057", ["BFO_0000057", "has_participant"]) is True

    def test_multiple_patterns(self):
        assert match_property("http://example.org/ont#realizes", ["has_participant", "realizes"]) is True

    def test_camel_case_token_boundary(self):
        assert match_property("http://example.org/ont#hasParticipant", ["has_participant"]) is True


class TestCategoryPatternsComplete:
    def test_all_categories_have_patterns(self):
        expected = {
            "Process", "Quality", "Role", "Disposition",
            "InformationContentEntity", "MaterialEntity", "Agent",
            "MaterialArtifact", "Act", "Facility", "GenericallyDependentContinuant",
        }
        assert set(CATEGORY_PATTERNS.keys()) == expected

    def test_each_pattern_has_role_prefix(self):
        for cat, patterns in CATEGORY_PATTERNS.items():
            for p in patterns:
                assert p.role_prefix, f"{cat} has pattern with empty role_prefix"
                assert p.property_patterns, f"{cat}/{p.role_prefix} has empty property_patterns"


class TestBfoCategoryMap:
    def test_known_bfo_entries(self):
        assert BFO_CATEGORY_MAP["http://purl.obolibrary.org/obo/BFO_0000015"] == "Process"
        assert BFO_CATEGORY_MAP["http://purl.obolibrary.org/obo/BFO_0000040"] == "MaterialEntity"
        assert BFO_CATEGORY_MAP["http://purl.obolibrary.org/obo/BFO_0000023"] == "Role"

    def test_cco_shortcuts(self):
        assert BFO_CATEGORY_MAP["https://www.commoncoreontologies.org/ont00000958"] == "InformationContentEntity"
        assert BFO_CATEGORY_MAP["https://www.commoncoreontologies.org/ont00001017"] == "Agent"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ontoquery && uv run pytest tests/test_bfo.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ontoquery.bfo'`

- [ ] **Step 3: Implement `bfo.py`**

```python
# ontoquery/src/ontoquery/bfo.py
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class ConstitutivePattern:
    role_prefix: str
    property_patterns: list[str]
    inverse: bool = False


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


CATEGORY_PATTERNS: dict[str, list[ConstitutivePattern]] = {
    "Process": [
        ConstitutivePattern("Participants", [
            "has_participant", "has_agent", "has_patient", "involves",
            "BFO_0000057"]),
        ConstitutivePattern("Realizes", ["realizes", "is_realization_of"]),
        ConstitutivePattern("Inputs/Outputs", [
            "has_input", "has_output", "transforms"]),
    ],
    "Quality": [
        ConstitutivePattern("Characterizes", [
            "inheres_in", "bearer_of", "quality_of", "characterizes",
            "BFO_0000052"],
            inverse=True),
    ],
    "Role": [
        ConstitutivePattern("Borne by", [
            "inheres_in", "role_of", "BFO_0000052"], inverse=True),
        ConstitutivePattern("Realized in", ["realized_in", "realizes"]),
    ],
    "Disposition": [
        ConstitutivePattern("Borne by", [
            "inheres_in", "disposition_of", "BFO_0000052"], inverse=True),
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
            "has_participant", "has_agent", "has_patient", "BFO_0000057"]),
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


def _tokenize(name: str) -> list[str]:
    """Split a property local name into lowercase tokens.

    Handles both underscore_case and camelCase:
      "has_participant" -> ["has", "participant"]
      "hasParticipant"  -> ["has", "participant"]
    """
    # Insert underscore before uppercase letters (camelCase -> underscore_case)
    underscored = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    return [t.lower() for t in underscored.split("_") if t]


def match_property(property_uri: str, patterns: list[str]) -> bool:
    """Check if a property URI matches any of the given patterns.

    Extracts the local name (after # or last /), tokenizes it, then checks
    whether the token sequence of any pattern appears as a contiguous
    subsequence. Case-insensitive.

    Patterns that look like BFO numeric URIs (e.g. "BFO_0000057") are
    matched literally against the local name.
    """
    local = property_uri.rsplit("#", 1)[-1].rsplit("/", 1)[-1]
    local_lower = local.lower()
    local_tokens = _tokenize(local)

    for pat in patterns:
        pat_lower = pat.lower()
        # Literal match for BFO numeric IDs
        if pat_lower.startswith("bfo_") and pat_lower == local_lower:
            return True
        pat_tokens = _tokenize(pat)
        if not pat_tokens:
            continue
        # Check contiguous subsequence
        for i in range(len(local_tokens) - len(pat_tokens) + 1):
            if local_tokens[i:i + len(pat_tokens)] == pat_tokens:
                return True
    return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ontoquery && uv run pytest tests/test_bfo.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add ontoquery/src/ontoquery/bfo.py ontoquery/tests/test_bfo.py
git commit -m "feat(ontoquery): add BFO category map, constitutive patterns, and property matcher"
```

---

### Task 2: BFO Category Classification from Projected Graph

**Files:**
- Modify: `ontoquery/src/ontoquery/bfo.py`
- Modify: `ontoquery/tests/test_bfo.py`

- [ ] **Step 1: Write failing tests for `classify_bfo_categories()`**

Add to `ontoquery/tests/test_bfo.py`:

```python
from ontoquery.bfo import classify_bfo_categories
from ontoquery.owl2vec import ProjectedGraph, SUBCLASS_OF


class TestClassifyBfoCategories:
    def _make_graph(self, edges):
        g = ProjectedGraph()
        for s, o in edges:
            g.edges.append((s, SUBCLASS_OF, o))
            g.classes.add(s)
            g.classes.add(o)
        return g

    def test_direct_bfo_child(self):
        graph = self._make_graph([
            ("http://example.org/MyProcess", "http://purl.obolibrary.org/obo/BFO_0000015"),
        ])
        result = classify_bfo_categories(graph)
        assert result["http://example.org/MyProcess"] == "Process"

    def test_indirect_via_chain(self):
        graph = self._make_graph([
            ("http://example.org/DataCollection", "http://example.org/InformationProcessing"),
            ("http://example.org/InformationProcessing", "http://purl.obolibrary.org/obo/BFO_0000015"),
        ])
        result = classify_bfo_categories(graph)
        assert result["http://example.org/DataCollection"] == "Process"
        assert result["http://example.org/InformationProcessing"] == "Process"

    def test_cco_shortcut(self):
        graph = self._make_graph([
            ("http://example.org/Report", "https://www.commoncoreontologies.org/ont00000958"),
        ])
        result = classify_bfo_categories(graph)
        assert result["http://example.org/Report"] == "InformationContentEntity"

    def test_no_bfo_ancestor(self):
        graph = self._make_graph([
            ("http://example.org/Thing", "http://example.org/OtherThing"),
        ])
        result = classify_bfo_categories(graph)
        assert "http://example.org/Thing" not in result

    def test_bfo_class_itself_not_included(self):
        graph = ProjectedGraph()
        graph.classes.add("http://purl.obolibrary.org/obo/BFO_0000015")
        result = classify_bfo_categories(graph)
        assert "http://purl.obolibrary.org/obo/BFO_0000015" not in result

    def test_most_specific_category_wins(self):
        """Role is more specific than RealizableEntity — Role should win."""
        graph = self._make_graph([
            ("http://example.org/DataControllerRole", "http://purl.obolibrary.org/obo/BFO_0000023"),
            ("http://purl.obolibrary.org/obo/BFO_0000023", "http://purl.obolibrary.org/obo/BFO_0000017"),
        ])
        result = classify_bfo_categories(graph)
        assert result["http://example.org/DataControllerRole"] == "Role"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ontoquery && uv run pytest tests/test_bfo.py::TestClassifyBfoCategories -v`
Expected: FAIL — `ImportError: cannot import name 'classify_bfo_categories'`

- [ ] **Step 3: Implement `classify_bfo_categories()`**

Add to `ontoquery/src/ontoquery/bfo.py`:

```python
def classify_bfo_categories(
    projected_graph,
    category_map: dict[str, str] | None = None,
    max_depth: int = 10,
) -> dict[str, str]:
    """Walk SubClassOf edges to classify each class's BFO category.

    Returns {uri: category_label} for classes that have a BFO/CCO ancestor
    in the category_map. BFO/CCO map entries themselves are excluded.
    """
    if category_map is None:
        category_map = BFO_CATEGORY_MAP

    from ontoquery.owl2vec import SUBCLASS_OF

    # Build parent lookup from projected edges
    parents: dict[str, list[str]] = {}
    for s, p, o in projected_graph.edges:
        if p == SUBCLASS_OF:
            parents.setdefault(s, []).append(o)

    result: dict[str, str] = {}
    for uri in projected_graph.classes:
        if uri in category_map:
            continue
        visited: set[str] = set()
        frontier = [uri]
        found = ""
        for _ in range(max_depth):
            if not frontier:
                break
            current = frontier.pop(0)
            if current in visited:
                continue
            visited.add(current)
            if current != uri and current in category_map:
                found = category_map[current]
                break
            for parent in parents.get(current, []):
                if parent not in visited:
                    frontier.append(parent)
        if found:
            result[uri] = found

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ontoquery && uv run pytest tests/test_bfo.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add ontoquery/src/ontoquery/bfo.py ontoquery/tests/test_bfo.py
git commit -m "feat(ontoquery): add classify_bfo_categories from projected graph"
```

---

### Task 3: Category-Aware `build_structural_context()`

**Files:**
- Modify: `ontoquery/src/ontoquery/index.py`
- Modify: `ontoquery/tests/test_index.py`

- [ ] **Step 1: Write failing test for category-aware context**

Add to `ontoquery/tests/test_index.py`:

```python
def test_build_structural_context_category_aware():
    from rdflib import Graph
    from ontoquery.backend import RdflibBackend
    from ontoquery.owl2vec import project_ontology
    from ontoquery.bfo import classify_bfo_categories

    ttl = """\
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix ex: <http://example.org/ont#> .
@prefix bfo: <http://purl.obolibrary.org/obo/> .

bfo:BFO_0000015 a owl:Class ; rdfs:label "process" .
ex:DataCollection a owl:Class ; rdfs:label "DataCollection" ;
    rdfs:subClassOf bfo:BFO_0000015 ;
    rdfs:subClassOf [
        a owl:Restriction ;
        owl:onProperty ex:has_participant ;
        owl:someValuesFrom ex:Agent
    ] ;
    rdfs:subClassOf [
        a owl:Restriction ;
        owl:onProperty ex:governed_by ;
        owl:someValuesFrom ex:Regulation
    ] .
ex:Agent a owl:Class ; rdfs:label "Agent" .
ex:Regulation a owl:Class ; rdfs:label "Regulation" .
ex:has_participant a owl:ObjectProperty .
ex:governed_by a owl:ObjectProperty .
"""
    g = Graph()
    g.parse(data=ttl, format="turtle")
    backend = RdflibBackend(g)
    projected = project_ontology(backend, bidirectional_taxonomy=True, include_literals=True)
    bfo_cats = classify_bfo_categories(projected)
    ctx = build_structural_context(projected, bfo_categories=bfo_cats)

    dc_ctx = ctx["http://example.org/ont#DataCollection"]
    # Constitutive "Participants" should appear before "governed_by"
    assert "[Process]" in dc_ctx
    assert "Participants: Agent" in dc_ctx
    # governed_by is contextual, should appear but after constitutive
    assert "governed_by" in dc_ctx
    participants_pos = dc_ctx.index("Participants")
    governed_pos = dc_ctx.index("governed_by")
    assert participants_pos < governed_pos


def test_build_structural_context_no_category_unchanged():
    """When bfo_categories is None, output should be identical to current behavior."""
    from rdflib import Graph
    from ontoquery.backend import RdflibBackend
    from ontoquery.owl2vec import project_ontology

    ttl = """\
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix ex: <http://example.org/ont#> .

ex:Animal a owl:Class ; rdfs:label "Animal" .
ex:Mammal a owl:Class ; rdfs:label "Mammal" ; rdfs:subClassOf ex:Animal .
"""
    g = Graph()
    g.parse(data=ttl, format="turtle")
    backend = RdflibBackend(g)
    projected = project_ontology(backend, bidirectional_taxonomy=True, include_literals=True)
    ctx_without = build_structural_context(projected)
    ctx_with_none = build_structural_context(projected, bfo_categories=None)
    assert ctx_without == ctx_with_none


def test_build_structural_context_quality_characterizes():
    from rdflib import Graph
    from ontoquery.backend import RdflibBackend
    from ontoquery.owl2vec import project_ontology
    from ontoquery.bfo import classify_bfo_categories

    ttl = """\
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix ex: <http://example.org/ont#> .
@prefix bfo: <http://purl.obolibrary.org/obo/> .

bfo:BFO_0000020 a owl:Class ; rdfs:label "quality" .
ex:ImageQuality a owl:Class ; rdfs:label "ImageQuality" ;
    rdfs:subClassOf bfo:BFO_0000020 ;
    rdfs:subClassOf [
        a owl:Restriction ;
        owl:onProperty ex:inheres_in ;
        owl:someValuesFrom ex:Photo
    ] .
ex:Photo a owl:Class ; rdfs:label "Photo" .
ex:inheres_in a owl:ObjectProperty .
"""
    g = Graph()
    g.parse(data=ttl, format="turtle")
    backend = RdflibBackend(g)
    projected = project_ontology(backend, bidirectional_taxonomy=True, include_literals=True)
    bfo_cats = classify_bfo_categories(projected)
    ctx = build_structural_context(projected, bfo_categories=bfo_cats)

    iq_ctx = ctx["http://example.org/ont#ImageQuality"]
    assert "[Quality]" in iq_ctx
    assert "Characterizes: Photo" in iq_ctx
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ontoquery && uv run pytest tests/test_index.py::test_build_structural_context_category_aware tests/test_index.py::test_build_structural_context_quality_characterizes -v`
Expected: FAIL — `TypeError: build_structural_context() got an unexpected keyword argument 'bfo_categories'`

- [ ] **Step 3: Modify `build_structural_context()`**

In `ontoquery/src/ontoquery/index.py`, modify `build_structural_context()` to accept and use `bfo_categories`:

```python
def build_structural_context(
    projected_graph, *, bfo_categories: dict[str, str] | None = None,
    max_children: int = 8, max_properties: int = 6,
) -> dict[str, str]:
```

The implementation changes:
1. Import `CATEGORY_PATTERNS` and `match_property` from `ontoquery.bfo`
2. After collecting parents/children/properties for each URI, check if `bfo_categories` provides a category
3. If yes, partition properties into constitutive (matched by `match_property` against the category's patterns) and contextual (everything else)
4. Build the context string as: `[Category] {constitutive}. {taxonomy}. {contextual}.`
5. If no category or `bfo_categories is None`, use existing uniform logic

The key change is in the per-URI loop (currently lines 98-116). Replace:

```python
    result: dict[str, str] = {}
    for uri in projected_graph.classes:
        parts: list[str] = []
        if uri in parents:
            parent_labels = sorted(set(_label(p) for p in parents[uri]))
            parts.append(f"SubClassOf: {_cap(parent_labels, max_children)}")
        if uri in children:
            child_labels = sorted(set(_label(c) for c in children[uri]))
            parts.append(f"HasSubClass: {_cap(child_labels, max_children)}")
        if uri in properties:
            prop_groups: dict[str, list[str]] = defaultdict(list)
            for prop_uri, target_uri in properties[uri]:
                target_label = _label(target_uri)
                if target_label not in prop_groups[_prop_label(prop_uri)]:
                    prop_groups[_prop_label(prop_uri)].append(target_label)
            for prop_name, targets in sorted(prop_groups.items())[:max_properties]:
                parts.append(f"{prop_name}: {_cap(targets, max_children)}")
        if parts:
            result[uri] = ". ".join(parts)
    return result
```

With:

```python
    if bfo_categories:
        from ontoquery.bfo import CATEGORY_PATTERNS, match_property

    result: dict[str, str] = {}
    for uri in projected_graph.classes:
        # Build taxonomy parts (always present)
        taxonomy_parts: list[str] = []
        if uri in parents:
            parent_labels = sorted(set(_label(p) for p in parents[uri]))
            taxonomy_parts.append(f"SubClassOf: {_cap(parent_labels, max_children)}")
        if uri in children:
            child_labels = sorted(set(_label(c) for c in children[uri]))
            taxonomy_parts.append(f"HasSubClass: {_cap(child_labels, max_children)}")

        # Build property groups
        prop_groups: dict[str, list[str]] = defaultdict(list)
        prop_uris_by_name: dict[str, str] = {}
        if uri in properties:
            for prop_uri, target_uri in properties[uri]:
                pname = _prop_label(prop_uri)
                target_label = _label(target_uri)
                if target_label not in prop_groups[pname]:
                    prop_groups[pname].append(target_label)
                if pname not in prop_uris_by_name:
                    prop_uris_by_name[pname] = prop_uri

        category = bfo_categories.get(uri, "") if bfo_categories else ""
        cat_patterns = CATEGORY_PATTERNS.get(category, []) if bfo_categories and category else []

        if cat_patterns:
            constitutive_parts: list[str] = []
            contextual_names: set[str] = set()

            for cp in cat_patterns:
                matched_targets: list[str] = []
                for pname, targets in prop_groups.items():
                    full_uri = prop_uris_by_name.get(pname, pname)
                    if match_property(full_uri, cp.property_patterns):
                        matched_targets.extend(targets)
                        contextual_names.add(pname)
                if matched_targets:
                    unique = sorted(set(matched_targets))
                    constitutive_parts.append(
                        f"{cp.role_prefix}: {_cap(unique, max_children)}")

            contextual_parts: list[str] = []
            for pname, targets in sorted(prop_groups.items())[:max_properties]:
                if pname not in contextual_names:
                    contextual_parts.append(f"{pname}: {_cap(targets, max_children)}")

            parts = [f"[{category}]"]
            if constitutive_parts:
                parts.extend(constitutive_parts)
            parts.extend(taxonomy_parts)
            parts.extend(contextual_parts)
            result[uri] = " ".join(parts[:1]) + " " + ". ".join(parts[1:]) if len(parts) > 1 else parts[0]
        else:
            parts = taxonomy_parts[:]
            for pname, targets in sorted(prop_groups.items())[:max_properties]:
                parts.append(f"{pname}: {_cap(targets, max_children)}")
            if parts:
                result[uri] = ". ".join(parts)

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ontoquery && uv run pytest tests/test_index.py -v`
Expected: All tests PASS (including existing ones — backward compat)

- [ ] **Step 5: Commit**

```bash
git add ontoquery/src/ontoquery/index.py ontoquery/tests/test_index.py
git commit -m "feat(ontoquery): category-aware build_structural_context with constitutive property foregrounding"
```

---

### Task 4: Wire Up Indexing CLI + Sidecar

**Files:**
- Modify: `ontoquery/src/ontoquery/cli.py`
- Modify: `ontoquery/tests/test_cli.py` (if CLI tests exist for index)

- [ ] **Step 1: Write failing test for sidecar output**

Add to `ontoquery/tests/test_bfo.py`:

```python
import json
from pathlib import Path


def test_sidecar_round_trip(tmp_path):
    """Classify, save to JSON, reload — should be identical."""
    from ontoquery.owl2vec import ProjectedGraph, SUBCLASS_OF

    graph = ProjectedGraph()
    graph.edges.append(("http://example.org/MyProcess", SUBCLASS_OF, "http://purl.obolibrary.org/obo/BFO_0000015"))
    graph.classes.add("http://example.org/MyProcess")
    graph.classes.add("http://purl.obolibrary.org/obo/BFO_0000015")

    categories = classify_bfo_categories(graph)
    sidecar_path = tmp_path / "bfo_categories.json"
    sidecar_path.write_text(json.dumps(categories))

    reloaded = json.loads(sidecar_path.read_text())
    assert reloaded == categories
    assert reloaded["http://example.org/MyProcess"] == "Process"
```

- [ ] **Step 2: Run test to verify it passes**

Run: `cd ontoquery && uv run pytest tests/test_bfo.py::test_sidecar_round_trip -v`
Expected: PASS (this tests the data format, not the CLI)

- [ ] **Step 3: Modify CLI `index` command**

In `ontoquery/src/ontoquery/cli.py`, after `projected = project_ontology(...)`, add BFO classification and pass to `build_structural_context`:

```python
    # Classify BFO categories from projected graph
    from ontoquery.bfo import classify_bfo_categories
    bfo_categories = classify_bfo_categories(projected)
    typer.echo(f"Classified {len(bfo_categories)} classes into BFO categories")

    structural_context = build_structural_context(projected, bfo_categories=bfo_categories)
```

After indexing, save the sidecar:

```python
    # Save BFO categories sidecar for downstream consumers
    import json as _json
    sidecar_path = chroma / "bfo_categories.json"
    sidecar_path.write_text(_json.dumps(bfo_categories))
    typer.echo(f"BFO categories sidecar saved to {sidecar_path}")
```

- [ ] **Step 4: Run existing CLI tests**

Run: `cd ontoquery && uv run pytest tests/test_cli.py -v`
Expected: All existing tests PASS

- [ ] **Step 5: Commit**

```bash
git add ontoquery/src/ontoquery/cli.py ontoquery/tests/test_bfo.py
git commit -m "feat(ontoquery): wire BFO classification into index CLI, save sidecar"
```

---

### Task 5: Add `semantic_role` to `VariationAxis`

**Files:**
- Modify: `refiner/src/refiner/models.py`
- Modify: `refiner/tests/test_structural_navigation.py`

- [ ] **Step 1: Write failing test**

Add to `refiner/tests/test_structural_navigation.py`:

```python
from refiner.models import VariationAxis


class TestVariationAxisSemanticRole:
    def test_semantic_role_defaults_empty(self):
        axis = VariationAxis(
            cco_class_uri="http://example.org/X",
            cco_class_label="X",
            rationale="test",
        )
        assert axis.semantic_role == ""

    def test_semantic_role_set(self):
        axis = VariationAxis(
            cco_class_uri="http://example.org/X",
            cco_class_label="X",
            rationale="test",
            semantic_role="agent",
        )
        assert axis.semantic_role == "agent"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd refiner && uv run pytest tests/test_structural_navigation.py::TestVariationAxisSemanticRole -v`
Expected: FAIL — `ValidationError` or `TypeError` for `semantic_role`

- [ ] **Step 3: Add field to model**

In `refiner/src/refiner/models.py`, add to `VariationAxis`:

```python
class VariationAxis(BaseModel):
    cco_class_uri: str
    cco_class_label: str
    bfo_category: str = ""
    vocabulary_concept: str = ""
    vocabulary_label: str = ""
    rationale: str
    derivation: AxisDerivation | None = None
    semantic_role: str = ""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd refiner && uv run pytest tests/test_structural_navigation.py::TestVariationAxisSemanticRole -v`
Expected: PASS

- [ ] **Step 5: Run full refiner test suite for regressions**

Run: `cd refiner && uv run pytest -x -q`
Expected: All tests PASS (default empty string is backward compatible)

- [ ] **Step 6: Commit**

```bash
git add refiner/src/refiner/models.py refiner/tests/test_structural_navigation.py
git commit -m "feat(refiner): add semantic_role field to VariationAxis"
```

---

### Task 6: Semantic Role Derivation

**Files:**
- Modify: `refiner/src/refiner/stages/anchor.py`
- Modify: `refiner/tests/test_structural_navigation.py`

- [ ] **Step 1: Write failing tests for `derive_role()`**

Add to `refiner/tests/test_structural_navigation.py`:

```python
from refiner.stages.anchor import derive_role


class TestDeriveRole:
    def test_process_participant_agent(self):
        role = derive_role(
            candidate_category="Agent",
            seed_category="Process",
            restriction_property="http://example.org/has_participant",
        )
        assert role == "agent"

    def test_process_participant_material(self):
        role = derive_role(
            candidate_category="MaterialEntity",
            seed_category="Process",
            restriction_property="http://example.org/has_participant",
        )
        assert role == "patient"

    def test_process_participant_ice(self):
        role = derive_role(
            candidate_category="InformationContentEntity",
            seed_category="Process",
            restriction_property="http://example.org/has_participant",
        )
        assert role == "information"

    def test_process_realizes(self):
        role = derive_role(
            candidate_category="Disposition",
            seed_category="Process",
            restriction_property="http://example.org/realizes",
        )
        assert role == "obligation"

    def test_process_input(self):
        role = derive_role(
            candidate_category="MaterialEntity",
            seed_category="Process",
            restriction_property="http://example.org/has_input",
        )
        assert role == "input"

    def test_process_output(self):
        role = derive_role(
            candidate_category="InformationContentEntity",
            seed_category="Process",
            restriction_property="http://example.org/has_output",
        )
        assert role == "output"

    def test_quality_inheres_in(self):
        role = derive_role(
            candidate_category="MaterialEntity",
            seed_category="Quality",
            restriction_property="http://example.org/inheres_in",
        )
        assert role == "bearer"

    def test_role_inheres_in(self):
        role = derive_role(
            candidate_category="Agent",
            seed_category="Role",
            restriction_property="http://example.org/inheres_in",
        )
        assert role == "bearer"

    def test_role_realized_in(self):
        role = derive_role(
            candidate_category="Process",
            seed_category="Role",
            restriction_property="http://example.org/realized_in",
        )
        assert role == "realization"

    def test_ice_is_about(self):
        role = derive_role(
            candidate_category="Agent",
            seed_category="InformationContentEntity",
            restriction_property="http://example.org/is_about",
        )
        assert role == "subject"

    def test_ice_depends_on(self):
        role = derive_role(
            candidate_category="MaterialEntity",
            seed_category="InformationContentEntity",
            restriction_property="http://example.org/generically_depends_on",
        )
        assert role == "medium"

    def test_fallback_no_restriction(self):
        role = derive_role(
            candidate_category="Agent",
            seed_category="",
            restriction_property="",
        )
        assert role == "agent"

    def test_fallback_process_category(self):
        role = derive_role(
            candidate_category="Process",
            seed_category="",
            restriction_property="",
        )
        assert role == "process"

    def test_fallback_facility(self):
        role = derive_role(
            candidate_category="Facility",
            seed_category="",
            restriction_property="",
        )
        assert role == "location"

    def test_fallback_unknown_category(self):
        role = derive_role(
            candidate_category="",
            seed_category="",
            restriction_property="",
        )
        assert role == ""

    def test_unmatched_property_falls_back_to_category(self):
        role = derive_role(
            candidate_category="Agent",
            seed_category="Process",
            restriction_property="http://example.org/some_unknown_prop",
        )
        assert role == "agent"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd refiner && uv run pytest tests/test_structural_navigation.py::TestDeriveRole -v`
Expected: FAIL — `ImportError: cannot import name 'derive_role'`

- [ ] **Step 3: Implement `derive_role()`**

Add to `refiner/src/refiner/stages/anchor.py`:

```python
from ontoquery.bfo import CATEGORY_PATTERNS, match_property


_PARTICIPANT_ROLE_BY_CATEGORY: dict[str, str] = {
    "Agent": "agent",
    "MaterialEntity": "patient",
    "MaterialArtifact": "patient",
    "InformationContentEntity": "information",
    "GenericallyDependentContinuant": "information",
    "Quality": "quality",
    "Role": "obligation",
    "Disposition": "obligation",
}

_FALLBACK_ROLES: dict[str, str] = {
    "Agent": "agent",
    "Process": "process",
    "Act": "process",
    "InformationContentEntity": "information",
    "GenericallyDependentContinuant": "information",
    "Quality": "quality",
    "Role": "role",
    "Disposition": "disposition",
    "MaterialEntity": "object",
    "MaterialArtifact": "object",
    "Facility": "location",
    "Site": "location",
}


def derive_role(
    candidate_category: str,
    seed_category: str,
    restriction_property: str,
) -> str:
    if seed_category and restriction_property:
        patterns = CATEGORY_PATTERNS.get(seed_category, [])
        for cp in patterns:
            if match_property(restriction_property, cp.property_patterns):
                prefix_lower = cp.role_prefix.lower()
                if "participant" in prefix_lower:
                    return _PARTICIPANT_ROLE_BY_CATEGORY.get(
                        candidate_category, "participant")
                if "realizes" in prefix_lower:
                    return "obligation"
                if "input" in prefix_lower or "output" in prefix_lower:
                    if match_property(restriction_property, ["has_input"]):
                        return "input"
                    return "output"
                if "characterizes" in prefix_lower or "borne by" in prefix_lower:
                    return "bearer"
                if "realized in" in prefix_lower:
                    return "realization"
                if "about" in prefix_lower:
                    return "subject"
                if "carried by" in prefix_lower or "concretized" in prefix_lower:
                    return "medium"
                return cp.role_prefix.lower().replace("/", "_").replace(" ", "_")
    return _FALLBACK_ROLES.get(candidate_category, "")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd refiner && uv run pytest tests/test_structural_navigation.py::TestDeriveRole -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add refiner/src/refiner/stages/anchor.py refiner/tests/test_structural_navigation.py
git commit -m "feat(refiner): add derive_role() for BFO pattern-based semantic role derivation"
```

---

### Task 7: Category-Aware Navigation Dispatch

**Files:**
- Modify: `refiner/src/refiner/stages/anchor.py`
- Modify: `refiner/tests/test_structural_navigation.py`

- [ ] **Step 1: Write failing tests for `_expand_by_category()`**

Add to `refiner/tests/test_structural_navigation.py`:

```python
from refiner.stages.anchor import _expand_by_category


class TestExpandByCategory:
    @pytest.fixture
    def base_kwargs(self):
        return dict(
            seed_label="TestSeed",
            confidence=0.9,
            predicate="skos:relatedMatch",
            vocab_concept=None,
            vocab_label=None,
            safety=set(),
            selected_domains=None,
        )

    def test_process_prioritizes_participant_restrictions(self, mock_onto, base_kwargs):
        mock_onto["get_restrictions"].return_value = [
            {"property": "http://ex.org/has_participant", "filler": "http://ex.org/Agent"},
            {"property": "http://ex.org/governed_by", "filler": "http://ex.org/Regulation"},
        ]
        mock_onto["get_class_definition"].side_effect = lambda uri: {
            "uri": uri, "label": uri.split("/")[-1], "definition": "test"}
        mock_onto["get_siblings"].return_value = []
        candidates = []
        _expand_by_category(
            category="Process",
            seed_uri="http://ex.org/DataCollection",
            onto_handlers=mock_onto,
            candidates=candidates,
            bfo_categories={"http://ex.org/Agent": "Agent"},
            **base_kwargs,
        )
        # Both restrictions should be followed
        uris = {c["uri"] for c in candidates}
        assert "http://ex.org/Agent" in uris
        assert "http://ex.org/Regulation" in uris
        # Constitutive (has_participant) should have higher confidence
        agent_c = next(c for c in candidates if c["uri"] == "http://ex.org/Agent")
        reg_c = next(c for c in candidates if c["uri"] == "http://ex.org/Regulation")
        assert agent_c["effective_confidence"] > reg_c["effective_confidence"]

    def test_ice_skips_siblings(self, mock_onto, base_kwargs):
        mock_onto["get_restrictions"].return_value = []
        mock_onto["get_siblings"].return_value = [
            {"uri": "http://ex.org/OtherDoc", "label": "OtherDoc"},
        ]
        mock_onto["get_class_definition"].return_value = None
        candidates = []
        _expand_by_category(
            category="InformationContentEntity",
            seed_uri="http://ex.org/Report",
            onto_handlers=mock_onto,
            candidates=candidates,
            bfo_categories={},
            **base_kwargs,
        )
        uris = {c["uri"] for c in candidates}
        assert "http://ex.org/OtherDoc" not in uris

    def test_quality_expands_siblings_aggressively(self, mock_onto, base_kwargs):
        mock_onto["get_restrictions"].return_value = []
        mock_onto["get_siblings"].return_value = [
            {"uri": "http://ex.org/GoodQuality", "label": "GoodQuality"},
            {"uri": "http://ex.org/PoorQuality", "label": "PoorQuality"},
        ]
        candidates = []
        _expand_by_category(
            category="Quality",
            seed_uri="http://ex.org/ImageQuality",
            onto_handlers=mock_onto,
            candidates=candidates,
            bfo_categories={},
            **base_kwargs,
        )
        uris = {c["uri"] for c in candidates}
        assert "http://ex.org/GoodQuality" in uris
        assert "http://ex.org/PoorQuality" in uris

    def test_fallback_for_unknown_category(self, mock_onto, base_kwargs):
        """Unknown category should behave like the existing uniform expansion."""
        mock_onto["get_restrictions"].return_value = [
            {"property": "http://ex.org/some_prop", "filler": "http://ex.org/Target"},
        ]
        mock_onto["get_class_definition"].side_effect = lambda uri: {
            "uri": uri, "label": uri.split("/")[-1], "definition": "test"}
        mock_onto["get_siblings"].return_value = [
            {"uri": "http://ex.org/Sibling", "label": "Sibling"},
        ]
        candidates = []
        _expand_by_category(
            category="",
            seed_uri="http://ex.org/Unknown",
            onto_handlers=mock_onto,
            candidates=candidates,
            bfo_categories={},
            **base_kwargs,
        )
        uris = {c["uri"] for c in candidates}
        assert "http://ex.org/Target" in uris
        assert "http://ex.org/Sibling" in uris
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd refiner && uv run pytest tests/test_structural_navigation.py::TestExpandByCategory -v`
Expected: FAIL — `ImportError: cannot import name '_expand_by_category'`

- [ ] **Step 3: Implement `_expand_by_category()`**

Add to `refiner/src/refiner/stages/anchor.py`:

```python
_SIBLING_AGGRESSIVE = {"Quality", "Role", "Disposition", "RealizableEntity"}
_SIBLING_CONDITIONAL = {"Process", "Act"}
_SIBLING_SKIP = {"InformationContentEntity", "GenericallyDependentContinuant"}
_CONDITIONAL_THRESHOLD = 4


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
    patterns = CATEGORY_PATTERNS.get(category, [])
    constitutive_props = set()
    for cp in patterns:
        for p in cp.property_patterns:
            constitutive_props.add(p)

    def _make_candidate(uri, label, conf, restriction_prop=""):
        return {
            "uri": uri,
            "label": label,
            "source": "structural",
            "path": [seed_uri, uri],
            "path_labels": [seed_label, label],
            "seed_uri": seed_uri,
            "seed_label": seed_label,
            "effective_confidence": conf,
            "predicate": predicate,
            "vocabulary_concept": vocab_concept,
            "vocabulary_label": vocab_label,
            "restriction_property": restriction_prop,
        }

    # --- Restriction expansion ---
    if onto_handlers.get("get_restrictions"):
        for r in onto_handlers["get_restrictions"](seed_uri):
            filler = r.get("filler", "")
            prop = r.get("property", "")
            if not filler or _is_excluded_uri(filler, safety):
                continue
            if selected_domains:
                domain = derive_source_ontology(filler)
                if domain and domain not in selected_domains:
                    continue
            filler_defn = onto_handlers["get_class_definition"](filler)
            if not filler_defn:
                continue
            filler_label = filler_defn.get("label", "")

            is_constitutive = bool(patterns) and match_property(
                prop, list(constitutive_props))
            conf_mult = 0.95 if is_constitutive else 0.8
            candidates.append(
                _make_candidate(filler, filler_label, confidence * conf_mult, prop))

    # --- Sibling expansion ---
    if category in _SIBLING_SKIP:
        pass
    elif category in _SIBLING_CONDITIONAL:
        structural_count = len(candidates)
        if structural_count < _CONDITIONAL_THRESHOLD:
            for s in onto_handlers["get_siblings"](seed_uri):
                s_uri = s["uri"]
                if _is_excluded_uri(s_uri, safety):
                    continue
                if selected_domains:
                    domain = derive_source_ontology(s_uri)
                    if domain and domain not in selected_domains:
                        continue
                candidates.append(
                    _make_candidate(s_uri, s.get("label", ""), confidence * 0.7))
    elif category in _SIBLING_AGGRESSIVE:
        for s in onto_handlers["get_siblings"](seed_uri):
            s_uri = s["uri"]
            if _is_excluded_uri(s_uri, safety):
                continue
            if selected_domains:
                domain = derive_source_ontology(s_uri)
                if domain and domain not in selected_domains:
                    continue
            candidates.append(
                _make_candidate(s_uri, s.get("label", ""), confidence * 0.85))
    else:
        # Default / fallback (unknown category or MaterialEntity, Agent, etc.)
        for s in onto_handlers["get_siblings"](seed_uri):
            s_uri = s["uri"]
            if _is_excluded_uri(s_uri, safety):
                continue
            if selected_domains:
                domain = derive_source_ontology(s_uri)
                if domain and domain not in selected_domains:
                    continue
            candidates.append(
                _make_candidate(s_uri, s.get("label", ""), confidence * 0.8))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd refiner && uv run pytest tests/test_structural_navigation.py::TestExpandByCategory -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add refiner/src/refiner/stages/anchor.py refiner/tests/test_structural_navigation.py
git commit -m "feat(refiner): add _expand_by_category() with constitutive restriction prioritization"
```

---

### Task 8: Wire Dispatch into `navigate_from_seeds()` and Enrichment

**Files:**
- Modify: `refiner/src/refiner/stages/anchor.py`
- Modify: `refiner/tests/test_structural_navigation.py`

- [ ] **Step 1: Write failing test for category-aware navigation**

Add to `refiner/tests/test_structural_navigation.py`:

```python
class TestNavigateCategoryAware:
    def test_related_match_uses_category_dispatch(self, mock_onto):
        """When bfo_categories is provided, relatedMatch should use _expand_by_category."""
        mock_onto["get_restrictions"].return_value = [
            {"property": "http://ex.org/has_participant", "filler": "http://ex.org/Agent"},
        ]
        mock_onto["get_class_definition"].side_effect = lambda uri: {
            "uri": uri, "label": uri.split("/")[-1], "definition": "test"}
        mock_onto["get_siblings"].return_value = []

        seeds = [{
            "object_id": "http://ex.org/DataCollection",
            "object_label": "DataCollection",
            "predicate_id": "skos:relatedMatch",
            "effective_confidence": 0.9,
            "vocabulary_concept": "risk:X",
            "vocabulary_label": "X",
        }]
        bfo_cats = {"http://ex.org/DataCollection": "Process"}
        result = navigate_from_seeds(
            seeds, mock_onto, selected_domains=None,
            bfo_categories=bfo_cats)

        agent = [c for c in result if c["uri"] == "http://ex.org/Agent"]
        assert len(agent) == 1
        # Constitutive confidence: 0.9 * 0.95 = 0.855
        assert abs(agent[0]["effective_confidence"] - 0.855) < 0.01

    def test_broad_match_unchanged_with_categories(self, mock_onto):
        """broadMatch should be unaffected by bfo_categories."""
        mock_onto["get_subclasses"].return_value = [
            {"uri": "http://ex.org/Sub1", "label": "Sub1"},
        ]
        seeds = [{
            "object_id": "http://ex.org/Parent",
            "object_label": "Parent",
            "predicate_id": "skos:broadMatch",
            "effective_confidence": 0.9,
            "vocabulary_concept": None,
            "vocabulary_label": None,
        }]
        result = navigate_from_seeds(
            seeds, mock_onto, selected_domains=None,
            bfo_categories={"http://ex.org/Parent": "Process"})
        assert len(result) >= 1
        assert result[0]["effective_confidence"] == 0.9

    def test_backward_compat_no_categories(self, mock_onto):
        """Without bfo_categories, behavior should be identical to before."""
        mock_onto["get_restrictions"].return_value = [
            {"property": "http://ex.org/prop", "filler": "http://ex.org/Filler"},
        ]
        mock_onto["get_class_definition"].side_effect = lambda uri: {
            "uri": uri, "label": uri.split("/")[-1], "definition": "test"}
        mock_onto["get_siblings"].return_value = [
            {"uri": "http://ex.org/Sibling", "label": "Sibling"},
        ]
        seeds = [{
            "object_id": "http://ex.org/Related",
            "object_label": "Related",
            "predicate_id": "skos:relatedMatch",
            "effective_confidence": 0.8,
            "vocabulary_concept": None,
            "vocabulary_label": None,
        }]
        result = navigate_from_seeds(seeds, mock_onto, selected_domains=None)
        uris = {c["uri"] for c in result}
        assert "http://ex.org/Related" in uris
        assert "http://ex.org/Filler" in uris
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd refiner && uv run pytest tests/test_structural_navigation.py::TestNavigateCategoryAware -v`
Expected: FAIL — `TypeError: navigate_from_seeds() got an unexpected keyword argument 'bfo_categories'`

- [ ] **Step 3: Modify `navigate_from_seeds()` signature and `relatedMatch` branch**

In `refiner/src/refiner/stages/anchor.py`, update `navigate_from_seeds`:

Add `bfo_categories: dict[str, str] | None = None` parameter.

In the `relatedMatch` branch, replace the restriction + sibling expansion (lines 267-311) with a call to `_expand_by_category`:

```python
        elif predicate == "skos:relatedMatch":
            # Seed itself is a candidate
            defn = onto_handlers["get_class_definition"](seed_uri)
            if defn:
                resolved_label = defn.get("label", mapping.get("object_label", ""))
                candidates.append({
                    "uri": seed_uri,
                    "label": resolved_label,
                    "source": "structural",
                    "path": [seed_uri],
                    "path_labels": [resolved_label],
                    "seed_uri": seed_uri,
                    "seed_label": seed_label,
                    "effective_confidence": confidence,
                    "predicate": predicate,
                    "vocabulary_concept": vocab_concept,
                    "vocabulary_label": vocab_label,
                })
            # Category-aware expansion
            seed_category = bfo_categories.get(seed_uri, "") if bfo_categories else ""
            _expand_by_category(
                category=seed_category,
                seed_uri=seed_uri,
                onto_handlers=onto_handlers,
                candidates=candidates,
                bfo_categories=bfo_categories or {},
                seed_label=seed_label,
                confidence=confidence,
                predicate=predicate,
                vocab_concept=vocab_concept,
                vocab_label=vocab_label,
                safety=safety,
                selected_domains=selected_domains,
            )
```

- [ ] **Step 4: Update `_process_single_risk()` to pass `bfo_categories`**

In `_process_single_risk()` (around line 747), load and pass `bfo_categories`:

```python
    structural = navigate_from_seeds(
        seed_mappings=ontology_seeds,
        onto_handlers=onto_handlers,
        selected_domains=selected_domains,
        generic_safety_uris=generic_safety_uris,
        bfo_categories=bfo_categories_map,
    )
```

The `bfo_categories_map` needs to be loaded from the sidecar. Add to `anchor()` function, before the processing loop:

```python
    # Load pre-computed BFO categories from sidecar (if available)
    bfo_categories_map: dict[str, str] = {}
    if onto_handlers:
        chroma_dir = onto_handlers.get("_chroma_dir")
        if chroma_dir:
            sidecar = Path(chroma_dir) / "bfo_categories.json"
            if sidecar.exists():
                import json
                bfo_categories_map = json.loads(sidecar.read_text())
```

Thread `bfo_categories_map` into `shared_kwargs` and `_process_single_risk`.

- [ ] **Step 5: Update enrichment to derive and attach `semantic_role`**

In the enrichment loop (around line 815-833), after `derive_bfo_category()`, add:

```python
        restriction_prop = c.get("restriction_property", "")
        seed_cat = bfo_categories_map.get(c.get("seed_uri", ""), "")
        sem_role = derive_role(bfo_cat, seed_cat, restriction_prop)
```

And in the enriched dict:

```python
            "semantic_role": sem_role,
```

Update the LLM prompt candidate block (around line 847):

```python
        role_tag = f"/{e['semantic_role']}" if e.get("semantic_role") else ""
        cat_tag = f" [{e['bfo_category']}{role_tag}]" if e["bfo_category"] else ""
```

Update the `VariationAxis` construction (around line 931):

```python
            semantic_role=enriched_match.get("semantic_role", "") if enriched_match else "",
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd refiner && uv run pytest tests/test_structural_navigation.py -v`
Expected: All tests PASS

- [ ] **Step 7: Run full refiner test suite**

Run: `cd refiner && uv run pytest -x -q`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
git add refiner/src/refiner/stages/anchor.py refiner/tests/test_structural_navigation.py
git commit -m "feat(refiner): wire category-aware dispatch into navigate_from_seeds and enrichment"
```

---

### Task 9: Migrate `_BFO_CATEGORIES` Import

**Files:**
- Modify: `refiner/src/refiner/stages/anchor.py`

- [ ] **Step 1: Replace `_BFO_CATEGORIES` with import from `ontoquery.bfo`**

In `refiner/src/refiner/stages/anchor.py`:

1. Remove the `_BFO_CATEGORIES` dict definition (lines 106-129)
2. Add import: `from ontoquery.bfo import BFO_CATEGORY_MAP`
3. Update `derive_bfo_category()` to use `BFO_CATEGORY_MAP` instead of `_BFO_CATEGORIES`:

```python
def derive_bfo_category(
    class_uri: str,
    onto_handlers: dict,
    max_depth: int = 10,
    bfo_fallbacks: dict[str, str] | None = None,
) -> str:
    visited = set()
    current = class_uri
    for _ in range(max_depth):
        if current in BFO_CATEGORY_MAP:
            return BFO_CATEGORY_MAP[current]
        if current in visited:
            break
        visited.add(current)
        supers = onto_handlers["get_superclasses"](current)
        named = [s for s in supers if s.get("uri") and s["uri"] not in visited]
        if not named:
            break
        current = named[0]["uri"]
    if bfo_fallbacks and class_uri in bfo_fallbacks:
        return bfo_fallbacks[class_uri]
    return ""
```

- [ ] **Step 2: Run existing `TestDeriveBfoCategory` tests**

Run: `cd refiner && uv run pytest tests/test_structural_navigation.py::TestDeriveBfoCategory -v`
Expected: All tests PASS (behavior unchanged, just source of dict moved)

- [ ] **Step 3: Run full test suite**

Run: `cd refiner && uv run pytest -x -q`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add refiner/src/refiner/stages/anchor.py
git commit -m "refactor(refiner): import BFO_CATEGORY_MAP from ontoquery.bfo, remove local duplicate"
```

---

### Task 10: Integration Smoke Test

**Files:** No new files — validation only.

- [ ] **Step 1: Run full ontoquery test suite**

Run: `cd ontoquery && uv run pytest -v`
Expected: All ~139 tests PASS

- [ ] **Step 2: Run full refiner test suite**

Run: `cd refiner && uv run pytest -v`
Expected: All ~350 tests PASS

- [ ] **Step 3: Verify no import cycles**

Run: `cd refiner && uv run python -c "from refiner.stages.anchor import anchor, navigate_from_seeds, derive_bfo_category, derive_role, _expand_by_category; print('OK')"`
Expected: `OK`

Run: `cd ontoquery && uv run python -c "from ontoquery.bfo import BFO_CATEGORY_MAP, CATEGORY_PATTERNS, classify_bfo_categories, match_property; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit (if any fixups needed)**

```bash
git add -A
git commit -m "test: integration smoke test for category-aware deep semantics"
```

---

Plan complete and saved to `docs/superpowers/plans/2026-04-20-category-aware-deep-semantics.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?