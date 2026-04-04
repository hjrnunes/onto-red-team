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

    def index_classes(self, classes: list[dict], source_dir: str) -> None:
        """Index extracted classes into unified ChromaDB collection. Overwrites existing."""

        collection = self._get_or_create_collection(
            metadata={"source_dir": source_dir, "hnsw:space": "cosine"}
        )
        if not classes:
            return

        self._upsert_batch(collection, classes)

    def index_domain_classes(self, classes: list[dict], source_dir: str) -> dict[str, int]:
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
            self._upsert_batch(collection, domain_classes)
            counts[domain] = len(domain_classes)

        return counts

    def _upsert_batch(self, collection: chromadb.Collection, classes: list[dict]) -> None:
        ids = []
        documents = []
        metadatas = []
        for cls in classes:
            uri = cls["uri"]
            label = cls["label"]
            definition = cls.get("definition")
            source_file = cls.get("source_file", "")

            doc = f"{label}: {definition}" if definition else label
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
