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


def test_structural_context_cross_mappings(mock_risks, mock_groups, mock_actions):
    risks_by_id = {r.id: r for r in mock_risks}
    actions_by_id = {a.id: a for a in mock_actions}
    ctx = build_structural_context(risks_by_id, mock_groups, actions_by_id)

    # atlas-prompt-injection has exact_mappings=["llm01-prompt-injection"]
    # and related_mappings=["atlas-jailbreaking"] (not in mock_risks, so skipped)
    pi_ctx = ctx["atlas-prompt-injection"]
    assert "Exact: LLM01: Prompt Injection" in pi_ctx

    # atlas-confidential-data-in-prompt has close_mappings=["llm022025-..."]
    cd_ctx = ctx["atlas-confidential-data-in-prompt"]
    assert "Close: LLM02: Sensitive Information Disclosure" in cd_ctx


def test_structural_context_actions(mock_risks, mock_groups, mock_actions):
    risks_by_id = {r.id: r for r in mock_risks}
    actions_by_id = {a.id: a for a in mock_actions}
    ctx = build_structural_context(risks_by_id, mock_groups, actions_by_id)

    # atlas-prompt-injection has hasRelatedAction=["action-input-validation"]
    assert "Actions: Input validation" in ctx["atlas-prompt-injection"]

    # atlas-confidential-data-in-prompt has hasRelatedAction=["action-output-filtering"]
    assert "Actions: Output filtering" in ctx["atlas-confidential-data-in-prompt"]


def test_structural_context_empty_risk_omitted():
    """A risk with no group, no mappings, no actions is omitted."""
    from tests.conftest import MockRisk
    bare_risk = MockRisk(id="bare", name="Bare Risk")
    ctx = build_structural_context({"bare": bare_risk}, [], None)
    assert "bare" not in ctx


def test_structural_context_full_string(mock_risks, mock_groups, mock_actions):
    risks_by_id = {r.id: r for r in mock_risks}
    actions_by_id = {a.id: a for a in mock_actions}
    ctx = build_structural_context(risks_by_id, mock_groups, actions_by_id)

    # atlas-prompt-injection has group, exact mapping, related mapping (unresolved), and action
    pi_ctx = ctx["atlas-prompt-injection"]
    assert "PartOf: Robustness" in pi_ctx
    assert "Exact: LLM01: Prompt Injection" in pi_ctx
    assert "Actions: Input validation" in pi_ctx
    # atlas-jailbreaking not in risks_by_id, so Related section should not appear
    assert "Related:" not in pi_ctx


def test_structural_context_sibling_cap():
    from tests.conftest import MockRisk, MockGroup

    group = MockGroup(id="big-group", name="Big Group")
    risks = [
        MockRisk(id=f"r-{i}", name=f"Risk {i:02d}", isPartOf="big-group")
        for i in range(12)
    ]
    risks_by_id = {r.id: r for r in risks}

    ctx = build_structural_context(risks_by_id, [group], None, max_siblings=8)

    # r-0 has 11 siblings, cap at 8 with overflow
    r0_ctx = ctx["r-0"]
    assert "PartOf: Big Group" in r0_ctx
    assert "(+3 more)" in r0_ctx
    # Should show exactly 8 sibling names
    siblings_part = r0_ctx.split("Siblings: ")[1]
    names_str = siblings_part.split(" (+")[0]
    assert len(names_str.split(", ")) == 8


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
