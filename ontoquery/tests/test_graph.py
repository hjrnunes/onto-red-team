from ontoquery.graph import find_ontology_files, load_graph, extract_classes, get_superclasses, get_subclasses, get_properties, load_graph_cached


def test_find_ontology_files(sample_ontology_dir):
    files = find_ontology_files(sample_ontology_dir)
    extensions = {f.suffix for f in files}
    assert ".ttl" in extensions
    assert ".rdf" in extensions
    assert len(files) >= 2


def test_find_ontology_files_recursive(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    (tmp_path / "top.ttl").write_text("")
    (sub / "nested.rdf").write_text("")
    files = find_ontology_files(tmp_path)
    assert len(files) == 2


def test_load_graph(sample_ontology_dir):
    graph = load_graph(sample_ontology_dir)
    assert len(graph) > 0


def test_load_graph_skips_bad_files(tmp_path):
    (tmp_path / "bad.ttl").write_text("this is not valid turtle @@@@")
    (tmp_path / "good.ttl").write_text(
        '@prefix owl: <http://www.w3.org/2002/07/owl#> .\n'
        '<http://example.org/X> a owl:Class .\n'
    )
    graph = load_graph(tmp_path)
    assert len(graph) > 0


def test_extract_classes(sample_ontology_dir):
    graph = load_graph(sample_ontology_dir)
    classes = extract_classes(graph)
    uris = {c["uri"] for c in classes}
    assert "http://example.org/ont#ClassA" in uris
    assert "http://example.org/ont#ClassB" in uris
    assert "http://example.org/ont#ClassC" not in uris
    assert "http://example.org/ont#ClassD" in uris
    assert "http://example.org/iof#Machine" in uris


def test_extract_classes_definitions(sample_ontology_dir):
    graph = load_graph(sample_ontology_dir)
    classes = extract_classes(graph)
    by_uri = {c["uri"]: c for c in classes}
    assert by_uri["http://example.org/ont#ClassA"]["definition"] == "An entity that acts."
    assert by_uri["http://example.org/ont#ClassB"]["definition"] == "A group of agents."
    assert by_uri["http://example.org/iof#Machine"]["definition"] == "A device that performs work."


def test_extract_classes_labels(sample_ontology_dir):
    graph = load_graph(sample_ontology_dir)
    classes = extract_classes(graph)
    by_uri = {c["uri"]: c for c in classes}
    assert by_uri["http://example.org/ont#ClassA"]["label"] == "Agent"
    assert by_uri["http://example.org/ont#ClassD"]["label"] == "Person"


def test_extract_classes_source_file(sample_ontology_dir):
    graph = load_graph(sample_ontology_dir)
    classes = extract_classes(graph, source_file="test.ttl")
    for c in classes:
        assert c["source_file"] == "test.ttl"


def test_get_superclasses(sample_ontology_dir):
    graph = load_graph(sample_ontology_dir)
    supers = get_superclasses(graph, "http://example.org/ont#ClassD")
    uris = {s["uri"] for s in supers}
    assert "http://example.org/ont#ClassA" in uris


def test_get_superclasses_filters_blank_nodes(sample_ontology_dir):
    graph = load_graph(sample_ontology_dir)
    supers = get_superclasses(graph, "http://example.org/ont#ClassD")
    for s in supers:
        assert s["uri"].startswith("http")


def test_get_subclasses(sample_ontology_dir):
    graph = load_graph(sample_ontology_dir)
    subs = get_subclasses(graph, "http://example.org/ont#ClassA")
    uris = {s["uri"] for s in subs}
    assert "http://example.org/ont#ClassD" in uris


def test_get_properties_domain(sample_ontology_dir):
    graph = load_graph(sample_ontology_dir)
    props = get_properties(graph, "http://example.org/ont#ClassD")
    assert len(props) >= 1
    prop = next(p for p in props if p["label"] == "member of")
    assert prop["role"] == "domain"
    assert prop["other_class"]["uri"] == "http://example.org/ont#ClassB"


def test_get_properties_range(sample_ontology_dir):
    graph = load_graph(sample_ontology_dir)
    props = get_properties(graph, "http://example.org/ont#ClassB")
    prop = next(p for p in props if p["label"] == "member of")
    assert prop["role"] == "range"
    assert prop["other_class"]["uri"] == "http://example.org/ont#ClassD"


def test_load_graph_cached_creates_cache(sample_ontology_dir, tmp_path):
    cache_path = tmp_path / "graph.nt"
    graph = load_graph_cached([sample_ontology_dir], cache_path)
    assert len(graph) > 0
    assert cache_path.exists()


def test_load_graph_cached_uses_cache(sample_ontology_dir, tmp_path):
    cache_path = tmp_path / "graph.nt"
    graph1 = load_graph_cached([sample_ontology_dir], cache_path)
    count1 = len(graph1)
    graph2 = load_graph_cached([sample_ontology_dir], cache_path)
    assert len(graph2) == count1


def test_find_owl_files(tmp_path):
    (tmp_path / "test.owl").write_text(
        '<?xml version="1.0"?>\n'
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"\n'
        '         xmlns:owl="http://www.w3.org/2002/07/owl#"\n'
        '         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#">\n'
        '  <owl:Class rdf:about="http://example.org/obo#Test">\n'
        '    <rdfs:label>Test</rdfs:label>\n'
        '  </owl:Class>\n'
        '</rdf:RDF>\n'
    )
    files = find_ontology_files(tmp_path)
    assert len(files) == 1
    assert files[0].suffix == ".owl"


def test_extract_obo_definition(tmp_path):
    (tmp_path / "test.owl").write_text(
        '<?xml version="1.0"?>\n'
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"\n'
        '         xmlns:owl="http://www.w3.org/2002/07/owl#"\n'
        '         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"\n'
        '         xmlns:obo="http://purl.obolibrary.org/obo/">\n'
        '  <owl:Class rdf:about="http://example.org/obo#Disease">\n'
        '    <rdfs:label>disease</rdfs:label>\n'
        '    <obo:IAO_0000115>A disorder of structure or function.</obo:IAO_0000115>\n'
        '  </owl:Class>\n'
        '</rdf:RDF>\n'
    )
    graph = load_graph(tmp_path)
    classes = extract_classes(graph)
    by_uri = {c["uri"]: c for c in classes}
    assert "http://example.org/obo#Disease" in by_uri
    assert by_uri["http://example.org/obo#Disease"]["definition"] == "A disorder of structure or function."
