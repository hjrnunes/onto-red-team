from refiner.models import Policy
from refiner.stages.identify_domains import (
    identify_domains,
    derive_source_ontology,
    _DomainSelection,
    ALWAYS_INCLUDED,
)


def _make_policies():
    return [
        Policy(
            policy_concept="Fraud", concept_definition="Fraudulent financial activity",
        ),
        Policy(
            policy_concept="Executive Compensation", concept_definition="Salary info for execs",
        ),
    ]


def test_identify_domains_returns_selected_domains(mock_client, mock_config):
    policies = _make_policies()
    mock_client.chat.completions.create.return_value = _DomainSelection(
        domains=["FIBO"],
        justification="Banking client",
    )
    result = identify_domains(policies, mock_client, mock_config)
    assert "FIBO" in result
    assert "CCO" in result
    assert "Commons" in result
    assert "D3FEND" in result
    assert "CSO" in result
    assert "OBO" not in result


def test_identify_domains_filters_invalid_keys(mock_client, mock_config):
    policies = _make_policies()
    mock_client.chat.completions.create.return_value = _DomainSelection(
        domains=["FIBO", "HALLUCINATED"],
        justification="test",
    )
    result = identify_domains(policies, mock_client, mock_config)
    assert "FIBO" in result
    assert "HALLUCINATED" not in result


def test_identify_domains_empty_policies(mock_client, mock_config):
    result = identify_domains([], mock_client, mock_config)
    assert result == list(ALWAYS_INCLUDED)


def test_derive_source_ontology():
    assert derive_source_ontology("https://www.commoncoreontologies.org/ont00000123") == "CCO"
    assert derive_source_ontology("https://spec.edmcouncil.org/fibo/ontology/FND/Foo") == "FIBO"
    assert derive_source_ontology("https://www.omg.org/spec/Commons/Parties") == "Commons"
    assert derive_source_ontology("http://purl.obolibrary.org/obo/MONDO_0001234") == "OBO"
    assert derive_source_ontology("https://www.industrialontologies.org/ont/core") == "IOF"
    assert derive_source_ontology("http://d3fend.mitre.org/ontologies/d3fend.owl#Phishing") == "D3FEND"
    assert derive_source_ontology("http://taxonomy-refiner.io/ontologies/cso#RacialHate") == "CSO"
    assert derive_source_ontology("http://example.org/Unknown") == "unknown"


def test_identify_domains_emits_selected_domains(mock_client, mock_config):
    from refiner.models import RunReport
    policies = _make_policies()
    mock_client.chat.completions.create.return_value = _DomainSelection(
        domains=["FIBO"], justification="Banking client",
    )
    report = RunReport(model="m", policy_set="p", timestamp="t")
    result = identify_domains(policies, mock_client, mock_config, report=report)
    selected_events = [e for e in report.events if e["event"] == "selected_domains"]
    assert len(selected_events) == 1
    assert "FIBO" in selected_events[0]["domains"]
    assert "CCO" in selected_events[0]["domains"]


def test_identify_domains_emits_invalid_domain_key(mock_client, mock_config):
    from refiner.models import RunReport
    policies = _make_policies()
    mock_client.chat.completions.create.return_value = _DomainSelection(
        domains=["FIBO", "BOGUS"], justification="test",
    )
    report = RunReport(model="m", policy_set="p", timestamp="t")
    result = identify_domains(policies, mock_client, mock_config, report=report)
    invalid_events = [e for e in report.events if e["event"] == "invalid_domain_key"]
    assert len(invalid_events) == 1
    assert invalid_events[0]["raw_key"] == "BOGUS"


def test_identify_domains_no_report_works(mock_client, mock_config):
    policies = _make_policies()
    mock_client.chat.completions.create.return_value = _DomainSelection(
        domains=["FIBO"], justification="j",
    )
    result = identify_domains(policies, mock_client, mock_config)
    assert "FIBO" in result
