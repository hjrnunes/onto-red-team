import json
import pytest
from ontoquery.index import OntologyIndex
from ontoquery.backend import create_index_backend
from ontoquery.mcp_server import create_tool_handlers


EXTENDED_SAMPLE_TTL = """\
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

<http://example.org/ont#prop1> a owl:ObjectProperty ;
    rdfs:label "member of" ;
    rdfs:domain <http://example.org/ont#ClassD> ;
    rdfs:range <http://example.org/ont#ClassB> .
"""


@pytest.fixture
def tools(tmp_path):
    """Set up index + graph backend and return tool handlers dict."""
    ttl_file = tmp_path / "ontology" / "test.ttl"
    ttl_file.parent.mkdir()
    ttl_file.write_text(EXTENDED_SAMPLE_TTL)

    chroma_dir = tmp_path / "chroma"
    chroma_dir.mkdir()
    ontology_dir = tmp_path / "ontology"

    from ontoquery.graph import find_ontology_files
    files = find_ontology_files(ontology_dir)
    backend = create_index_backend(files, chroma_dir)
    classes = backend.extract_classes()
    del backend  # Release RocksDB lock before create_tool_handlers reopens
    idx = OntologyIndex(chroma_dir)
    idx.index_classes(classes, source_dir=str(ontology_dir))

    return create_tool_handlers(chroma_dir)


def test_search_classes(tools):
    result = tools["search_classes"](query="human person agent", top_k=3)
    assert len(result) <= 3
    assert any(r["label"] == "Person" for r in result)


def test_get_class_definition(tools):
    result = tools["get_class_definition"](class_uri="http://example.org/ont#ClassD")
    assert result["label"] == "Person"
    assert result["definition"] == "A human agent."
    assert any(s["uri"] == "http://example.org/ont#ClassA" for s in result["superclasses"])


def test_get_class_definition_not_found(tools):
    result = tools["get_class_definition"](class_uri="http://example.org/nonexistent")
    assert result is None


def test_get_subclasses(tools):
    result = tools["get_subclasses"](class_uri="http://example.org/ont#ClassA", depth=1)
    uris = {r["uri"] for r in result}
    assert "http://example.org/ont#ClassD" in uris
    assert "http://example.org/ont#ClassE" in uris


def test_get_subclasses_recursive(tools):
    result = tools["get_subclasses"](class_uri="http://example.org/ont#ClassA", depth=2)
    uris = {r["uri"] for r in result}
    assert "http://example.org/ont#ClassF" in uris


def test_get_superclasses(tools):
    result = tools["get_superclasses"](class_uri="http://example.org/ont#ClassD")
    uris = {r["uri"] for r in result}
    assert "http://example.org/ont#ClassA" in uris


def test_get_siblings(tools):
    result = tools["get_siblings"](class_uri="http://example.org/ont#ClassD")
    uris = {r["uri"] for r in result}
    assert "http://example.org/ont#ClassE" in uris
    assert "http://example.org/ont#ClassD" not in uris


def test_get_properties(tools):
    result = tools["get_properties"](class_uri="http://example.org/ont#ClassD")
    assert any(p["label"] == "member of" for p in result)


def test_explore_class(tools):
    result = tools["explore_class"](class_uri="http://example.org/ont#ClassD")
    assert result["label"] == "Person"
    assert result["definition"] == "A human agent."
    assert "superclasses" in result
    assert "subclasses" in result
    assert "siblings" in result
    assert "properties" in result
    assert any(s["uri"] == "http://example.org/ont#ClassE" for s in result["siblings"])


def test_get_restrictions(tools):
    result = tools["get_restrictions"](class_uri="http://example.org/ont#ClassA")
    assert isinstance(result, list)


def test_get_disjoint_classes(tools):
    result = tools["get_disjoint_classes"](class_uri="http://example.org/ont#ClassA")
    assert isinstance(result, list)


def test_get_equivalent_axioms(tools):
    result = tools["get_equivalent_axioms"](class_uri="http://example.org/ont#ClassA")
    assert isinstance(result, list)
