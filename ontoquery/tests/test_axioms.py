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
