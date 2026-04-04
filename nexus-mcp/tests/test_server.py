import pytest
from nexus_mcp.risk_index import RiskIndex
from nexus_mcp.server import create_tool_handlers


@pytest.fixture
def tools(chroma_dir, mock_risks, mock_actions, mock_taxonomies, mock_groups):
    """Build risk index and return tool handlers."""
    idx = RiskIndex(chroma_dir)
    idx.index_risks(mock_risks)

    # Build lookup dicts simulating what the server does with AIAtlasNexus data
    risks_by_id = {r.id: r for r in mock_risks}
    actions_by_id = {a.id: a for a in mock_actions}
    taxonomies = mock_taxonomies
    groups = mock_groups

    return create_tool_handlers(
        risk_index=idx,
        risks_by_id=risks_by_id,
        actions_by_id=actions_by_id,
        taxonomies=taxonomies,
        groups=groups,
    )


def test_search_risks(tools):
    result = tools["search_risks"](query="prompt injection", top_k=3)
    assert len(result) <= 3
    assert any(r["name"] == "Prompt injection" for r in result)


def test_get_risk_details(tools):
    result = tools["get_risk_details"](risk_id="atlas-prompt-injection")
    assert result["name"] == "Prompt injection"
    assert result["risk_type"] == "output"
    assert result["taxonomy"] == "ibm-risk-atlas"


def test_get_risk_details_by_tag(tools):
    result = tools["get_risk_details"](risk_id="prompt-injection")
    assert result["name"] == "Prompt injection"


def test_get_risk_details_not_found(tools):
    result = tools["get_risk_details"](risk_id="nonexistent")
    assert result is None


def test_get_related_risks(tools):
    result = tools["get_related_risks"](risk_id="atlas-prompt-injection")
    assert len(result) >= 1
    # Should find llm01-prompt-injection as exact mapping
    exact = [r for r in result if r["mapping_type"] == "exact"]
    assert any(r["id"] == "llm01-prompt-injection" for r in exact)


def test_get_related_risks_includes_mapping_type(tools):
    result = tools["get_related_risks"](risk_id="atlas-prompt-injection")
    for r in result:
        assert r["mapping_type"] in ("exact", "close", "broad", "narrow", "related")


def test_get_related_actions(tools):
    result = tools["get_related_actions"](risk_id="atlas-prompt-injection")
    assert len(result) >= 1
    assert any(a["name"] == "Input validation" for a in result)


def test_list_taxonomies(tools):
    result = tools["list_taxonomies"]()
    assert len(result) == 2
    ibm = next(t for t in result if t["id"] == "ibm-risk-atlas")
    assert ibm["name"] == "IBM AI Risk Atlas"
    assert "risk_count" in ibm


def test_list_risk_groups(tools):
    result = tools["list_risk_groups"]()
    assert len(result) == 4


def test_list_risk_groups_filtered(tools):
    result = tools["list_risk_groups"](taxonomy="ibm-risk-atlas")
    assert all(g["taxonomy"] == "ibm-risk-atlas" for g in result)
    assert len(result) == 3


def test_explore_risk(tools):
    result = tools["explore_risk"](risk_id="atlas-prompt-injection")
    assert result["name"] == "Prompt injection"
    assert "related_risks" in result
    assert "related_actions" in result
    assert any(r["id"] == "llm01-prompt-injection" for r in result["related_risks"])


def test_gap_analysis(tools):
    descriptions = [
        "Prompts that seek to gain advice and strategies to commit fraud",
        "Prompts that attempt to inject malicious instructions into the model",
    ]
    result = tools["gap_analysis"](
        risk_descriptions=descriptions,
        target_taxonomy="ibm-risk-atlas",
        distance_threshold=1.5,  # generous threshold for mock data
    )
    assert "covered" in result
    assert "gaps" in result
    assert "coverage_pct" in result
    assert isinstance(result["coverage_pct"], float)


def test_get_risk_group_returns_group_for_risk(tools):
    result = tools["get_risk_group"]("atlas-prompt-injection")
    assert result is not None
    assert result["id"] == "ibm-risk-atlas-robustness"
    assert result["name"] == "Robustness"


def test_get_risk_group_returns_none_for_unknown(tools):
    result = tools["get_risk_group"]("nonexistent-risk")
    assert result is None


def test_get_risk_group_works_with_tag(tools):
    result = tools["get_risk_group"]("prompt-injection")
    assert result is not None
    assert result["id"] == "ibm-risk-atlas-robustness"
