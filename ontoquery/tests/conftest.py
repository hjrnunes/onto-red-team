import os
import pytest


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

<http://example.org/ont#ClassC> a owl:Class ;
    rdfs:subClassOf <http://example.org/ont#ClassA> .

<http://example.org/ont#ClassD> a owl:Class ;
    rdfs:label "Person" ;
    skos:definition "A human agent." ;
    rdfs:subClassOf <http://example.org/ont#ClassA> .

<http://example.org/ont#prop1> a owl:ObjectProperty ;
    rdfs:label "member of" ;
    rdfs:domain <http://example.org/ont#ClassD> ;
    rdfs:range <http://example.org/ont#ClassB> .
"""

SAMPLE_RDF = """\
<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
         xmlns:owl="http://www.w3.org/2002/07/owl#"
         xmlns:iof-av="https://spec.industrialontologies.org/ontology/annotation/">
  <owl:Class rdf:about="http://example.org/iof#Machine">
    <rdfs:label xml:lang="en">Machine</rdfs:label>
    <iof-av:naturalLanguageDefinition xml:lang="en">A device that performs work.</iof-av:naturalLanguageDefinition>
  </owl:Class>
</rdf:RDF>
"""


@pytest.fixture
def sample_ontology_dir(tmp_path):
    """Create a temp directory with sample TTL and RDF files."""
    ttl_file = tmp_path / "test.ttl"
    ttl_file.write_text(SAMPLE_TTL)
    rdf_file = tmp_path / "test.rdf"
    rdf_file.write_text(SAMPLE_RDF)
    return tmp_path


@pytest.fixture
def chroma_dir(tmp_path):
    """Provide a temp directory for ChromaDB storage."""
    d = tmp_path / "chroma"
    d.mkdir()
    return d


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
def extended_ontology_dir(tmp_path):
    """Create a temp directory with extended hierarchy for testing."""
    ttl_file = tmp_path / "extended.ttl"
    ttl_file.write_text(EXTENDED_SAMPLE_TTL)
    return tmp_path
