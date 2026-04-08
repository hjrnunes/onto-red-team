import json
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from nexus_mcp.risk_index import RiskIndex


def create_tool_handlers(
        risk_index: RiskIndex,
        risks_by_id: dict,
        actions_by_id: dict,
        taxonomies: list,
        groups: list,
) -> dict:
    """Create tool handler functions. Returns dict of name -> callable.

    Used by tests to call tool logic directly without MCP transport.
    """

    risks_by_tag = {}
    for risk in risks_by_id.values():
        if hasattr(risk, "tag") and risk.tag:
            risks_by_tag[risk.tag] = risk

    def search_risks(query: str, top_k: int = 10) -> list[dict]:
        return risk_index.search(query, top_k=top_k)

    def get_risk_details(risk_id: str) -> dict | None:
        risk = risks_by_id.get(risk_id) or risks_by_tag.get(risk_id)
        if risk is None:
            return None
        return {
            "id": risk.id,
            "name": risk.name,
            "description": risk.description,
            "concern": risk.concern,
            "risk_type": getattr(risk, "risk_type", None),
            "descriptor": getattr(risk, "descriptor", []),
            "taxonomy": getattr(risk, "isDefinedByTaxonomy", ""),
            "group": getattr(risk, "isPartOf", ""),
        }

    def get_related_risks(risk_id: str) -> list[dict]:
        risk = risks_by_id.get(risk_id) or risks_by_tag.get(risk_id)
        if risk is None:
            return []

        results = []
        mapping_attrs = [
            ("exact_mappings", "exact"),
            ("close_mappings", "close"),
            ("broad_mappings", "broad"),
            ("narrow_mappings", "narrow"),
            ("related_mappings", "related"),
        ]
        for attr, mapping_type in mapping_attrs:
            for ref_id in getattr(risk, attr, []):
                ref_risk = risks_by_id.get(ref_id)
                if ref_risk is None:
                    continue
                results.append({
                    "id": ref_risk.id,
                    "name": ref_risk.name,
                    "description": ref_risk.description,
                    "taxonomy": getattr(ref_risk, "isDefinedByTaxonomy", ""),
                    "mapping_type": mapping_type,
                })
        return results

    def get_related_actions(risk_id: str) -> list[dict]:
        risk = risks_by_id.get(risk_id) or risks_by_tag.get(risk_id)
        if risk is None:
            return []

        results = []
        for action_id in getattr(risk, "hasRelatedAction", []):
            action = actions_by_id.get(action_id)
            if action is None:
                continue
            results.append({
                "id": action.id,
                "name": action.name,
                "description": action.description,
            })
        return results

    def _is_risk_taxonomy(t) -> bool:
        """Check if object is a RiskTaxonomy (works with mocks and real LinkML objects)."""
        # First check type attribute (works for mocks and LinkML)
        if getattr(t, "type", "") == "RiskTaxonomy":
            return True
        # Fallback to isinstance check for LinkML objects without type attribute
        try:
            from ai_atlas_nexus.ai_risk_ontology.datamodel.ai_risk_ontology import RiskTaxonomy
            return isinstance(t, RiskTaxonomy)
        except ImportError:
            return False

    def _is_risk_group(g) -> bool:
        """Check if object is a RiskGroup (works with mocks and real LinkML objects)."""
        # First check type attribute (works for mocks and LinkML)
        if getattr(g, "type", "") == "RiskGroup":
            return True
        # Fallback to isinstance check for LinkML objects without type attribute
        try:
            from ai_atlas_nexus.ai_risk_ontology.datamodel.ai_risk_ontology import RiskGroup
            return isinstance(g, RiskGroup)
        except ImportError:
            return False

    def list_taxonomies() -> list[dict]:
        results = []
        for t in taxonomies:
            if not _is_risk_taxonomy(t):
                continue
            risk_count = sum(
                1 for r in risks_by_id.values()
                if getattr(r, "isDefinedByTaxonomy", "") == t.id
            )
            results.append({
                "id": t.id,
                "name": t.name,
                "description": getattr(t, "description", ""),
                "risk_count": risk_count,
            })
        return results

    def list_risk_groups(taxonomy: str | None = None) -> list[dict]:
        results = []
        for g in groups:
            if not _is_risk_group(g):
                continue
            g_taxonomy = getattr(g, "isDefinedByTaxonomy", "")
            if taxonomy and g_taxonomy != taxonomy:
                continue
            risk_count = sum(
                1 for r in risks_by_id.values()
                if getattr(r, "isPartOf", "") == g.id
            )
            results.append({
                "id": g.id,
                "name": g.name,
                "taxonomy": g_taxonomy,
                "risk_count": risk_count,
            })
        return results

    def get_risk_group(risk_id: str) -> dict | None:
        """Return the RiskGroup containing the given risk."""
        risk = risks_by_id.get(risk_id) or risks_by_tag.get(risk_id)
        if risk is None:
            return None
        group_id = getattr(risk, "isPartOf", "")
        if not group_id:
            return None
        for g in groups:
            if not _is_risk_group(g):
                continue
            if g.id == group_id:
                return {
                    "id": g.id,
                    "name": g.name,
                    "taxonomy": getattr(g, "isDefinedByTaxonomy", ""),
                }
        return None

    def explore_risk(risk_id: str) -> dict | None:
        details = get_risk_details(risk_id)
        if details is None:
            return None
        details["related_risks"] = get_related_risks(risk_id)
        details["related_actions"] = get_related_actions(risk_id)
        return details

    def gap_analysis(
            risk_descriptions: list[str],
            target_taxonomy: str = "ibm-risk-atlas",
            distance_threshold: float = 0.5,
    ) -> dict:
        # Get all risks from target taxonomy
        target_risks = {
            r.id: r for r in risks_by_id.values()
            if getattr(r, "isDefinedByTaxonomy", "") == target_taxonomy
        }

        covered = {}  # target_risk_id -> {target_risk, matched_description, distance}
        for desc in risk_descriptions:
            matches = risk_index.search(desc, top_k=5, taxonomy=target_taxonomy)
            for match in matches:
                if match["distance"] <= distance_threshold:
                    rid = match["id"]
                    if rid not in covered or match["distance"] < covered[rid]["distance"]:
                        covered[rid] = {
                            "target_risk": {"id": rid, "name": match["name"]},
                            "matched_description": desc,
                            "distance": match["distance"],
                        }

        gap_risks = []
        for rid, risk in target_risks.items():
            if rid not in covered:
                gap_risks.append({"id": rid, "name": risk.name})

        total = len(target_risks)
        coverage_pct = (len(covered) / total * 100) if total > 0 else 0.0

        return {
            "covered": list(covered.values()),
            "gaps": gap_risks,
            "coverage_pct": round(coverage_pct, 1),
        }

    return {
        "search_risks": search_risks,
        "get_risk_details": get_risk_details,
        "get_related_risks": get_related_risks,
        "get_related_actions": get_related_actions,
        "list_taxonomies": list_taxonomies,
        "list_risk_groups": list_risk_groups,
        "get_risk_group": get_risk_group,
        "explore_risk": explore_risk,
        "gap_analysis": gap_analysis,
    }


# --- MCP Server ---

mcp = FastMCP("ai-atlas-nexus")

_handlers = None


def _get_handlers():
    global _handlers
    if _handlers is not None:
        return _handlers

    nexus_base_dir = os.environ.get("NEXUS_BASE_DIR")
    if not nexus_base_dir:
        raise RuntimeError("NEXUS_BASE_DIR environment variable must be set")

    from ai_atlas_nexus import AIAtlasNexus

    nexus = AIAtlasNexus(base_dir=nexus_base_dir)

    # Build lookup dicts
    all_risks = nexus.get_all_risks()
    risks_by_id = {r.id: r for r in all_risks}
    all_actions = nexus.get_all_actions()
    actions_by_id = {a.id: a for a in all_actions}
    taxonomies = nexus.get_all_taxonomies()
    groups = nexus.get_all("groups")

    # Build risk index
    chroma_dir = Path(os.environ.get("NEXUS_CHROMA_DIR", ".chroma"))
    chroma_dir.mkdir(parents=True, exist_ok=True)
    idx = RiskIndex(chroma_dir)
    if idx.needs_reindex(len(all_risks)):
        idx.index_risks(all_risks)

    _handlers = create_tool_handlers(
        risk_index=idx,
        risks_by_id=risks_by_id,
        actions_by_id=actions_by_id,
        taxonomies=taxonomies,
        groups=groups,
    )
    return _handlers


@mcp.tool()
def search_risks(query: str, top_k: int = 10) -> str:
    """Semantic search over risk descriptions across all frameworks."""
    return json.dumps(_get_handlers()["search_risks"](query, top_k))


@mcp.tool()
def get_risk_details(risk_id: str) -> str:
    """Get full details for a single risk entry."""
    result = _get_handlers()["get_risk_details"](risk_id)
    if result is None:
        return json.dumps({"error": f"Risk {risk_id} not found"})
    return json.dumps(result)


@mcp.tool()
def get_related_risks(risk_id: str) -> str:
    """Get cross-framework mappings for a risk, with mapping type (exact/close/broad/narrow/related)."""
    return json.dumps(_get_handlers()["get_related_risks"](risk_id))


@mcp.tool()
def get_related_actions(risk_id: str) -> str:
    """Get mitigation actions linked to a risk."""
    return json.dumps(_get_handlers()["get_related_actions"](risk_id))


@mcp.tool()
def list_taxonomies() -> str:
    """List all risk taxonomies in the knowledge graph."""
    return json.dumps(_get_handlers()["list_taxonomies"]())


@mcp.tool()
def list_risk_groups(taxonomy: str = "") -> str:
    """List risk groups, optionally filtered by taxonomy ID."""
    tax = taxonomy if taxonomy else None
    return json.dumps(_get_handlers()["list_risk_groups"](tax))


@mcp.tool()
def explore_risk(risk_id: str) -> str:
    """Get risk details + all cross-mappings + related actions in one call."""
    result = _get_handlers()["explore_risk"](risk_id)
    if result is None:
        return json.dumps({"error": f"Risk {risk_id} not found"})
    return json.dumps(result)


@mcp.tool()
def gap_analysis(risk_descriptions: list[str], target_taxonomy: str = "ibm-risk-atlas", distance_threshold: float = 0.5) -> str:
    """Compare client risk descriptions against a target taxonomy to find coverage gaps."""
    return json.dumps(_get_handlers()["gap_analysis"](risk_descriptions, target_taxonomy, distance_threshold))


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
