"""OWL2Vec*-style ontology projection, random walks, and embedding.

Projects OWL axioms into a flat graph of (subject, predicate, object) edges,
then generates random walks and trains Word2Vec embeddings that capture both
structural and lexical signals.

Implements the core projection rules from:
  Chen et al. "OWL2Vec*: Embedding of OWL ontologies"
  Machine Learning (2021). doi:10.1007/s10994-021-05997-6

Works with both pyoxigraph and rdflib backends via the _query_triples adapter
from axioms.py.
"""

from __future__ import annotations

import logging
import random
from collections import defaultdict
from dataclasses import dataclass, field

from rdflib import OWL, RDF, RDFS, Graph

from ontoquery.axioms import (
    _get_raw_store,
    _is_blank,
    _is_named,
    _node_str,
    _query_triples,
    _to_node,
    _traverse_rdf_list,
)

try:
    import pyoxigraph as ox

    _HAS_OXIGRAPH = True
except ImportError:
    _HAS_OXIGRAPH = False

_logger = logging.getLogger(__name__)

# Synthetic predicates for projected edges
SUBCLASS_OF = "http://www.w3.org/2000/01/rdf-schema#subClassOf"
SUPERCLASS_OF = "http://owl2vec.projection/superClassOf"
TYPE_OF = "http://owl2vec.projection/typeOf"
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"

# Annotation predicates to include as literal edges
_ANNOTATION_PREDS = [
    "http://www.w3.org/2000/01/rdf-schema#label",
    "http://www.w3.org/2004/02/skos/core#prefLabel",
    "http://www.w3.org/2004/02/skos/core#definition",
    "http://www.w3.org/2000/01/rdf-schema#comment",
    "http://purl.obolibrary.org/obo/IAO_0000115",
    "http://d3fend.mitre.org/ontologies/d3fend.owl#definition",
    "https://spec.industrialontologies.org/ontology/annotation/naturalLanguageDefinition",
]


@dataclass
class ProjectedGraph:
    """Result of OWL2Vec* projection: a flat graph of edges."""

    edges: list[tuple[str, str, str]] = field(default_factory=list)
    """(subject, predicate, object) triples — all strings (URIs or literals)."""

    literal_edges: list[tuple[str, str, str]] = field(default_factory=list)
    """Annotation edges where object is a literal string, not a URI."""

    classes: set[str] = field(default_factory=set)
    """All named class URIs found during projection."""

    def edge_count(self) -> int:
        return len(self.edges)

    def literal_edge_count(self) -> int:
        return len(self.literal_edges)


def project_ontology(
    backend,
    *,
    bidirectional_taxonomy: bool = True,
    include_literals: bool = True,
) -> ProjectedGraph:
    """Apply OWL2Vec* projection rules to produce a flat graph.

    Args:
        backend: A GraphBackend (OxigraphBackend or RdflibBackend).
        bidirectional_taxonomy: Add reverse superClassOf edges for each subClassOf.
        include_literals: Include annotation property edges (labels, definitions).

    Returns:
        ProjectedGraph with structural edges and optional literal edges.
    """
    store = _get_raw_store(backend)
    graph = ProjectedGraph()

    # Collect all named classes
    rdf_type = _to_node(str(RDF.type), store)
    owl_class = _to_node(str(OWL.Class), store)
    for s, _, _ in _query_triples(store, None, rdf_type, owl_class):
        if _is_named(s):
            graph.classes.add(_node_str(s))

    _project_taxonomy(store, graph, bidirectional_taxonomy)
    _project_equivalences_atomic(store, graph, bidirectional_taxonomy)
    _project_restrictions(store, graph)
    _project_domain_range(store, graph)

    if include_literals:
        _project_annotations(store, graph)

    _logger.info(
        "Projected %d structural edges + %d literal edges from %d classes",
        graph.edge_count(),
        graph.literal_edge_count(),
        len(graph.classes),
    )
    return graph


# --- Projection rules ---


def _project_taxonomy(store, graph: ProjectedGraph, bidirectional: bool) -> None:
    """Rule 7: SubClassOf between named classes."""
    rdfs_sub = _to_node(str(RDFS.subClassOf), store)
    owl_thing = _to_node(str(OWL.Thing), store)
    owl_nothing = _to_node(str(OWL.Nothing), store)

    for s, _, o in _query_triples(store, None, rdfs_sub, None):
        if not _is_named(s) or not _is_named(o):
            continue
        s_uri, o_uri = _node_str(s), _node_str(o)
        # Skip owl:Thing and owl:Nothing — too abstract
        if o_uri == str(OWL.Thing) or s_uri == str(OWL.Nothing):
            continue
        graph.edges.append((s_uri, SUBCLASS_OF, o_uri))
        if bidirectional:
            graph.edges.append((o_uri, SUPERCLASS_OF, s_uri))


def _project_equivalences_atomic(
    store, graph: ProjectedGraph, bidirectional: bool
) -> None:
    """Atomic EquivalentClasses: decompose into bidirectional SubClassOf."""
    owl_equiv = _to_node(str(OWL.equivalentClass), store)

    for s, _, o in _query_triples(store, None, owl_equiv, None):
        if not _is_named(s) or not _is_named(o):
            continue
        s_uri, o_uri = _node_str(s), _node_str(o)
        graph.edges.append((s_uri, SUBCLASS_OF, o_uri))
        graph.edges.append((o_uri, SUBCLASS_OF, s_uri))
        if bidirectional:
            graph.edges.append((o_uri, SUPERCLASS_OF, s_uri))
            graph.edges.append((s_uri, SUPERCLASS_OF, o_uri))


def _project_restrictions(store, graph: ProjectedGraph) -> None:
    """Rule 1: Existential/universal restrictions -> property edges.

    Handles:
    - A rdfs:subClassOf [owl:onProperty R; owl:someValuesFrom B] -> (A, R, B)
    - A owl:equivalentClass [owl:onProperty R; owl:someValuesFrom B] -> (A, R, B)
    - Same for allValuesFrom
    - Complex fillers (intersectionOf/unionOf) -> one edge per named member
    """
    rdfs_sub = _to_node(str(RDFS.subClassOf), store)
    owl_equiv = _to_node(str(OWL.equivalentClass), store)

    for axiom_pred in (rdfs_sub, owl_equiv):
        # RHS restrictions: A <axiom_pred> [restriction]
        for s, _, o in _query_triples(store, None, axiom_pred, None):
            if not _is_named(s) or not _is_blank(o):
                continue
            s_uri = _node_str(s)
            _extract_restriction_edges(store, s_uri, o, graph)

        # Also handle complex equivalences with intersectionOf
        if axiom_pred == _to_node(str(OWL.equivalentClass), store):
            owl_intersection = _to_node(str(OWL.intersectionOf), store)
            for s, _, o in _query_triples(store, None, axiom_pred, None):
                if not _is_named(s) or not _is_blank(o):
                    continue
                s_uri = _node_str(s)
                for head in _query_objects_list(store, o, owl_intersection):
                    members = _traverse_rdf_list(store, head)
                    for member in members:
                        if _is_blank(member):
                            _extract_restriction_edges(store, s_uri, member, graph)
                        elif _is_named(member):
                            # Named class in intersection -> subClassOf edge
                            graph.edges.append(
                                (s_uri, SUBCLASS_OF, _node_str(member))
                            )


def _extract_restriction_edges(
    store, subject_uri: str, bnode, graph: ProjectedGraph
) -> None:
    """Extract (subject, property, filler) edges from an OWL restriction bnode."""
    rdf_type = _to_node(str(RDF.type), store)
    owl_restriction = _to_node(str(OWL.Restriction), store)
    owl_on_property = _to_node(str(OWL.onProperty), store)

    # Verify it's a restriction
    if not any(_query_triples(store, bnode, rdf_type, owl_restriction)):
        return

    # Get the property
    prop_uri = None
    for p in _query_objects_list(store, bnode, owl_on_property):
        if _is_named(p):
            prop_uri = _node_str(p)
            break
    if prop_uri is None:
        return

    # Get the filler (someValuesFrom, allValuesFrom, onClass)
    for filler_pred_str in (
        str(OWL.someValuesFrom),
        str(OWL.allValuesFrom),
        "http://www.w3.org/2002/07/owl#onClass",
    ):
        filler_pred = _to_node(filler_pred_str, store)
        for filler in _query_objects_list(store, bnode, filler_pred):
            if _is_named(filler):
                graph.edges.append((subject_uri, prop_uri, _node_str(filler)))
            elif _is_blank(filler):
                # Complex filler: unionOf or intersectionOf
                _extract_complex_filler_edges(
                    store, subject_uri, prop_uri, filler, graph
                )


def _extract_complex_filler_edges(
    store, subject_uri: str, prop_uri: str, bnode, graph: ProjectedGraph
) -> None:
    """Handle union/intersection fillers in restrictions."""
    owl_union = _to_node(str(OWL.unionOf), store)
    owl_intersection = _to_node(str(OWL.intersectionOf), store)

    for list_pred in (owl_union, owl_intersection):
        for head in _query_objects_list(store, bnode, list_pred):
            members = _traverse_rdf_list(store, head)
            for member in members:
                if _is_named(member):
                    graph.edges.append((subject_uri, prop_uri, _node_str(member)))


def _project_domain_range(store, graph: ProjectedGraph) -> None:
    """Rule 2: Domain + Range combination -> property edges."""
    rdfs_domain = _to_node(str(RDFS.domain), store)
    rdfs_range = _to_node(str(RDFS.range), store)

    # Collect domain and range for each property
    prop_domains: dict[str, list[str]] = defaultdict(list)
    prop_ranges: dict[str, list[str]] = defaultdict(list)

    for prop, _, domain in _query_triples(store, None, rdfs_domain, None):
        if _is_named(prop) and _is_named(domain):
            prop_domains[_node_str(prop)].append(_node_str(domain))

    for prop, _, range_cls in _query_triples(store, None, rdfs_range, None):
        if _is_named(prop) and _is_named(range_cls):
            prop_ranges[_node_str(prop)].append(_node_str(range_cls))

    # Emit (domain, prop, range) for each combination
    for prop_uri in set(prop_domains) & set(prop_ranges):
        for d in prop_domains[prop_uri]:
            for r in prop_ranges[prop_uri]:
                graph.edges.append((d, prop_uri, r))


def _project_annotations(store, graph: ProjectedGraph) -> None:
    """Include annotation properties as literal edges."""
    rdf_type = _to_node(str(RDF.type), store)
    owl_class = _to_node(str(OWL.Class), store)

    for ann_pred_str in _ANNOTATION_PREDS:
        ann_pred = _to_node(ann_pred_str, store)
        for s, _, o in _query_triples(store, None, ann_pred, None):
            if not _is_named(s):
                continue
            s_uri = _node_str(s)
            if s_uri not in graph.classes:
                continue
            literal_val = _node_str(o)
            if literal_val:
                graph.literal_edges.append((s_uri, ann_pred_str, literal_val))


def _query_objects_list(store, subject, predicate) -> list:
    """Collect all objects matching (subject, predicate, ?) into a list."""
    results = []
    for _, _, o in _query_triples(store, subject, predicate, None):
        results.append(o)
    return results


# --- Random walks ---


def build_adjacency(
    graph: ProjectedGraph, *, include_literals: bool = False
) -> dict[str, list[tuple[str, str]]]:
    """Build adjacency list from projected edges.

    Returns:
        {node: [(predicate, neighbor), ...]} for efficient walk generation.
    """
    adj: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for s, p, o in graph.edges:
        adj[s].append((p, o))
    if include_literals:
        for s, p, o in graph.literal_edges:
            adj[s].append((p, o))
    return dict(adj)


def random_walks(
    adjacency: dict[str, list[tuple[str, str]]],
    seeds: list[str] | None = None,
    *,
    num_walks: int = 10,
    walk_length: int = 30,
    rng_seed: int | None = 42,
) -> list[list[str]]:
    """Generate DeepWalk-style random walks over the projected graph.

    Each walk interleaves entities and predicates:
    [entity, predicate, entity, predicate, entity, ...]

    Args:
        adjacency: {node: [(predicate, neighbor), ...]}
        seeds: Starting nodes. Defaults to all nodes in adjacency.
        num_walks: Number of walks per seed node.
        walk_length: Maximum number of hops (each hop adds predicate + entity).
        rng_seed: Random seed for reproducibility.

    Returns:
        List of walks, each a list of URI/literal strings.
    """
    rng = random.Random(rng_seed)
    if seeds is None:
        seeds = list(adjacency.keys())

    walks: list[list[str]] = []
    for _ in range(num_walks):
        for seed in seeds:
            walk = [seed]
            current = seed
            for _ in range(walk_length):
                neighbors = adjacency.get(current, [])
                if not neighbors:
                    break
                predicate, next_node = rng.choice(neighbors)
                walk.extend([predicate, next_node])
                current = next_node
            walks.append(walk)

    return walks


# --- Word2Vec training ---


def train_embeddings(
    walks: list[list[str]],
    *,
    vector_size: int = 100,
    window: int = 5,
    min_count: int = 1,
    negative: int = 25,
    epochs: int = 10,
    seed: int = 42,
    workers: int = 1,
):
    """Train Word2Vec (skip-gram) on walk corpus.

    Args:
        walks: List of token sequences from random_walks().
        vector_size: Embedding dimensionality.
        window: Context window size.
        min_count: Minimum token frequency.
        negative: Negative sampling count.
        epochs: Training epochs.
        seed: Random seed.
        workers: Number of training threads.

    Returns:
        gensim.models.Word2Vec model.

    Raises:
        ImportError: If gensim is not installed.
    """
    try:
        from gensim.models import Word2Vec
    except ImportError:
        raise ImportError(
            "gensim is required for OWL2Vec* embeddings. "
            "Install it with: pip install gensim"
        )

    model = Word2Vec(
        sentences=walks,
        vector_size=vector_size,
        window=window,
        min_count=min_count,
        negative=negative,
        sg=1,  # Skip-gram
        epochs=epochs,
        seed=seed,
        workers=workers,
    )
    return model


def get_class_embeddings(model, classes: set[str]) -> dict[str, list[float]]:
    """Extract embeddings for ontology classes from a trained Word2Vec model.

    Returns:
        {uri: embedding_vector} for classes that have embeddings.
    """
    result = {}
    for uri in classes:
        if uri in model.wv:
            result[uri] = model.wv[uri].tolist()
    return result


# --- High-level API ---


def owl2vec_embed(
    backend,
    *,
    bidirectional_taxonomy: bool = True,
    include_literals: bool = True,
    num_walks: int = 10,
    walk_length: int = 30,
    vector_size: int = 100,
    window: int = 5,
    epochs: int = 10,
    rng_seed: int = 42,
) -> tuple[dict[str, list[float]], ProjectedGraph]:
    """End-to-end OWL2Vec* embedding: project -> walk -> train -> extract.

    Args:
        backend: A GraphBackend (OxigraphBackend or RdflibBackend).
        Plus parameters for projection, walking, and training.

    Returns:
        (embeddings_dict, projected_graph) where embeddings_dict is
        {uri: vector} for each class with an embedding.
    """
    graph = project_ontology(
        backend,
        bidirectional_taxonomy=bidirectional_taxonomy,
        include_literals=include_literals,
    )

    adjacency = build_adjacency(graph, include_literals=include_literals)

    walks = random_walks(
        adjacency,
        seeds=list(graph.classes),
        num_walks=num_walks,
        walk_length=walk_length,
        rng_seed=rng_seed,
    )

    model = train_embeddings(
        walks,
        vector_size=vector_size,
        window=window,
        epochs=epochs,
        seed=rng_seed,
    )

    embeddings = get_class_embeddings(model, graph.classes)
    return embeddings, graph
