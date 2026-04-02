import logging
from refiner.models import (
    PolicyRiskMapping,
    RiskMatch,
    RiskVariationAxes,
    VariationAxis,
    RunReport,
)
from refiner.stages.anchor import anchor, _AnchorResponse, _SlimAxis, derive_roles


def _make_mapping():
    return PolicyRiskMapping(
        policy_concept="Fraud",
        policy_type="A",
        matched_risks=[
            RiskMatch(risk_id="atlas-fraud", risk_name="Fraud", relevance="primary", justification="j"),
        ],
    )


def _make_risk_details():
    return {
        "atlas-fraud": {
            "id": "atlas-fraud",
            "name": "Fraud",
            "description": "Fraudulent activities targeting financial systems",
            "concern": "Financial loss and trust erosion",
        }
    }


def test_anchor_searches_ontology(mock_client, mock_config, mock_onto_handlers):
    mappings = [_make_mapping()]
    risk_details = _make_risk_details()
    mock_onto_handlers["search_classes"].return_value = [
        {"uri": "http://example.org/Person", "label": "Person", "definition": "A human.", "distance": 0.3},
    ]
    mock_onto_handlers["get_class_definition"].return_value = {
        "uri": "http://example.org/Person", "label": "Person", "definition": "A human.",
        "superclasses": [],
    }
    mock_onto_handlers["get_siblings"].return_value = []
    mock_client.chat.completions.create.return_value = _AnchorResponse(
        axes=[
            _SlimAxis(
                cco_class_uri="http://example.org/Person",
                cco_class_label="Person",
                role="agent",
                rationale="Person committing fraud",
            ),
        ],
    )
    result = anchor(mappings, risk_details, mock_client, mock_config, mock_onto_handlers)
    assert len(result) == 1
    assert result[0].axes[0].cco_class_uri == "http://example.org/Person"
    assert result[0].axes[0].roles == ["agent"]  # falls back to LLM role (no BFO ancestor)
    assert result[0].risk_id == "atlas-fraud"
    assert result[0].policy_concept == "Fraud"
    assert mock_onto_handlers["search_classes"].call_count >= 1


def test_anchor_filters_invalid_uris(mock_client, mock_config, mock_onto_handlers):
    mappings = [_make_mapping()]
    risk_details = _make_risk_details()
    mock_onto_handlers["search_classes"].return_value = [
        {"uri": "http://example.org/Person", "label": "Person", "definition": "A human.", "distance": 0.3},
    ]
    mock_onto_handlers["get_class_definition"].side_effect = lambda uri: (
        {"uri": uri, "label": "Person", "definition": "A human.", "superclasses": []}
        if uri == "http://example.org/Person" else None
    )
    mock_onto_handlers["get_siblings"].return_value = []
    # LLM returns a valid and an invalid URI
    mock_client.chat.completions.create.return_value = _AnchorResponse(
        axes=[
            _SlimAxis(cco_class_uri="http://example.org/Person", cco_class_label="Person", role="agent", rationale="r"),
            _SlimAxis(cco_class_uri="http://example.org/Fake", cco_class_label="Fake", role="object", rationale="r"),
        ],
    )
    result = anchor(mappings, risk_details, mock_client, mock_config, mock_onto_handlers)
    assert len(result[0].axes) == 1
    assert result[0].axes[0].cco_class_uri == "http://example.org/Person"


def test_anchor_filters_candidates_by_domain(mock_client, mock_config, mock_onto_handlers):
    """When selected_domains is set, candidates from other domains are excluded."""
    mappings = [_make_mapping()]
    risk_details = _make_risk_details()
    # Search returns candidates from FIBO and OBO
    mock_onto_handlers["search_classes"].return_value = [
        {"uri": "http://purl.obolibrary.org/obo/MAXO_0000943", "label": "deep brain stimulation", "distance": 0.1},
        {"uri": "https://spec.edmcouncil.org/fibo/ontology/FND/Foo/Bar", "label": "Bar", "distance": 0.2},
        {"uri": "http://purl.obolibrary.org/obo/MONDO_123", "label": "some disease", "distance": 0.3},
    ]
    mock_onto_handlers["get_class_definition"].return_value = {
        "uri": "https://spec.edmcouncil.org/fibo/ontology/FND/Foo/Bar",
        "label": "Bar", "definition": "A bar.", "superclasses": [],
    }
    mock_onto_handlers["get_siblings"].return_value = []
    mock_client.chat.completions.create.return_value = _AnchorResponse(
        axes=[
            _SlimAxis(
                cco_class_uri="https://spec.edmcouncil.org/fibo/ontology/FND/Foo/Bar",
                cco_class_label="Bar", role="object", rationale="r",
            ),
        ],
    )
    # Only FIBO and CCO selected — OBO candidates should be filtered out
    result = anchor(mappings, risk_details, mock_client, mock_config, mock_onto_handlers,
                    selected_domains=["CCO", "Commons", "FIBO"])
    assert len(result) == 1
    # The search was called at least once with top_k=10 (extra headroom for filtering)
    assert mock_onto_handlers["search_classes"].call_count >= 1
    call_kwargs = mock_onto_handlers["search_classes"].call_args_list[0]
    assert call_kwargs[1]["top_k"] == 10


def test_anchor_caches_by_risk_id(mock_client, mock_config, mock_onto_handlers):
    """Same risk_id from two policies should only trigger one LLM call."""
    mappings = [
        PolicyRiskMapping(
            policy_concept="Fraud", policy_type="A",
            matched_risks=[RiskMatch(risk_id="atlas-fraud", risk_name="Fraud", relevance="primary", justification="j")],
        ),
        PolicyRiskMapping(
            policy_concept="AML", policy_type="A",
            matched_risks=[RiskMatch(risk_id="atlas-fraud", risk_name="Fraud", relevance="supporting", justification="j")],
        ),
    ]
    risk_details = _make_risk_details()
    mock_onto_handlers["search_classes"].return_value = [
        {"uri": "http://example.org/Person", "label": "Person", "definition": "A human.", "distance": 0.3},
    ]
    mock_onto_handlers["get_class_definition"].return_value = {
        "uri": "http://example.org/Person", "label": "Person", "definition": "A human.", "superclasses": [],
    }
    mock_onto_handlers["get_siblings"].return_value = []
    mock_client.chat.completions.create.return_value = _AnchorResponse(
        axes=[
            _SlimAxis(cco_class_uri="http://example.org/Person", cco_class_label="Person", role="agent", rationale="r"),
        ],
    )
    result = anchor(mappings, risk_details, mock_client, mock_config, mock_onto_handlers)
    assert len(result) == 2
    assert result[0].policy_concept == "Fraud"
    assert result[1].policy_concept == "AML"
    assert result[0].axes == result[1].axes
    # LLM called only once despite two mappings with the same risk
    mock_client.chat.completions.create.assert_called_once()


def test_derive_roles_bfo_process(mock_onto_handlers):
    """Class whose superclass is BFO process should get ['object'] roles."""
    mock_onto_handlers["get_superclasses"].side_effect = lambda uri: (
        [{"uri": "http://purl.obolibrary.org/obo/BFO_0000015", "label": "process"}]
        if uri == "http://example.org/SomeAct" else []
    )
    roles = derive_roles("http://example.org/SomeAct", mock_onto_handlers)
    assert roles == ["object"]


def test_derive_roles_cco_agent(mock_onto_handlers):
    """Class whose superclass chain reaches CCO Agent should get ['agent']."""
    mock_onto_handlers["get_superclasses"].side_effect = lambda uri: {
        "http://example.org/Employee": [{"uri": "https://www.commoncoreontologies.org/ont00001017", "label": "Agent"}],
    }.get(uri, [])
    roles = derive_roles("http://example.org/Employee", mock_onto_handlers)
    assert roles == ["agent"]


def test_derive_roles_no_bfo_ancestor(mock_onto_handlers):
    """Class with no BFO/CCO ancestor should return None (LLM fallback)."""
    mock_onto_handlers["get_superclasses"].return_value = []
    roles = derive_roles("http://example.org/FiboClass", mock_onto_handlers)
    assert roles is None


def test_derive_roles_multi_hop(mock_onto_handlers):
    """Class several hops from BFO category should still find it."""
    mock_onto_handlers["get_superclasses"].side_effect = lambda uri: {
        "http://example.org/DeepClass": [{"uri": "http://example.org/MidClass", "label": "Mid"}],
        "http://example.org/MidClass": [{"uri": "http://purl.obolibrary.org/obo/BFO_0000029", "label": "site"}],
    }.get(uri, [])
    roles = derive_roles("http://example.org/DeepClass", mock_onto_handlers)
    assert roles == ["location"]


def test_anchor_derives_roles_from_bfo(mock_client, mock_config, mock_onto_handlers):
    """When BFO ancestor exists, anchor uses derived roles instead of LLM's."""
    mappings = [_make_mapping()]
    risk_details = _make_risk_details()
    mock_onto_handlers["search_classes"].return_value = [
        {"uri": "http://example.org/Person", "label": "Person", "definition": "A human.", "distance": 0.3},
    ]
    mock_onto_handlers["get_class_definition"].return_value = {
        "uri": "http://example.org/Person", "label": "Person", "definition": "A human.", "superclasses": [],
    }
    mock_onto_handlers["get_siblings"].return_value = []
    # Superclass chain: Person → CCO Agent
    mock_onto_handlers["get_superclasses"].side_effect = lambda uri: (
        [{"uri": "https://www.commoncoreontologies.org/ont00001017", "label": "Agent"}]
        if uri == "http://example.org/Person" else []
    )
    # LLM assigns wrong role "object" — should be overridden by derive_roles
    mock_client.chat.completions.create.return_value = _AnchorResponse(
        axes=[
            _SlimAxis(cco_class_uri="http://example.org/Person", cco_class_label="Person", role="object", rationale="r"),
        ],
    )
    result = anchor(mappings, risk_details, mock_client, mock_config, mock_onto_handlers)
    assert result[0].axes[0].roles == ["agent"]  # derived from CCO Agent, not LLM's "object"


def test_anchor_emits_candidate_expansion_with_domain_filter(mock_client, mock_config, mock_onto_handlers):
    """When selected_domains filters candidates, candidate_expansion shows kept count."""
    mappings = [_make_mapping()]
    risk_details = _make_risk_details()
    # Search returns 3 results: 2 OBO + 1 FIBO
    mock_onto_handlers["search_classes"].return_value = [
        {"uri": "http://purl.obolibrary.org/obo/MAXO_001", "label": "MaxO1", "distance": 0.1},
        {"uri": "http://purl.obolibrary.org/obo/MONDO_001", "label": "Mondo1", "distance": 0.2},
        {"uri": "https://spec.edmcouncil.org/fibo/ontology/FND/Foo/Bar", "label": "Bar", "distance": 0.3},
    ]
    mock_onto_handlers["get_class_definition"].return_value = {
        "uri": "https://spec.edmcouncil.org/fibo/ontology/FND/Foo/Bar",
        "label": "Bar", "definition": "A bar.", "superclasses": [],
    }
    mock_onto_handlers["get_siblings"].return_value = []
    mock_onto_handlers["get_superclasses"].return_value = []
    mock_client.chat.completions.create.return_value = _AnchorResponse(
        axes=[_SlimAxis(
            cco_class_uri="https://spec.edmcouncil.org/fibo/ontology/FND/Foo/Bar",
            cco_class_label="Bar", role="object", rationale="r",
        )],
    )
    report = RunReport(model="m", policy_set="p", timestamp="t")
    result = anchor(mappings, risk_details, mock_client, mock_config, mock_onto_handlers,
                    selected_domains=["CCO", "Commons", "FIBO"], report=report)
    expansion = [e for e in report.events if e["event"] == "candidate_expansion"]
    assert len(expansion) == 1
    assert expansion[0]["kept_after_filter"] == 1  # only FIBO kept after domain filter


def test_anchor_emits_cache_hit(mock_client, mock_config, mock_onto_handlers):
    """Same risk_id from two policies emits cache_hit for second."""
    mappings = [
        PolicyRiskMapping(
            policy_concept="Fraud", policy_type="A",
            matched_risks=[RiskMatch(risk_id="atlas-fraud", risk_name="Fraud", relevance="primary", justification="j")],
        ),
        PolicyRiskMapping(
            policy_concept="AML", policy_type="A",
            matched_risks=[RiskMatch(risk_id="atlas-fraud", risk_name="Fraud", relevance="supporting", justification="j")],
        ),
    ]
    risk_details = _make_risk_details()
    mock_onto_handlers["search_classes"].return_value = [
        {"uri": "http://example.org/Person", "label": "Person", "definition": "A human.", "distance": 0.3},
    ]
    mock_onto_handlers["get_class_definition"].return_value = {
        "uri": "http://example.org/Person", "label": "Person", "definition": "A human.", "superclasses": [],
    }
    mock_onto_handlers["get_siblings"].return_value = []
    mock_onto_handlers["get_superclasses"].return_value = []
    mock_client.chat.completions.create.return_value = _AnchorResponse(
        axes=[_SlimAxis(cco_class_uri="http://example.org/Person", cco_class_label="Person", role="agent", rationale="r")],
    )
    report = RunReport(model="m", policy_set="p", timestamp="t")
    result = anchor(mappings, risk_details, mock_client, mock_config, mock_onto_handlers, report=report)
    hits = [e for e in report.events if e["event"] == "cache_hit"]
    assert len(hits) == 1
    assert hits[0]["risk_id"] == "atlas-fraud"


def test_anchor_emits_empty_axes(mock_client, mock_config, mock_onto_handlers):
    """When no enriched candidates, emit empty_axes."""
    mappings = [_make_mapping()]
    risk_details = _make_risk_details()
    mock_onto_handlers["search_classes"].return_value = [
        {"uri": "http://example.org/Person", "label": "Person", "distance": 0.3},
    ]
    mock_onto_handlers["get_class_definition"].return_value = None  # all fail enrichment
    mock_onto_handlers["get_siblings"].return_value = []
    report = RunReport(model="m", policy_set="p", timestamp="t")
    result = anchor(mappings, risk_details, mock_client, mock_config, mock_onto_handlers, report=report)
    empty = [e for e in report.events if e["event"] == "empty_axes"]
    assert len(empty) == 1
    assert empty[0]["risk_id"] == "atlas-fraud"


def test_anchor_emits_role_derivation(mock_client, mock_config, mock_onto_handlers):
    """For each axis, emit role_derivation with method derived or llm_fallback."""
    mappings = [_make_mapping()]
    risk_details = _make_risk_details()
    mock_onto_handlers["search_classes"].return_value = [
        {"uri": "http://example.org/Person", "label": "Person", "definition": "A human.", "distance": 0.3},
    ]
    mock_onto_handlers["get_class_definition"].return_value = {
        "uri": "http://example.org/Person", "label": "Person", "definition": "A human.", "superclasses": [],
    }
    mock_onto_handlers["get_siblings"].return_value = []
    # Set up superclass chain to hit CCO Agent
    mock_onto_handlers["get_superclasses"].side_effect = lambda uri: (
        [{"uri": "https://www.commoncoreontologies.org/ont00001017", "label": "Agent"}]
        if uri == "http://example.org/Person" else []
    )
    mock_client.chat.completions.create.return_value = _AnchorResponse(
        axes=[_SlimAxis(cco_class_uri="http://example.org/Person", cco_class_label="Person", role="object", rationale="r")],
    )
    report = RunReport(model="m", policy_set="p", timestamp="t")
    result = anchor(mappings, risk_details, mock_client, mock_config, mock_onto_handlers, report=report)
    derivations = [e for e in report.events if e["event"] == "role_derivation"]
    assert len(derivations) == 1
    assert derivations[0]["method"] == "derived"
    assert derivations[0]["uri"] == "http://example.org/Person"


def test_anchor_emits_role_derivation_llm_fallback(mock_client, mock_config, mock_onto_handlers):
    """When derive_roles returns None, method is llm_fallback."""
    mappings = [_make_mapping()]
    risk_details = _make_risk_details()
    mock_onto_handlers["search_classes"].return_value = [
        {"uri": "http://example.org/FiboThing", "label": "FiboThing", "definition": "A thing.", "distance": 0.3},
    ]
    mock_onto_handlers["get_class_definition"].return_value = {
        "uri": "http://example.org/FiboThing", "label": "FiboThing", "definition": "A thing.", "superclasses": [],
    }
    mock_onto_handlers["get_siblings"].return_value = []
    mock_onto_handlers["get_superclasses"].return_value = []  # no BFO ancestor
    mock_client.chat.completions.create.return_value = _AnchorResponse(
        axes=[_SlimAxis(cco_class_uri="http://example.org/FiboThing", cco_class_label="FiboThing", role="object", rationale="r")],
    )
    report = RunReport(model="m", policy_set="p", timestamp="t")
    result = anchor(mappings, risk_details, mock_client, mock_config, mock_onto_handlers, report=report)
    derivations = [e for e in report.events if e["event"] == "role_derivation"]
    assert len(derivations) == 1
    assert derivations[0]["method"] == "llm_fallback"


def test_anchor_no_report_works(mock_client, mock_config, mock_onto_handlers):
    """anchor works without report param (backward compat)."""
    mappings = [_make_mapping()]
    risk_details = _make_risk_details()
    mock_onto_handlers["search_classes"].return_value = [
        {"uri": "http://example.org/Person", "label": "Person", "definition": "A human.", "distance": 0.3},
    ]
    mock_onto_handlers["get_class_definition"].return_value = {
        "uri": "http://example.org/Person", "label": "Person", "definition": "A human.", "superclasses": [],
    }
    mock_onto_handlers["get_siblings"].return_value = []
    mock_onto_handlers["get_superclasses"].return_value = []
    mock_client.chat.completions.create.return_value = _AnchorResponse(
        axes=[_SlimAxis(cco_class_uri="http://example.org/Person", cco_class_label="Person", role="agent", rationale="r")],
    )
    result = anchor(mappings, risk_details, mock_client, mock_config, mock_onto_handlers)
    assert len(result) == 1


def test_anchor_empty_mappings(mock_client, mock_config, mock_onto_handlers):
    result = anchor([], {}, mock_client, mock_config, mock_onto_handlers)
    assert result == []


# expand_candidates() tests


from refiner.stages.anchor import expand_candidates


def test_expand_candidates_single_query(mock_onto_handlers):
    """With only a description, behaves like current single search."""
    mock_onto_handlers["search_classes"].return_value = [
        {"uri": "http://example.org/A", "label": "A", "distance": 0.2},
        {"uri": "http://example.org/B", "label": "B", "distance": 0.4},
    ]
    candidates, stats = expand_candidates(
        description="Fraud risk",
        concern="",
        action_descriptions=[],
        cross_mapped_descriptions=[],
        onto_handlers=mock_onto_handlers,
        selected_domains=None,
    )
    assert len(candidates) == 2
    assert candidates[0]["uri"] == "http://example.org/A"
    assert stats["queries_run"] == 1
    mock_onto_handlers["search_classes"].assert_called_once()


def test_expand_candidates_multi_query_dedup(mock_onto_handlers):
    """Same URI from multiple queries gets hit_count > 1."""
    mock_onto_handlers["search_classes"].side_effect = [
        [{"uri": "http://example.org/A", "label": "A", "distance": 0.3},
         {"uri": "http://example.org/B", "label": "B", "distance": 0.5}],
        [{"uri": "http://example.org/A", "label": "A", "distance": 0.2},
         {"uri": "http://example.org/C", "label": "C", "distance": 0.4}],
    ]
    candidates, stats = expand_candidates(
        description="Fraud risk",
        concern="Loss",
        action_descriptions=[],
        cross_mapped_descriptions=[],
        onto_handlers=mock_onto_handlers,
        selected_domains=None,
    )
    assert stats["queries_run"] == 2
    assert stats["unique_after_dedup"] == 3
    a = next(c for c in candidates if c["uri"] == "http://example.org/A")
    assert a["hit_count"] == 2
    assert a["best_distance"] == 0.2


def test_expand_candidates_with_actions(mock_onto_handlers):
    """Action descriptions generate additional search queries."""
    mock_onto_handlers["search_classes"].side_effect = [
        [{"uri": "http://example.org/A", "label": "A", "distance": 0.3}],
        [{"uri": "http://example.org/B", "label": "B", "distance": 0.4}],
        [{"uri": "http://example.org/C", "label": "C", "distance": 0.5}],
    ]
    candidates, stats = expand_candidates(
        description="Fraud risk",
        concern="",
        action_descriptions=["Monitor transactions", "Verify identity"],
        cross_mapped_descriptions=[],
        onto_handlers=mock_onto_handlers,
        selected_domains=None,
    )
    assert stats["queries_run"] == 3
    assert len(candidates) == 3


def test_expand_candidates_with_cross_mappings(mock_onto_handlers):
    """Cross-mapped descriptions generate additional search queries."""
    mock_onto_handlers["search_classes"].side_effect = [
        [{"uri": "http://example.org/A", "label": "A", "distance": 0.3}],
        [{"uri": "http://example.org/A", "label": "A", "distance": 0.1}],
    ]
    candidates, stats = expand_candidates(
        description="Fraud risk",
        concern="",
        action_descriptions=[],
        cross_mapped_descriptions=["Financial fraud and scams"],
        onto_handlers=mock_onto_handlers,
        selected_domains=None,
    )
    assert stats["queries_run"] == 2
    a = next(c for c in candidates if c["uri"] == "http://example.org/A")
    assert a["hit_count"] == 2
    assert a["best_distance"] == 0.1


def test_expand_candidates_domain_filter(mock_onto_handlers):
    """Domain filtering is applied after merge."""
    mock_onto_handlers["search_classes"].return_value = [
        {"uri": "http://purl.obolibrary.org/obo/MAXO_001", "label": "MaxO1", "distance": 0.1},
        {"uri": "https://spec.edmcouncil.org/fibo/ontology/FND/Foo", "label": "Foo", "distance": 0.2},
    ]
    candidates, stats = expand_candidates(
        description="Fraud risk",
        concern="",
        action_descriptions=[],
        cross_mapped_descriptions=[],
        onto_handlers=mock_onto_handlers,
        selected_domains=["CCO", "Commons", "FIBO", "D3FEND", "CSO"],
    )
    assert all(c["uri"] != "http://purl.obolibrary.org/obo/MAXO_001" for c in candidates)
    assert stats["kept_after_filter"] == 1


def test_expand_candidates_max_candidates(mock_onto_handlers):
    """Results are capped at max_candidates."""
    mock_onto_handlers["search_classes"].return_value = [
        {"uri": f"http://example.org/{i}", "label": f"C{i}", "distance": i * 0.1}
        for i in range(10)
    ]
    candidates, stats = expand_candidates(
        description="Fraud risk",
        concern="",
        action_descriptions=[],
        cross_mapped_descriptions=[],
        onto_handlers=mock_onto_handlers,
        selected_domains=None,
        max_candidates=5,
    )
    assert len(candidates) == 5


def test_expand_candidates_sorts_by_hit_count_then_distance(mock_onto_handlers):
    """Candidates sorted by hit_count desc, then best_distance asc."""
    mock_onto_handlers["search_classes"].side_effect = [
        [{"uri": "http://example.org/A", "label": "A", "distance": 0.5},
         {"uri": "http://example.org/B", "label": "B", "distance": 0.1}],
        [{"uri": "http://example.org/A", "label": "A", "distance": 0.4}],
    ]
    candidates, _ = expand_candidates(
        description="Fraud",
        concern="Loss",
        action_descriptions=[],
        cross_mapped_descriptions=[],
        onto_handlers=mock_onto_handlers,
        selected_domains=None,
    )
    assert candidates[0]["uri"] == "http://example.org/A"
    assert candidates[1]["uri"] == "http://example.org/B"


def test_expand_candidates_skips_empty_queries(mock_onto_handlers):
    """Empty strings are not searched."""
    mock_onto_handlers["search_classes"].return_value = [
        {"uri": "http://example.org/A", "label": "A", "distance": 0.3},
    ]
    candidates, stats = expand_candidates(
        description="Fraud risk",
        concern="",
        action_descriptions=["", "  "],
        cross_mapped_descriptions=[],
        onto_handlers=mock_onto_handlers,
        selected_domains=None,
    )
    assert stats["queries_run"] == 1


def test_expand_candidates_tracks_query_sources(mock_onto_handlers):
    """Each candidate tracks which query sources found it."""
    mock_onto_handlers["search_classes"].side_effect = [
        [{"uri": "http://example.org/A", "label": "A", "distance": 0.3}],
        [{"uri": "http://example.org/A", "label": "A", "distance": 0.2}],
        [{"uri": "http://example.org/A", "label": "A", "distance": 0.4}],
    ]
    candidates, _ = expand_candidates(
        description="Fraud",
        concern="Loss",
        action_descriptions=["Monitor"],
        cross_mapped_descriptions=[],
        onto_handlers=mock_onto_handlers,
        selected_domains=None,
    )
    a = candidates[0]
    assert "description" in a["query_sources"]
    assert "concern" in a["query_sources"]
    assert "action" in a["query_sources"]


# Integration tests: expand_candidates wired into anchor()


def test_anchor_uses_expand_candidates_with_actions(mock_client, mock_config, mock_onto_handlers):
    """When risk_actions are provided, expand_candidates uses them."""
    mappings = [_make_mapping()]
    risk_details = _make_risk_details()
    risk_actions = {"atlas-fraud": ["Monitor financial transactions"]}
    # 3 calls: description, concern (from _make_risk_details), action
    mock_onto_handlers["search_classes"].side_effect = [
        [{"uri": "http://example.org/Person", "label": "Person", "distance": 0.3}],
        [{"uri": "http://example.org/Person", "label": "Person", "distance": 0.4}],
        [{"uri": "http://example.org/Transaction", "label": "Transaction", "distance": 0.2}],
    ]
    mock_onto_handlers["get_class_definition"].side_effect = lambda uri: {
        "uri": uri, "label": uri.split("/")[-1], "definition": "d", "superclasses": [],
    }
    mock_onto_handlers["get_siblings"].return_value = []
    mock_onto_handlers["get_superclasses"].return_value = []
    mock_client.chat.completions.create.return_value = _AnchorResponse(
        axes=[_SlimAxis(
            cco_class_uri="http://example.org/Transaction",
            cco_class_label="Transaction", role="object", rationale="r",
        )],
    )
    result = anchor(mappings, risk_details, mock_client, mock_config, mock_onto_handlers,
                    risk_actions=risk_actions)
    assert result[0].axes[0].cco_class_uri == "http://example.org/Transaction"
    assert mock_onto_handlers["search_classes"].call_count == 3


def test_anchor_uses_cross_mapped_descriptions(mock_client, mock_config, mock_onto_handlers):
    """When related_risks have descriptions, they drive additional searches."""
    mappings = [_make_mapping()]
    risk_details = _make_risk_details()
    related_risks = {
        "atlas-fraud": [
            {"id": "owasp-fraud", "mapping_type": "close", "description": "Social engineering attacks"},
        ],
    }
    mock_onto_handlers["search_classes"].side_effect = [
        [{"uri": "http://example.org/Person", "label": "Person", "distance": 0.3}],
        [{"uri": "http://example.org/Person", "label": "Person", "distance": 0.4}],
        [{"uri": "http://example.org/SocialEngineer", "label": "Social Engineer", "distance": 0.2}],
    ]
    mock_onto_handlers["get_class_definition"].side_effect = lambda uri: {
        "uri": uri, "label": uri.split("/")[-1], "definition": "d", "superclasses": [],
    }
    mock_onto_handlers["get_siblings"].return_value = []
    mock_onto_handlers["get_superclasses"].return_value = []
    mock_client.chat.completions.create.return_value = _AnchorResponse(
        axes=[_SlimAxis(
            cco_class_uri="http://example.org/SocialEngineer",
            cco_class_label="Social Engineer", role="agent", rationale="r",
        )],
    )
    result = anchor(mappings, risk_details, mock_client, mock_config, mock_onto_handlers,
                    related_risks=related_risks)
    assert result[0].axes[0].cco_class_uri == "http://example.org/SocialEngineer"


def test_anchor_emits_candidate_expansion(mock_client, mock_config, mock_onto_handlers):
    """Anchor emits candidate_expansion event with stats."""
    mappings = [_make_mapping()]
    risk_details = _make_risk_details()
    mock_onto_handlers["search_classes"].return_value = [
        {"uri": "http://example.org/A", "label": "A", "distance": 0.3},
    ]
    mock_onto_handlers["get_class_definition"].return_value = {
        "uri": "http://example.org/A", "label": "A", "definition": "d", "superclasses": [],
    }
    mock_onto_handlers["get_siblings"].return_value = []
    mock_onto_handlers["get_superclasses"].return_value = []
    mock_client.chat.completions.create.return_value = _AnchorResponse(
        axes=[_SlimAxis(cco_class_uri="http://example.org/A", cco_class_label="A", role="agent", rationale="r")],
    )
    report = RunReport(model="m", policy_set="p", timestamp="t")
    anchor(mappings, risk_details, mock_client, mock_config, mock_onto_handlers, report=report)
    expansion = [e for e in report.events if e["event"] == "candidate_expansion"]
    assert len(expansion) == 1
    assert expansion[0]["queries_run"] >= 1


def test_anchor_emits_multi_query_hit(mock_client, mock_config, mock_onto_handlers):
    """Anchor emits multi_query_hit per kept candidate."""
    mappings = [_make_mapping()]
    risk_details = _make_risk_details()
    mock_onto_handlers["search_classes"].side_effect = [
        [{"uri": "http://example.org/A", "label": "A", "distance": 0.3}],
        [{"uri": "http://example.org/A", "label": "A", "distance": 0.2}],
    ]
    mock_onto_handlers["get_class_definition"].return_value = {
        "uri": "http://example.org/A", "label": "A", "definition": "d", "superclasses": [],
    }
    mock_onto_handlers["get_siblings"].return_value = []
    mock_onto_handlers["get_superclasses"].return_value = []
    mock_client.chat.completions.create.return_value = _AnchorResponse(
        axes=[_SlimAxis(cco_class_uri="http://example.org/A", cco_class_label="A", role="agent", rationale="r")],
    )
    report = RunReport(model="m", policy_set="p", timestamp="t")
    anchor(mappings, risk_details, mock_client, mock_config, mock_onto_handlers, report=report)
    hits = [e for e in report.events if e["event"] == "multi_query_hit"]
    assert len(hits) >= 1
    assert hits[0]["hit_count"] >= 1
