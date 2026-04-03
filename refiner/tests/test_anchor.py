import logging
from unittest.mock import MagicMock
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
                class_id="C1",
                class_label="Person",
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
            _SlimAxis(class_id="C1", class_label="Person", role="agent", rationale="r"),
            _SlimAxis(class_id="C99", class_label="Fake", role="object", rationale="r"),
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
                class_id="C1",
                class_label="Bar", role="object", rationale="r",
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
            _SlimAxis(class_id="C1", class_label="Person", role="agent", rationale="r"),
        ],
    )
    result = anchor(mappings, risk_details, mock_client, mock_config, mock_onto_handlers)
    assert len(result) == 2
    assert result[0].policy_concept == "Fraud"
    assert result[1].policy_concept == "AML"
    assert result[0].axes == result[1].axes


def test_strategy_protocol_new_signature():
    """Protocol accepts risk_context and generic_safety_uris parameters."""
    from refiner.stages.anchor import SearchMergeStrategy, WeightedMergeStrategy

    strategy = WeightedMergeStrategy()
    per_domain = {
        "CSO": [
            {"uri": "http://cso/X", "label": "X", "hit_count": 1, "best_distance": 0.1,
             "domain": "CSO", "query_sources": []},
        ],
    }
    risk_context = {"description": "fraud", "concern": "loss", "policy_concept": "Fraud"}
    result = strategy.merge(
        per_domain, ["CSO"], max_candidates=5,
        risk_context=risk_context, generic_safety_uris=set(),
    )
    assert isinstance(result, list)
    assert isinstance(strategy, SearchMergeStrategy)


def test_grouped_merge_new_signature():
    """GroupedMergeStrategy accepts new protocol parameters."""
    from refiner.stages.anchor import GroupedMergeStrategy, SearchMergeStrategy

    strategy = GroupedMergeStrategy()
    per_domain = {
        "CSO": [
            {"uri": "http://cso/X", "label": "X", "hit_count": 1, "best_distance": 0.1,
             "domain": "CSO", "query_sources": []},
        ],
    }
    risk_context = {"description": "fraud", "concern": "loss", "policy_concept": "Fraud"}
    result = strategy.merge(
        per_domain, ["CSO"], max_candidates=5,
        risk_context=risk_context, generic_safety_uris=set(),
    )
    assert isinstance(result, list)
    assert isinstance(strategy, SearchMergeStrategy)


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


def test_derive_roles_commons_agent(mock_onto_handlers):
    """FIBO class walking to Commons Agent should get ['agent'] roles."""
    mock_onto_handlers["get_superclasses"].side_effect = lambda uri: {
        "http://example.org/FiboBank": [{"uri": "https://www.omg.org/spec/Commons/Organizations/FormalOrganization", "label": "FormalOrganization"}],
    }.get(uri, [])
    roles = derive_roles("http://example.org/FiboBank", mock_onto_handlers)
    assert roles == ["agent"]


def test_derive_roles_commons_document(mock_onto_handlers):
    """FIBO class walking to Commons Document should get ['object'] roles."""
    mock_onto_handlers["get_superclasses"].side_effect = lambda uri: {
        "http://example.org/FiboContract": [{"uri": "https://www.omg.org/spec/Commons/Documents/LegalDocument", "label": "LegalDocument"}],
    }.get(uri, [])
    roles = derive_roles("http://example.org/FiboContract", mock_onto_handlers)
    assert roles == ["object"]


def test_derive_roles_commons_location(mock_onto_handlers):
    """FIBO class walking to Commons Location should get ['location'] roles."""
    mock_onto_handlers["get_superclasses"].side_effect = lambda uri: {
        "http://example.org/FiboCountry": [{"uri": "https://www.omg.org/spec/Commons/Locations/Location", "label": "Location"}],
    }.get(uri, [])
    roles = derive_roles("http://example.org/FiboCountry", mock_onto_handlers)
    assert roles == ["location"]


def test_derive_roles_commons_functional_role(mock_onto_handlers):
    """FIBO class walking to Commons FunctionalRole should get ['agent', 'instrument']."""
    mock_onto_handlers["get_superclasses"].side_effect = lambda uri: {
        "http://example.org/FiboLendingOfficer": [{"uri": "https://www.omg.org/spec/Commons/RolesAndCompositions/FunctionalRole", "label": "FunctionalRole"}],
    }.get(uri, [])
    roles = derive_roles("http://example.org/FiboLendingOfficer", mock_onto_handlers)
    assert roles == ["agent", "instrument"]


def test_derive_roles_commons_identifier(mock_onto_handlers):
    """FIBO class walking to Commons Identifier should get ['object', 'instrument']."""
    mock_onto_handlers["get_superclasses"].side_effect = lambda uri: {
        "http://example.org/FiboLEI": [{"uri": "https://www.omg.org/spec/Commons/Identifiers/Identifier", "label": "Identifier"}],
    }.get(uri, [])
    roles = derive_roles("http://example.org/FiboLEI", mock_onto_handlers)
    assert roles == ["object", "instrument"]


def test_derive_roles_facility_direct(mock_onto_handlers):
    """CCO Facility should get ['location'] via direct _CATEGORY_ROLES entry (no bridge axiom)."""
    roles = derive_roles("https://www.commoncoreontologies.org/ont00000192", mock_onto_handlers)
    assert roles == ["location"]


def test_derive_roles_commons_multi_hop(mock_onto_handlers):
    """FIBO class 2 hops from Commons should still resolve roles."""
    mock_onto_handlers["get_superclasses"].side_effect = lambda uri: {
        "http://example.org/FiboCorp": [{"uri": "http://example.org/FiboLegalEntity", "label": "LegalEntity"}],
        "http://example.org/FiboLegalEntity": [{"uri": "https://www.omg.org/spec/Commons/Organizations/LegalEntity", "label": "LegalEntity"}],
    }.get(uri, [])
    roles = derive_roles("http://example.org/FiboCorp", mock_onto_handlers)
    assert roles == ["agent"]


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
            _SlimAxis(class_id="C1", class_label="Person", role="object", rationale="r"),
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
            class_id="C1",
            class_label="Bar", role="object", rationale="r",
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
        axes=[_SlimAxis(class_id="C1", class_label="Person", role="agent", rationale="r")],
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
        axes=[_SlimAxis(class_id="C1", class_label="Person", role="object", rationale="r")],
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
        axes=[_SlimAxis(class_id="C1", class_label="FiboThing", role="object", rationale="r")],
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
        axes=[_SlimAxis(class_id="C1", class_label="Person", role="agent", rationale="r")],
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
            class_id="C2",
            class_label="Transaction", role="object", rationale="r",
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
            class_id="C2",
            class_label="Social Engineer", role="agent", rationale="r",
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
        axes=[_SlimAxis(class_id="C1", class_label="A", role="agent", rationale="r")],
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
        axes=[_SlimAxis(class_id="C1", class_label="A", role="agent", rationale="r")],
    )
    report = RunReport(model="m", policy_set="p", timestamp="t")
    anchor(mappings, risk_details, mock_client, mock_config, mock_onto_handlers, report=report)
    hits = [e for e in report.events if e["event"] == "multi_query_hit"]
    assert len(hits) >= 1
    assert hits[0]["hit_count"] >= 1


# Restriction/equivalence expansion tests


def test_expand_candidates_with_restriction_expansion(mock_onto_handlers):
    """Restriction fillers are added as candidates when get_restrictions is available."""
    # Set up search to return one candidate
    mock_onto_handlers["search_classes"].return_value = [
        {"uri": "http://example.org/Artifact", "label": "Artifact", "distance": 0.1},
    ]
    # Artifact has a restriction: someValuesFrom -> ContentEntity
    mock_onto_handlers["get_restrictions"].return_value = [
        {"type": "someValuesFrom", "property": "http://example.org/is_about", "filler": "http://example.org/ContentEntity"},
    ]
    mock_onto_handlers["get_class_definition"].side_effect = lambda uri: (
        {"uri": uri, "label": "Content Entity", "definition": "d", "superclasses": []}
        if uri == "http://example.org/ContentEntity"
        else None
    )

    candidates, stats = expand_candidates(
        description="Information artifact",
        concern="",
        action_descriptions=[],
        cross_mapped_descriptions=[],
        onto_handlers=mock_onto_handlers,
        selected_domains=None,
    )
    uris = {c["uri"] for c in candidates}
    assert "http://example.org/ContentEntity" in uris
    # Check it has restriction metadata
    restriction_cand = next(c for c in candidates if c["uri"] == "http://example.org/ContentEntity")
    assert "restriction" in restriction_cand["query_sources"]


def test_expand_candidates_restriction_cap_at_3(mock_onto_handlers):
    """At most 3 restriction candidates are added."""
    mock_onto_handlers["search_classes"].return_value = [
        {"uri": "http://example.org/A", "label": "A", "distance": 0.1},
    ]
    # 5 restrictions — should be capped at 3
    mock_onto_handlers["get_restrictions"].return_value = [
        {"type": "someValuesFrom", "property": "p", "filler": f"http://example.org/F{i}"}
        for i in range(5)
    ]
    mock_onto_handlers["get_class_definition"].side_effect = lambda uri: (
        {"uri": uri, "label": uri.split("/")[-1], "definition": "d", "superclasses": []}
    )

    candidates, stats = expand_candidates(
        description="test",
        concern="",
        action_descriptions=[],
        cross_mapped_descriptions=[],
        onto_handlers=mock_onto_handlers,
        selected_domains=None,
    )
    restriction_cands = [c for c in candidates if "restriction" in c.get("query_sources", [])]
    assert len(restriction_cands) == 3


def test_expand_candidates_no_restriction_when_handler_absent():
    """Without get_restrictions handler, no restriction expansion occurs."""
    from unittest.mock import MagicMock
    handlers = {
        "search_classes": MagicMock(return_value=[
            {"uri": "http://example.org/A", "label": "A", "distance": 0.1},
        ]),
        "get_class_definition": MagicMock(return_value=None),
        "get_subclasses": MagicMock(return_value=[]),
        "get_superclasses": MagicMock(return_value=[]),
        "get_siblings": MagicMock(return_value=[]),
        "get_properties": MagicMock(return_value=[]),
        "explore_class": MagicMock(return_value=None),
        # No get_restrictions key
    }
    candidates, stats = expand_candidates(
        description="test",
        concern="",
        action_descriptions=[],
        cross_mapped_descriptions=[],
        onto_handlers=handlers,
        selected_domains=None,
    )
    assert stats.get("restriction_candidates_added", 0) == 0


# SearchMergeStrategy Protocol and implementations


from refiner.stages.anchor import (
    SearchMergeStrategy,
    WeightedMergeStrategy,
    GroupedMergeStrategy,
    _search_per_domain,
)


def _make_domain_candidates():
    """Helper: per-domain candidates for merge strategy tests."""
    return {
        "FIBO": [
            {"uri": "http://fibo/A", "label": "FIBO A", "hit_count": 2, "best_distance": 0.1, "domain": "FIBO", "query_sources": ["description"]},
            {"uri": "http://fibo/B", "label": "FIBO B", "hit_count": 1, "best_distance": 0.3, "domain": "FIBO", "query_sources": ["concern"]},
        ],
        "CSO": [
            {"uri": "http://cso/X", "label": "CSO X", "hit_count": 3, "best_distance": 0.05, "domain": "CSO", "query_sources": ["description", "concern"]},
            {"uri": "http://cso/Y", "label": "CSO Y", "hit_count": 1, "best_distance": 0.2, "domain": "CSO", "query_sources": ["description"]},
            {"uri": "http://cso/Z", "label": "CSO Z", "hit_count": 1, "best_distance": 0.4, "domain": "CSO", "query_sources": ["concern"]},
        ],
        "CCO": [
            {"uri": "http://cco/P", "label": "CCO P", "hit_count": 1, "best_distance": 0.15, "domain": "CCO", "query_sources": ["description"]},
        ],
    }


def test_weighted_merge_guarantees_domain_selected_slots():
    """Domain-selected ontologies (e.g. FIBO) get guaranteed slots."""
    strategy = WeightedMergeStrategy(always_included=["CCO", "Commons", "D3FEND", "CSO"])
    per_domain = _make_domain_candidates()
    selected = ["CCO", "Commons", "D3FEND", "CSO", "FIBO"]

    result = strategy.merge(
        per_domain, selected, max_candidates=5,
        risk_context={}, generic_safety_uris=set(),
    )
    uris = [c["uri"] for c in result]

    # FIBO must be represented
    assert any("fibo" in u for u in uris)
    assert len(result) <= 5


def test_weighted_merge_fills_with_always_included():
    """Remaining slots filled by always-included domains sorted by distance."""
    strategy = WeightedMergeStrategy(always_included=["CCO", "CSO"])
    per_domain = _make_domain_candidates()
    selected = ["CCO", "CSO", "FIBO"]

    result = strategy.merge(
        per_domain, selected, max_candidates=5,
        risk_context={}, generic_safety_uris=set(),
    )
    uris = [c["uri"] for c in result]

    # CSO X has best distance (0.05) among always-included — should be present
    assert "http://cso/X" in uris
    assert len(result) <= 5


def test_weighted_merge_no_domain_selected():
    """When no LLM-selected domains, all slots go to always-included by distance."""
    strategy = WeightedMergeStrategy(always_included=["CCO", "CSO"])
    per_domain = _make_domain_candidates()
    selected = ["CCO", "CSO"]

    result = strategy.merge(
        per_domain, selected, max_candidates=3,
        risk_context={}, generic_safety_uris=set(),
    )
    # All from always-included, sorted by hit_count then distance
    assert len(result) == 3
    assert result[0]["uri"] == "http://cso/X"  # hit_count 3, distance 0.05


def test_weighted_merge_deduplicates():
    """Same URI from different domains is not duplicated."""
    strategy = WeightedMergeStrategy(always_included=["CCO", "CSO"])
    per_domain = {
        "FIBO": [{"uri": "http://shared/A", "label": "A", "hit_count": 1, "best_distance": 0.1, "domain": "FIBO", "query_sources": []}],
        "CSO": [{"uri": "http://shared/A", "label": "A", "hit_count": 1, "best_distance": 0.2, "domain": "CSO", "query_sources": []}],
    }
    result = strategy.merge(
        per_domain, ["CCO", "CSO", "FIBO"], max_candidates=5,
        risk_context={}, generic_safety_uris=set(),
    )
    uris = [c["uri"] for c in result]
    assert uris.count("http://shared/A") == 1


def test_grouped_merge_equal_distribution():
    """Each domain gets roughly equal slots."""
    strategy = GroupedMergeStrategy(always_included=["CCO", "CSO"])
    per_domain = _make_domain_candidates()
    selected = ["CCO", "CSO", "FIBO"]

    result = strategy.merge(
        per_domain, selected, max_candidates=6,
        risk_context={}, generic_safety_uris=set(),
    )
    # 6 / 3 domains = 2 per domain
    domains_in_result = [c["domain"] for c in result]
    assert domains_in_result.count("FIBO") <= 2
    assert domains_in_result.count("CSO") <= 2
    assert domains_in_result.count("CCO") <= 2
    assert len(result) <= 6


def test_grouped_merge_caps_at_max():
    """Total results never exceed max_candidates."""
    strategy = GroupedMergeStrategy()
    per_domain = _make_domain_candidates()
    selected = ["CCO", "CSO", "FIBO"]

    result = strategy.merge(
        per_domain, selected, max_candidates=3,
        risk_context={}, generic_safety_uris=set(),
    )
    assert len(result) <= 3


def test_grouped_merge_skips_empty_domains():
    """Domains with no candidates are skipped without error."""
    strategy = GroupedMergeStrategy()
    per_domain = {"FIBO": _make_domain_candidates()["FIBO"]}
    selected = ["CCO", "CSO", "FIBO"]

    result = strategy.merge(
        per_domain, selected, max_candidates=5,
        risk_context={}, generic_safety_uris=set(),
    )
    assert all(c["domain"] == "FIBO" for c in result)


def test_strategy_protocol_compliance():
    """Both strategy implementations satisfy the Protocol."""
    assert isinstance(WeightedMergeStrategy(), SearchMergeStrategy)
    assert isinstance(GroupedMergeStrategy(), SearchMergeStrategy)


# Per-domain search integration in expand_candidates


def test_expand_candidates_with_weighted_strategy(mock_onto_handlers):
    """expand_candidates uses strategy when search_domains is available."""
    mock_onto_handlers["search_domains"] = MagicMock(return_value={
        "CSO": [
            {"uri": "http://cso/X", "label": "CSO X", "distance": 0.1},
        ],
        "CCO": [
            {"uri": "http://cco/A", "label": "CCO A", "distance": 0.2},
        ],
    })
    strategy = WeightedMergeStrategy(always_included=["CCO", "CSO"])

    candidates, stats = expand_candidates(
        description="fraud risk",
        concern="",
        action_descriptions=[],
        cross_mapped_descriptions=[],
        onto_handlers=mock_onto_handlers,
        selected_domains=["CCO", "CSO"],
        merge_strategy=strategy,
    )
    assert stats["search_strategy"] == "WeightedMergeStrategy"
    assert len(candidates) >= 1
    mock_onto_handlers["search_domains"].assert_called()


def test_expand_candidates_falls_back_without_search_domains(mock_onto_handlers):
    """Without search_domains handler, expand_candidates uses legacy path."""
    # search_domains not in handlers — should use search_classes
    mock_onto_handlers["search_classes"].return_value = [
        {"uri": "http://example.org/A", "label": "A", "distance": 0.2},
    ]
    strategy = WeightedMergeStrategy()

    candidates, stats = expand_candidates(
        description="fraud risk",
        concern="",
        action_descriptions=[],
        cross_mapped_descriptions=[],
        onto_handlers=mock_onto_handlers,
        selected_domains=None,
        merge_strategy=strategy,
    )
    assert "search_strategy" not in stats
    mock_onto_handlers["search_classes"].assert_called()


def test_expand_candidates_per_domain_multi_query(mock_onto_handlers):
    """Multiple queries accumulate hit_count per URI within each domain."""
    call_count = [0]

    def mock_search_domains(query, domains, top_k_per_domain=10):
        call_count[0] += 1
        if call_count[0] == 1:
            return {"CSO": [{"uri": "http://cso/X", "label": "X", "distance": 0.2}]}
        return {"CSO": [{"uri": "http://cso/X", "label": "X", "distance": 0.1}]}

    mock_onto_handlers["search_domains"] = mock_search_domains
    strategy = WeightedMergeStrategy(always_included=["CSO"])

    candidates, stats = expand_candidates(
        description="fraud",
        concern="loss",
        action_descriptions=[],
        cross_mapped_descriptions=[],
        onto_handlers=mock_onto_handlers,
        selected_domains=["CSO"],
        merge_strategy=strategy,
    )
    assert stats["queries_run"] == 2
    x = next(c for c in candidates if c["uri"] == "http://cso/X")
    assert x["hit_count"] == 2
    assert x["best_distance"] == 0.1


# Distance normalization and threshold tests


def test_normalize_distances_zscore():
    """Z-score normalization produces correct values for n >= 2."""
    candidates = [
        {"uri": "a", "best_distance": 0.1},
        {"uri": "b", "best_distance": 0.3},
        {"uri": "c", "best_distance": 0.8},
    ]
    WeightedMergeStrategy._normalize_distances(candidates)
    # All should have normalized_distance
    assert all("normalized_distance" in c for c in candidates)
    # Best distance should have negative z-score
    assert candidates[0]["normalized_distance"] < 0
    # Worst distance should have positive z-score
    assert candidates[2]["normalized_distance"] > 0


def test_normalize_distances_single_candidate():
    """Single candidate gets neutral z-score (0.0)."""
    candidates = [{"uri": "a", "best_distance": 0.5}]
    WeightedMergeStrategy._normalize_distances(candidates)
    assert candidates[0]["normalized_distance"] == 0.0


def test_normalize_distances_uniform():
    """All-identical distances get neutral z-scores."""
    candidates = [
        {"uri": "a", "best_distance": 0.3},
        {"uri": "b", "best_distance": 0.3},
    ]
    WeightedMergeStrategy._normalize_distances(candidates)
    assert all(c["normalized_distance"] == 0.0 for c in candidates)


def test_weighted_merge_filters_poor_distance_candidate():
    """Single FIBO candidate with distance above ceiling is filtered from quota."""
    strategy = WeightedMergeStrategy(always_included=["CCO", "CSO"])
    per_domain = {
        "FIBO": [
            {"uri": "http://fibo/bad", "label": "Bad", "hit_count": 1, "best_distance": 0.7,
             "domain": "FIBO", "query_sources": []},
        ],
        "CSO": [
            {"uri": "http://cso/X", "label": "Good", "hit_count": 2, "best_distance": 0.1,
             "domain": "CSO", "query_sources": []},
        ],
    }
    result = strategy.merge(
        per_domain, ["CCO", "CSO", "FIBO"], max_candidates=5,
        risk_context={}, generic_safety_uris=set(),
    )
    uris = [c["uri"] for c in result]
    assert "http://fibo/bad" not in uris
    assert "http://cso/X" in uris


def test_weighted_merge_keeps_good_single_candidate():
    """Single FIBO candidate with good distance passes into quota."""
    strategy = WeightedMergeStrategy(always_included=["CCO", "CSO"])
    per_domain = {
        "FIBO": [
            {"uri": "http://fibo/good", "label": "Good", "hit_count": 1, "best_distance": 0.35,
             "domain": "FIBO", "query_sources": []},
        ],
        "CSO": [
            {"uri": "http://cso/X", "label": "X", "hit_count": 1, "best_distance": 0.2,
             "domain": "CSO", "query_sources": []},
        ],
    }
    result = strategy.merge(
        per_domain, ["CCO", "CSO", "FIBO"], max_candidates=5,
        risk_context={}, generic_safety_uris=set(),
    )
    uris = [c["uri"] for c in result]
    assert "http://fibo/good" in uris


def test_weighted_merge_filters_domain_outlier_by_zscore():
    """Within-domain outlier filtered by z-score even if below raw ceiling."""
    strategy = WeightedMergeStrategy(always_included=["CCO", "CSO"])
    per_domain = {
        "CSO": [
            {"uri": "http://cso/good", "label": "Good", "hit_count": 1, "best_distance": 0.1,
             "domain": "CSO", "query_sources": []},
            {"uri": "http://cso/ok", "label": "OK", "hit_count": 1, "best_distance": 0.15,
             "domain": "CSO", "query_sources": []},
            {"uri": "http://cso/outlier", "label": "Outlier", "hit_count": 1, "best_distance": 0.55,
             "domain": "CSO", "query_sources": []},
        ],
    }
    result = strategy.merge(
        per_domain, ["CSO"], max_candidates=5,
        risk_context={}, generic_safety_uris=set(),
    )
    uris = [c["uri"] for c in result]
    assert "http://cso/good" in uris
    assert "http://cso/ok" in uris
    # 0.55 is below raw ceiling (0.6) but z-score is well above 1.0
    assert "http://cso/outlier" not in uris


def test_weighted_merge_pool_filters_by_threshold():
    """Always-included pool also respects distance threshold."""
    strategy = WeightedMergeStrategy(always_included=["CCO", "CSO"])
    per_domain = {
        "CSO": [
            {"uri": "http://cso/good", "label": "Good", "hit_count": 1, "best_distance": 0.2,
             "domain": "CSO", "query_sources": []},
            {"uri": "http://cso/bad", "label": "Bad", "hit_count": 1, "best_distance": 0.75,
             "domain": "CSO", "query_sources": []},
        ],
    }
    result = strategy.merge(
        per_domain, ["CSO"], max_candidates=5,
        risk_context={}, generic_safety_uris=set(),
    )
    uris = [c["uri"] for c in result]
    assert "http://cso/good" in uris
    assert "http://cso/bad" not in uris


# --- Generic safety URI filtering ---

from refiner.stages.anchor import build_generic_safety_uris


def test_weighted_merge_filters_generic_safety_uris():
    """Candidates in generic_safety_uris are excluded from merge results."""
    strategy = WeightedMergeStrategy(always_included=["CCO", "CSO"])
    per_domain = {
        "CSO": [
            {"uri": "http://cso/fraud", "label": "Fraud", "hit_count": 3, "best_distance": 0.20,
             "domain": "CSO", "query_sources": []},
            {"uri": "http://cso/arson", "label": "Arson Methods", "hit_count": 5, "best_distance": 0.21,
             "domain": "CSO", "query_sources": []},
            {"uri": "http://cso/cbrn", "label": "CBRN Information", "hit_count": 4, "best_distance": 0.22,
             "domain": "CSO", "query_sources": []},
            {"uri": "http://cso/privacy", "label": "Privacy", "hit_count": 2, "best_distance": 0.23,
             "domain": "CSO", "query_sources": []},
            {"uri": "http://cso/deception", "label": "Deception", "hit_count": 2, "best_distance": 0.24,
             "domain": "CSO", "query_sources": []},
        ],
    }
    result = strategy.merge(
        per_domain, ["CSO"], max_candidates=5,
        risk_context={}, generic_safety_uris={"http://cso/arson", "http://cso/cbrn"},
    )
    uris = [c["uri"] for c in result]
    assert "http://cso/fraud" in uris
    assert "http://cso/privacy" in uris
    assert "http://cso/arson" not in uris
    assert "http://cso/cbrn" not in uris


def test_weighted_merge_no_filter_when_generic_safety_empty():
    """When generic_safety_uris is empty, all candidates pass."""
    strategy = WeightedMergeStrategy(always_included=["CCO", "CSO"])
    # default: generic_safety_uris is empty
    per_domain = {
        "CSO": [
            {"uri": "http://cso/arson", "label": "Arson Methods", "hit_count": 3, "best_distance": 0.2,
             "domain": "CSO", "query_sources": []},
        ],
    }
    result = strategy.merge(
        per_domain, ["CSO"], max_candidates=5,
        risk_context={}, generic_safety_uris=set(),
    )
    uris = [c["uri"] for c in result]
    assert "http://cso/arson" in uris


def test_weighted_merge_generic_safety_filters_quota_pass():
    """Generic safety filter also applies to domain-selected quota slots."""
    strategy = WeightedMergeStrategy(always_included=["CCO"])
    per_domain = {
        "CSO": [
            {"uri": "http://cso/arson", "label": "Arson", "hit_count": 3, "best_distance": 0.20,
             "domain": "CSO", "query_sources": []},
            {"uri": "http://cso/fraud", "label": "Fraud", "hit_count": 2, "best_distance": 0.22,
             "domain": "CSO", "query_sources": []},
            {"uri": "http://cso/privacy", "label": "Privacy", "hit_count": 2, "best_distance": 0.24,
             "domain": "CSO", "query_sources": []},
        ],
    }
    # CSO is domain-selected (not in always_included=["CCO"])
    result = strategy.merge(
        per_domain, ["CCO", "CSO"], max_candidates=5,
        risk_context={}, generic_safety_uris={"http://cso/arson"},
    )
    uris = [c["uri"] for c in result]
    assert "http://cso/arson" not in uris
    assert "http://cso/fraud" in uris


def test_grouped_merge_filters_generic_safety_uris():
    """GroupedMergeStrategy also filters generic_safety_uris."""
    from refiner.stages.anchor import GroupedMergeStrategy
    strategy = GroupedMergeStrategy(always_included=["CCO", "CSO"])
    per_domain = {
        "CSO": [
            {"uri": "http://cso/arson", "label": "Arson", "hit_count": 3, "best_distance": 0.2,
             "domain": "CSO", "query_sources": []},
            {"uri": "http://cso/fraud", "label": "Fraud", "hit_count": 2, "best_distance": 0.25,
             "domain": "CSO", "query_sources": []},
        ],
    }
    result = strategy.merge(
        per_domain, ["CSO"], max_candidates=5,
        risk_context={}, generic_safety_uris={"http://cso/arson"},
    )
    uris = [c["uri"] for c in result]
    assert "http://cso/arson" not in uris
    assert "http://cso/fraud" in uris


def test_build_generic_safety_uris_with_subclasses():
    """build_generic_safety_uris returns parent + descendants."""
    handlers = {
        "get_subclasses": lambda uri, depth=1: [
            {"uri": "http://cso#WeaponsManufacturing", "label": "WM", "depth": 1},
            {"uri": "http://cso#DrugSynthesis", "label": "DS", "depth": 1},
            {"uri": "http://cso#FirearmsManufacturing", "label": "FM", "depth": 2},
        ],
    }
    uris = build_generic_safety_uris(handlers)
    assert "http://taxonomy-refiner.io/ontologies/cso#DangerousInformation" in uris
    assert "http://cso#WeaponsManufacturing" in uris
    assert "http://cso#DrugSynthesis" in uris
    assert "http://cso#FirearmsManufacturing" in uris
    assert len(uris) == 4  # parent + 3 descendants


def test_build_generic_safety_uris_no_handler():
    """Returns empty set when get_subclasses is unavailable."""
    uris = build_generic_safety_uris({})
    assert uris == set()


def test_build_generic_safety_uris_empty_descendants():
    """Returns just the parent URI when no descendants found."""
    handlers = {"get_subclasses": lambda uri, depth=1: []}
    uris = build_generic_safety_uris(handlers)
    assert uris == {"http://taxonomy-refiner.io/ontologies/cso#DangerousInformation"}


def test_expand_candidates_passes_risk_context_to_strategy(mock_onto_handlers):
    """expand_candidates assembles risk_context and passes to merge strategy."""
    from unittest.mock import MagicMock
    from refiner.stages.anchor import expand_candidates

    mock_strategy = MagicMock()
    mock_strategy.merge.return_value = [
        {"uri": "http://cso/X", "label": "X", "hit_count": 1, "best_distance": 0.1,
         "domain": "CSO", "query_sources": ["description"]},
    ]
    mock_onto_handlers["search_domains"] = MagicMock(return_value={
        "CSO": [{"uri": "http://cso/X", "label": "X", "distance": 0.1}],
    })

    candidates, stats = expand_candidates(
        description="fraud risk",
        concern="financial loss",
        action_descriptions=[],
        cross_mapped_descriptions=[],
        onto_handlers=mock_onto_handlers,
        selected_domains=["CSO"],
        merge_strategy=mock_strategy,
        policy_concept="Fraud Prevention",
        generic_safety_uris={"http://cso/arson"},
    )

    mock_strategy.merge.assert_called_once()
    call_kwargs = mock_strategy.merge.call_args
    assert call_kwargs[1]["risk_context"] == {
        "description": "fraud risk",
        "concern": "financial loss",
        "policy_concept": "Fraud Prevention",
    }
    assert call_kwargs[1]["generic_safety_uris"] == {"http://cso/arson"}
