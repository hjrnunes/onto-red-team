from refiner.models import (
    RiskVariationAxes,
    VariationAxis,
    DomainContextProfile,
    DomainContextAxis,
    AxisEnumeration,
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
                role="agent",
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
    assert result[0].axes[0].role == "agent"
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


def test_contextualize_empty_axes(mock_client, mock_config, mock_onto_handlers):
    result = contextualize([], mock_client, mock_config, mock_onto_handlers)
    assert result == []
