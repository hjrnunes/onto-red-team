from collections import defaultdict
from pathlib import Path
from typing import Any

import chromadb

COLLECTION_NAME = "risk_entries"
SCHEMA_VERSION = 2  # bump when document format changes


def build_structural_context(
    risks_by_id: dict[str, Any],
    groups: list,
    actions_by_id: dict[str, Any] | None = None,
    *,
    max_siblings: int = 8,
) -> dict[str, str]:
    """Build structural context strings for risk embeddings.

    Returns {risk_id: context_string} for risks that have structural signals.
    """
    # Build group lookup: group_id -> group_name
    group_names: dict[str, str] = {}
    for g in groups:
        g_type = getattr(g, "type", "")
        if g_type == "RiskGroup" or hasattr(g, "isDefinedByTaxonomy"):
            group_names[g.id] = g.name

    # Build group membership: group_id -> [risk]
    group_members: dict[str, list] = defaultdict(list)
    for risk in risks_by_id.values():
        group_id = getattr(risk, "isPartOf", "")
        if group_id:
            group_members[group_id].append(risk)

    result: dict[str, str] = {}
    for risk_id, risk in risks_by_id.items():
        parts: list[str] = []

        # Group + siblings
        group_id = getattr(risk, "isPartOf", "")
        if group_id and group_id in group_names:
            parts.append(f"PartOf: {group_names[group_id]}")
            siblings = [r.name for r in group_members[group_id] if r.id != risk_id]
            if siblings:
                siblings.sort()
                if len(siblings) <= max_siblings:
                    parts.append(f"Siblings: {', '.join(siblings)}")
                else:
                    shown = siblings[:max_siblings]
                    parts.append(
                        f"Siblings: {', '.join(shown)} (+{len(siblings) - max_siblings} more)"
                    )

        # Cross-mappings
        mapping_attrs = [
            ("exact_mappings", "Exact"),
            ("close_mappings", "Close"),
            ("broad_mappings", "Broad"),
            ("narrow_mappings", "Narrow"),
            ("related_mappings", "Related"),
        ]
        for attr, label in mapping_attrs:
            target_ids = getattr(risk, attr, [])
            if not target_ids:
                continue
            names = []
            for tid in target_ids:
                target = risks_by_id.get(tid)
                if target:
                    names.append(target.name)
            if names:
                parts.append(f"{label}: {', '.join(names)}")

        # Actions
        if actions_by_id:
            action_ids = getattr(risk, "hasRelatedAction", [])
            action_names = []
            for aid in action_ids:
                action = actions_by_id.get(aid)
                if action:
                    action_names.append(action.name)
            if action_names:
                parts.append(f"Actions: {', '.join(action_names)}")

        if parts:
            result[risk_id] = ". ".join(parts)

    return result


class RiskIndex:
    def __init__(self, chroma_dir: Path):
        self._chroma_dir = Path(chroma_dir)
        self._client = chromadb.PersistentClient(path=str(self._chroma_dir))

    def index_risks(self, risks: list, structural_context: dict[str, str] | None = None) -> None:
        """Index risk entries into ChromaDB. Overwrites existing collection."""
        try:
            self._client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass

        collection = self._client.create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine", "schema_version": SCHEMA_VERSION},
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
            if structural_context and risk.id in structural_context:
                doc = f"{doc}. {structural_context[risk.id]}"

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
            collection = self._client.get_collection(name=COLLECTION_NAME)
            if collection.count() != expected_count:
                return True
            version = collection.metadata.get("schema_version", 1)
            return version != SCHEMA_VERSION
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
