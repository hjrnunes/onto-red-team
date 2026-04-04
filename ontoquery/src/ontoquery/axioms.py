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


def extract_axioms(backend) -> dict:
    """Extract all axiom types from a backend's underlying store.

    Returns {"restrictions": ..., "disjointness": ..., "equivalences": ...}.
    Accepts a GraphBackend — accesses backend._store (oxigraph) or backend._graph (rdflib).
    Filters to indexed classes only (those with labels in the backend).
    """
    store = _get_raw_store(backend)
    raw = {
        "restrictions": extract_restrictions(store),
        "disjointness": extract_disjointness(store),
        "equivalences": extract_equivalences(store),
    }
    # Filter to indexed classes only — removes axioms for anonymous/intermediate
    # classes that are not in the ChromaDB index
    for key in ("restrictions", "equivalences"):
        raw[key] = {uri: v for uri, v in raw[key].items() if backend.get_label(uri) is not None}
    raw["disjointness"] = {
        uri: [d for d in disjoints if backend.get_label(d) is not None]
        for uri, disjoints in raw["disjointness"].items()
        if backend.get_label(uri) is not None
    }
    # Remove empty entries
    raw["disjointness"] = {uri: v for uri, v in raw["disjointness"].items() if v}
    return raw


def save_axioms(axioms: dict, path: Path) -> None:
    """Write axiom index to JSON file."""
    path.write_text(json.dumps(axioms, indent=2))


def load_axioms(path: Path) -> dict | None:
    """Load axiom index from JSON file. Returns None if file doesn't exist."""
    if not path.exists():
        return None
    return json.loads(path.read_text())
