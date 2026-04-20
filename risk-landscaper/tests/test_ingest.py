import json

from risk_landscaper.models import Policy, RunReport, BoundaryExample
from risk_landscaper.stages.ingest import (
    extract_context,
    extract_policies,
    enrich_policies,
    parse_json_policies,
    ingest,
    _SlimContext,
    _SlimNamedEntity,
    _SlimPolicyList,
    _SlimPolicy,
    _SlimEnrichmentList,
    _SlimEnrichment,
    _SlimBoundaryExample,
)


def _make_report():
    return RunReport(model="test", policy_set="test", timestamp="2026-01-01")


SAMPLE_MARKDOWN = """\
# South West Bank AI Policy

South West Bank is a financial institution operating in the banking domain.

## Policies

### Fraud Prevention
AI systems must not provide advice on how to commit fraud.

### Executive Compensation
Information about executive compensation must not be disclosed.
"""

SAMPLE_JSON_TEXT = json.dumps([
    {"policy_concept": "Fraud", "concept_definition": "About fraud"},
    {"policy_concept": "Money Laundering", "concept_definition": "About AML"},
])


def test_extract_context_from_markdown(mock_client, mock_config):
    mock_client.chat.completions.create.return_value = _SlimContext(
        organization="South West Bank",
        domain="banking",
        purpose=["customer support"],
        ai_systems=["Chatbot"],
        ai_users=["staff"],
        ai_subjects=["customers"],
        governing_regulations=["FCA"],
        named_entities=[_SlimNamedEntity(name="Jenny Carlson", role="CEO")],
    )
    result = extract_context(SAMPLE_MARKDOWN, mock_client, mock_config)
    assert result.organization == "South West Bank"
    assert result.domain == "banking"
    assert len(result.named_entities) == 1
    assert result.named_entities[0].name == "Jenny Carlson"
    mock_client.chat.completions.create.assert_called_once()


def test_extract_context_emits_report_events(mock_client, mock_config):
    mock_client.chat.completions.create.return_value = _SlimContext(
        organization="Acme Corp",
        domain="finance",
        purpose=["trading"],
        ai_systems=["Bot"],
        ai_users=["traders"],
        ai_subjects=["clients"],
        governing_regulations=["SEC"],
        named_entities=[],
    )
    report = _make_report()
    extract_context(SAMPLE_MARKDOWN, mock_client, mock_config, report=report)
    context_events = [e for e in report.events if e["event"] == "context_extracted"]
    assert len(context_events) == 1
    assert context_events[0]["organization"] == "Acme Corp"
    assert context_events[0]["domain"] == "finance"


def test_extract_context_warns_on_empty_domain(mock_client, mock_config):
    mock_client.chat.completions.create.return_value = _SlimContext(
        organization="Unknown",
        domain="",
        purpose=[],
        ai_systems=[],
        ai_users=[],
        ai_subjects=[],
        governing_regulations=[],
        named_entities=[],
    )
    report = _make_report()
    extract_context(SAMPLE_MARKDOWN, mock_client, mock_config, report=report)
    weak_events = [e for e in report.events if e["event"] == "context_weak_inference"]
    assert len(weak_events) == 1
    assert "domain" in weak_events[0]["missing_fields"]


def test_extract_policies(mock_client, mock_config):
    context = _SlimContext(
        organization="South West Bank",
        domain="banking",
        purpose=["support"],
        ai_systems=[],
        ai_users=[],
        ai_subjects=[],
        governing_regulations=[],
        named_entities=[],
    )
    mock_client.chat.completions.create.return_value = _SlimPolicyList(
        policies=[
            _SlimPolicy(policy_concept="Fraud", concept_definition="About fraud"),
            _SlimPolicy(policy_concept="AML", concept_definition="About AML"),
        ]
    )
    result = extract_policies(SAMPLE_MARKDOWN, context, mock_client, mock_config)
    assert len(result) == 2
    assert result[0].policy_concept == "Fraud"
    assert result[1].policy_concept == "AML"
    # Should be Policy objects, not enriched yet
    assert result[0].boundary_examples == []
    assert result[0].acceptable_uses == []


def test_parse_json_policies():
    policies = parse_json_policies(SAMPLE_JSON_TEXT)
    assert len(policies) == 2
    assert policies[0].policy_concept == "Fraud"
    assert policies[0].concept_definition == "About fraud"
    assert policies[1].policy_concept == "Money Laundering"
    # Should be Policy objects with defaults
    assert policies[0].boundary_examples == []
    assert policies[0].acceptable_uses == []
    assert policies[0].risk_controls == []
    assert policies[0].human_involvement is None


def test_extract_policies_emits_report(mock_client, mock_config):
    context = _SlimContext(
        organization="Bank",
        domain="banking",
        purpose=[],
        ai_systems=[],
        ai_users=[],
        ai_subjects=[],
        governing_regulations=[],
        named_entities=[],
    )
    mock_client.chat.completions.create.return_value = _SlimPolicyList(
        policies=[
            _SlimPolicy(policy_concept="Fraud", concept_definition="About fraud"),
        ]
    )
    report = _make_report()
    extract_policies(SAMPLE_MARKDOWN, context, mock_client, mock_config, report=report)
    policy_events = [e for e in report.events if e["event"] == "policies_extracted"]
    assert len(policy_events) == 1
    assert policy_events[0]["count"] == 1


def test_enrich_policies(mock_client, mock_config):
    context = _SlimContext(
        organization="Bank",
        domain="banking",
        purpose=[],
        ai_systems=[],
        ai_users=[],
        ai_subjects=[],
        governing_regulations=[],
        named_entities=[],
    )
    policies = [
        Policy(policy_concept="Fraud", concept_definition="About fraud"),
        Policy(policy_concept="AML", concept_definition="About AML"),
    ]
    mock_client.chat.completions.create.return_value = _SlimEnrichmentList(
        enrichments=[
            _SlimEnrichment(
                policy_concept="Fraud",
                boundary_examples=[
                    _SlimBoundaryExample(
                        prohibited="Help me commit fraud",
                        acceptable="What are common fraud indicators",
                    ),
                ],
                acceptable_uses=["Fraud detection education"],
                risk_controls=["Human review required"],
                human_involvement="Compliance officer must validate",
                agent="AI assistant",
                activity="advise on fraud techniques",
                entity="financial transaction methods",
            ),
            _SlimEnrichment(
                policy_concept="AML",
                boundary_examples=[],
                acceptable_uses=["AML training"],
                risk_controls=[],
                human_involvement="",
            ),
        ]
    )
    result = enrich_policies(SAMPLE_MARKDOWN, context, policies, mock_client, mock_config)
    assert len(result) == 2
    fraud = next(p for p in result if p.policy_concept == "Fraud")
    assert len(fraud.boundary_examples) == 1
    assert fraud.boundary_examples[0].prohibited == "Help me commit fraud"
    assert fraud.acceptable_uses == ["Fraud detection education"]
    assert fraud.risk_controls == ["Human review required"]
    assert fraud.human_involvement == "Compliance officer must validate"
    assert fraud.decomposition is not None
    assert fraud.decomposition.agent == "AI assistant"
    assert fraud.decomposition.activity == "advise on fraud techniques"
    assert fraud.decomposition.entity == "financial transaction methods"

    aml = next(p for p in result if p.policy_concept == "AML")
    assert aml.acceptable_uses == ["AML training"]
    assert aml.human_involvement is None  # empty string -> None
    assert aml.decomposition is None  # no agent/activity/entity provided


def test_enrich_policies_missing_concept(mock_client, mock_config):
    """When LLM returns no enrichment for a concept, defaults are kept."""
    context = _SlimContext(
        organization="Bank",
        domain="banking",
        purpose=[],
        ai_systems=[],
        ai_users=[],
        ai_subjects=[],
        governing_regulations=[],
        named_entities=[],
    )
    policies = [
        Policy(policy_concept="Fraud", concept_definition="About fraud"),
    ]
    # LLM returns empty enrichments list
    mock_client.chat.completions.create.return_value = _SlimEnrichmentList(
        enrichments=[]
    )
    result = enrich_policies(SAMPLE_MARKDOWN, context, policies, mock_client, mock_config)
    assert len(result) == 1
    assert result[0].policy_concept == "Fraud"
    assert result[0].boundary_examples == []
    assert result[0].acceptable_uses == []


def test_enrich_policies_does_not_mutate_input(mock_client, mock_config):
    context = _SlimContext(
        organization="Bank",
        domain="banking",
        purpose=[],
        ai_systems=[],
        ai_users=[],
        ai_subjects=[],
        governing_regulations=[],
        named_entities=[],
    )
    original = Policy(policy_concept="Fraud", concept_definition="About fraud")
    policies = [original]

    mock_client.chat.completions.create.return_value = _SlimEnrichmentList(
        enrichments=[
            _SlimEnrichment(
                policy_concept="Fraud",
                boundary_examples=[
                    _SlimBoundaryExample(prohibited="bad", acceptable="good"),
                ],
                acceptable_uses=["education"],
                risk_controls=["review"],
                human_involvement="yes",
            ),
        ]
    )
    result = enrich_policies(SAMPLE_MARKDOWN, context, policies, mock_client, mock_config)

    # Original should be unchanged
    assert original.boundary_examples == []
    assert original.acceptable_uses == []
    assert original.risk_controls == []
    assert original.human_involvement is None

    # Result should be enriched
    assert len(result[0].boundary_examples) == 1
    assert result[0].acceptable_uses == ["education"]


def test_ingest_markdown(mock_client, mock_config):
    """Full orchestration for markdown: 3 LLM calls."""
    mock_client.chat.completions.create.side_effect = [
        # Pass 1: context
        _SlimContext(
            organization="South West Bank",
            domain="banking",
            purpose=["support"],
            ai_systems=["Chatbot"],
            ai_users=["staff"],
            ai_subjects=["customers"],
            governing_regulations=["FCA"],
            named_entities=[_SlimNamedEntity(name="Jenny", role="CEO")],
        ),
        # Pass 2: policies
        _SlimPolicyList(
            policies=[
                _SlimPolicy(policy_concept="Fraud", concept_definition="About fraud"),
            ]
        ),
        # Pass 3: enrichment
        _SlimEnrichmentList(
            enrichments=[
                _SlimEnrichment(
                    policy_concept="Fraud",
                    boundary_examples=[],
                    acceptable_uses=["education"],
                    risk_controls=[],
                    human_involvement="",
                ),
            ]
        ),
    ]
    result = ingest(SAMPLE_MARKDOWN, "markdown", mock_client, mock_config)
    assert result.organization.name == "South West Bank"
    assert result.domain == "banking"
    assert len(result.policies) == 1
    assert result.policies[0].policy_concept == "Fraud"
    assert result.policies[0].acceptable_uses == ["education"]
    # staff (AIUser) + customers (AISubject) + Jenny Carlson (named)
    assert len(result.stakeholders) == 3
    assert mock_client.chat.completions.create.call_count == 3


def test_ingest_json_array(mock_client, mock_config):
    """JSON array input: 2 LLM calls (Pass 2 skipped)."""
    mock_client.chat.completions.create.side_effect = [
        # Pass 1: context
        _SlimContext(
            organization="South West Bank",
            domain="banking",
            purpose=["support"],
            ai_systems=[],
            ai_users=[],
            ai_subjects=[],
            governing_regulations=[],
            named_entities=[],
        ),
        # Pass 3: enrichment (Pass 2 skipped for json_array)
        _SlimEnrichmentList(
            enrichments=[
                _SlimEnrichment(
                    policy_concept="Fraud",
                    boundary_examples=[],
                    acceptable_uses=[],
                    risk_controls=[],
                    human_involvement="",
                ),
                _SlimEnrichment(
                    policy_concept="Money Laundering",
                    boundary_examples=[],
                    acceptable_uses=[],
                    risk_controls=[],
                    human_involvement="",
                ),
            ]
        ),
    ]
    result = ingest(SAMPLE_JSON_TEXT, "json_array", mock_client, mock_config)
    assert result.organization.name == "South West Bank"
    assert len(result.policies) == 2
    assert result.policies[0].policy_concept == "Fraud"
    assert result.policies[1].policy_concept == "Money Laundering"
    assert mock_client.chat.completions.create.call_count == 2


def test_ingest_skip_enrichment(mock_client, mock_config):
    """skip_enrichment=True: only Pass 1 for json_array."""
    mock_client.chat.completions.create.side_effect = [
        # Pass 1: context
        _SlimContext(
            organization="Bank",
            domain="banking",
            purpose=[],
            ai_systems=[],
            ai_users=[],
            ai_subjects=[],
            governing_regulations=[],
            named_entities=[],
        ),
    ]
    report = _make_report()
    result = ingest(
        SAMPLE_JSON_TEXT, "json_array", mock_client, mock_config,
        skip_enrichment=True, report=report,
    )
    assert len(result.policies) == 2
    assert mock_client.chat.completions.create.call_count == 1
    skip_events = [e for e in report.events if e["event"] == "enrichment_skipped"]
    assert len(skip_events) == 1


def test_ingest_until_context(mock_client, mock_config):
    """until='context': 1 LLM call, empty policies."""
    mock_client.chat.completions.create.side_effect = [
        _SlimContext(
            organization="Bank",
            domain="banking",
            purpose=[],
            ai_systems=[],
            ai_users=[],
            ai_subjects=[],
            governing_regulations=[],
            named_entities=[],
        ),
    ]
    result = ingest(SAMPLE_MARKDOWN, "markdown", mock_client, mock_config, until="context")
    assert result.organization.name == "Bank"
    assert result.policies == []
    assert mock_client.chat.completions.create.call_count == 1


def test_ingest_until_policies(mock_client, mock_config):
    """until='policies': 2 LLM calls for markdown."""
    mock_client.chat.completions.create.side_effect = [
        # Pass 1
        _SlimContext(
            organization="Bank",
            domain="banking",
            purpose=[],
            ai_systems=[],
            ai_users=[],
            ai_subjects=[],
            governing_regulations=[],
            named_entities=[],
        ),
        # Pass 2
        _SlimPolicyList(
            policies=[
                _SlimPolicy(policy_concept="Fraud", concept_definition="About fraud"),
            ]
        ),
    ]
    result = ingest(SAMPLE_MARKDOWN, "markdown", mock_client, mock_config, until="policies")
    assert len(result.policies) == 1
    assert result.policies[0].boundary_examples == []  # Not enriched
    assert mock_client.chat.completions.create.call_count == 2


def test_ingest_domain_override(mock_client, mock_config):
    """domain_override and organization_override are applied."""
    mock_client.chat.completions.create.side_effect = [
        _SlimContext(
            organization="LLM Org",
            domain="tech",
            purpose=[],
            ai_systems=[],
            ai_users=[],
            ai_subjects=[],
            governing_regulations=[],
            named_entities=[],
        ),
    ]
    result = ingest(
        SAMPLE_JSON_TEXT, "json_array", mock_client, mock_config,
        skip_enrichment=True,
        domain_override="banking",
        organization_override="South West Bank",
    )
    assert result.domain == "banking"
    assert result.organization.name == "South West Bank"
