# CCO→Commons Bridge Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a bridge ontology (14 `rdfs:subClassOf` axioms in a TTL file) and extend `_CATEGORY_ROLES` in anchor.py (~15 entries) so that FIBO/Commons classes get semantic roles during the anchor stage's `derive_roles()` walk.

**Architecture:** A standalone Turtle file (`ontologies/bridges/cco-commons.ttl`) declares CCO classes as subclasses of Commons classes. The file is included in the `ontoquery index` command and becomes part of the graph automatically. The `_CATEGORY_ROLES` dict in `anchor.py` is extended with Commons URIs so `derive_roles()` returns roles when walking through Commons classes. The justfile recipe is updated to include the bridge directory.

**Tech Stack:** OWL/Turtle (ontology), Python (anchor.py), pytest (tests)

---

## File Structure

```
ontologies/
  bridges/
    cco-commons.ttl          # CREATE — 14 rdfs:subClassOf bridge axioms

refiner/
  src/refiner/stages/
    anchor.py                # MODIFY — extend _CATEGORY_ROLES (lines 16-38) and docstring (line 42)
  tests/
    test_anchor.py           # MODIFY — add tests for Commons role derivation

justfile                     # MODIFY — update index-ontologies recipe (line 198-205)
```

---

### Task 1: Create bridge TTL file

**Files:**
- Create: `ontologies/bridges/cco-commons.ttl`

- [ ] **Step 1: Create the bridges directory and TTL file**

Create `ontologies/bridges/cco-commons.ttl` with these exact contents:

```turtle
@prefix rdf:      <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs:     <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl:      <http://www.w3.org/2002/07/owl#> .
@prefix cco:      <https://www.commoncoreontologies.org/> .
@prefix cmns-pts: <https://www.omg.org/spec/Commons/PartiesAndSituations/> .
@prefix cmns-org: <https://www.omg.org/spec/Commons/Organizations/> .
@prefix cmns-rlcmp: <https://www.omg.org/spec/Commons/RolesAndCompositions/> .
@prefix cmns-doc: <https://www.omg.org/spec/Commons/Documents/> .
@prefix cmns-id:  <https://www.omg.org/spec/Commons/Identifiers/> .
@prefix cmns-loc: <https://www.omg.org/spec/Commons/Locations/> .

<https://www.commoncoreontologies.org/bridges/cco-commons>
    rdf:type owl:Ontology ;
    rdfs:label "CCO-Commons Bridge Ontology" ;
    rdfs:comment "Bridge axioms mapping CCO classes to OMG Commons classes for FIBO interoperability. All axioms are rdfs:subClassOf (conservative, no owl:equivalentClass)." .

# --- Entity Bridges (7) ---

# Agent → Agent
cco:ont00001017 rdfs:subClassOf cmns-pts:Agent .

# Person → Party
cco:ont00001262 rdfs:subClassOf cmns-pts:Party .

# Person → LegalPerson
cco:ont00001262 rdfs:subClassOf cmns-org:LegalPerson .

# Organization → FormalOrganization
cco:ont00001180 rdfs:subClassOf cmns-org:FormalOrganization .

# Document Content Entity → Document
cco:ont00002039 rdfs:subClassOf cmns-doc:Document .

# Legal Instrument → LegalDocument
cco:ont00001346 rdfs:subClassOf cmns-doc:LegalDocument .

# Geospatial Region → Location
cco:ont00000472 rdfs:subClassOf cmns-loc:Location .

# --- Identifier Bridge (1) ---

# Designative ICE → Identifier
cco:ont00000686 rdfs:subClassOf cmns-id:Identifier .

# --- Role Bridges (6) ---

# Authority Role → StructuralRole
cco:ont00000187 rdfs:subClassOf cmns-rlcmp:StructuralRole .

# Occupation Role → FunctionalRole
cco:ont00000984 rdfs:subClassOf cmns-rlcmp:FunctionalRole .

# Organization Member Role → PartyRole
cco:ont00000175 rdfs:subClassOf cmns-pts:PartyRole .

# Commercial Role → StructuralRole
cco:ont00000485 rdfs:subClassOf cmns-rlcmp:StructuralRole .

# Citizen Role → PartyRole
cco:ont00000987 rdfs:subClassOf cmns-pts:PartyRole .

# Contractor Role → FunctionalRole
cco:ont00000506 rdfs:subClassOf cmns-rlcmp:FunctionalRole .
```

- [ ] **Step 2: Verify the TTL is valid syntax**

Run: `cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner && python3 -c "from rdflib import Graph; g = Graph(); g.parse('ontologies/bridges/cco-commons.ttl', format='turtle'); print(f'{len(g)} triples loaded'); assert len(g) == 17, f'Expected 17, got {len(g)}'"`

Expected: `17 triples loaded` (14 subClassOf + 1 rdf:type + 1 rdfs:label + 1 rdfs:comment). No parse errors.

- [ ] **Step 3: Commit**

```bash
git add ontologies/bridges/cco-commons.ttl
git commit -m "feat: add CCO→Commons bridge ontology (14 axioms)"
```

---

### Task 2: Extend `_CATEGORY_ROLES` with Commons URIs

**Files:**
- Modify: `refiner/src/refiner/stages/anchor.py:16-38`
- Test: `refiner/tests/test_anchor.py`

- [ ] **Step 1: Write failing tests for Commons role derivation**

Add these tests to `refiner/tests/test_anchor.py`, after the existing `test_derive_roles_multi_hop` function (around line 186):

```python
def test_derive_roles_commons_agent(mock_onto_handlers):
    """FIBO class walking to Commons Agent should get ['agent'] roles."""
    mock_onto_handlers["get_superclasses"].side_effect = lambda uri: {
        "http://example.org/FiboBank": [{"uri": "https://www.omg.org/spec/Commons/Organizations/FormalOrganization", "label": "FormalOrganization"}],
    }.get(uri, [])
    roles = derive_roles("http://example.org/FiboBank", mock_onto_handlers)
    assert roles == ["agent"]


def test_derive_roles_commons_document(mock_onto_handlers):
    """FIBO class walking to Commons Document should get ['object'] roles."""
    mock_onto_handlers["get_superclasses"].side_effect = lambda uri: {
        "http://example.org/FiboContract": [{"uri": "https://www.omg.org/spec/Commons/Documents/LegalDocument", "label": "LegalDocument"}],
    }.get(uri, [])
    roles = derive_roles("http://example.org/FiboContract", mock_onto_handlers)
    assert roles == ["object"]


def test_derive_roles_commons_location(mock_onto_handlers):
    """FIBO class walking to Commons Location should get ['location'] roles."""
    mock_onto_handlers["get_superclasses"].side_effect = lambda uri: {
        "http://example.org/FiboCountry": [{"uri": "https://www.omg.org/spec/Commons/Locations/Location", "label": "Location"}],
    }.get(uri, [])
    roles = derive_roles("http://example.org/FiboCountry", mock_onto_handlers)
    assert roles == ["location"]


def test_derive_roles_commons_functional_role(mock_onto_handlers):
    """FIBO class walking to Commons FunctionalRole should get ['agent', 'instrument']."""
    mock_onto_handlers["get_superclasses"].side_effect = lambda uri: {
        "http://example.org/FiboLendingOfficer": [{"uri": "https://www.omg.org/spec/Commons/RolesAndCompositions/FunctionalRole", "label": "FunctionalRole"}],
    }.get(uri, [])
    roles = derive_roles("http://example.org/FiboLendingOfficer", mock_onto_handlers)
    assert roles == ["agent", "instrument"]


def test_derive_roles_commons_identifier(mock_onto_handlers):
    """FIBO class walking to Commons Identifier should get ['object', 'instrument']."""
    mock_onto_handlers["get_superclasses"].side_effect = lambda uri: {
        "http://example.org/FiboLEI": [{"uri": "https://www.omg.org/spec/Commons/Identifiers/Identifier", "label": "Identifier"}],
    }.get(uri, [])
    roles = derive_roles("http://example.org/FiboLEI", mock_onto_handlers)
    assert roles == ["object", "instrument"]


def test_derive_roles_facility_direct(mock_onto_handlers):
    """CCO Facility should get ['location'] via direct _CATEGORY_ROLES entry (no bridge axiom)."""
    roles = derive_roles("https://www.commoncoreontologies.org/ont00000192", mock_onto_handlers)
    assert roles == ["location"]


def test_derive_roles_commons_multi_hop(mock_onto_handlers):
    """FIBO class 2 hops from Commons should still resolve roles."""
    mock_onto_handlers["get_superclasses"].side_effect = lambda uri: {
        "http://example.org/FiboCorp": [{"uri": "http://example.org/FiboLegalEntity", "label": "LegalEntity"}],
        "http://example.org/FiboLegalEntity": [{"uri": "https://www.omg.org/spec/Commons/Organizations/LegalEntity", "label": "LegalEntity"}],
    }.get(uri, [])
    roles = derive_roles("http://example.org/FiboCorp", mock_onto_handlers)
    assert roles == ["agent"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/refiner && uv run pytest tests/test_anchor.py::test_derive_roles_commons_agent tests/test_anchor.py::test_derive_roles_commons_document tests/test_anchor.py::test_derive_roles_commons_location tests/test_anchor.py::test_derive_roles_commons_functional_role tests/test_anchor.py::test_derive_roles_commons_identifier tests/test_anchor.py::test_derive_roles_facility_direct tests/test_anchor.py::test_derive_roles_commons_multi_hop -v`

Expected: All 7 FAIL — Commons URIs and Facility URI not in `_CATEGORY_ROLES`.

- [ ] **Step 3: Extend `_CATEGORY_ROLES` in anchor.py**

In `refiner/src/refiner/stages/anchor.py`, replace lines 16-38 (the comment block and `_CATEGORY_ROLES` dict) with:

```python
# BFO/CCO/Commons category → semantic roles mapping.
# More specific categories are checked first (via superclass walk),
# falling back to broader categories.
_CATEGORY_ROLES: dict[str, list[str]] = {
    # CCO categories (more specific — checked first)
    "https://www.commoncoreontologies.org/ont00001017": ["agent"],               # Agent
    "https://www.commoncoreontologies.org/ont00000995": ["object", "instrument"],  # Material Artifact
    "https://www.commoncoreontologies.org/ont00000005": ["object"],               # Act (process)
    "https://www.commoncoreontologies.org/ont00000958": ["object", "instrument"],  # Information Content Entity
    "https://www.commoncoreontologies.org/ont00000192": ["location"],             # Facility (not bridged — Material Artifact, not spatial)
    # BFO categories (broader fallback)
    "http://purl.obolibrary.org/obo/BFO_0000040": ["agent", "object"],   # material entity
    "http://purl.obolibrary.org/obo/BFO_0000015": ["object"],            # process
    "http://purl.obolibrary.org/obo/BFO_0000023": ["agent"],             # role (bearer acts)
    "http://purl.obolibrary.org/obo/BFO_0000016": ["instrument"],        # disposition
    "http://purl.obolibrary.org/obo/BFO_0000031": ["object"],            # generically dependent continuant
    "http://purl.obolibrary.org/obo/BFO_0000019": ["object"],            # quality
    "http://purl.obolibrary.org/obo/BFO_0000029": ["location"],          # site
    "http://purl.obolibrary.org/obo/BFO_0000006": ["location"],          # spatial region
    "http://purl.obolibrary.org/obo/BFO_0000141": ["location"],          # immaterial entity
    "http://purl.obolibrary.org/obo/BFO_0000008": ["temporal"],          # temporal region
    # Commons categories (reached via FIBO superclass chains)
    "https://www.omg.org/spec/Commons/PartiesAndSituations/Agent": ["agent"],
    "https://www.omg.org/spec/Commons/PartiesAndSituations/Party": ["agent"],
    "https://www.omg.org/spec/Commons/PartiesAndSituations/PartyRole": ["agent"],
    "https://www.omg.org/spec/Commons/RolesAndCompositions/Role": ["agent"],
    "https://www.omg.org/spec/Commons/RolesAndCompositions/FunctionalRole": ["agent", "instrument"],
    "https://www.omg.org/spec/Commons/RolesAndCompositions/StructuralRole": ["agent"],
    "https://www.omg.org/spec/Commons/Organizations/Organization": ["agent"],
    "https://www.omg.org/spec/Commons/Organizations/FormalOrganization": ["agent"],
    "https://www.omg.org/spec/Commons/Organizations/LegalEntity": ["agent"],
    "https://www.omg.org/spec/Commons/Organizations/LegalPerson": ["agent"],
    "https://www.omg.org/spec/Commons/Documents/Document": ["object"],
    "https://www.omg.org/spec/Commons/Documents/LegalDocument": ["object"],
    "https://www.omg.org/spec/Commons/Identifiers/Identifier": ["object", "instrument"],
    "https://www.omg.org/spec/Commons/Locations/Location": ["location"],
}
```

Also update the comment on `derive_roles` docstring (line 42):

```python
def derive_roles(class_uri: str, onto_handlers: dict, max_depth: int = 10) -> list[str] | None:
    """Walk superclass chain looking for BFO/CCO/Commons categories. Returns roles or None."""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/refiner && uv run pytest tests/test_anchor.py -v`

Expected: All tests pass, including the 7 new ones and all existing ones.

- [ ] **Step 5: Commit**

```bash
cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/refiner
git add src/refiner/stages/anchor.py tests/test_anchor.py
git commit -m "feat(refiner): extend _CATEGORY_ROLES with Commons URIs for FIBO role derivation"
```

---

### Task 3: Update justfile index recipe

**Files:**
- Modify: `justfile:197-205`

- [ ] **Step 1: Update `index-ontologies` recipe to include bridge directory**

In the root `justfile`, update the `index-ontologies` recipe to add `../ontologies/bridges/` as an additional directory:

```just
# Index all ontologies into ontoquery ChromaDB (CCO + Commons + FIBO + OBO + D3FEND + CSO + bridges)
index-ontologies:
    cd ontoquery && uv run ontoquery index \
        ../ontologies/CommonCoreOntologies/src/cco-modules/ \
        ../ontologies/commons/ \
        ../ontologies/fibo/ \
        ../ontologies/obo/ \
        ../ontologies/d3fend-ontology/src/ontology/d3fend-protege.ttl \
        ../ontologies/cso/ \
        ../ontologies/bridges/
```

- [ ] **Step 2: Verify the recipe parses**

Run: `cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner && just --list | grep index`

Expected: `index-ontologies` appears in the list.

- [ ] **Step 3: Commit**

```bash
cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner
git add justfile
git commit -m "build: add bridges directory to index-ontologies recipe"
```

---

### Task 4: Run full test suite and verify no regressions

**Files:**
- None (verification only)

- [ ] **Step 1: Run all refiner tests**

Run: `cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/refiner && uv run pytest tests/ -v`

Expected: All 290 tests pass (283 current + 7 new).

- [ ] **Step 2: Verify bridge file parses cleanly with rdflib**

Run: `cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner && python3 -c "from rdflib import Graph; g = Graph(); g.parse('ontologies/bridges/cco-commons.ttl', format='turtle'); subs = [str(s) for s, p, o in g if str(p) == 'http://www.w3.org/2000/01/rdf-schema#subClassOf']; print(f'{len(subs)} subClassOf axioms'); assert len(subs) == 14, f'Expected 14, got {len(subs)}'"`

Expected: `14 subClassOf axioms`
