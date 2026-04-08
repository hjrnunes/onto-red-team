from pathlib import Path

import chromadb

COLLECTION_NAME = "risk_entries"


class RiskIndex:
    def __init__(self, chroma_dir: Path):
        self._chroma_dir = Path(chroma_dir)
        self._client = chromadb.PersistentClient(path=str(self._chroma_dir))

    def index_risks(self, risks: list) -> None:
        """Index risk entries into ChromaDB. Overwrites existing collection."""
        try:
            self._client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass

        collection = self._client.create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

        if not risks:
            return

        ids = []
        documents = []
        metadatas = []
        for risk in risks:
            doc_parts = [f"{risk.name}: {risk.description}"]
            if risk.concern:
                doc_parts.append(f"Concern: {risk.concern}")
            doc = ". ".join(doc_parts)

            ids.append(risk.id)
            documents.append(doc)
            metadatas.append({
                "id": risk.id,
                "name": risk.name,
                "description": risk.description or "",
                "concern": risk.concern or "",
                "taxonomy": risk.isDefinedByTaxonomy or "",
                "risk_type": risk.risk_type or "",
                "group": risk.isPartOf or "",
            })

        batch_size = 5000
        for i in range(0, len(ids), batch_size):
            collection.upsert(
                ids=ids[i:i + batch_size],
                documents=documents[i:i + batch_size],
                metadatas=metadatas[i:i + batch_size],
            )

    def count(self) -> int:
        collection = self._client.get_collection(name=COLLECTION_NAME)
        return collection.count()

    def needs_reindex(self, expected_count: int) -> bool:
        """Check if the index needs rebuilding."""
        try:
            return self.count() != expected_count
        except Exception:
            return True

    def search(self, query: str, top_k: int = 10, taxonomy: str | None = None) -> list[dict]:
        """Semantic search over risk descriptions."""
        try:
            collection = self._client.get_collection(name=COLLECTION_NAME)
        except Exception:
            raise ValueError("No risk index found. Server must index risks on startup.")

        kwargs = {"query_texts": [query], "n_results": top_k}
        if taxonomy:
            kwargs["where"] = {"taxonomy": taxonomy}

        results = collection.query(**kwargs)

        output = []
        for i in range(len(results["ids"][0])):
            meta = results["metadatas"][0][i]
            output.append({
                "id": meta.get("id", results["ids"][0][i]),
                "name": meta.get("name", meta.get("id", "")),
                "description": meta.get("description") or None,
                "concern": meta.get("concern") or None,
                "taxonomy": meta.get("taxonomy", ""),
                "distance": results["distances"][0][i],
            })
        return output
