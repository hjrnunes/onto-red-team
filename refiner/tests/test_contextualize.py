from refiner.models import (
    RiskVariationAxes,
    VariationAxis,
    DomainContextProfile,
    DomainContextAxis,
    AxisEnumeration,
    RunReport,
)
from refiner.stages.contextualize import contextualize, _ContextResponse, _AxisResponse, _EnumResponse
from refiner.stages.identify_domains import derive_source_ontology


def _make_axes():
    return RiskVariationAxes(
        risk_id="atlas-fraud",
        risk_name="Fraud",
        policy_concept="Fraud",
        axes=[
            VariationAxis(
                cco_class_uri="http://example.org/Person",
                cco_class_label="Person",
                roles=["agent"],
                rationale="Actor",
            ),
        ],
    )


def test_contextualize_gets_subclasses(mock_client, mock_config, mock_onto_handlers):
    axes = [_make_axes()]
    mock_onto_handlers["get_subclasses"].return_value = [
        {"uri": "http://example.org/Employee", "label": "Employee", "depth": 1},
        {"uri": "http://example.org/Manager", "label": "Manager", "depth": 2},
    ]
    mock_onto_handlers["get_class_definition"].return_value = {
        "uri": "http://example.org/Employee", "label": "Employee", "definition": "An employee", "superclasses": []
    }
    mock_client.chat.completions.create.return_value = _ContextResponse(
        axes=[
            _AxisResponse(
                cco_class_uri="http://example.org/Person",
                enumerations=[
                    _EnumResponse(class_uri="http://example.org/Employee", class_label="Employee", relevance="high"),
                ],
            ),
        ],
    )
    result = contextualize(axes, mock_client, mock_config, mock_onto_handlers)
    assert len(result) == 1
    assert result[0].axes[0].enumerations[0].class_label == "Employee"
    assert result[0].axes[0].cco_class_label == "Person"
    assert result[0].axes[0].roles == ["agent"]
    mock_onto_handlers["get_subclasses"].assert_called_once_with("http://example.org/Person", depth=1)


def test_contextualize_preserves_policy_concept(mock_client, mock_config, mock_onto_handlers):
    axes = [_make_axes()]
    mock_onto_handlers["get_subclasses"].return_value = []
    mock_client.chat.completions.create.return_value = _ContextResponse(axes=[])
    result = contextualize(axes, mock_client, mock_config, mock_onto_handlers)
    assert result[0].policy_concept == "Fraud"


def test_contextualize_filters_invalid_enumeration_uris(mock_client, mock_config, mock_onto_handlers):
    axes = [_make_axes()]
    mock_onto_handlers["get_subclasses"].return_value = [
        {"uri": "http://example.org/Employee", "label": "Employee", "depth": 1},
    ]
    mock_onto_handlers["get_class_definition"].side_effect = lambda uri: (
        {"uri": uri, "label": "Employee", "definition": "d", "superclasses": []}
        if uri == "http://example.org/Employee" else None
    )
    mock_client.chat.completions.create.return_value = _ContextResponse(
        axes=[
            _AxisResponse(
                cco_class_uri="http://example.org/Person",
                enumerations=[
                    _EnumResponse(class_uri="http://example.org/Employee", class_label="Employee", relevance="high"),
                    _EnumResponse(class_uri="http://example.org/FakeClass", class_label="Fake", relevance="low"),
                ],
            ),
        ],
    )
    result = contextualize(axes, mock_client, mock_config, mock_onto_handlers)
    assert len(result[0].axes[0].enumerations) == 1
    assert result[0].axes[0].enumerations[0].class_uri == "http://example.org/Employee"


def test_contextualize_derives_source_ontology(mock_client, mock_config, mock_onto_handlers):
    axes = [_make_axes()]
    mock_onto_handlers["get_subclasses"].return_value = [
        {"uri": "https://spec.edmcouncil.org/fibo/ontology/FND/Foo/Bar", "label": "Bar", "depth": 1},
    ]
    mock_onto_handlers["get_class_definition"].return_value = {
        "uri": "https://spec.edmcouncil.org/fibo/ontology/FND/Foo/Bar", "label": "Bar", "definition": "d", "superclasses": []
    }
    mock_client.chat.completions.create.return_value = _ContextResponse(
        axes=[
            _AxisResponse(
                cco_class_uri="http://example.org/Person",
                enumerations=[
                    _EnumResponse(
                        class_uri="https://spec.edmcouncil.org/fibo/ontology/FND/Foo/Bar",
                        class_label="Bar", relevance="high",
                    ),
                ],
            ),
        ],
    )
    result = contextualize(axes, mock_client, mock_config, mock_onto_handlers)
    assert result[0].axes[0].enumerations[0].source_ontology == "FIBO"


def test_contextualize_falls_back_to_siblings(mock_client, mock_config, mock_onto_handlers):
    axes = [_make_axes()]
    mock_onto_handlers["get_subclasses"].return_value = []  # no subclasses — leaf node
    mock_onto_handlers["get_siblings"].return_value = [
        {"uri": "http://example.org/Person", "label": "Person"},  # self — should be excluded
        {"uri": "http://example.org/Organization", "label": "Organization"},
        {"uri": "http://example.org/Group", "label": "Group"},
    ]
    mock_onto_handlers["get_class_definition"].return_value = {
        "uri": "http://example.org/Organization", "label": "Organization", "definition": "d", "superclasses": []
    }
    mock_client.chat.completions.create.return_value = _ContextResponse(
        axes=[
            _AxisResponse(
                cco_class_uri="http://example.org/Person",
                enumerations=[
                    _EnumResponse(class_uri="http://example.org/Organization", class_label="Organization", relevance="high"),
                ],
            ),
        ],
    )
    result = contextualize(axes, mock_client, mock_config, mock_onto_handlers)
    assert len(result[0].axes[0].enumerations) == 1
    assert result[0].axes[0].enumerations[0].class_label == "Organization"
    mock_onto_handlers["get_siblings"].assert_called_once_with("http://example.org/Person")


def test_contextualize_sibling_fallback_excludes_self(mock_client, mock_config, mock_onto_handlers):
    axes = [_make_axes()]
    mock_onto_handlers["get_subclasses"].return_value = []
    mock_onto_handlers["get_siblings"].return_value = [
        {"uri": "http://example.org/Person", "label": "Person"},  # self
    ]
    mock_client.chat.completions.create.return_value = _ContextResponse(axes=[])
    result = contextualize(axes, mock_client, mock_config, mock_onto_handlers)
    # Self was excluded, so LLM got "(none)" and returned empty axes
    assert result[0].axes == []


def test_contextualize_filters_self_reference_enumerations(mock_client, mock_config, mock_onto_handlers):
    axes = [_make_axes()]
    mock_onto_handlers["get_subclasses"].return_value = [
        {"uri": "http://example.org/Employee", "label": "Employee", "depth": 1},
    ]
    mock_onto_handlers["get_class_definition"].return_value = {
        "uri": "http://example.org/Employee", "label": "Employee", "definition": "d", "superclasses": []
    }
    mock_client.chat.completions.create.return_value = _ContextResponse(
        axes=[
            _AxisResponse(
                cco_class_uri="http://example.org/Person",
                enumerations=[
                    _EnumResponse(class_uri="http://example.org/Person", class_label="Person", relevance="high"),
                    _EnumResponse(class_uri="http://example.org/Employee", class_label="Employee", relevance="high"),
                ],
            ),
        ],
    )
    result = contextualize(axes, mock_client, mock_config, mock_onto_handlers)
    assert len(result[0].axes[0].enumerations) == 1
    assert result[0].axes[0].enumerations[0].class_uri == "http://example.org/Employee"


def test_contextualize_caches_by_risk_id(mock_client, mock_config, mock_onto_handlers):
    """Same risk_id from two policies should only trigger one LLM call."""
    axes = [
        RiskVariationAxes(
            risk_id="atlas-fraud", risk_name="Fraud", policy_concept="Fraud",
            axes=[VariationAxis(cco_class_uri="http://example.org/Person", cco_class_label="Person", roles=["agent"], rationale="r")],
        ),
        RiskVariationAxes(
            risk_id="atlas-fraud", risk_name="Fraud", policy_concept="AML",
            axes=[VariationAxis(cco_class_uri="http://example.org/Person", cco_class_label="Person", roles=["agent"], rationale="r")],
        ),
    ]
    mock_onto_handlers["get_subclasses"].return_value = [
        {"uri": "http://example.org/Employee", "label": "Employee", "depth": 1},
    ]
    mock_onto_handlers["get_class_definition"].return_value = {
        "uri": "http://example.org/Employee", "label": "Employee", "definition": "d", "superclasses": [],
    }
    mock_client.chat.completions.create.return_value = _ContextResponse(
        axes=[
            _AxisResponse(
                cco_class_uri="http://example.org/Person",
                enumerations=[
                    _EnumResponse(class_uri="http://example.org/Employee", class_label="Employee", relevance="high"),
                ],
            ),
        ],
    )
    result = contextualize(axes, mock_client, mock_config, mock_onto_handlers)
    assert len(result) == 2
    assert result[0].policy_concept == "Fraud"
    assert result[1].policy_concept == "AML"
    assert result[0].axes[0].enumerations == result[1].axes[0].enumerations
    # LLM called only once despite two entries with the same risk_id
    mock_client.chat.completions.create.assert_called_once()


def test_contextualize_empty_axes(mock_client, mock_config, mock_onto_handlers):
    result = contextualize([], mock_client, mock_config, mock_onto_handlers)
    assert result == []


def test_contextualize_emits_sibling_fallback(mock_client, mock_config, mock_onto_handlers):
    """When subclasses empty and siblings used, emit sibling_fallback."""
    axes = [_make_axes()]
    mock_onto_handlers["get_subclasses"].return_value = []  # leaf node
    mock_onto_handlers["get_siblings"].return_value = [
        {"uri": "http://example.org/Person", "label": "Person"},  # self
        {"uri": "http://example.org/Organization", "label": "Organization"},
    ]
    mock_onto_handlers["get_class_definition"].return_value = {
        "uri": "http://example.org/Organization", "label": "Organization", "definition": "d", "superclasses": []
    }
    mock_client.chat.completions.create.return_value = _ContextResponse(
        axes=[_AxisResponse(
            cco_class_uri="http://example.org/Person",
            enumerations=[_EnumResponse(class_uri="http://example.org/Organization", class_label="Organization", relevance="high")],
        )],
    )
    report = RunReport(model="m", policy_set="p", timestamp="t")
    result = contextualize(axes, mock_client, mock_config, mock_onto_handlers, report=report)
    fallbacks = [e for e in report.events if e["event"] == "sibling_fallback"]
    assert len(fallbacks) == 1
    assert fallbacks[0]["axis_uri"] == "http://example.org/Person"
    assert fallbacks[0]["sibling_count"] == 1  # self excluded, 1 remaining


def test_contextualize_emits_self_reference_filtered(mock_client, mock_config, mock_onto_handlers):
    """When enumeration URI matches axis URI, emit self_reference_filtered."""
    axes = [_make_axes()]
    mock_onto_handlers["get_subclasses"].return_value = [
        {"uri": "http://example.org/Employee", "label": "Employee", "depth": 1},
    ]
    mock_onto_handlers["get_class_definition"].return_value = {
        "uri": "http://example.org/Employee", "label": "Employee", "definition": "d", "superclasses": []
    }
    mock_client.chat.completions.create.return_value = _ContextResponse(
        axes=[_AxisResponse(
            cco_class_uri="http://example.org/Person",
            enumerations=[
                _EnumResponse(class_uri="http://example.org/Person", class_label="Person", relevance="high"),  # self-ref
                _EnumResponse(class_uri="http://example.org/Employee", class_label="Employee", relevance="high"),
            ],
        )],
    )
    report = RunReport(model="m", policy_set="p", timestamp="t")
    result = contextualize(axes, mock_client, mock_config, mock_onto_handlers, report=report)
    self_refs = [e for e in report.events if e["event"] == "self_reference_filtered"]
    assert len(self_refs) == 1
    assert self_refs[0]["axis_uri"] == "http://example.org/Person"


def test_contextualize_emits_empty_enumerations(mock_client, mock_config, mock_onto_handlers):
    """When an axis has no valid enumerations, emit empty_enumerations."""
    axes = [_make_axes()]
    mock_onto_handlers["get_subclasses"].return_value = [
        {"uri": "http://example.org/Employee", "label": "Employee", "depth": 1},
    ]
    mock_onto_handlers["get_class_definition"].return_value = None  # all enum URIs invalid
    mock_client.chat.completions.create.return_value = _ContextResponse(
        axes=[_AxisResponse(
            cco_class_uri="http://example.org/Person",
            enumerations=[
                _EnumResponse(class_uri="http://example.org/Employee", class_label="Employee", relevance="high"),
            ],
        )],
    )
    report = RunReport(model="m", policy_set="p", timestamp="t")
    result = contextualize(axes, mock_client, mock_config, mock_onto_handlers, report=report)
    empty = [e for e in report.events if e["event"] == "empty_enumerations"]
    assert len(empty) == 1
    assert empty[0]["risk_id"] == "atlas-fraud"
    assert empty[0]["axis_uri"] == "http://example.org/Person"


def test_contextualize_filters_enumerations_by_domain(mock_client, mock_config, mock_onto_handlers):
    """Enumerations from non-selected domains are filtered out."""
    axes = [_make_axes()]
    mock_onto_handlers["get_subclasses"].return_value = [
        {"uri": "https://spec.edmcouncil.org/fibo/ontology/FND/Foo/CreditMsg", "label": "Credit Message", "depth": 1},
        {"uri": "http://purl.obolibrary.org/obo/OGMS_12345", "label": "Clinical Finding", "depth": 1},
    ]
    mock_onto_handlers["get_class_definition"].return_value = {
        "uri": "http://purl.obolibrary.org/obo/OGMS_12345", "label": "Clinical Finding", "definition": "d", "superclasses": []
    }
    mock_client.chat.completions.create.return_value = _ContextResponse(
        axes=[
            _AxisResponse(
                cco_class_uri="http://example.org/Person",
                enumerations=[
                    _EnumResponse(
                        class_uri="https://spec.edmcouncil.org/fibo/ontology/FND/Foo/CreditMsg",
                        class_label="Credit Message", relevance="high",
                    ),
                    _EnumResponse(
                        class_uri="http://purl.obolibrary.org/obo/OGMS_12345",
                        class_label="Clinical Finding", relevance="high",
                    ),
                ],
            ),
        ],
    )
    # Healthcare run: CCO, Commons, OBO selected — FIBO not selected
    result = contextualize(
        axes, mock_client, mock_config, mock_onto_handlers,
        selected_domains=["CCO", "Commons", "OBO"],
    )
    assert len(result[0].axes[0].enumerations) == 1
    assert result[0].axes[0].enumerations[0].class_uri == "http://purl.obolibrary.org/obo/OGMS_12345"


def test_contextualize_domain_filter_emits_event(mock_client, mock_config, mock_onto_handlers):
    """Domain-filtered enumerations emit enumeration_domain_filtered event."""
    axes = [_make_axes()]
    mock_onto_handlers["get_subclasses"].return_value = [
        {"uri": "https://spec.edmcouncil.org/fibo/ontology/FND/Foo/CreditMsg", "label": "Credit Message", "depth": 1},
    ]
    mock_client.chat.completions.create.return_value = _ContextResponse(
        axes=[
            _AxisResponse(
                cco_class_uri="http://example.org/Person",
                enumerations=[
                    _EnumResponse(
                        class_uri="https://spec.edmcouncil.org/fibo/ontology/FND/Foo/CreditMsg",
                        class_label="Credit Message", relevance="high",
                    ),
                ],
            ),
        ],
    )
    report = RunReport(model="m", policy_set="p", timestamp="t")
    contextualize(
        axes, mock_client, mock_config, mock_onto_handlers,
        selected_domains=["CCO", "Commons", "OBO"], report=report,
    )
    filtered = [e for e in report.events if e["event"] == "enumeration_domain_filtered"]
    assert len(filtered) == 1
    assert filtered[0]["enum_domain"] == "FIBO"
    assert filtered[0]["enum_uri"] == "https://spec.edmcouncil.org/fibo/ontology/FND/Foo/CreditMsg"


def test_contextualize_no_domain_filter_when_none(mock_client, mock_config, mock_onto_handlers):
    """When selected_domains is None, no domain filtering is applied."""
    axes = [_make_axes()]
    mock_onto_handlers["get_subclasses"].return_value = [
        {"uri": "https://spec.edmcouncil.org/fibo/ontology/FND/Foo/CreditMsg", "label": "Credit Message", "depth": 1},
    ]
    mock_onto_handlers["get_class_definition"].return_value = {
        "uri": "https://spec.edmcouncil.org/fibo/ontology/FND/Foo/CreditMsg", "label": "Credit Message", "definition": "d", "superclasses": []
    }
    mock_client.chat.completions.create.return_value = _ContextResponse(
        axes=[
            _AxisResponse(
                cco_class_uri="http://example.org/Person",
                enumerations=[
                    _EnumResponse(
                        class_uri="https://spec.edmcouncil.org/fibo/ontology/FND/Foo/CreditMsg",
                        class_label="Credit Message", relevance="high",
                    ),
                ],
            ),
        ],
    )
    # No selected_domains — all enumerations pass
    result = contextualize(axes, mock_client, mock_config, mock_onto_handlers)
    assert len(result[0].axes[0].enumerations) == 1


def test_contextualize_no_report_works(mock_client, mock_config, mock_onto_handlers):
    """contextualize works without report param (backward compat)."""
    axes = [_make_axes()]
    mock_onto_handlers["get_subclasses"].return_value = []
    mock_client.chat.completions.create.return_value = _ContextResponse(axes=[])
    result = contextualize(axes, mock_client, mock_config, mock_onto_handlers)
    assert len(result) == 1


def test_contextualize_subclass_provenance(mock_client, mock_config, mock_onto_handlers):
    """Enumerations from subclass traversal should have provenance='subclass'."""
    axes = [_make_axes()]
    mock_onto_handlers["get_subclasses"].return_value = [
        {"uri": "http://example.org/Employee", "label": "Employee", "depth": 1},
    ]
    mock_onto_handlers["get_class_definition"].return_value = {
        "uri": "http://example.org/Employee", "label": "Employee", "definition": "d", "superclasses": []
    }
    mock_client.chat.completions.create.return_value = _ContextResponse(
        axes=[_AxisResponse(
            cco_class_uri="http://example.org/Person",
            enumerations=[_EnumResponse(class_uri="http://example.org/Employee", class_label="Employee", relevance="high")],
        )],
    )
    result = contextualize(axes, mock_client, mock_config, mock_onto_handlers)
    assert result[0].axes[0].enumerations[0].provenance == "subclass"


def test_contextualize_sibling_provenance(mock_client, mock_config, mock_onto_handlers):
    """Enumerations from sibling fallback should have provenance='sibling'."""
    axes = [_make_axes()]
    mock_onto_handlers["get_subclasses"].return_value = []
    mock_onto_handlers["get_siblings"].return_value = [
        {"uri": "http://example.org/Person", "label": "Person"},
        {"uri": "http://example.org/Organization", "label": "Organization"},
    ]
    mock_onto_handlers["get_class_definition"].return_value = {
        "uri": "http://example.org/Organization", "label": "Organization", "definition": "d", "superclasses": []
    }
    mock_client.chat.completions.create.return_value = _ContextResponse(
        axes=[_AxisResponse(
            cco_class_uri="http://example.org/Person",
            enumerations=[_EnumResponse(class_uri="http://example.org/Organization", class_label="Organization", relevance="high")],
        )],
    )
    result = contextualize(axes, mock_client, mock_config, mock_onto_handlers)
    assert result[0].axes[0].enumerations[0].provenance == "sibling"


def test_contextualize_includes_risk_description_in_prompt(mock_client, mock_config, mock_onto_handlers):
    """When risk_details provided, description and concern appear in LLM prompt."""
    axes = [RiskVariationAxes(
        risk_id="atlas-fraud", risk_name="Fraud", policy_concept="Fraud",
        axes=[VariationAxis(
            cco_class_uri="http://example.org/Person", cco_class_label="Person",
            roles=["agent"], rationale="r",
        )],
    )]
    risk_details = {
        "atlas-fraud": {
            "description": "Fraudulent activities targeting financial systems",
            "concern": "Financial loss and trust erosion",
        },
    }
    mock_onto_handlers["get_subclasses"].return_value = [
        {"uri": "http://example.org/Employee", "label": "Employee", "depth": 1},
    ]
    mock_client.chat.completions.create.return_value = _ContextResponse(axes=[
        _AxisResponse(cco_class_uri="http://example.org/Person", enumerations=[
            _EnumResponse(class_uri="http://example.org/Employee", class_label="Employee", relevance="high"),
        ]),
    ])
    mock_onto_handlers["get_class_definition"].return_value = {
        "uri": "http://example.org/Employee", "label": "Employee", "definition": "d", "superclasses": [],
    }
    result = contextualize(axes, mock_client, mock_config, mock_onto_handlers,
                           risk_details=risk_details)
    # Check the LLM was called with description and concern in the prompt
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    messages = call_kwargs["messages"]
    user_msg = messages[1]["content"]
    assert "Fraudulent activities targeting financial systems" in user_msg
    assert "Financial loss and trust erosion" in user_msg


def test_contextualize_works_without_risk_details(mock_client, mock_config, mock_onto_handlers):
    """Backward compat: risk_details=None still works."""
    axes = [RiskVariationAxes(
        risk_id="atlas-fraud", risk_name="Fraud", policy_concept="Fraud",
        axes=[VariationAxis(
            cco_class_uri="http://example.org/Person", cco_class_label="Person",
            roles=["agent"], rationale="r",
        )],
    )]
    mock_onto_handlers["get_subclasses"].return_value = []
    mock_onto_handlers["get_siblings"].return_value = []
    mock_client.chat.completions.create.return_value = _ContextResponse(axes=[])
    result = contextualize(axes, mock_client, mock_config, mock_onto_handlers)
    assert len(result) == 1


def test_contextualize_filters_disjoint_enumerations(mock_client, mock_config, mock_onto_handlers):
    """When two enumerations are disjoint, keep the higher-relevance one."""
    axes = [_make_axes()]
    mock_onto_handlers["get_subclasses"].return_value = [
        {"uri": "http://example.org/Employee", "label": "Employee", "depth": 1},
        {"uri": "http://example.org/Contractor", "label": "Contractor", "depth": 1},
    ]
    mock_onto_handlers["get_class_definition"].return_value = {
        "uri": "http://example.org/Employee", "label": "Employee", "definition": "d", "superclasses": []
    }
    # Employee and Contractor are disjoint
    mock_onto_handlers["get_disjoint_classes"].side_effect = lambda uri: (
        ["http://example.org/Contractor"] if uri == "http://example.org/Employee"
        else ["http://example.org/Employee"] if uri == "http://example.org/Contractor"
        else []
    )
    mock_client.chat.completions.create.return_value = _ContextResponse(
        axes=[_AxisResponse(
            cco_class_uri="http://example.org/Person",
            enumerations=[
                _EnumResponse(class_uri="http://example.org/Employee", class_label="Employee", relevance="high"),
                _EnumResponse(class_uri="http://example.org/Contractor", class_label="Contractor", relevance="low"),
            ],
        )],
    )
    result = contextualize(axes, mock_client, mock_config, mock_onto_handlers)
    enums = result[0].axes[0].enumerations
    assert len(enums) == 1
    assert enums[0].class_uri == "http://example.org/Employee"  # higher relevance kept


def test_contextualize_emits_disjoint_filtered_event(mock_client, mock_config, mock_onto_handlers):
    """Disjointness filtering emits disjoint_filtered event."""
    axes = [_make_axes()]
    mock_onto_handlers["get_subclasses"].return_value = [
        {"uri": "http://example.org/Employee", "label": "Employee", "depth": 1},
        {"uri": "http://example.org/Contractor", "label": "Contractor", "depth": 1},
    ]
    mock_onto_handlers["get_class_definition"].return_value = {
        "uri": "http://example.org/Employee", "label": "Employee", "definition": "d", "superclasses": []
    }
    mock_onto_handlers["get_disjoint_classes"].side_effect = lambda uri: (
        ["http://example.org/Contractor"] if uri == "http://example.org/Employee"
        else ["http://example.org/Employee"] if uri == "http://example.org/Contractor"
        else []
    )
    mock_client.chat.completions.create.return_value = _ContextResponse(
        axes=[_AxisResponse(
            cco_class_uri="http://example.org/Person",
            enumerations=[
                _EnumResponse(class_uri="http://example.org/Employee", class_label="Employee", relevance="high"),
                _EnumResponse(class_uri="http://example.org/Contractor", class_label="Contractor", relevance="low"),
            ],
        )],
    )
    report = RunReport(model="m", policy_set="p", timestamp="t")
    contextualize(axes, mock_client, mock_config, mock_onto_handlers, report=report)
    disjoint_events = [e for e in report.events if e["event"] == "disjoint_filtered"]
    assert len(disjoint_events) == 1
    assert "http://example.org/Contractor" in disjoint_events[0]["filtered"]


def test_contextualize_no_disjoint_filter_when_handler_absent(mock_client, mock_config):
    """Without get_disjoint_classes handler, no filtering occurs."""
    from unittest.mock import MagicMock
    handlers = {
        "search_classes": MagicMock(return_value=[]),
        "get_class_definition": MagicMock(return_value={"uri": "u", "label": "l", "definition": "d", "superclasses": []}),
        "get_subclasses": MagicMock(return_value=[{"uri": "http://example.org/Employee", "label": "Employee", "depth": 1}]),
        "get_superclasses": MagicMock(return_value=[]),
        "get_siblings": MagicMock(return_value=[]),
        "get_properties": MagicMock(return_value=[]),
        "explore_class": MagicMock(return_value=None),
        # No get_disjoint_classes key
    }
    axes = [_make_axes()]
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _ContextResponse(
        axes=[_AxisResponse(
            cco_class_uri="http://example.org/Person",
            enumerations=[
                _EnumResponse(class_uri="http://example.org/Employee", class_label="Employee", relevance="high"),
            ],
        )],
    )
    mock_config_local = MagicMock()
    mock_config_local.model = "test"
    mock_config_local.temperature = 0.0
    mock_config_local.max_retries = 1
    mock_config_local.max_tokens = 500
    result = contextualize(axes, mock_client, mock_config_local, handlers)
    assert len(result[0].axes[0].enumerations) == 1
