from ontoquery.index import OntologyIndex, build_structural_context, derive_domain


def test_index_classes(chroma_dir):
    classes = [
        {"uri": "http://example.org/ont#ClassA", "label": "Agent", "definition": "An entity that acts."},
        {"uri": "http://example.org/ont#ClassB", "label": "Organization", "definition": None},
    ]
    idx = OntologyIndex(chroma_dir)
    idx.index_classes(classes, source_dir="/some/path")
    assert idx.count() == 2


def test_index_stores_source_dir(chroma_dir):
    idx = OntologyIndex(chroma_dir)
    idx.index_classes([], source_dir="/some/path")
    assert idx.get_source_dir() == "/some/path"


def test_search(chroma_dir):
    classes = [
        {"uri": "http://example.org/ont#ClassA", "label": "Agent", "definition": "An entity that acts."},
        {"uri": "http://example.org/ont#ClassB", "label": "Financial Instrument", "definition": "A tradeable asset."},
        {"uri": "http://example.org/ont#ClassC", "label": "Organization", "definition": "A group of agents."},
    ]
    idx = OntologyIndex(chroma_dir)
    idx.index_classes(classes, source_dir="/some/path")

    results = idx.search("Investment Advice", "Strategies for stock market investment", top_k=2)
    assert len(results) <= 2
    for r in results:
        assert "uri" in r
        assert "label" in r
        assert "definition" in r
        assert "distance" in r


def test_search_no_collection(chroma_dir):
    idx = OntologyIndex(chroma_dir)
    try:
        idx.search("test", "test")
        assert False, "Should have raised"
    except ValueError:
        pass


def test_search_raw(chroma_dir):
    classes = [
        {"uri": "http://example.org/ont#ClassA", "label": "Agent", "definition": "An entity that acts."},
        {"uri": "http://example.org/ont#ClassB", "label": "Financial Instrument", "definition": "A tradeable asset."},
        {"uri": "http://example.org/ont#ClassC", "label": "Organization", "definition": "A group of agents."},
    ]
    idx = OntologyIndex(chroma_dir)
    idx.index_classes(classes, source_dir="/some/path")

    results = idx.search_raw("tradeable financial asset", top_k=2)
    assert len(results) <= 2
    assert results[0]["label"] == "Financial Instrument"
    for r in results:
        assert "uri" in r
        assert "label" in r
        assert "definition" in r
        assert "distance" in r


def test_search_raw_no_collection(chroma_dir):
    idx = OntologyIndex(chroma_dir)
    try:
        idx.search_raw("test")
        assert False, "Should have raised"
    except ValueError:
        pass


# derive_domain tests


def test_derive_domain_cco():
    assert derive_domain("https://www.commoncoreontologies.org/ont00001017") == "CCO"


def test_derive_domain_fibo():
    assert derive_domain("https://spec.edmcouncil.org/fibo/ontology/FND/Foo/Bar") == "FIBO"


def test_derive_domain_commons():
    assert derive_domain("https://www.omg.org/spec/Commons/Organizations/Organization") == "Commons"


def test_derive_domain_obo():
    assert derive_domain("http://purl.obolibrary.org/obo/MAXO_0000943") == "OBO"


def test_derive_domain_iof():
    assert derive_domain("https://spec.industrialontologies.org/ontology/core/Core/Machine") == "IOF"


def test_derive_domain_d3fend():
    assert derive_domain("http://d3fend.mitre.org/ontologies/d3fend.owl#PhishingEmail") == "D3FEND"


def test_derive_domain_cso():
    assert derive_domain("http://taxonomy-refiner.io/ontologies/cso#ActOfViolence") == "CSO"


def test_derive_domain_unknown():
    assert derive_domain("http://example.org/thing") == "unknown"


# Per-domain indexing tests


def test_index_domain_classes(chroma_dir):
    classes = [
        {"uri": "https://www.commoncoreontologies.org/ont00001017", "label": "Agent", "definition": "An entity."},
        {"uri": "https://www.commoncoreontologies.org/ont00000995", "label": "Material Artifact"},
        {"uri": "https://spec.edmcouncil.org/fibo/ontology/FND/Foo/Bar", "label": "Bar", "definition": "A bar."},
        {"uri": "http://taxonomy-refiner.io/ontologies/cso#ActOfViolence", "label": "Act of Violence"},
    ]
    idx = OntologyIndex(chroma_dir)
    counts = idx.index_domain_classes(classes, source_dir="/src")
    assert counts == {"CCO": 2, "FIBO": 1, "CSO": 1}


def test_index_domain_classes_unknown_domain(chroma_dir):
    classes = [
        {"uri": "http://example.org/Thing", "label": "Thing", "definition": "A thing."},
    ]
    idx = OntologyIndex(chroma_dir)
    counts = idx.index_domain_classes(classes, source_dir="/src")
    assert counts == {"unknown": 1}


# Per-domain search tests


def test_search_domains(chroma_dir):
    classes = [
        {"uri": "https://www.commoncoreontologies.org/ont00001017", "label": "Agent", "definition": "An entity that acts."},
        {"uri": "https://spec.edmcouncil.org/fibo/ontology/FND/Foo/Bar", "label": "Financial Instrument", "definition": "A tradeable asset."},
        {"uri": "http://taxonomy-refiner.io/ontologies/cso#Fraud", "label": "Fraud", "definition": "Deceptive financial activity."},
    ]
    idx = OntologyIndex(chroma_dir)
    idx.index_domain_classes(classes, source_dir="/src")

    results = idx.search_domains("financial fraud", ["CCO", "FIBO", "CSO"], top_k_per_domain=2)
    assert "FIBO" in results or "CSO" in results
    for domain, hits in results.items():
        for r in hits:
            assert "uri" in r
            assert "label" in r
            assert r["domain"] == domain


def test_search_domains_missing_domain(chroma_dir):
    """Searching a domain that wasn't indexed returns empty for that domain."""
    classes = [
        {"uri": "https://www.commoncoreontologies.org/ont00001017", "label": "Agent", "definition": "An entity."},
    ]
    idx = OntologyIndex(chroma_dir)
    idx.index_domain_classes(classes, source_dir="/src")

    results = idx.search_domains("agent", ["CCO", "FIBO"], top_k_per_domain=5)
    assert "CCO" in results
    assert "FIBO" not in results


def test_search_domains_isolation(chroma_dir):
    """Per-domain search only returns classes from that domain."""
    classes = [
        {"uri": "https://www.commoncoreontologies.org/ont00001017", "label": "Agent", "definition": "An entity that acts."},
        {"uri": "https://spec.edmcouncil.org/fibo/ontology/FND/Foo/Agent", "label": "FIBO Agent", "definition": "A financial agent."},
    ]
    idx = OntologyIndex(chroma_dir)
    idx.index_domain_classes(classes, source_dir="/src")

    cco_results = idx.search_domains("agent entity", ["CCO"], top_k_per_domain=5)
    assert "CCO" in cco_results
    assert all(r["domain"] == "CCO" for r in cco_results["CCO"])
    assert all("commoncoreontologies.org" in r["uri"] for r in cco_results["CCO"])


def test_list_domains(chroma_dir):
    classes = [
        {"uri": "https://www.commoncoreontologies.org/ont00001017", "label": "Agent"},
        {"uri": "https://spec.edmcouncil.org/fibo/ontology/FND/Foo/Bar", "label": "Bar"},
        {"uri": "http://taxonomy-refiner.io/ontologies/cso#Fraud", "label": "Fraud"},
    ]
    idx = OntologyIndex(chroma_dir)
    idx.index_domain_classes(classes, source_dir="/src")

    domains = idx.list_domains()
    assert "CCO" in domains
    assert "FIBO" in domains
    assert "CSO" in domains


# --- Structural context tests ---


def test_build_structural_context():
    from rdflib import Graph
    from ontoquery.backend import RdflibBackend
    from ontoquery.owl2vec import project_ontology

    ttl = """\
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix ex: <http://example.org/ont#> .

ex:Animal a owl:Class ; rdfs:label "Animal" .
ex:Mammal a owl:Class ; rdfs:label "Mammal" ; rdfs:subClassOf ex:Animal .
ex:Dog a owl:Class ; rdfs:label "Dog" ; rdfs:subClassOf ex:Mammal .
ex:Cat a owl:Class ; rdfs:label "Cat" ; rdfs:subClassOf ex:Mammal .
"""
    g = Graph()
    g.parse(data=ttl, format="turtle")
    backend = RdflibBackend(g)
    projected = project_ontology(backend, bidirectional_taxonomy=True, include_literals=True)
    ctx = build_structural_context(projected)

    # Mammal should mention parent (Animal) and children (Cat, Dog)
    assert "http://example.org/ont#Mammal" in ctx
    mammal_ctx = ctx["http://example.org/ont#Mammal"]
    assert "Animal" in mammal_ctx
    assert "SubClassOf" in mammal_ctx
    assert "HasSubClass" in mammal_ctx
    assert "Dog" in mammal_ctx or "Cat" in mammal_ctx


def test_build_structural_context_with_properties():
    from rdflib import Graph
    from ontoquery.backend import RdflibBackend
    from ontoquery.owl2vec import project_ontology

    ttl = """\
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix ex: <http://example.org/ont#> .

ex:Person a owl:Class ; rdfs:label "Person" .
ex:Company a owl:Class ; rdfs:label "Company" .
ex:worksFor a owl:ObjectProperty ;
    rdfs:domain ex:Person ;
    rdfs:range ex:Company .
"""
    g = Graph()
    g.parse(data=ttl, format="turtle")
    backend = RdflibBackend(g)
    projected = project_ontology(backend, bidirectional_taxonomy=True, include_literals=True)
    ctx = build_structural_context(projected)

    assert "http://example.org/ont#Person" in ctx
    person_ctx = ctx["http://example.org/ont#Person"]
    assert "worksFor" in person_ctx
    assert "Company" in person_ctx


def test_index_with_structural_context(chroma_dir):
    """Structural context should be included in indexed documents."""
    from rdflib import Graph
    from ontoquery.backend import RdflibBackend
    from ontoquery.owl2vec import project_ontology

    ttl = """\
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix ex: <http://example.org/ont#> .

ex:Animal a owl:Class ;
    rdfs:label "Animal" ;
    skos:definition "A living creature." .
ex:Mammal a owl:Class ;
    rdfs:label "Mammal" ;
    skos:definition "A warm-blooded animal." ;
    rdfs:subClassOf ex:Animal .
ex:Dog a owl:Class ;
    rdfs:label "Dog" ;
    skos:definition "A domesticated canine." ;
    rdfs:subClassOf ex:Mammal .
"""
    g = Graph()
    g.parse(data=ttl, format="turtle")
    backend = RdflibBackend(g)
    projected = project_ontology(backend, bidirectional_taxonomy=True, include_literals=True)
    ctx = build_structural_context(projected)

    classes = [
        {"uri": "http://example.org/ont#Animal", "label": "Animal", "definition": "A living creature."},
        {"uri": "http://example.org/ont#Mammal", "label": "Mammal", "definition": "A warm-blooded animal."},
        {"uri": "http://example.org/ont#Dog", "label": "Dog", "definition": "A domesticated canine."},
    ]

    idx = OntologyIndex(chroma_dir)
    idx.index_classes(classes, source_dir="/src", structural_context=ctx)

    # Search for "warm-blooded creature that is a parent of dogs"
    # With structural context, Mammal's doc includes "HasSubClass: Dog"
    # so it should rank well
    results = idx.search_raw("parent class of dog", top_k=3)
    labels = [r["label"] for r in results]
    assert "Mammal" in labels


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
    assert "[Process]" in dc_ctx
    assert "Participants: Agent" in dc_ctx
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
