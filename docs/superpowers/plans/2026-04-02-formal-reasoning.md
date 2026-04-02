# Formal Reasoning Integration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract OWL axioms (restrictions, disjointness, equivalences) from ontology stores and use them for disjointness validation in contextualize and restriction-based candidate discovery in anchor.

**Architecture:** New `axioms.py` module in ontoquery extracts axioms from the graph backend at index time, persists as JSON sidecar. Backend protocol extended with 3 new methods backed by dict lookups. Pipeline stages consume axioms via `onto_handlers` dict with `.get()` guards for backward compatibility.

**Tech Stack:** pyoxigraph, rdflib, pytest, existing ontoquery + refiner packages

---

## File Structure

| File | Responsibility |
|------|---------------|
| `ontoquery/src/ontoquery/axioms.py` | **New.** Axiom extraction from oxigraph/rdflib stores, RDF list traversal, JSON persistence, filtering |
| `ontoquery/src/ontoquery/backend.py` | Add `axioms` param to constructors, 3 new protocol methods, factory wiring |
| `ontoquery/src/ontoquery/mcp_server.py` | 3 new tool handlers + MCP tool definitions |
| `ontoquery/src/ontoquery/cli.py` | Wire axiom extraction into `index` command |
| `refiner/src/refiner/stages/contextualize.py` | Disjointness post-filter, restriction context in prompt |
| `refiner/src/refiner/stages/anchor.py` | Restriction/equivalence candidate expansion after `expand_candidates()` |
| `refiner/src/refiner/evaluate.py` | 3 new event handlers in `aggregate_stage_quality`, 2 new metric functions |
| `refiner/tests/conftest.py` | Add 3 new mock handlers to `mock_onto_handlers` fixture |
| `ontoquery/tests/test_axioms.py` | **New.** Tests for extraction, persistence, RDF list traversal |
| `ontoquery/tests/test_backend.py` | Constructor injection tests, new method tests, graceful degradation |
| `ontoquery/tests/test_mcp_server.py` | New tool handler tests |
| `refiner/tests/test_contextualize.py` | Disjointness filtering tests |
| `refiner/tests/test_anchor.py` | Restriction/equivalence expansion tests |
| `refiner/tests/test_evaluate.py` | New event handler + metric tests |

---

### Task 1: Axiom Extraction Module — Core Functions

**Files:**
- Create: `ontoquery/src/ontoquery/axioms.py`
- Create: `ontoquery/tests/test_axioms.py`

This task implements the extraction functions, RDF list traversal, and JSON persistence — all tested against in-memory rdflib graphs with synthetic OWL axioms.

- [ ] **Step 1: Write test fixtures and disjointness extraction test**

```python
# ontoquery/tests/test_axioms.py
import pytest
from rdflib import Graph, RDF, OWL, RDFS, URIRef, BNode, Namespace


EX = Namespace("http://example.org/ont#")

DISJOINT_TTL = """\
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix ex: <http://example.org/ont#> .

ex:A a owl:Class ; rdfs:label "A" .
ex:B a owl:Class ; rdfs:label "B" .
ex:C a owl:Class ; rdfs:label "C" .
ex:A owl:disjointWith ex:B .
"""

RESTRICTION_TTL = """\
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix ex: <http://example.org/ont#> .

ex:Parent a owl:Class ; rdfs:label "Parent" .
ex:Filler a owl:Class ; rdfs:label "Filler" .
ex:prop a owl:ObjectProperty .

ex:Child a owl:Class ;
    rdfs:label "Child" ;
    rdfs:subClassOf ex:Parent ;
    rdfs:subClassOf [
        a owl:Restriction ;
        owl:onProperty ex:prop ;
        owl:someValuesFrom ex:Filler
    ] .
"""

EQUIVALENCE_TTL = """\
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix ex: <http://example.org/ont#> .

ex:Base a owl:Class ; rdfs:label "Base" .
ex:Other a owl:Class ; rdfs:label "Other" .
ex:prop a owl:ObjectProperty .

ex:Equiv a owl:Class ;
    rdfs:label "Equiv" ;
    owl:equivalentClass [
        owl:intersectionOf ( ex:Base [
            a owl:Restriction ;
            owl:onProperty ex:prop ;
            owl:someValuesFrom ex:Other
        ] )
    ] .
"""

ALL_DISJOINT_TTL = """\
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix ex: <http://example.org/ont#> .

ex:X a owl:Class ; rdfs:label "X" .
ex:Y a owl:Class ; rdfs:label "Y" .
ex:Z a owl:Class ; rdfs:label "Z" .

[] a owl:AllDisjointClasses ;
   owl:members ( ex:X ex:Y ex:Z ) .
"""

SIMPLE_EQUIV_TTL = """\
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix ex: <http://example.org/ont#> .

ex:Alpha a owl:Class ; rdfs:label "Alpha" .
ex:Beta a owl:Class ; rdfs:label "Beta" .
ex:Alpha owl:equivalentClass ex:Beta .
"""


def _make_graph(ttl: str) -> Graph:
    g = Graph()
    g.parse(data=ttl, format="turtle")
    return g


def test_extract_disjointness_pairwise():
    from ontoquery.axioms import extract_disjointness
    g = _make_graph(DISJOINT_TTL)
    result = extract_disjointness(g)
    assert "http://example.org/ont#A" in result
    assert "http://example.org/ont#B" in result[str(EX.A)]
    # Symmetric
    assert "http://example.org/ont#A" in result[str(EX.B)]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ontoquery && uv run pytest tests/test_axioms.py::test_extract_disjointness_pairwise -v`
Expected: FAIL with `ModuleNotFoundError` or `ImportError`

- [ ] **Step 3: Write axioms.py with disjointness extraction**

```python
# ontoquery/src/ontoquery/axioms.py
"""OWL axiom extraction, persistence, and loading.

Extracts restrictions, disjointness, and equivalence axioms from
graph stores (oxigraph or rdflib). Uses _query_triples() adapter to
abstract over both APIs. Persisted as JSON sidecar alongside the
oxigraph store.
"""

import json
import logging
from pathlib import Path

from rdflib import RDF, OWL, RDFS, URIRef, BNode, Graph

logger = logging.getLogger(__name__)

try:
    import pyoxigraph as ox
    _HAS_OXIGRAPH = True
except ImportError:
    _HAS_OXIGRAPH = False


def _is_named(node) -> bool:
    """Check if a node is a named (URI) node in either rdflib or oxigraph."""
    if isinstance(node, URIRef):
        return True
    if _HAS_OXIGRAPH and isinstance(node, ox.NamedNode):
        return True
    return False


def _is_blank(node) -> bool:
    """Check if a node is a blank node in either rdflib or oxigraph."""
    if isinstance(node, BNode):
        return True
    if _HAS_OXIGRAPH and isinstance(node, ox.BlankNode):
        return True
    return False


def _node_str(node) -> str:
    """Get string value from a named node (rdflib URIRef or oxigraph NamedNode)."""
    if isinstance(node, URIRef):
        return str(node)
    if _HAS_OXIGRAPH and isinstance(node, ox.NamedNode):
        return node.value
    return str(node)


def _to_node(uri_str: str, store):
    """Convert a URI string to the appropriate node type for the store."""
    if isinstance(store, Graph):
        return URIRef(uri_str)
    if _HAS_OXIGRAPH and isinstance(store, ox.Store):
        return ox.NamedNode(uri_str)
    return URIRef(uri_str)


def _query_triples(store, subject, predicate, obj):
    """Yield (s, p, o) triples matching the pattern. Works with oxigraph Store or rdflib Graph."""
    if isinstance(store, Graph):
        yield from store.triples((subject, predicate, obj))
    elif _HAS_OXIGRAPH and isinstance(store, ox.Store):
        for quad in store.quads_for_pattern(subject, predicate, obj, None):
            yield quad.subject, quad.predicate, quad.object


def _query_objects(store, subject, predicate):
    """Yield objects matching (subject, predicate, ?)."""
    for _, _, o in _query_triples(store, subject, predicate, None):
        yield o


def _traverse_rdf_list(store, list_head) -> list:
    """Walk rdf:first/rdf:rest chain, return list of nodes."""
    rdf_first = _to_node(str(RDF.first), store)
    rdf_rest = _to_node(str(RDF.rest), store)
    rdf_nil = _to_node(str(RDF.nil), store)

    items = []
    current = list_head
    while current is not None:
        if _is_named(current) and _node_str(current) == str(RDF.nil):
            break
        firsts = list(_query_objects(store, current, rdf_first))
        if firsts:
            items.append(firsts[0])
        rests = list(_query_objects(store, current, rdf_rest))
        current = rests[0] if rests else None
    return items


def _get_raw_store(backend):
    """Get the raw store from a GraphBackend (oxigraph Store or rdflib Graph)."""
    if hasattr(backend, '_store'):
        return backend._store
    if hasattr(backend, '_graph'):
        return backend._graph
    raise TypeError(f"Cannot extract raw store from {type(backend)}")


def extract_disjointness(store) -> dict[str, list[str]]:
    """Extract disjointness declarations (symmetric)."""
    result: dict[str, list[str]] = {}

    owl_disjoint = _to_node(str(OWL.disjointWith), store)
    rdf_type = _to_node(str(RDF.type), store)
    owl_all_disjoint = _to_node(str(OWL.AllDisjointClasses), store)
    owl_members = _to_node(str(OWL.members), store)

    def _add_pair(a: str, b: str):
        result.setdefault(a, [])
        result.setdefault(b, [])
        if b not in result[a]:
            result[a].append(b)
        if a not in result[b]:
            result[b].append(a)

    # Pattern 1: <class> owl:disjointWith <other>
    for s, _, o in _query_triples(store, None, owl_disjoint, None):
        if _is_named(s) and _is_named(o):
            _add_pair(_node_str(s), _node_str(o))

    # Pattern 2: [] a owl:AllDisjointClasses ; owl:members (...)
    for bnode, _, _ in _query_triples(store, None, rdf_type, owl_all_disjoint):
        for members_head in _query_objects(store, bnode, owl_members):
            members = _traverse_rdf_list(store, members_head)
            named = [_node_str(m) for m in members if _is_named(m)]
            for i, a in enumerate(named):
                for b in named[i + 1:]:
                    _add_pair(a, b)

    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ontoquery && uv run pytest tests/test_axioms.py::test_extract_disjointness_pairwise -v`
Expected: PASS

- [ ] **Step 5: Add restriction extraction test**

Add to `ontoquery/tests/test_axioms.py`:

```python
def test_extract_restrictions_from_subclass():
    from ontoquery.axioms import extract_restrictions
    g = _make_graph(RESTRICTION_TTL)
    result = extract_restrictions(g)
    child_uri = str(EX.Child)
    assert child_uri in result
    restrictions = result[child_uri]
    assert len(restrictions) == 1
    assert restrictions[0]["type"] == "someValuesFrom"
    assert restrictions[0]["property"] == str(EX.prop)
    assert restrictions[0]["filler"] == str(EX.Filler)
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd ontoquery && uv run pytest tests/test_axioms.py::test_extract_restrictions_from_subclass -v`
Expected: FAIL with `ImportError`

- [ ] **Step 7: Implement extract_restrictions**

Add to `ontoquery/src/ontoquery/axioms.py`:

```python
def _extract_restriction(store, bnode) -> dict | None:
    """Extract a single OWL restriction from a blank node."""
    rdf_type = _to_node(str(RDF.type), store)
    owl_restriction = _to_node(str(OWL.Restriction), store)
    owl_on_property = _to_node(str(OWL.onProperty), store)

    if not any(_query_triples(store, bnode, rdf_type, owl_restriction)):
        return None
    prop = None
    for p in _query_objects(store, bnode, owl_on_property):
        if _is_named(p):
            prop = _node_str(p)
            break
    if prop is None:
        return None
    for pred_name, pred_str in [
        ("someValuesFrom", str(OWL.someValuesFrom)),
        ("allValuesFrom", str(OWL.allValuesFrom)),
        ("hasValue", str(OWL.hasValue)),
    ]:
        pred = _to_node(pred_str, store)
        for filler in _query_objects(store, bnode, pred):
            if _is_named(filler):
                return {"type": pred_name, "property": prop, "filler": _node_str(filler)}
    return None


def extract_restrictions(store) -> dict[str, list[dict]]:
    """Extract OWL restrictions from rdfs:subClassOf and owl:equivalentClass."""
    result: dict[str, list[dict]] = {}
    rdfs_subclass = _to_node(str(RDFS.subClassOf), store)
    owl_equiv = _to_node(str(OWL.equivalentClass), store)
    owl_intersection = _to_node(str(OWL.intersectionOf), store)

    # Pattern 1: <class> rdfs:subClassOf <bnode> where bnode is owl:Restriction
    for s, _, o in _query_triples(store, None, rdfs_subclass, None):
        if not _is_named(s) or not _is_blank(o):
            continue
        r = _extract_restriction(store, o)
        if r:
            result.setdefault(_node_str(s), []).append(r)

    # Pattern 2: restrictions inside owl:equivalentClass intersections
    for s, _, o in _query_triples(store, None, owl_equiv, None):
        if not _is_named(s) or not _is_blank(o):
            continue
        for intersection_head in _query_objects(store, o, owl_intersection):
            members = _traverse_rdf_list(store, intersection_head)
            for member in members:
                if _is_blank(member):
                    r = _extract_restriction(store, member)
                    if r:
                        result.setdefault(_node_str(s), []).append(r)

    return result
```

- [ ] **Step 8: Run test to verify it passes**

Run: `cd ontoquery && uv run pytest tests/test_axioms.py -v`
Expected: 2 PASS

- [ ] **Step 9: Add equivalence extraction tests**

Add to `ontoquery/tests/test_axioms.py`:

```python
def test_extract_equivalences_intersection():
    from ontoquery.axioms import extract_equivalences
    g = _make_graph(EQUIVALENCE_TTL)
    result = extract_equivalences(g)
    equiv_uri = str(EX.Equiv)
    assert equiv_uri in result
    eq = result[equiv_uri]
    assert len(eq) == 1
    assert eq[0]["type"] == "intersection"
    assert str(EX.Base) in eq[0]["members"]
    assert len(eq[0]["restrictions"]) == 1
    assert eq[0]["restrictions"][0]["filler"] == str(EX.Other)


def test_extract_equivalences_simple():
    from ontoquery.axioms import extract_equivalences
    g = _make_graph(SIMPLE_EQUIV_TTL)
    result = extract_equivalences(g)
    alpha_uri = str(EX.Alpha)
    assert alpha_uri in result
    eq = result[alpha_uri]
    assert len(eq) == 1
    assert eq[0]["type"] == "class"
    assert str(EX.Beta) in eq[0]["members"]


def test_extract_disjointness_all_disjoint_classes():
    from ontoquery.axioms import extract_disjointness
    g = _make_graph(ALL_DISJOINT_TTL)
    result = extract_disjointness(g)
    # All 3 classes should be pairwise disjoint
    assert str(EX.Y) in result[str(EX.X)]
    assert str(EX.Z) in result[str(EX.X)]
    assert str(EX.X) in result[str(EX.Y)]
    assert str(EX.Z) in result[str(EX.Y)]
    assert str(EX.X) in result[str(EX.Z)]
    assert str(EX.Y) in result[str(EX.Z)]
```

- [ ] **Step 10: Implement extract_equivalences**

Add to `ontoquery/src/ontoquery/axioms.py`:

```python
def extract_equivalences(store) -> dict[str, list[dict]]:
    """Extract equivalence class definitions."""
    result: dict[str, list[dict]] = {}
    owl_equiv = _to_node(str(OWL.equivalentClass), store)
    owl_intersection = _to_node(str(OWL.intersectionOf), store)

    for s, _, o in _query_triples(store, None, owl_equiv, None):
        if not _is_named(s):
            continue

        # Simple equivalence: named class
        if _is_named(o):
            result.setdefault(_node_str(s), []).append({
                "type": "class",
                "members": [_node_str(o)],
                "restrictions": [],
            })
            continue

        # Intersection equivalence: bnode with owl:intersectionOf
        if _is_blank(o):
            for intersection_head in _query_objects(store, o, owl_intersection):
                items = _traverse_rdf_list(store, intersection_head)
                members = [_node_str(item) for item in items if _is_named(item)]
                restrictions = []
                for item in items:
                    if _is_blank(item):
                        r = _extract_restriction(store, item)
                        if r:
                            restrictions.append(r)
                result.setdefault(_node_str(s), []).append({
                    "type": "intersection",
                    "members": members,
                    "restrictions": restrictions,
                })

    return result
```

- [ ] **Step 11: Run all axiom tests**

Run: `cd ontoquery && uv run pytest tests/test_axioms.py -v`
Expected: 5 PASS

- [ ] **Step 12: Add orchestration and persistence tests**

Add to `ontoquery/tests/test_axioms.py`:

```python
def test_extract_axioms_combines_all():
    from ontoquery.axioms import extract_axioms
    from ontoquery.backend import RdflibBackend
    g = _make_graph(DISJOINT_TTL + RESTRICTION_TTL)
    backend = RdflibBackend(g)
    result = extract_axioms(backend)
    assert "restrictions" in result
    assert "disjointness" in result
    assert "equivalences" in result
    assert str(EX.A) in result["disjointness"]
    assert str(EX.Child) in result["restrictions"]


def test_save_and_load_axioms(tmp_path):
    from ontoquery.axioms import extract_axioms, save_axioms, load_axioms
    from ontoquery.backend import RdflibBackend
    g = _make_graph(DISJOINT_TTL)
    backend = RdflibBackend(g)
    axioms = extract_axioms(backend)
    path = tmp_path / "axioms.json"
    save_axioms(axioms, path)
    loaded = load_axioms(path)
    assert loaded is not None
    assert loaded["disjointness"] == axioms["disjointness"]


def test_load_axioms_missing_file(tmp_path):
    from ontoquery.axioms import load_axioms
    result = load_axioms(tmp_path / "nonexistent.json")
    assert result is None
```

- [ ] **Step 13: Implement extract_axioms, save_axioms, load_axioms**

Add to `ontoquery/src/ontoquery/axioms.py`:

```python
def extract_axioms(backend) -> dict:
    """Extract all axiom types from a backend's underlying store.

    Returns {"restrictions": ..., "disjointness": ..., "equivalences": ...}.
    Accepts a GraphBackend — accesses backend._store (oxigraph) or backend._graph (rdflib).
    """
    store = _get_raw_store(backend)
    return {
        "restrictions": extract_restrictions(store),
        "disjointness": extract_disjointness(store),
        "equivalences": extract_equivalences(store),
    }


def save_axioms(axioms: dict, path: Path) -> None:
    """Write axiom index to JSON file."""
    path.write_text(json.dumps(axioms, indent=2))


def load_axioms(path: Path) -> dict | None:
    """Load axiom index from JSON file. Returns None if file doesn't exist."""
    if not path.exists():
        return None
    return json.loads(path.read_text())
```

- [ ] **Step 14: Run all tests**

Run: `cd ontoquery && uv run pytest tests/test_axioms.py -v`
Expected: 8 PASS

- [ ] **Step 15: Commit**

```bash
git add ontoquery/src/ontoquery/axioms.py ontoquery/tests/test_axioms.py
git commit -m "feat(ontoquery): add OWL axiom extraction module

Extract restrictions, disjointness, and equivalences from rdflib
graphs. Includes RDF list traversal, JSON persistence, and tests
for pairwise disjoint, AllDisjointClasses, intersection equivalence,
and simple equivalence patterns."
```

---

### Task 2: Backend Protocol Extension

**Files:**
- Modify: `ontoquery/src/ontoquery/backend.py`
- Modify: `ontoquery/tests/test_backend.py`

Add `axioms` parameter to both backend constructors, 3 new dict-lookup methods, and update factory functions.

- [ ] **Step 1: Write tests for new backend methods**

Add to `ontoquery/tests/test_backend.py`:

```python
# --- axiom methods ---

AXIOM_TTL = """\
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix ex: <http://example.org/ont#> .

ex:ClassA a owl:Class ; rdfs:label "Agent" .
ex:ClassB a owl:Class ; rdfs:label "Organization" .
"""

SAMPLE_AXIOMS = {
    "restrictions": {
        "http://example.org/ont#ClassA": [
            {"type": "someValuesFrom", "property": "http://example.org/ont#prop1", "filler": "http://example.org/ont#ClassB"}
        ],
    },
    "disjointness": {
        "http://example.org/ont#ClassA": ["http://example.org/ont#ClassB"],
        "http://example.org/ont#ClassB": ["http://example.org/ont#ClassA"],
    },
    "equivalences": {},
}


def test_get_restrictions_with_axioms(backend):
    backend._axioms = SAMPLE_AXIOMS
    result = backend.get_restrictions("http://example.org/ont#ClassA")
    assert len(result) == 1
    assert result[0]["type"] == "someValuesFrom"


def test_get_restrictions_empty_when_no_axioms(backend):
    result = backend.get_restrictions("http://example.org/ont#ClassA")
    assert result == []


def test_get_disjoint_classes_with_axioms(backend):
    backend._axioms = SAMPLE_AXIOMS
    result = backend.get_disjoint_classes("http://example.org/ont#ClassA")
    assert "http://example.org/ont#ClassB" in result


def test_get_disjoint_classes_empty_when_no_axioms(backend):
    result = backend.get_disjoint_classes("http://example.org/ont#ClassA")
    assert result == []


def test_get_equivalent_axioms_empty(backend):
    result = backend.get_equivalent_axioms("http://example.org/ont#ClassA")
    assert result == []


def test_constructor_accepts_axioms_param():
    """Both backends accept axioms=None (backward compat)."""
    from rdflib import Graph
    g = Graph()
    g.parse(data=AXIOM_TTL, format="turtle")
    rb = RdflibBackend(g)
    assert rb.get_restrictions("http://example.org/ont#ClassA") == []

    rb2 = RdflibBackend(g, axioms=SAMPLE_AXIOMS)
    assert len(rb2.get_restrictions("http://example.org/ont#ClassA")) == 1

    if has_oxigraph():
        import pyoxigraph as ox
        store = ox.Store()
        ob = OxigraphBackend(store)
        assert ob.get_restrictions("http://example.org/ont#ClassA") == []

        ob2 = OxigraphBackend(store, axioms=SAMPLE_AXIOMS)
        assert len(ob2.get_restrictions("http://example.org/ont#ClassA")) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ontoquery && uv run pytest tests/test_backend.py::test_get_restrictions_with_axioms -v`
Expected: FAIL with `AttributeError`

- [ ] **Step 3: Add axioms param to constructors and new methods**

In `ontoquery/src/ontoquery/backend.py`, add to `GraphBackend` protocol:

```python
class GraphBackend(Protocol):
    # ... existing 10 methods ...
    def get_restrictions(self, class_uri: str) -> list[dict]: ...
    def get_disjoint_classes(self, class_uri: str) -> list[str]: ...
    def get_equivalent_axioms(self, class_uri: str) -> list[dict]: ...
```

Update `RdflibBackend.__init__`:

```python
class RdflibBackend:
    """Graph backend using rdflib (pure Python)."""

    def __init__(self, graph: Graph, axioms: dict | None = None):
        self._graph = graph
        self._axioms = axioms or {"restrictions": {}, "disjointness": {}, "equivalences": {}}

    # ... existing methods ...

    def get_restrictions(self, class_uri: str) -> list[dict]:
        return self._axioms.get("restrictions", {}).get(class_uri, [])

    def get_disjoint_classes(self, class_uri: str) -> list[str]:
        return self._axioms.get("disjointness", {}).get(class_uri, [])

    def get_equivalent_axioms(self, class_uri: str) -> list[dict]:
        return self._axioms.get("equivalences", {}).get(class_uri, [])
```

Update `OxigraphBackend.__init__` (inside `if _HAS_OXIGRAPH:` block):

```python
class OxigraphBackend:
    """Graph backend using pyoxigraph (Rust, RocksDB persistence)."""

    def __init__(self, store: ox.Store, axioms: dict | None = None):
        self._store = store
        self._axioms = axioms or {"restrictions": {}, "disjointness": {}, "equivalences": {}}

    # ... existing methods ...

    def get_restrictions(self, class_uri: str) -> list[dict]:
        return self._axioms.get("restrictions", {}).get(class_uri, [])

    def get_disjoint_classes(self, class_uri: str) -> list[str]:
        return self._axioms.get("disjointness", {}).get(class_uri, [])

    def get_equivalent_axioms(self, class_uri: str) -> list[dict]:
        return self._axioms.get("equivalences", {}).get(class_uri, [])
```

- [ ] **Step 4: Run all backend tests**

Run: `cd ontoquery && uv run pytest tests/test_backend.py -v`
Expected: All PASS (existing + 6 new)

- [ ] **Step 5: Update factory functions to wire axioms**

In `ontoquery/src/ontoquery/backend.py`, update `load_backend()`:

```python
import logging

_logger = logging.getLogger(__name__)

def load_backend(chroma_dir: Path, source_dirs: list[Path] | None = None) -> GraphBackend:
    # Add at top of function:
    from ontoquery.axioms import load_axioms
    axioms = load_axioms(chroma_dir / "axioms.json")
    if axioms is None:
        _logger.warning("Axiom index not found — run 'ontoquery index' to enable formal reasoning features.")

    # Then pass axioms to constructors:
    # 1. oxigraph path:
    if _HAS_OXIGRAPH:
        ox_path = chroma_dir / "oxigraph"
        if ox_path.exists():
            return OxigraphBackend(ox.Store(str(ox_path)), axioms=axioms)

    # 2. rdflib paths:
    # ... (pass axioms=axioms to RdflibBackend constructors)
```

Update `create_index_backend()` to extract and save axioms after graph loading:

```python
def create_index_backend(files: list[Path], chroma_dir: Path) -> GraphBackend:
    # ... existing parsing code ...

    # After backend is created, extract and save axioms.
    # extract_axioms() uses _query_triples() adapter which works with both
    # oxigraph Store and rdflib Graph — no re-parsing needed.
    from ontoquery.axioms import extract_axioms, save_axioms
    if _HAS_OXIGRAPH:
        # ... existing oxigraph code ...
        store.optimize()
        backend = OxigraphBackend(store)
        axioms = extract_axioms(backend)
        save_axioms(axioms, chroma_dir / "axioms.json")
        backend._axioms = axioms
        return backend
    else:
        # ... existing rdflib code ...
        backend = RdflibBackend(g)
        axioms = extract_axioms(backend)
        save_axioms(axioms, chroma_dir / "axioms.json")
        backend._axioms = axioms
        return backend
```

**Note for implementer:** `extract_axioms()` accepts a `GraphBackend` and calls `_get_raw_store()` to access the underlying `ox.Store` or `rdflib.Graph`. The `_query_triples()` adapter function handles both APIs, so axiom extraction works directly on the oxigraph store without needing to re-parse files with rdflib.

- [ ] **Step 6: Run all ontoquery tests**

Run: `cd ontoquery && uv run pytest -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add ontoquery/src/ontoquery/backend.py ontoquery/tests/test_backend.py
git commit -m "feat(ontoquery): extend backend protocol with axiom methods

Add axioms parameter to OxigraphBackend and RdflibBackend constructors
(defaults to None for backward compat). Three new methods:
get_restrictions, get_disjoint_classes, get_equivalent_axioms —
all pure dict lookups. Factory functions wire axiom loading/extraction."
```

---

### Task 3: MCP Server Tools and CLI Integration

**Files:**
- Modify: `ontoquery/src/ontoquery/mcp_server.py`
- Modify: `ontoquery/src/ontoquery/cli.py`
- Modify: `ontoquery/tests/test_mcp_server.py`

- [ ] **Step 1: Add new tool handlers to create_tool_handlers**

In `ontoquery/src/ontoquery/mcp_server.py`, add 3 new handler functions inside `create_tool_handlers()`, after the existing `explore_class` handler:

```python
    def get_restrictions(class_uri: str) -> list[dict]:
        return backend.get_restrictions(class_uri)

    def get_disjoint_classes(class_uri: str) -> list[str]:
        return backend.get_disjoint_classes(class_uri)

    def get_equivalent_axioms(class_uri: str) -> list[dict]:
        return backend.get_equivalent_axioms(class_uri)
```

Add them to the returned dict:

```python
    return {
        # ... existing 7 handlers ...
        "get_restrictions": get_restrictions,
        "get_disjoint_classes": get_disjoint_classes,
        "get_equivalent_axioms": get_equivalent_axioms,
    }
```

Add 3 new MCP tool definitions after the existing `explore_class` tool:

```python
@mcp.tool()
def get_restrictions(class_uri: str) -> str:
    """Get OWL restrictions (someValuesFrom, allValuesFrom) for a class."""
    return json.dumps(_get_handlers()["get_restrictions"](class_uri))


@mcp.tool()
def get_disjoint_classes(class_uri: str) -> str:
    """Get classes declared mutually exclusive with this class."""
    return json.dumps(_get_handlers()["get_disjoint_classes"](class_uri))


@mcp.tool()
def get_equivalent_axioms(class_uri: str) -> str:
    """Get equivalence class definitions (intersection members and restrictions)."""
    return json.dumps(_get_handlers()["get_equivalent_axioms"](class_uri))
```

- [ ] **Step 2: Add axiom extraction output to CLI index command**

In `ontoquery/src/ontoquery/cli.py`, after the `idx.index_classes(classes, ...)` line (line ~39), add:

```python
    # Report axiom index stats
    from ontoquery.axioms import load_axioms
    axioms = load_axioms(chroma / "axioms.json")
    if axioms:
        n_restrictions = sum(len(v) for v in axioms["restrictions"].values())
        n_disjoint = sum(len(v) for v in axioms["disjointness"].values()) // 2
        n_equivalences = sum(len(v) for v in axioms["equivalences"].values())
        typer.echo(f"Axiom index: {n_restrictions} restrictions, {n_disjoint} disjoint pairs, {n_equivalences} equivalences")
```

- [ ] **Step 3: Write tests for new MCP tools**

Check the existing test pattern in `ontoquery/tests/test_mcp_server.py` and add tests for the 3 new tools that verify they delegate to the backend correctly. The test pattern should mock the backend or use a fixture with known axiom data.

- [ ] **Step 4: Run all ontoquery tests**

Run: `cd ontoquery && uv run pytest -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add ontoquery/src/ontoquery/mcp_server.py ontoquery/src/ontoquery/cli.py ontoquery/tests/test_mcp_server.py
git commit -m "feat(ontoquery): add axiom MCP tools and CLI reporting

Three new MCP tools: get_restrictions, get_disjoint_classes,
get_equivalent_axioms. CLI index command reports axiom counts."
```

---

### Task 4: Disjointness Validation in Contextualize

**Files:**
- Modify: `refiner/src/refiner/stages/contextualize.py`
- Modify: `refiner/tests/conftest.py`
- Modify: `refiner/tests/test_contextualize.py`

- [ ] **Step 1: Update mock_onto_handlers fixture**

In `refiner/tests/conftest.py`, add 3 new keys to the `mock_onto_handlers` fixture:

```python
@pytest.fixture
def mock_onto_handlers():
    """Mock ontoquery ontology handlers dict."""
    return {
        # ... existing 7 handlers ...
        "get_restrictions": MagicMock(return_value=[]),
        "get_disjoint_classes": MagicMock(return_value=[]),
        "get_equivalent_axioms": MagicMock(return_value=[]),
    }
```

- [ ] **Step 2: Write test for disjointness filtering**

Add to `refiner/tests/test_contextualize.py`:

```python
def test_contextualize_filters_disjoint_enumerations(mock_client, mock_config, mock_onto_handlers):
    """When two enumerations are disjoint, keep the higher-relevance one."""
    axes = [_make_axes()]
    mock_onto_handlers["get_subclasses"].return_value = [
        {"uri": "http://example.org/Employee", "label": "Employee", "depth": 1},
        {"uri": "http://example.org/Contractor", "label": "Contractor", "depth": 1},
    ]
    mock_onto_handlers["get_class_definition"].return_value = {
        "uri": "http://example.org/Employee", "label": "Employee", "definition": "d", "superclasses": []
    }
    # Employee and Contractor are disjoint
    mock_onto_handlers["get_disjoint_classes"].side_effect = lambda uri: (
        ["http://example.org/Contractor"] if uri == "http://example.org/Employee"
        else ["http://example.org/Employee"] if uri == "http://example.org/Contractor"
        else []
    )
    mock_client.chat.completions.create.return_value = _ContextResponse(
        axes=[_AxisResponse(
            cco_class_uri="http://example.org/Person",
            enumerations=[
                _EnumResponse(class_uri="http://example.org/Employee", class_label="Employee", relevance="high"),
                _EnumResponse(class_uri="http://example.org/Contractor", class_label="Contractor", relevance="low"),
            ],
        )],
    )
    result = contextualize(axes, mock_client, mock_config, mock_onto_handlers)
    enums = result[0].axes[0].enumerations
    assert len(enums) == 1
    assert enums[0].class_uri == "http://example.org/Employee"  # higher relevance kept
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd refiner && uv run pytest tests/test_contextualize.py::test_contextualize_filters_disjoint_enumerations -v`
Expected: FAIL (2 enumerations returned instead of 1)

- [ ] **Step 4: Implement disjointness filter**

In `refiner/src/refiner/stages/contextualize.py`, add the helper function before `contextualize()`:

```python
def _relevance_rank(relevance: str) -> int:
    return {"high": 3, "medium": 2, "low": 1}.get(relevance, 0)
```

Then in `contextualize()`, after the `valid_enums` list is built (after the domain filter / URI validation loop, around line 191), add:

```python
            # Disjointness filter
            if onto_handlers.get("get_disjoint_classes"):
                filtered_by_disjoint = []
                removed_uris: set[str] = set()
                for enum in valid_enums:
                    if enum.class_uri in removed_uris:
                        continue
                    disjoints = set(onto_handlers["get_disjoint_classes"](enum.class_uri))
                    conflicting = [e for e in valid_enums if e.class_uri in disjoints and e.class_uri not in removed_uris]
                    for conflict in conflicting:
                        if _relevance_rank(enum.relevance) >= _relevance_rank(conflict.relevance):
                            removed_uris.add(conflict.class_uri)
                        else:
                            removed_uris.add(enum.class_uri)
                            break
                    if enum.class_uri not in removed_uris:
                        filtered_by_disjoint.append(enum)
                if removed_uris and report:
                    report.events.append({
                        "stage": "contextualize", "event": "disjoint_filtered",
                        "risk_id": rva.risk_id,
                        "axis_uri": input_axis.cco_class_uri,
                        "kept": [e.class_uri for e in filtered_by_disjoint],
                        "filtered": list(removed_uris),
                    })
                valid_enums = filtered_by_disjoint
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd refiner && uv run pytest tests/test_contextualize.py::test_contextualize_filters_disjoint_enumerations -v`
Expected: PASS

- [ ] **Step 6: Add test for disjointness event emission**

Add to `refiner/tests/test_contextualize.py`:

```python
def test_contextualize_emits_disjoint_filtered_event(mock_client, mock_config, mock_onto_handlers):
    """Disjointness filtering emits disjoint_filtered event."""
    axes = [_make_axes()]
    mock_onto_handlers["get_subclasses"].return_value = [
        {"uri": "http://example.org/Employee", "label": "Employee", "depth": 1},
        {"uri": "http://example.org/Contractor", "label": "Contractor", "depth": 1},
    ]
    mock_onto_handlers["get_class_definition"].return_value = {
        "uri": "http://example.org/Employee", "label": "Employee", "definition": "d", "superclasses": []
    }
    mock_onto_handlers["get_disjoint_classes"].side_effect = lambda uri: (
        ["http://example.org/Contractor"] if uri == "http://example.org/Employee"
        else ["http://example.org/Employee"] if uri == "http://example.org/Contractor"
        else []
    )
    mock_client.chat.completions.create.return_value = _ContextResponse(
        axes=[_AxisResponse(
            cco_class_uri="http://example.org/Person",
            enumerations=[
                _EnumResponse(class_uri="http://example.org/Employee", class_label="Employee", relevance="high"),
                _EnumResponse(class_uri="http://example.org/Contractor", class_label="Contractor", relevance="low"),
            ],
        )],
    )
    report = RunReport(model="m", policy_set="p", timestamp="t")
    contextualize(axes, mock_client, mock_config, mock_onto_handlers, report=report)
    disjoint_events = [e for e in report.events if e["event"] == "disjoint_filtered"]
    assert len(disjoint_events) == 1
    assert "http://example.org/Contractor" in disjoint_events[0]["filtered"]


def test_contextualize_no_disjoint_filter_when_handler_absent(mock_client, mock_config):
    """Without get_disjoint_classes handler, no filtering occurs."""
    handlers = {
        "search_classes": MagicMock(return_value=[]),
        "get_class_definition": MagicMock(return_value={"uri": "u", "label": "l", "definition": "d", "superclasses": []}),
        "get_subclasses": MagicMock(return_value=[{"uri": "http://example.org/Employee", "label": "Employee", "depth": 1}]),
        "get_superclasses": MagicMock(return_value=[]),
        "get_siblings": MagicMock(return_value=[]),
        "get_properties": MagicMock(return_value=[]),
        "explore_class": MagicMock(return_value=None),
        # No get_disjoint_classes key
    }
    axes = [_make_axes()]
    mock_client.chat.completions.create.return_value = _ContextResponse(
        axes=[_AxisResponse(
            cco_class_uri="http://example.org/Person",
            enumerations=[
                _EnumResponse(class_uri="http://example.org/Employee", class_label="Employee", relevance="high"),
            ],
        )],
    )
    result = contextualize(axes, mock_client, mock_config, handlers)
    assert len(result[0].axes[0].enumerations) == 1
```

- [ ] **Step 7: Run all contextualize tests**

Run: `cd refiner && uv run pytest tests/test_contextualize.py -v`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add refiner/src/refiner/stages/contextualize.py refiner/tests/conftest.py refiner/tests/test_contextualize.py
git commit -m "feat(refiner): add disjointness validation to contextualize

Filter mutually exclusive enumerations using owl:disjointWith data.
Keep higher-relevance enum, break on self-removal. Emits
disjoint_filtered pipeline event. Guarded by .get() — no-op when
axiom handlers absent."
```

---

### Task 5: Restriction-Based Discovery in Anchor

**Files:**
- Modify: `refiner/src/refiner/stages/anchor.py`
- Modify: `refiner/tests/test_anchor.py`

- [ ] **Step 1: Write test for restriction expansion**

Add to `refiner/tests/test_anchor.py` (check existing test patterns first):

```python
def test_expand_candidates_with_restriction_expansion(mock_onto_handlers):
    """Restriction fillers are added as candidates when get_restrictions is available."""
    # Set up search to return one candidate
    mock_onto_handlers["search_classes"].return_value = [
        {"uri": "http://example.org/Artifact", "label": "Artifact", "distance": 0.1},
    ]
    # Artifact has a restriction: someValuesFrom -> ContentEntity
    mock_onto_handlers["get_restrictions"].return_value = [
        {"type": "someValuesFrom", "property": "http://example.org/is_about", "filler": "http://example.org/ContentEntity"},
    ]
    mock_onto_handlers["get_class_definition"].side_effect = lambda uri: (
        {"uri": uri, "label": "Content Entity", "definition": "d", "superclasses": []}
        if uri == "http://example.org/ContentEntity"
        else None
    )

    from refiner.stages.anchor import expand_candidates
    candidates, stats = expand_candidates(
        description="Information artifact",
        concern="",
        action_descriptions=[],
        cross_mapped_descriptions=[],
        onto_handlers=mock_onto_handlers,
        selected_domains=None,
    )
    uris = {c["uri"] for c in candidates}
    assert "http://example.org/ContentEntity" in uris
    # Check it has restriction metadata
    restriction_cand = next(c for c in candidates if c["uri"] == "http://example.org/ContentEntity")
    assert "restriction" in restriction_cand["query_sources"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd refiner && uv run pytest tests/test_anchor.py::test_expand_candidates_with_restriction_expansion -v`
Expected: FAIL

- [ ] **Step 3: Implement restriction/equivalence expansion**

In `refiner/src/refiner/stages/anchor.py`, at the end of `expand_candidates()` (after `kept = sorted_candidates[:max_candidates]` around line 155), add:

```python
    # Restriction/equivalence expansion
    if onto_handlers.get("get_restrictions"):
        restriction_candidates = []
        seen_uris = {c["uri"] for c in kept}
        for c in kept:
            for r in onto_handlers["get_restrictions"](c["uri"]):
                filler = r.get("filler", "")
                if not filler or filler in seen_uris:
                    continue
                defn = onto_handlers["get_class_definition"](filler)
                if defn is None:
                    continue
                seen_uris.add(filler)
                restriction_candidates.append({
                    "uri": filler,
                    "label": defn.get("label", ""),
                    "hit_count": 0,
                    "best_distance": 0.0,
                    "query_sources": ["restriction"],
                    "restriction_property": r.get("property", ""),
                    "restriction_from": c["uri"],
                })

        if onto_handlers.get("get_equivalent_axioms"):
            for c in kept:
                for eq in onto_handlers["get_equivalent_axioms"](c["uri"]):
                    for member in eq.get("members", []):
                        if member in seen_uris:
                            continue
                        defn = onto_handlers["get_class_definition"](member)
                        if defn is None:
                            continue
                        seen_uris.add(member)
                        restriction_candidates.append({
                            "uri": member,
                            "label": defn.get("label", ""),
                            "hit_count": 0,
                            "best_distance": 0.0,
                            "query_sources": ["equivalence"],
                        })

        # Domain filter restriction candidates
        if selected_domains and restriction_candidates:
            restriction_candidates = [
                c for c in restriction_candidates
                if derive_source_ontology(c["uri"]) in selected_domains
            ]

        # Cap at 3 additional candidates
        restriction_candidates = restriction_candidates[:3]
        kept = kept + restriction_candidates
        stats["restriction_candidates_added"] = len(restriction_candidates)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd refiner && uv run pytest tests/test_anchor.py::test_expand_candidates_with_restriction_expansion -v`
Expected: PASS

- [ ] **Step 5: Add test for restriction expansion cap**

```python
def test_expand_candidates_restriction_cap_at_3(mock_onto_handlers):
    """At most 3 restriction candidates are added."""
    mock_onto_handlers["search_classes"].return_value = [
        {"uri": "http://example.org/A", "label": "A", "distance": 0.1},
    ]
    # 5 restrictions — should be capped at 3
    mock_onto_handlers["get_restrictions"].return_value = [
        {"type": "someValuesFrom", "property": "p", "filler": f"http://example.org/F{i}"}
        for i in range(5)
    ]
    mock_onto_handlers["get_class_definition"].side_effect = lambda uri: (
        {"uri": uri, "label": uri.split("/")[-1], "definition": "d", "superclasses": []}
    )

    from refiner.stages.anchor import expand_candidates
    candidates, stats = expand_candidates(
        description="test",
        concern="",
        action_descriptions=[],
        cross_mapped_descriptions=[],
        onto_handlers=mock_onto_handlers,
        selected_domains=None,
    )
    restriction_cands = [c for c in candidates if "restriction" in c.get("query_sources", [])]
    assert len(restriction_cands) == 3
```

- [ ] **Step 6: Add restriction expansion event to anchor()**

In `anchor()`, after the `expand_candidates()` call, add an event if restriction candidates were added:

```python
            if report and expansion_stats.get("restriction_candidates_added", 0) > 0:
                report.events.append({
                    "stage": "anchor", "event": "restriction_expansion",
                    "risk_id": rm.risk_id,
                    "source_uri": "",  # multiple sources
                    "candidates_added": expansion_stats["restriction_candidates_added"],
                    "source_type": "restriction",
                })
```

- [ ] **Step 7: Run all anchor tests**

Run: `cd refiner && uv run pytest tests/test_anchor.py -v`
Expected: All PASS

- [ ] **Step 8: Run full refiner test suite**

Run: `cd refiner && uv run pytest -v`
Expected: All PASS

- [ ] **Step 9: Commit**

```bash
git add refiner/src/refiner/stages/anchor.py refiner/tests/test_anchor.py
git commit -m "feat(refiner): add restriction-based candidate discovery in anchor

Expand candidates with OWL restriction fillers and equivalence class
members after search-based discovery. Capped at 3 additional candidates.
Domain filtered. Emits restriction_expansion pipeline event."
```

---

### Task 6: Evaluation Metrics

**Files:**
- Modify: `refiner/src/refiner/evaluate.py`
- Modify: `refiner/tests/test_evaluate.py`

- [ ] **Step 1: Write tests for new aggregate_stage_quality event types**

Add to `refiner/tests/test_evaluate.py`:

```python
def test_aggregate_disjoint_filtered_event():
    events = [
        {"stage": "contextualize", "event": "disjoint_filtered",
         "risk_id": "r1", "axis_uri": "http://ex/A",
         "kept": ["http://ex/B"], "filtered": ["http://ex/C"]},
    ]
    result = aggregate_stage_quality(events)
    df = result["contextualize"]["disjoint_filtered"]
    assert len(df) == 1
    assert df[0]["risk_id"] == "r1"
    assert "http://ex/C" in df[0]["filtered"]


def test_aggregate_restriction_expansion_event():
    events = [
        {"stage": "anchor", "event": "restriction_expansion",
         "risk_id": "r1", "source_uri": "http://ex/A",
         "candidates_added": 2, "source_type": "restriction"},
    ]
    result = aggregate_stage_quality(events)
    re = result["anchor"]["restriction_expansions"]
    assert len(re) == 1
    assert re[0]["candidates_added"] == 2


def test_aggregate_restriction_context_added_event():
    events = [
        {"stage": "contextualize", "event": "restriction_context_added",
         "axis_uri": "http://ex/A", "restriction_count": 3},
    ]
    result = aggregate_stage_quality(events)
    assert result["contextualize"]["restriction_contexts_added"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd refiner && uv run pytest tests/test_evaluate.py::test_aggregate_disjoint_filtered_event -v`
Expected: FAIL (key not found)

- [ ] **Step 3: Add event handlers to aggregate_stage_quality**

In `refiner/src/refiner/evaluate.py`, in `aggregate_stage_quality()`, after the `cross_mapping_filtered` handler (line 79), add:

```python
        elif etype == "disjoint_filtered":
            s.setdefault("disjoint_filtered", []).append({
                "risk_id": event["risk_id"],
                "axis_uri": event["axis_uri"],
                "kept": event["kept"],
                "filtered": event["filtered"],
            })
        elif etype == "restriction_expansion":
            s.setdefault("restriction_expansions", []).append({
                "risk_id": event["risk_id"],
                "source_uri": event["source_uri"],
                "candidates_added": event["candidates_added"],
                "source_type": event["source_type"],
            })
        elif etype == "restriction_context_added":
            s["restriction_contexts_added"] = s.get("restriction_contexts_added", 0) + 1
```

- [ ] **Step 4: Run event handler tests**

Run: `cd refiner && uv run pytest tests/test_evaluate.py::test_aggregate_disjoint_filtered_event tests/test_evaluate.py::test_aggregate_restriction_expansion_event tests/test_evaluate.py::test_aggregate_restriction_context_added_event -v`
Expected: 3 PASS

- [ ] **Step 5: Write tests for new metric functions**

Add to `refiner/tests/test_evaluate.py`:

```python
def test_compute_disjoint_filter_rate():
    from refiner.evaluate import compute_disjoint_filter_rate
    events = [
        {"stage": "contextualize", "event": "disjoint_filtered",
         "risk_id": "r1", "axis_uri": "a", "kept": ["b"], "filtered": ["c"]},
        {"stage": "contextualize", "event": "empty_enumerations",
         "risk_id": "r2", "axis_uri": "d"},  # no disjoint event for r2
    ]
    result = compute_disjoint_filter_rate(events, total_risks=3)
    assert result["risks_with_disjoint_filtering"] == 1
    assert result["total_risks"] == 3
    assert abs(result["disjoint_filter_rate"] - 1 / 3) < 0.01


def test_compute_disjoint_filter_rate_empty():
    from refiner.evaluate import compute_disjoint_filter_rate
    result = compute_disjoint_filter_rate([], total_risks=0)
    assert result["disjoint_filter_rate"] == 0


def test_compute_restriction_discovery_rate():
    from refiner.evaluate import compute_restriction_discovery_rate
    events = [
        {"stage": "anchor", "event": "restriction_expansion",
         "risk_id": "r1", "source_uri": "a", "candidates_added": 2, "source_type": "restriction"},
    ]
    result = compute_restriction_discovery_rate(events, total_risks=4)
    assert result["risks_with_restriction_expansion"] == 1
    assert result["total_candidates_from_axioms"] == 2
    assert result["restriction_discovery_rate"] == 0.25
```

- [ ] **Step 6: Implement metric functions**

Add to `refiner/src/refiner/evaluate.py`:

```python
def compute_disjoint_filter_rate(events: list[dict], total_risks: int) -> dict:
    """Fraction of risks where disjointness filtering removed enumerations."""
    disjoint_events = [e for e in events if e.get("event") == "disjoint_filtered"]
    risk_ids = {e["risk_id"] for e in disjoint_events}
    return {
        "risks_with_disjoint_filtering": len(risk_ids),
        "total_risks": total_risks,
        "disjoint_filter_rate": round(len(risk_ids) / total_risks, 3) if total_risks > 0 else 0,
    }


def compute_restriction_discovery_rate(events: list[dict], total_risks: int) -> dict:
    """Fraction of risks where restriction/equivalence expansion added candidates."""
    expansion_events = [e for e in events if e.get("event") == "restriction_expansion"]
    risk_ids = {e["risk_id"] for e in expansion_events}
    total_added = sum(e.get("candidates_added", 0) for e in expansion_events)
    return {
        "risks_with_restriction_expansion": len(risk_ids),
        "total_risks": total_risks,
        "total_candidates_from_axioms": total_added,
        "restriction_discovery_rate": round(len(risk_ids) / total_risks, 3) if total_risks > 0 else 0,
    }
```

- [ ] **Step 7: Wire metrics into run_evaluation**

In `run_evaluation()`, after `profiles = dc_data.get("profiles", [])` (line ~715) and inside the `if profiles:` coverage block (around line 721), add the new metrics alongside the existing coverage metrics:

```python
    if profiles:
        # ... existing coverage metrics ...
        # Add axiom metrics (need events from earlier)
        if events:
            total_risks = len({p["risk_id"] for p in profiles})
            result.setdefault("stage_quality", {})["disjoint_filter_rate"] = compute_disjoint_filter_rate(events, total_risks)
            result.setdefault("stage_quality", {})["restriction_discovery_rate"] = compute_restriction_discovery_rate(events, total_risks)
```

Note: `events` is defined at line ~698 and `profiles` at line ~715. The new metrics need both, so place them after `profiles` is available. Using `setdefault` ensures `stage_quality` key exists even if the `if events:` block at line ~699 didn't run (though in practice both will be populated together).

- [ ] **Step 8: Run all evaluate tests**

Run: `cd refiner && uv run pytest tests/test_evaluate.py -v`
Expected: All PASS

- [ ] **Step 9: Run full refiner test suite**

Run: `cd refiner && uv run pytest -v`
Expected: All PASS

- [ ] **Step 10: Commit**

```bash
git add refiner/src/refiner/evaluate.py refiner/tests/test_evaluate.py
git commit -m "feat(refiner): add axiom evaluation metrics

Three new event handlers in aggregate_stage_quality for
disjoint_filtered, restriction_expansion, restriction_context_added.
Two new metric functions: compute_disjoint_filter_rate and
compute_restriction_discovery_rate. Wired into run_evaluation()."
```

---

### Task 7: Restriction Context in Contextualize Prompt

**Files:**
- Modify: `refiner/src/refiner/stages/contextualize.py`
- Modify: `refiner/tests/test_contextualize.py`

This task adds OWL restriction context to the LLM prompt in contextualize, giving the model more information for filtering decisions.

- [ ] **Step 1: Write test for restriction context in prompt**

Add to `refiner/tests/test_contextualize.py`:

```python
def test_contextualize_includes_restriction_context_in_prompt(mock_client, mock_config, mock_onto_handlers):
    """When restrictions exist for an axis, they appear in the LLM prompt."""
    axes = [_make_axes()]
    mock_onto_handlers["get_subclasses"].return_value = [
        {"uri": "http://example.org/Employee", "label": "Employee", "depth": 1},
    ]
    mock_onto_handlers["get_restrictions"].return_value = [
        {"type": "someValuesFrom", "property": "http://example.org/member_of", "filler": "http://example.org/Organization"},
    ]
    mock_onto_handlers["get_class_definition"].return_value = {
        "uri": "http://example.org/Employee", "label": "Employee", "definition": "d", "superclasses": []
    }
    mock_client.chat.completions.create.return_value = _ContextResponse(
        axes=[_AxisResponse(
            cco_class_uri="http://example.org/Person",
            enumerations=[_EnumResponse(class_uri="http://example.org/Employee", class_label="Employee", relevance="high")],
        )],
    )
    report = RunReport(model="m", policy_set="p", timestamp="t")
    contextualize(axes, mock_client, mock_config, mock_onto_handlers, report=report)

    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    user_msg = call_kwargs["messages"][1]["content"]
    assert "Ontology constraints:" in user_msg or "constraints:" in user_msg.lower()

    context_events = [e for e in report.events if e["event"] == "restriction_context_added"]
    assert len(context_events) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd refiner && uv run pytest tests/test_contextualize.py::test_contextualize_includes_restriction_context_in_prompt -v`
Expected: FAIL

- [ ] **Step 3: Add restriction context to prompt building**

In `contextualize()`, in the axis_context building loop (around line 108-112), after building the `source` and `candidate_lines`, add restriction context:

```python
            # Add restriction context if available
            restriction_lines = []
            if onto_handlers.get("get_restrictions"):
                restrictions = onto_handlers["get_restrictions"](axis.cco_class_uri)
                for r in restrictions[:5]:  # cap at 5 to avoid prompt bloat
                    prop_label = r.get("property", "").split("#")[-1].split("/")[-1]
                    filler_label = r.get("filler", "").split("#")[-1].split("/")[-1]
                    restriction_lines.append(f"  - {r['type']}: {prop_label} -> {filler_label}")
                if restriction_lines and report:
                    report.events.append({
                        "stage": "contextualize", "event": "restriction_context_added",
                        "axis_uri": axis.cco_class_uri,
                        "restriction_count": len(restrictions),
                    })

            constraint_block = ""
            if restriction_lines:
                constraint_block = "Ontology constraints:\n" + "\n".join(restriction_lines) + "\n"

            axis_context.append(
                f"Axis: {axis.cco_class_label} ({axis.cco_class_uri})\n"
                f"Roles: {', '.join(axis.roles)}\n"
                f"{constraint_block}"
                f"{source}:\n" + ("\n".join(candidate_lines) if candidate_lines else "  (none)")
            )
```

This replaces the existing `axis_context.append(...)` block.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd refiner && uv run pytest tests/test_contextualize.py::test_contextualize_includes_restriction_context_in_prompt -v`
Expected: PASS

- [ ] **Step 5: Run all contextualize tests**

Run: `cd refiner && uv run pytest tests/test_contextualize.py -v`
Expected: All PASS

- [ ] **Step 6: Run full refiner test suite**

Run: `cd refiner && uv run pytest -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add refiner/src/refiner/stages/contextualize.py refiner/tests/test_contextualize.py
git commit -m "feat(refiner): add restriction context to contextualize prompt

Include OWL restriction constraints in LLM prompt for each axis
(capped at 5 per axis). Emits restriction_context_added event."
```

---

### Task 8: Integration Verification

**Files:** None new — this verifies the full integration.

- [ ] **Step 1: Run full ontoquery test suite**

Run: `cd ontoquery && uv run pytest -v`
Expected: All PASS

- [ ] **Step 2: Run full refiner test suite**

Run: `cd refiner && uv run pytest -v`
Expected: All PASS

- [ ] **Step 3: Verify backward compatibility — existing pipeline works without axioms.json**

Run a quick check that the pipeline functions work when `get_restrictions`, `get_disjoint_classes`, `get_equivalent_axioms` are absent from `onto_handlers`. This is already covered by existing tests (which use the old fixture without axiom handlers up to Task 4 step 1), but verify no tests fail after all changes.

- [ ] **Step 4: Final commit if any cleanup needed**

```bash
git status
# If any uncommitted changes from test fixes:
git add -u
git commit -m "fix: address integration test issues"
```
