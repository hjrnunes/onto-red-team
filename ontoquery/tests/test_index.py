from ontoquery.index import OntologyIndex, derive_domain


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
