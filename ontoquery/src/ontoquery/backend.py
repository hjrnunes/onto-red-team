"""Graph backend abstraction for ontology queries.

Provides a Protocol with two implementations:
- OxigraphBackend: Rust-based, 65x faster parsing, instant RocksDB startup
- RdflibBackend: pure-Python fallback

The Protocol is structural (typing.Protocol) — the Python equivalent of a
Clojure protocol. Any object with the right methods satisfies it; no
inheritance required.

Factory functions:
- load_backend(): open a persisted graph for runtime queries
- create_index_backend(): parse ontology files and persist for later queries
"""

from __future__ import annotations

import shutil
import sys
from collections import deque
from pathlib import Path
from typing import Protocol, runtime_checkable
import logging

from rdflib import Graph, OWL, RDF, RDFS, SKOS, Namespace, URIRef

_logger = logging.getLogger(__name__)

from ontoquery.graph import (
    FORMAT_MAP,
    IOF_AV,
    OBO,
    _get_label as _rdflib_label,
    _get_definition as _rdflib_defn,
    extract_classes as _rdflib_extract,
    get_superclasses as _rdflib_supers,
    get_subclasses as _rdflib_subs,
    get_subclasses_recursive as _rdflib_subs_rec,
    get_siblings as _rdflib_sibs,
    get_properties as _rdflib_props,
    get_class_definition as _rdflib_classdef,
    load_graph_cached as _rdflib_load_cached,
)

try:
    import pyoxigraph as ox

    _HAS_OXIGRAPH = True
except ImportError:
    _HAS_OXIGRAPH = False


def has_oxigraph() -> bool:
    return _HAS_OXIGRAPH


# --- Protocol ---


@runtime_checkable
class GraphBackend(Protocol):
    """Structural protocol for ontology graph backends."""

    def extract_classes(self, source_file: str = "") -> list[dict]: ...
    def get_label(self, uri: str) -> str | None: ...
    def get_definition(self, uri: str) -> str | None: ...
    def get_superclasses(self, class_uri: str) -> list[dict]: ...
    def get_subclasses(self, class_uri: str) -> list[dict]: ...
    def get_subclasses_recursive(self, class_uri: str, depth: int = 1) -> list[dict]: ...
    def get_siblings(self, class_uri: str) -> list[dict]: ...
    def get_properties(self, class_uri: str) -> list[dict]: ...
    def get_class_definition(self, class_uri: str) -> dict | None: ...
    def is_class(self, class_uri: str) -> bool: ...
    def get_restrictions(self, class_uri: str) -> list[dict]: ...
    def get_disjoint_classes(self, class_uri: str) -> list[str]: ...
    def get_equivalent_axioms(self, class_uri: str) -> list[dict]: ...


# --- rdflib implementation ---


class RdflibBackend:
    """Graph backend using rdflib (pure Python)."""

    def __init__(self, graph: Graph, axioms: dict | None = None):
        self._graph = graph
        self._axioms = axioms or {"restrictions": {}, "disjointness": {}, "equivalences": {}}

    def extract_classes(self, source_file: str = "") -> list[dict]:
        return _rdflib_extract(self._graph, source_file)

    def get_label(self, uri: str) -> str | None:
        return _rdflib_label(self._graph, URIRef(uri))

    def get_definition(self, uri: str) -> str | None:
        return _rdflib_defn(self._graph, URIRef(uri))

    def get_superclasses(self, class_uri: str) -> list[dict]:
        return _rdflib_supers(self._graph, class_uri)

    def get_subclasses(self, class_uri: str) -> list[dict]:
        return _rdflib_subs(self._graph, class_uri)

    def get_subclasses_recursive(self, class_uri: str, depth: int = 1) -> list[dict]:
        return _rdflib_subs_rec(self._graph, class_uri, depth)

    def get_siblings(self, class_uri: str) -> list[dict]:
        return _rdflib_sibs(self._graph, class_uri)

    def get_properties(self, class_uri: str) -> list[dict]:
        return _rdflib_props(self._graph, class_uri)

    def get_class_definition(self, class_uri: str) -> dict | None:
        return _rdflib_classdef(self._graph, class_uri)

    def is_class(self, class_uri: str) -> bool:
        return (URIRef(class_uri), RDF.type, OWL.Class) in self._graph

    def get_restrictions(self, class_uri: str) -> list[dict]:
        return self._axioms.get("restrictions", {}).get(class_uri, [])

    def get_disjoint_classes(self, class_uri: str) -> list[str]:
        return self._axioms.get("disjointness", {}).get(class_uri, [])

    def get_equivalent_axioms(self, class_uri: str) -> list[dict]:
        return self._axioms.get("equivalences", {}).get(class_uri, [])


# --- oxigraph implementation ---


if _HAS_OXIGRAPH:
    # NamedNode constants (module-level for performance)
    _OWL_CLASS = ox.NamedNode("http://www.w3.org/2002/07/owl#Class")
    _RDF_TYPE = ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")
    _RDFS_LABEL = ox.NamedNode("http://www.w3.org/2000/01/rdf-schema#label")
    _RDFS_SUBCLASS_OF = ox.NamedNode("http://www.w3.org/2000/01/rdf-schema#subClassOf")
    _RDFS_COMMENT = ox.NamedNode("http://www.w3.org/2000/01/rdf-schema#comment")
    _RDFS_DOMAIN = ox.NamedNode("http://www.w3.org/2000/01/rdf-schema#domain")
    _RDFS_RANGE = ox.NamedNode("http://www.w3.org/2000/01/rdf-schema#range")
    _SKOS_DEFINITION = ox.NamedNode("http://www.w3.org/2004/02/skos/core#definition")
    _SKOS_PREFLABEL = ox.NamedNode("http://www.w3.org/2004/02/skos/core#prefLabel")
    _IOF_AV_NLDEF = ox.NamedNode(
        "https://spec.industrialontologies.org/ontology/annotation/naturalLanguageDefinition"
    )
    _OBO_IAO_DEF = ox.NamedNode("http://purl.obolibrary.org/obo/IAO_0000115")
    _D3F_DEFINITION = ox.NamedNode("http://d3fend.mitre.org/ontologies/d3fend.owl#definition")

    _OX_FORMAT_MAP = {
        ".ttl": ox.RdfFormat.TURTLE,
        ".rdf": ox.RdfFormat.RDF_XML,
        ".owl": ox.RdfFormat.RDF_XML,
    }

    class OxigraphBackend:
        """Graph backend using pyoxigraph (Rust, RocksDB persistence)."""

        def __init__(self, store: ox.Store, axioms: dict | None = None):
            self._store = store
            self._axioms = axioms or {"restrictions": {}, "disjointness": {}, "equivalences": {}}

        def extract_classes(self, source_file: str = "") -> list[dict]:
            classes = []
            seen: set[str] = set()
            for quad in self._store.quads_for_pattern(None, _RDF_TYPE, _OWL_CLASS, None):
                subj = quad.subject
                if not isinstance(subj, ox.NamedNode):
                    continue
                uri = subj.value
                if uri in seen:
                    continue
                seen.add(uri)
                label = self._get_label_node(subj)
                if label is None:
                    continue
                definition = self._get_definition_node(subj)
                classes.append({
                    "uri": uri,
                    "label": label,
                    "definition": definition,
                    "source_file": source_file,
                })
            return classes

        def get_label(self, uri: str) -> str | None:
            try:
                return self._get_label_node(ox.NamedNode(uri))
            except ValueError:
                return None

        def get_definition(self, uri: str) -> str | None:
            try:
                return self._get_definition_node(ox.NamedNode(uri))
            except ValueError:
                return None

        def get_superclasses(self, class_uri: str) -> list[dict]:
            try:
                node = ox.NamedNode(class_uri)
            except ValueError:
                return []
            results = []
            for quad in self._store.quads_for_pattern(node, _RDFS_SUBCLASS_OF, None, None):
                parent = quad.object
                if not isinstance(parent, ox.NamedNode):
                    continue
                label = self._get_label_node(parent)
                results.append({"uri": parent.value, "label": label})
            return results

        def get_subclasses(self, class_uri: str) -> list[dict]:
            try:
                node = ox.NamedNode(class_uri)
            except ValueError:
                return []
            results = []
            for quad in self._store.quads_for_pattern(None, _RDFS_SUBCLASS_OF, node, None):
                child = quad.subject
                if not isinstance(child, ox.NamedNode):
                    continue
                label = self._get_label_node(child)
                results.append({"uri": child.value, "label": label})
            return results

        def get_subclasses_recursive(self, class_uri: str, depth: int = 1) -> list[dict]:
            results = []
            seen: set[str] = set()
            queue: deque[tuple[ox.NamedNode, int]] = deque()
            try:
                start_node = ox.NamedNode(class_uri)
            except ValueError:
                return []
            queue.append((start_node, 0))
            seen.add(class_uri)

            while queue:
                current, d = queue.popleft()
                if d >= depth:
                    continue
                for quad in self._store.quads_for_pattern(None, _RDFS_SUBCLASS_OF, current, None):
                    child = quad.subject
                    if not isinstance(child, ox.NamedNode):
                        continue
                    child_uri = child.value
                    if child_uri in seen:
                        continue
                    seen.add(child_uri)
                    results.append({
                        "uri": child_uri,
                        "label": self._get_label_node(child),
                        "depth": d + 1,
                    })
                    queue.append((child, d + 1))
            return results

        def get_siblings(self, class_uri: str) -> list[dict]:
            try:
                node = ox.NamedNode(class_uri)
            except ValueError:
                return []
            results = []
            seen: set[str] = set()
            for pq in self._store.quads_for_pattern(node, _RDFS_SUBCLASS_OF, None, None):
                parent = pq.object
                if not isinstance(parent, ox.NamedNode):
                    continue
                parent_label = self._get_label_node(parent)
                for sq in self._store.quads_for_pattern(None, _RDFS_SUBCLASS_OF, parent, None):
                    sibling = sq.subject
                    if not isinstance(sibling, ox.NamedNode):
                        continue
                    if sibling == node:
                        continue
                    sib_uri = sibling.value
                    if sib_uri in seen:
                        continue
                    seen.add(sib_uri)
                    results.append({
                        "uri": sib_uri,
                        "label": self._get_label_node(sibling),
                        "shared_parent": {"uri": parent.value, "label": parent_label},
                    })
            return results

        def get_properties(self, class_uri: str) -> list[dict]:
            try:
                node = ox.NamedNode(class_uri)
            except ValueError:
                return []
            results = []
            # Properties where this class is domain
            for dq in self._store.quads_for_pattern(None, _RDFS_DOMAIN, node, None):
                prop = dq.subject
                if not isinstance(prop, ox.NamedNode):
                    continue
                prop_label = self._get_label_node(prop)
                for rq in self._store.quads_for_pattern(prop, _RDFS_RANGE, None, None):
                    range_cls = rq.object
                    if not isinstance(range_cls, ox.NamedNode):
                        continue
                    results.append({
                        "uri": prop.value,
                        "label": prop_label,
                        "role": "domain",
                        "other_class": {
                            "uri": range_cls.value,
                            "label": self._get_label_node(range_cls),
                        },
                    })
            # Properties where this class is range
            for rq in self._store.quads_for_pattern(None, _RDFS_RANGE, node, None):
                prop = rq.subject
                if not isinstance(prop, ox.NamedNode):
                    continue
                prop_label = self._get_label_node(prop)
                for dq in self._store.quads_for_pattern(prop, _RDFS_DOMAIN, None, None):
                    domain_cls = dq.object
                    if not isinstance(domain_cls, ox.NamedNode):
                        continue
                    results.append({
                        "uri": prop.value,
                        "label": prop_label,
                        "role": "range",
                        "other_class": {
                            "uri": domain_cls.value,
                            "label": self._get_label_node(domain_cls),
                        },
                    })
            return results

        def get_class_definition(self, class_uri: str) -> dict | None:
            try:
                node = ox.NamedNode(class_uri)
            except ValueError:
                return None
            if not self.is_class(class_uri):
                return None
            label = self._get_label_node(node)
            if label is None:
                return None
            definition = self._get_definition_node(node)
            superclasses = self.get_superclasses(class_uri)
            return {
                "uri": class_uri,
                "label": label,
                "definition": definition,
                "superclasses": superclasses,
            }

        def is_class(self, class_uri: str) -> bool:
            try:
                node = ox.NamedNode(class_uri)
            except ValueError:
                return False
            return any(self._store.quads_for_pattern(node, _RDF_TYPE, _OWL_CLASS, None))

        # --- internal helpers ---

        def _get_label_node(self, node: ox.NamedNode) -> str | None:
            for pred in (_RDFS_LABEL, _SKOS_PREFLABEL):
                for quad in self._store.quads_for_pattern(node, pred, None, None):
                    return quad.object.value
            return None

        def _get_definition_node(self, node: ox.NamedNode) -> str | None:
            for pred in (_SKOS_DEFINITION, _IOF_AV_NLDEF, _OBO_IAO_DEF, _D3F_DEFINITION, _RDFS_COMMENT):
                for quad in self._store.quads_for_pattern(node, pred, None, None):
                    return quad.object.value
            return None

        def get_restrictions(self, class_uri: str) -> list[dict]:
            return self._axioms.get("restrictions", {}).get(class_uri, [])

        def get_disjoint_classes(self, class_uri: str) -> list[str]:
            return self._axioms.get("disjointness", {}).get(class_uri, [])

        def get_equivalent_axioms(self, class_uri: str) -> list[dict]:
            return self._axioms.get("equivalences", {}).get(class_uri, [])


# --- Factory functions ---


def _clean_graph_caches(chroma_dir: Path) -> None:
    """Remove stale graph caches before re-indexing."""
    nt_cache = chroma_dir / "graph.nt"
    if nt_cache.exists():
        nt_cache.unlink()
    ox_store = chroma_dir / "oxigraph"
    if ox_store.exists():
        shutil.rmtree(ox_store)


def create_index_backend(files: list[Path], chroma_dir: Path) -> GraphBackend:
    """Parse ontology files into a backend, persisting for later queries.

    With oxigraph: creates a RocksDB persistent store (~5s for 338 files).
    With rdflib: creates an NT cache file (~6 min for 338 files).
    """
    _clean_graph_caches(chroma_dir)

    if _HAS_OXIGRAPH:
        store_path = chroma_dir / "oxigraph"
        store = ox.Store(str(store_path))
        for f in files:
            fmt = _OX_FORMAT_MAP.get(f.suffix)
            if fmt is None:
                continue
            try:
                store.bulk_load(path=str(f), format=fmt)
            except Exception as e:
                print(f"Warning: skipping {f.name}: {e}", file=sys.stderr)
        store.optimize()
        from ontoquery.axioms import extract_axioms, save_axioms
        backend = OxigraphBackend(store)
        axioms = extract_axioms(backend)
        save_axioms(axioms, chroma_dir / "axioms.json")
        backend._axioms = axioms
        return backend
    else:
        g = Graph()
        for f in files:
            fmt = FORMAT_MAP.get(f.suffix)
            if fmt is None:
                continue
            try:
                g.parse(str(f), format=fmt)
            except Exception as e:
                print(f"Warning: skipping {f.name}: {e}", file=sys.stderr)
        # Persist as NT cache for runtime loading
        nt_cache = chroma_dir / "graph.nt"
        g.serialize(str(nt_cache), format="nt")
        from ontoquery.axioms import extract_axioms, save_axioms
        backend = RdflibBackend(g)
        axioms = extract_axioms(backend)
        save_axioms(axioms, chroma_dir / "axioms.json")
        backend._axioms = axioms
        return backend


def load_backend(chroma_dir: Path, source_dirs: list[Path] | None = None) -> GraphBackend:
    """Load a persisted graph backend for runtime queries.

    Tries oxigraph RocksDB first (8ms), falls back to rdflib NT cache (~50s).
    """
    from ontoquery.axioms import load_axioms
    axioms = load_axioms(chroma_dir / "axioms.json")
    if axioms is None:
        _logger.warning("Axiom index not found — run 'ontoquery index' to enable formal reasoning features.")

    # 1. Prefer oxigraph persistent store
    if _HAS_OXIGRAPH:
        ox_path = chroma_dir / "oxigraph"
        if ox_path.exists():
            return OxigraphBackend(ox.Store(str(ox_path)), axioms=axioms)

    # 2. Fallback: rdflib with NT cache
    nt_cache = chroma_dir / "graph.nt"
    if source_dirs:
        g = _rdflib_load_cached(source_dirs, nt_cache)
        return RdflibBackend(g, axioms=axioms)
    if nt_cache.exists():
        g = Graph()
        g.parse(str(nt_cache), format="nt")
        return RdflibBackend(g, axioms=axioms)

    raise RuntimeError(f"No graph store at {chroma_dir}. Run 'ontoquery index' first.")
