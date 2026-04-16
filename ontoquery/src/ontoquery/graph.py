import sys
from collections import deque
from pathlib import Path
from rdflib import Graph, OWL, RDF, RDFS, SKOS, Namespace, URIRef

IOF_AV = Namespace("https://spec.industrialontologies.org/ontology/annotation/")
OBO = Namespace("http://purl.obolibrary.org/obo/")
D3F = Namespace("http://d3fend.mitre.org/ontologies/d3fend.owl#")

FORMAT_MAP = {".ttl": "turtle", ".rdf": "xml", ".owl": "xml"}


def find_ontology_files(path: Path) -> list[Path]:
    """Find ontology files from a path (file or directory).

    If *path* is a single file with a recognised extension, return it directly.
    If *path* is a directory, recursively find all .ttl, .rdf and .owl files.
    """
    path = Path(path)
    if path.is_file():
        if path.suffix in FORMAT_MAP:
            return [path]
        return []
    files = []
    for ext in ("*.ttl", "*.rdf", "*.owl"):
        files.extend(path.rglob(ext))
    return sorted(files)


def load_graph(directory: Path) -> Graph:
    """Parse all .ttl and .rdf files under directory into a single rdflib Graph."""
    g = Graph()
    for f in find_ontology_files(directory):
        fmt = FORMAT_MAP.get(f.suffix)
        if fmt is None:
            continue
        try:
            g.parse(str(f), format=fmt)
        except Exception as e:
            print(f"Warning: skipping {f.name}: {e}", file=sys.stderr)
    return g


def extract_classes(graph: Graph, source_file: str = "") -> list[dict]:
    """Extract all OWL classes with label and definition from the graph."""
    classes = []
    seen = set()
    for cls in graph.subjects(RDF.type, OWL.Class):
        if not isinstance(cls, URIRef):
            continue
        uri = str(cls)
        if uri in seen:
            continue
        seen.add(uri)
        label = _get_label(graph, cls)
        if label is None:
            continue
        definition = _get_definition(graph, cls)
        classes.append({
            "uri": uri,
            "label": label,
            "definition": definition,
            "source_file": source_file,
        })
    return classes


def _get_label(graph: Graph, uri: URIRef) -> str | None:
    """Get label from rdfs:label or skos:prefLabel."""
    for pred in (RDFS.label, SKOS.prefLabel):
        for obj in graph.objects(uri, pred):
            return str(obj)
    return None


def _get_definition(graph: Graph, uri: URIRef) -> str | None:
    """Get definition with fallback: skos:definition > iof-av:naturalLanguageDefinition > obo:IAO_0000115 > d3f:definition > rdfs:comment."""
    for pred in (SKOS.definition, IOF_AV.naturalLanguageDefinition, OBO.IAO_0000115, D3F.definition, RDFS.comment):
        for obj in graph.objects(uri, pred):
            return str(obj)
    return None


def get_superclasses(graph: Graph, class_uri: str) -> list[dict]:
    """Get direct named superclasses (filters out blank nodes)."""
    uri = URIRef(class_uri)
    results = []
    for parent in graph.objects(uri, RDFS.subClassOf):
        if not isinstance(parent, URIRef):
            continue
        label = _get_label(graph, parent)
        results.append({"uri": str(parent), "label": label})
    return results


def get_subclasses(graph: Graph, class_uri: str) -> list[dict]:
    """Get direct named subclasses."""
    uri = URIRef(class_uri)
    results = []
    for child in graph.subjects(RDFS.subClassOf, uri):
        if not isinstance(child, URIRef):
            continue
        label = _get_label(graph, child)
        results.append({"uri": str(child), "label": label})
    return results


def get_properties(graph: Graph, class_uri: str) -> list[dict]:
    """Get properties where this class appears as domain or range."""
    uri = URIRef(class_uri)
    results = []
    for prop in graph.subjects(RDFS.domain, uri):
        if not isinstance(prop, URIRef):
            continue
        prop_label = _get_label(graph, prop)
        for range_cls in graph.objects(prop, RDFS.range):
            if not isinstance(range_cls, URIRef):
                continue
            results.append({
                "uri": str(prop),
                "label": prop_label,
                "role": "domain",
                "other_class": {
                    "uri": str(range_cls),
                    "label": _get_label(graph, range_cls),
                },
            })
    for prop in graph.subjects(RDFS.range, uri):
        if not isinstance(prop, URIRef):
            continue
        prop_label = _get_label(graph, prop)
        for domain_cls in graph.objects(prop, RDFS.domain):
            if not isinstance(domain_cls, URIRef):
                continue
            results.append({
                "uri": str(prop),
                "label": prop_label,
                "role": "range",
                "other_class": {
                    "uri": str(domain_cls),
                    "label": _get_label(graph, domain_cls),
                },
            })
    return results


def load_graph_cached(directories: list[Path], cache_path: Path) -> Graph:
    """Load graph from cache if available, otherwise parse from directories and cache."""
    cache_path = Path(cache_path)
    if cache_path.exists():
        g = Graph()
        g.parse(str(cache_path), format="nt")
        return g

    g = Graph()
    for directory in directories:
        for f in find_ontology_files(directory):
            fmt = FORMAT_MAP.get(f.suffix)
            if fmt is None:
                continue
            try:
                g.parse(str(f), format=fmt)
            except Exception as e:
                print(f"Warning: skipping {f.name}: {e}", file=sys.stderr)
    g.serialize(str(cache_path), format="nt")
    return g


def get_siblings(graph: Graph, class_uri: str) -> list[dict]:
    """Get other classes that share the same direct superclass."""
    uri = URIRef(class_uri)
    results = []
    seen = set()
    for parent in graph.objects(uri, RDFS.subClassOf):
        if not isinstance(parent, URIRef):
            continue
        parent_label = _get_label(graph, parent)
        for sibling in graph.subjects(RDFS.subClassOf, parent):
            if not isinstance(sibling, URIRef):
                continue
            if sibling == uri:
                continue
            sib_str = str(sibling)
            if sib_str in seen:
                continue
            seen.add(sib_str)
            results.append({
                "uri": sib_str,
                "label": _get_label(graph, sibling),
                "shared_parent": {"uri": str(parent), "label": parent_label},
            })
    return results


def get_subclasses_recursive(graph: Graph, class_uri: str, depth: int = 1) -> list[dict]:
    """Get subclasses up to `depth` levels deep using BFS."""
    results = []
    seen = set()
    queue = deque()
    queue.append((URIRef(class_uri), 0))
    seen.add(class_uri)

    while queue:
        current_uri, current_depth = queue.popleft()
        if current_depth >= depth:
            continue
        for child in graph.subjects(RDFS.subClassOf, current_uri):
            if not isinstance(child, URIRef):
                continue
            child_str = str(child)
            if child_str in seen:
                continue
            seen.add(child_str)
            results.append({
                "uri": child_str,
                "label": _get_label(graph, child),
                "depth": current_depth + 1,
            })
            queue.append((child, current_depth + 1))

    return results


def get_class_definition(graph: Graph, class_uri: str) -> dict | None:
    """Get label, definition, and immediate superclasses for a class."""
    uri = URIRef(class_uri)
    if (uri, RDF.type, OWL.Class) not in graph:
        return None
    label = _get_label(graph, uri)
    if label is None:
        return None
    definition = _get_definition(graph, uri)
    superclasses = get_superclasses(graph, class_uri)
    return {
        "uri": class_uri,
        "label": label,
        "definition": definition,
        "superclasses": superclasses,
    }
