import logging
from refiner.models import Policy, PolicyClassification
from refiner.stages.classify import classify


def test_classify_returns_classifications(mock_client, mock_config):
    policies = [
        Policy(policy_concept="Fraud", concept_definition="Prompts about fraud"),
        Policy(policy_concept="Executive Compensation", concept_definition="Prompts about exec pay"),
    ]
    mock_client.chat.completions.create.return_value = [
        PolicyClassification(
            policy_concept="Fraud",
            concept_definition="Prompts about fraud",
            policy_type="A",
            justification="Safety concern",
        ),
        PolicyClassification(
            policy_concept="Executive Compensation",
            concept_definition="Prompts about exec pay",
            policy_type="B",
            justification="Confidentiality concern",
        ),
    ]
    result = classify(policies, mock_client, mock_config)
    assert len(result) == 2
    assert result[0].policy_type == "A"
    assert result[1].policy_type == "B"


def test_classify_calls_client_with_correct_params(mock_client, mock_config):
    policies = [Policy(policy_concept="X", concept_definition="Y")]
    mock_client.chat.completions.create.return_value = [
        PolicyClassification(
            policy_concept="X", concept_definition="Y", policy_type="A", justification="j"
        ),
    ]
    classify(policies, mock_client, mock_config)
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "test-model"
    assert call_kwargs["temperature"] == 0.3
    assert "messages" in call_kwargs


def test_classify_empty_policies(mock_client, mock_config):
    result = classify([], mock_client, mock_config)
    assert result == []
    mock_client.chat.completions.create.assert_not_called()


def test_classify_emits_type_distribution(mock_client, mock_config):
    from refiner.models import RunReport
    policies = [
        Policy(policy_concept="Fraud", concept_definition="About fraud"),
        Policy(policy_concept="Violence", concept_definition="About violence"),
        Policy(policy_concept="PII", concept_definition="About PII"),
    ]
    mock_client.chat.completions.create.return_value = [
        PolicyClassification(policy_concept="Fraud", concept_definition="About fraud", policy_type="A", justification="j"),
        PolicyClassification(policy_concept="Violence", concept_definition="About violence", policy_type="A", justification="j"),
        PolicyClassification(policy_concept="PII", concept_definition="About PII", policy_type="B", justification="j"),
    ]
    report = RunReport(model="m", policy_set="p", timestamp="t")
    result = classify(policies, mock_client, mock_config, report=report)
    type_dist_events = [e for e in report.events if e["event"] == "type_distribution"]
    assert len(type_dist_events) == 1
    assert type_dist_events[0]["stage"] == "classify"
    assert type_dist_events[0]["distribution"]["A"] == 2
    assert type_dist_events[0]["distribution"]["B"] == 1


def test_classify_no_report_works(mock_client, mock_config):
    policies = [Policy(policy_concept="X", concept_definition="Y")]
    mock_client.chat.completions.create.return_value = [
        PolicyClassification(policy_concept="X", concept_definition="Y", policy_type="A", justification="j"),
    ]
    # No report param — should work without error
    result = classify(policies, mock_client, mock_config)
    assert len(result) == 1
