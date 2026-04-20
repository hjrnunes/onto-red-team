from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import chromadb

COLLECTION_NAME = "ontology_classes"

# Canonical URI namespace → domain key mapping.
# Used by indexing (per-domain collections) and querying (domain routing).
DOMAIN_PATTERNS: dict[str, str] = {
    "CCO": "commoncoreontologies.org",
    "FIBO": "spec.edmcouncil.org/fibo",
    "Commons": "omg.org/spec/Commons",
    "OBO": "purl.obolibrary.org/obo",
    "IOF": "industrialontologies.org",
    "D3FEND": "d3fend.mitre.org",
    "CSO": "taxonomy-refiner.io/ontologies/cso",
    "LKIF": "estrellaproject.org/lkif-core",
}


def derive_domain(uri: str) -> str:
    """Map a class URI to its domain key by namespace pattern."""
    for domain, pattern in DOMAIN_PATTERNS.items():
        if pattern in uri:
            return domain
    return "unknown"


def _domain_collection_name(domain: str) -> str:
    return f"ontology_{domain}"


def _parse_results(results: dict, domain: str | None = None) -> list[dict]:
    """Extract structured result dicts from a ChromaDB query response."""
    output = []
    for i in range(len(results["ids"][0])):
        meta = results["metadatas"][0][i]
        entry = {
            "uri": meta["uri"],
            "label": meta["label"],
            "definition": meta["definition"] or None,
            "distance": results["distances"][0][i],
            "source_file": meta.get("source_file", ""),
        }
        if domain is not None:
            entry["domain"] = domain
        output.append(entry)
    return output


def build_structural_context(
    projected_graph, *, bfo_categories: dict[str, str] | None = None,
    max_children: int = 8, max_properties: int = 6,
) -> dict[str, str]:
    """Build a structural context string for each class from projected edges.

    Returns {uri: context_string} where context_string summarizes the class's
    structural neighborhood (parents, children, properties, equivalences).

    Caps children and property targets to avoid blowing up document length for
    broad parent classes (e.g. OBO disease hierarchies with 2000+ subclasses).
    """
    from ontoquery.owl2vec import SUBCLASS_OF, SUPERCLASS_OF

    # Collect edges by subject
    parents: dict[str, list[str]] = defaultdict(list)
    children: dict[str, list[str]] = defaultdict(list)
    properties: dict[str, list[tuple[str, str]]] = defaultdict(list)

    for s, p, o in projected_graph.edges:
        if p == SUBCLASS_OF:
            parents[s].append(o)
        elif p == SUPERCLASS_OF:
            children[s].append(o)
        else:
            properties[s].append((p, o))

    # Build label lookup from literal edges
    labels: dict[str, str] = {}
    label_pred = "http://www.w3.org/2000/01/rdf-schema#label"
    for s, p, o in projected_graph.literal_edges:
        if p == label_pred and s not in labels:
            labels[s] = o

    def _label(uri: str) -> str:
        return labels.get(uri, uri.rsplit("#", 1)[-1].rsplit("/", 1)[-1])

    def _prop_label(uri: str) -> str:
        return uri.rsplit("#", 1)[-1].rsplit("/", 1)[-1]

    def _cap(items: list[str], limit: int) -> str:
        if len(items) <= limit:
            return ", ".join(items)
        return ", ".join(items[:limit]) + f" (+{len(items) - limit} more)"

    if bfo_categories:
        from ontoquery.bfo import CATEGORY_PATTERNS, match_property

    result: dict[str, str] = {}
    for uri in projected_graph.classes:
        # Build taxonomy parts (always present)
        taxonomy_parts: list[str] = []
        if uri in parents:
            parent_labels = sorted(set(_label(p) for p in parents[uri]))
            taxonomy_parts.append(f"SubClassOf: {_cap(parent_labels, max_children)}")
        if uri in children:
            child_labels = sorted(set(_label(c) for c in children[uri]))
            taxonomy_parts.append(f"HasSubClass: {_cap(child_labels, max_children)}")

        # Build property groups
        prop_groups: dict[str, list[str]] = defaultdict(list)
        prop_uris_by_name: dict[str, str] = {}
        if uri in properties:
            for prop_uri, target_uri in properties[uri]:
                pname = _prop_label(prop_uri)
                target_label = _label(target_uri)
                if target_label not in prop_groups[pname]:
                    prop_groups[pname].append(target_label)
                if pname not in prop_uris_by_name:
                    prop_uris_by_name[pname] = prop_uri

        category = bfo_categories.get(uri, "") if bfo_categories else ""
        cat_patterns = CATEGORY_PATTERNS.get(category, []) if bfo_categories and category else []

        if cat_patterns:
            constitutive_parts: list[str] = []
            matched_prop_names: set[str] = set()

            for cp in cat_patterns:
                matched_targets: list[str] = []
                for pname, targets in prop_groups.items():
                    full_uri = prop_uris_by_name.get(pname, pname)
                    if match_property(full_uri, cp.property_patterns):
                        matched_targets.extend(targets)
                        matched_prop_names.add(pname)
                if matched_targets:
                    unique = sorted(set(matched_targets))
                    constitutive_parts.append(
                        f"{cp.role_prefix}: {_cap(unique, max_children)}")

            contextual_parts: list[str] = []
            for pname, targets in sorted(prop_groups.items())[:max_properties]:
                if pname not in matched_prop_names:
                    contextual_parts.append(f"{pname}: {_cap(targets, max_children)}")

            all_parts = constitutive_parts + taxonomy_parts + contextual_parts
            if all_parts:
                result[uri] = f"[{category}] " + ". ".join(all_parts)
        else:
            parts = taxonomy_parts[:]
            for pname, targets in sorted(prop_groups.items())[:max_properties]:
                parts.append(f"{pname}: {_cap(targets, max_children)}")
            if parts:
                result[uri] = ". ".join(parts)

    return result


class OntologyIndex:
    def __init__(self, chroma_dir: Path):
        self._chroma_dir = Path(chroma_dir)
        self._client = chromadb.PersistentClient(path=str(self._chroma_dir))
        self._collection = None

    def _get_or_create_collection(self, metadata: dict | None = None) -> chromadb.Collection:
        if metadata is not None:
            # Delete existing to do a clean re-index
            try:
                self._client.delete_collection(COLLECTION_NAME)
            except Exception:
                pass  # Collection may not exist yet
            self._collection = self._client.create_collection(
                name=COLLECTION_NAME,
                metadata=metadata,
            )
        else:
            self._collection = self._client.get_collection(name=COLLECTION_NAME)
        return self._collection

    def index_classes(
        self,
        classes: list[dict],
        source_dir: str,
        structural_context: dict[str, str] | None = None,
    ) -> None:
        """Index extracted classes into unified ChromaDB collection. Overwrites existing."""

        collection = self._get_or_create_collection(
            metadata={"source_dir": source_dir, "hnsw:space": "cosine"}
        )
        if not classes:
            return

        self._upsert_batch(collection, classes, structural_context)

    def index_domain_classes(
        self,
        classes: list[dict],
        source_dir: str,
        structural_context: dict[str, str] | None = None,
    ) -> dict[str, int]:
        """Index classes into per-domain ChromaDB collections. Returns domain -> count."""
        by_domain: dict[str, list[dict]] = {}
        for cls in classes:
            domain = derive_domain(cls["uri"])
            by_domain.setdefault(domain, []).append(cls)

        counts = {}
        for domain, domain_classes in by_domain.items():
            col_name = _domain_collection_name(domain)
            try:
                self._client.delete_collection(col_name)
            except Exception:
                pass
            collection = self._client.create_collection(
                name=col_name,
                metadata={"source_dir": source_dir, "hnsw:space": "cosine", "domain": domain},
            )
            self._upsert_batch(collection, domain_classes, structural_context)
            counts[domain] = len(domain_classes)

        return counts

    def _upsert_batch(
        self,
        collection: chromadb.Collection,
        classes: list[dict],
        structural_context: dict[str, str] | None = None,
    ) -> None:
        ids = []
        documents = []
        metadatas = []
        for cls in classes:
            uri = cls["uri"]
            label = cls["label"]
            definition = cls.get("definition")
            source_file = cls.get("source_file", "")

            doc = f"{label}: {definition}" if definition else label
            if structural_context and uri in structural_context:
                doc = f"{doc}. {structural_context[uri]}"
            ids.append(uri)
            documents.append(doc)
            metadatas.append({
                "uri": uri,
                "label": label,
                "definition": definition or "",
                "source_file": source_file,
            })

        batch_size = 5000
        for i in range(0, len(ids), batch_size):
            collection.upsert(
                ids=ids[i:i + batch_size],
                documents=documents[i:i + batch_size],
                metadatas=metadatas[i:i + batch_size],
            )

    def count(self) -> int:
        collection = self._get_or_create_collection()
        return collection.count()

    def get_source_dir(self) -> str:
        collection = self._get_or_create_collection()
        return collection.metadata["source_dir"]

    def search(self, concept: str, description: str, top_k: int = 10) -> list[dict]:
        """Semantic search for ontology classes matching a policy concept."""
        try:
            collection = self._get_or_create_collection()
        except Exception:
            raise ValueError("No index found. Run 'ontoquery index' first.")

        query = f"{concept}: {description}"
        results = collection.query(query_texts=[query], n_results=top_k)
        return _parse_results(results)

    def search_raw(self, query: str, top_k: int = 10) -> list[dict]:
        """Semantic search with a single query string (for MCP tool use)."""
        try:
            collection = self._get_or_create_collection()
        except Exception:
            raise ValueError("No index found. Run 'ontoquery index' first.")

        results = collection.query(query_texts=[query], n_results=top_k)
        return _parse_results(results)

    def search_domains(
        self, query: str, domains: list[str], top_k_per_domain: int = 10,
    ) -> dict[str, list[dict]]:
        """Search per-domain collections independently. Returns domain -> results."""
        output: dict[str, list[dict]] = {}
        for domain in domains:
            col_name = _domain_collection_name(domain)
            try:
                collection = self._client.get_collection(name=col_name)
            except Exception:
                continue
            n = min(top_k_per_domain, collection.count())
            if n == 0:
                continue
            results = collection.query(query_texts=[query], n_results=n)
            output[domain] = _parse_results(results, domain=domain)
        return output

    def list_domains(self) -> list[str]:
        """List available domain collections."""
        prefix = "ontology_"
        domains = []
        for c in self._client.list_collections():
            name = c if isinstance(c, str) else c.name
            if name.startswith(prefix) and name != COLLECTION_NAME:
                domains.append(name[len(prefix):])
        return sorted(domains)
