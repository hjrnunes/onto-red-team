from ontoquery.graph import load_graph, get_siblings, get_subclasses_recursive, get_class_definition


# Tests for get_siblings
def test_get_siblings(extended_ontology_dir):
    graph = load_graph(extended_ontology_dir)
    siblings = get_siblings(graph, "http://example.org/ont#ClassD")
    uris = {s["uri"] for s in siblings}
    assert "http://example.org/ont#ClassE" in uris
    assert "http://example.org/ont#ClassD" not in uris


def test_get_siblings_includes_shared_parent(extended_ontology_dir):
    graph = load_graph(extended_ontology_dir)
    siblings = get_siblings(graph, "http://example.org/ont#ClassD")
    for s in siblings:
        assert "shared_parent" in s
        assert s["shared_parent"]["uri"] == "http://example.org/ont#ClassA"


def test_get_siblings_no_siblings(extended_ontology_dir):
    graph = load_graph(extended_ontology_dir)
    siblings = get_siblings(graph, "http://example.org/ont#ClassG")
    assert len(siblings) == 0


def test_get_siblings_root_class(extended_ontology_dir):
    graph = load_graph(extended_ontology_dir)
    siblings = get_siblings(graph, "http://example.org/ont#ClassA")
    assert len(siblings) == 0


# Tests for get_subclasses_recursive
def test_get_subclasses_recursive_depth_1(extended_ontology_dir):
    graph = load_graph(extended_ontology_dir)
    subs = get_subclasses_recursive(graph, "http://example.org/ont#ClassA", depth=1)
    uris = {s["uri"] for s in subs}
    assert "http://example.org/ont#ClassD" in uris
    assert "http://example.org/ont#ClassE" in uris
    assert "http://example.org/ont#ClassF" not in uris


def test_get_subclasses_recursive_depth_2(extended_ontology_dir):
    graph = load_graph(extended_ontology_dir)
    subs = get_subclasses_recursive(graph, "http://example.org/ont#ClassA", depth=2)
    uris = {s["uri"] for s in subs}
    assert "http://example.org/ont#ClassD" in uris
    assert "http://example.org/ont#ClassE" in uris
    assert "http://example.org/ont#ClassF" in uris
    assert "http://example.org/ont#ClassG" not in uris


def test_get_subclasses_recursive_depth_3(extended_ontology_dir):
    graph = load_graph(extended_ontology_dir)
    subs = get_subclasses_recursive(graph, "http://example.org/ont#ClassA", depth=3)
    uris = {s["uri"] for s in subs}
    assert "http://example.org/ont#ClassG" in uris


def test_get_subclasses_recursive_includes_depth(extended_ontology_dir):
    graph = load_graph(extended_ontology_dir)
    subs = get_subclasses_recursive(graph, "http://example.org/ont#ClassA", depth=3)
    by_uri = {s["uri"]: s for s in subs}
    assert by_uri["http://example.org/ont#ClassD"]["depth"] == 1
    assert by_uri["http://example.org/ont#ClassF"]["depth"] == 2
    assert by_uri["http://example.org/ont#ClassG"]["depth"] == 3


def test_get_subclasses_recursive_leaf_node(extended_ontology_dir):
    graph = load_graph(extended_ontology_dir)
    subs = get_subclasses_recursive(graph, "http://example.org/ont#ClassG", depth=5)
    assert len(subs) == 0


# Tests for get_class_definition
def test_get_class_definition(extended_ontology_dir):
    graph = load_graph(extended_ontology_dir)
    result = get_class_definition(graph, "http://example.org/ont#ClassD")
    assert result["uri"] == "http://example.org/ont#ClassD"
    assert result["label"] == "Person"
    assert result["definition"] == "A human agent."
    assert any(s["uri"] == "http://example.org/ont#ClassA" for s in result["superclasses"])


def test_get_class_definition_no_definition(extended_ontology_dir):
    graph = load_graph(extended_ontology_dir)
    result = get_class_definition(graph, "http://example.org/ont#ClassB")
    assert result["label"] == "Organization"
    assert result["definition"] == "A group of agents."


def test_get_class_definition_not_found(extended_ontology_dir):
    graph = load_graph(extended_ontology_dir)
    result = get_class_definition(graph, "http://example.org/nonexistent")
    assert result is None
