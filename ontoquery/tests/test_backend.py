"""Tests for GraphBackend implementations (rdflib and oxigraph).

Both backends must produce the same results for the same input.
"""
import pytest
from pathlib import Path

from ontoquery.backend import (
    GraphBackend,
    RdflibBackend,
    OxigraphBackend,
    create_index_backend,
    load_backend,
    has_oxigraph,
    _clean_graph_caches,
)
from ontoquery.graph import load_graph, find_ontology_files


SAMPLE_TTL = """\
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .

<http://example.org/ont#ClassA> a owl:Class ;
    rdfs:label "Agent" ;
    skos:definition "An entity that acts." .

<http://example.org/ont#ClassB> a owl:Class ;
    rdfs:label "Organization" ;
    rdfs:comment "A group of agents." .

<http://example.org/ont#ClassD> a owl:Class ;
    rdfs:label "Person" ;
    skos:definition "A human agent." ;
    rdfs:subClassOf <http://example.org/ont#ClassA> .

<http://example.org/ont#ClassE> a owl:Class ;
    rdfs:label "Software Agent" ;
    skos:definition "An autonomous software entity." ;
    rdfs:subClassOf <http://example.org/ont#ClassA> .

<http://example.org/ont#ClassF> a owl:Class ;
    rdfs:label "Employee" ;
    skos:definition "A person employed by an organization." ;
    rdfs:subClassOf <http://example.org/ont#ClassD> .

<http://example.org/ont#ClassG> a owl:Class ;
    rdfs:label "Manager" ;
    skos:definition "An employee who manages others." ;
    rdfs:subClassOf <http://example.org/ont#ClassF> .

<http://example.org/ont#prop1> a owl:ObjectProperty ;
    rdfs:label "member of" ;
    rdfs:domain <http://example.org/ont#ClassD> ;
    rdfs:range <http://example.org/ont#ClassB> .
"""


@pytest.fixture
def ontology_dir(tmp_path):
    ttl_file = tmp_path / "ontology" / "test.ttl"
    ttl_file.parent.mkdir()
    ttl_file.write_text(SAMPLE_TTL)
    return tmp_path / "ontology"


@pytest.fixture
def rdflib_backend(ontology_dir):
    graph = load_graph(ontology_dir)
    return RdflibBackend(graph)


@pytest.fixture
def oxigraph_backend(ontology_dir):
    if not has_oxigraph():
        pytest.skip("pyoxigraph not installed")
    import pyoxigraph as ox
    store = ox.Store()
    for f in find_ontology_files(ontology_dir):
        store.bulk_load(path=str(f), format=ox.RdfFormat.TURTLE)
    return OxigraphBackend(store)


@pytest.fixture(params=["rdflib", "oxigraph"])
def backend(request, rdflib_backend, oxigraph_backend) -> GraphBackend:
    if request.param == "rdflib":
        return rdflib_backend
    return oxigraph_backend


# --- Protocol conformance ---

def test_protocol_conformance_rdflib(rdflib_backend):
    assert isinstance(rdflib_backend, GraphBackend)


def test_protocol_conformance_oxigraph(oxigraph_backend):
    assert isinstance(oxigraph_backend, GraphBackend)


# --- extract_classes ---

def test_extract_classes(backend):
    classes = backend.extract_classes()
    uris = {c["uri"] for c in classes}
    assert "http://example.org/ont#ClassA" in uris
    assert "http://example.org/ont#ClassD" in uris
    assert "http://example.org/ont#ClassB" in uris
    assert "http://example.org/ont#ClassE" in uris
    assert "http://example.org/ont#ClassF" in uris
    assert "http://example.org/ont#ClassG" in uris


def test_extract_classes_labels(backend):
    classes = backend.extract_classes()
    by_uri = {c["uri"]: c for c in classes}
    assert by_uri["http://example.org/ont#ClassA"]["label"] == "Agent"
    assert by_uri["http://example.org/ont#ClassD"]["label"] == "Person"


def test_extract_classes_definitions(backend):
    classes = backend.extract_classes()
    by_uri = {c["uri"]: c for c in classes}
    assert by_uri["http://example.org/ont#ClassA"]["definition"] == "An entity that acts."
    assert by_uri["http://example.org/ont#ClassB"]["definition"] == "A group of agents."


# --- get_label / get_definition ---

def test_get_label(backend):
    assert backend.get_label("http://example.org/ont#ClassA") == "Agent"
    assert backend.get_label("http://example.org/ont#ClassD") == "Person"


def test_get_definition(backend):
    assert backend.get_definition("http://example.org/ont#ClassA") == "An entity that acts."
    assert backend.get_definition("http://example.org/ont#ClassB") == "A group of agents."


# --- is_class ---

def test_is_class(backend):
    assert backend.is_class("http://example.org/ont#ClassA")
    assert not backend.is_class("http://example.org/nonexistent")
    assert not backend.is_class("http://example.org/ont#prop1")


# --- get_superclasses ---

def test_get_superclasses(backend):
    supers = backend.get_superclasses("http://example.org/ont#ClassD")
    uris = {s["uri"] for s in supers}
    assert "http://example.org/ont#ClassA" in uris


def test_get_superclasses_filters_blank_nodes(backend):
    supers = backend.get_superclasses("http://example.org/ont#ClassD")
    for s in supers:
        assert s["uri"].startswith("http")


# --- get_subclasses ---

def test_get_subclasses(backend):
    subs = backend.get_subclasses("http://example.org/ont#ClassA")
    uris = {s["uri"] for s in subs}
    assert "http://example.org/ont#ClassD" in uris
    assert "http://example.org/ont#ClassE" in uris


# --- get_subclasses_recursive ---

def test_get_subclasses_recursive_depth_1(backend):
    subs = backend.get_subclasses_recursive("http://example.org/ont#ClassA", depth=1)
    uris = {s["uri"] for s in subs}
    assert "http://example.org/ont#ClassD" in uris
    assert "http://example.org/ont#ClassE" in uris
    assert "http://example.org/ont#ClassF" not in uris


def test_get_subclasses_recursive_depth_2(backend):
    subs = backend.get_subclasses_recursive("http://example.org/ont#ClassA", depth=2)
    uris = {s["uri"] for s in subs}
    assert "http://example.org/ont#ClassF" in uris
    assert "http://example.org/ont#ClassG" not in uris


def test_get_subclasses_recursive_depth_3(backend):
    subs = backend.get_subclasses_recursive("http://example.org/ont#ClassA", depth=3)
    uris = {s["uri"] for s in subs}
    assert "http://example.org/ont#ClassG" in uris


def test_get_subclasses_recursive_includes_depth(backend):
    subs = backend.get_subclasses_recursive("http://example.org/ont#ClassA", depth=3)
    by_uri = {s["uri"]: s for s in subs}
    assert by_uri["http://example.org/ont#ClassD"]["depth"] == 1
    assert by_uri["http://example.org/ont#ClassF"]["depth"] == 2
    assert by_uri["http://example.org/ont#ClassG"]["depth"] == 3


def test_get_subclasses_recursive_leaf_node(backend):
    subs = backend.get_subclasses_recursive("http://example.org/ont#ClassG", depth=5)
    assert len(subs) == 0


# --- get_siblings ---

def test_get_siblings(backend):
    siblings = backend.get_siblings("http://example.org/ont#ClassD")
    uris = {s["uri"] for s in siblings}
    assert "http://example.org/ont#ClassE" in uris
    assert "http://example.org/ont#ClassD" not in uris


def test_get_siblings_shared_parent(backend):
    siblings = backend.get_siblings("http://example.org/ont#ClassD")
    for s in siblings:
        assert "shared_parent" in s
        assert s["shared_parent"]["uri"] == "http://example.org/ont#ClassA"


def test_get_siblings_no_siblings(backend):
    siblings = backend.get_siblings("http://example.org/ont#ClassG")
    assert len(siblings) == 0


def test_get_siblings_root_class(backend):
    siblings = backend.get_siblings("http://example.org/ont#ClassA")
    assert len(siblings) == 0


# --- get_properties ---

def test_get_properties_domain(backend):
    props = backend.get_properties("http://example.org/ont#ClassD")
    assert len(props) >= 1
    prop = next(p for p in props if p["label"] == "member of")
    assert prop["role"] == "domain"
    assert prop["other_class"]["uri"] == "http://example.org/ont#ClassB"


def test_get_properties_range(backend):
    props = backend.get_properties("http://example.org/ont#ClassB")
    prop = next(p for p in props if p["label"] == "member of")
    assert prop["role"] == "range"
    assert prop["other_class"]["uri"] == "http://example.org/ont#ClassD"


# --- get_class_definition ---

def test_get_class_definition(backend):
    result = backend.get_class_definition("http://example.org/ont#ClassD")
    assert result["uri"] == "http://example.org/ont#ClassD"
    assert result["label"] == "Person"
    assert result["definition"] == "A human agent."
    assert any(s["uri"] == "http://example.org/ont#ClassA" for s in result["superclasses"])


def test_get_class_definition_not_found(backend):
    result = backend.get_class_definition("http://example.org/nonexistent")
    assert result is None


# --- Factory functions ---

def test_create_index_backend_oxigraph(ontology_dir, tmp_path):
    if not has_oxigraph():
        pytest.skip("pyoxigraph not installed")
    chroma = tmp_path / "chroma"
    chroma.mkdir()
    files = find_ontology_files(ontology_dir)
    backend = create_index_backend(files, chroma)
    assert isinstance(backend, OxigraphBackend)
    assert (chroma / "oxigraph").exists()
    classes = backend.extract_classes()
    assert len(classes) >= 6


def test_create_index_backend_cleans_old_caches(ontology_dir, tmp_path):
    chroma = tmp_path / "chroma"
    chroma.mkdir()
    # Create fake old caches
    (chroma / "graph.nt").write_text("old cache")
    (chroma / "oxigraph").mkdir()
    (chroma / "oxigraph" / "dummy").write_text("old store")

    files = find_ontology_files(ontology_dir)
    create_index_backend(files, chroma)

    # Old NT cache should be gone
    assert not (chroma / "graph.nt").exists()


def test_load_backend_oxigraph(ontology_dir, tmp_path):
    if not has_oxigraph():
        pytest.skip("pyoxigraph not installed")
    chroma = tmp_path / "chroma"
    chroma.mkdir()
    files = find_ontology_files(ontology_dir)
    create_index_backend(files, chroma)

    # Reopen from persistent store
    backend = load_backend(chroma)
    assert isinstance(backend, OxigraphBackend)
    assert backend.is_class("http://example.org/ont#ClassA")


def test_load_backend_rdflib_fallback(ontology_dir, tmp_path):
    """load_backend falls back to rdflib when only NT cache exists."""
    chroma = tmp_path / "chroma"
    chroma.mkdir()
    # Create an NT cache manually (simulating pre-oxigraph state)
    graph = load_graph(ontology_dir)
    nt_path = chroma / "graph.nt"
    graph.serialize(str(nt_path), format="nt")

    backend = load_backend(chroma)
    assert isinstance(backend, RdflibBackend)
    assert backend.is_class("http://example.org/ont#ClassA")


def test_load_backend_no_store_raises(tmp_path):
    chroma = tmp_path / "chroma"
    chroma.mkdir()
    with pytest.raises(RuntimeError, match="No graph store"):
        load_backend(chroma)


# --- axiom methods ---

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
    g.parse(data=SAMPLE_TTL, format="turtle")
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
