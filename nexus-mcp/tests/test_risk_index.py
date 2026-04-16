from nexus_mcp.risk_index import RiskIndex, build_structural_context


def test_structural_context_group_and_siblings(mock_risks, mock_groups, mock_actions):
    risks_by_id = {r.id: r for r in mock_risks}
    actions_by_id = {a.id: a for a in mock_actions}
    ctx = build_structural_context(risks_by_id, mock_groups, actions_by_id)

    # atlas-prompt-injection is in Robustness group (only member in that group)
    assert "atlas-prompt-injection" in ctx
    assert "PartOf: Robustness" in ctx["atlas-prompt-injection"]

    # llm01-prompt-injection shares owasp-llm-top-10-group with llm02
    owasp_ctx = ctx["llm01-prompt-injection"]
    assert "PartOf: OWASP LLM Top 10" in owasp_ctx
    assert "Siblings:" in owasp_ctx
    assert "LLM02: Sensitive Information Disclosure" in owasp_ctx


def test_index_risks(chroma_dir, mock_risks):
    idx = RiskIndex(chroma_dir)
    idx.index_risks(mock_risks)
    assert idx.count() == len(mock_risks)


def test_search(chroma_dir, mock_risks):
    idx = RiskIndex(chroma_dir)
    idx.index_risks(mock_risks)

    results = idx.search("prompt injection attack", top_k=3)
    assert len(results) <= 3
    assert results[0]["name"] == "Prompt injection" or results[0]["name"] == "LLM01: Prompt Injection"
    for r in results:
        assert "id" in r
        assert "name" in r
        assert "description" in r
        assert "taxonomy" in r
        assert "distance" in r


def test_search_filtered_by_taxonomy(chroma_dir, mock_risks):
    idx = RiskIndex(chroma_dir)
    idx.index_risks(mock_risks)

    results = idx.search("injection", top_k=10, taxonomy="ibm-risk-atlas")
    for r in results:
        assert r["taxonomy"] == "ibm-risk-atlas"


def test_search_no_index(chroma_dir):
    idx = RiskIndex(chroma_dir)
    try:
        idx.search("test")
        assert False, "Should have raised"
    except ValueError:
        pass


def test_needs_reindex_empty(chroma_dir, mock_risks):
    idx = RiskIndex(chroma_dir)
    assert idx.needs_reindex(len(mock_risks)) is True


def test_needs_reindex_current(chroma_dir, mock_risks):
    idx = RiskIndex(chroma_dir)
    idx.index_risks(mock_risks)
    assert idx.needs_reindex(len(mock_risks)) is False


def test_needs_reindex_stale(chroma_dir, mock_risks):
    idx = RiskIndex(chroma_dir)
    idx.index_risks(mock_risks)
    # Simulate adding a new risk
    assert idx.needs_reindex(len(mock_risks) + 1) is True
