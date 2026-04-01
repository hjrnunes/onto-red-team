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
    mock_onto_handlers["search_classes"].assert_called_once()


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
    # The search was called with top_k=10 (extra headroom for filtering)
    mock_onto_handlers["search_classes"].assert_called_once()
    call_kwargs = mock_onto_handlers["search_classes"].call_args
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


def test_anchor_emits_domain_filtered(mock_client, mock_config, mock_onto_handlers):
    """When selected_domains filters candidates, emit domain_filtered."""
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
    filtered = [e for e in report.events if e["event"] == "domain_filtered"]
    assert len(filtered) == 1
    assert filtered[0]["filtered_count"] == 2  # 2 OBO candidates removed
    assert filtered[0]["kept_count"] == 1  # 1 FIBO kept


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
