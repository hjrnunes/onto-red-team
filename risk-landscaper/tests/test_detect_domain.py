from unittest.mock import MagicMock
from risk_landscaper.models import Policy, PolicyProfile, RunReport
from risk_landscaper.stages.detect_domain import (
    detect_domain,
    normalize_domain,
    DOMAIN_MENU,
    _DomainDetection,
)


def _make_report():
    return RunReport(model="test", policy_set="test", timestamp="2026-01-01")


def test_normalize_domain_exact_match():
    assert normalize_domain("healthcare") == "healthcare"
    assert normalize_domain("financial_services") == "financial_services"


def test_normalize_domain_case_insensitive():
    assert normalize_domain("Healthcare") == "healthcare"
    assert normalize_domain("ENERGY") == "energy"


def test_normalize_domain_partial_match():
    assert normalize_domain("banking and finance") == "financial_services"
    assert normalize_domain("medical") == "healthcare"


def test_normalize_domain_unknown():
    assert normalize_domain("underwater basket weaving") == "general"


def test_detect_domain_uses_profile_domain_when_set():
    profile = PolicyProfile(
        domain="healthcare",
        policies=[Policy(policy_concept="Test", concept_definition="Test def")],
    )
    client = MagicMock()
    from risk_landscaper.llm import LLMConfig
    config = LLMConfig(base_url="http://localhost:8000/v1", model="test")
    result = detect_domain(profile, client, config)
    assert result == ["healthcare"]
    client.chat.completions.create.assert_not_called()


def test_detect_domain_calls_llm_when_no_domain(mock_client, mock_config):
    profile = PolicyProfile(
        policies=[Policy(policy_concept="Fraud", concept_definition="Do not assist with fraud")],
    )
    mock_client.chat.completions.create.return_value = _DomainDetection(domain="financial_services")
    result = detect_domain(profile, mock_client, mock_config)
    assert result == ["financial_services"]
    mock_client.chat.completions.create.assert_called_once()


def test_detect_domain_normalizes_llm_output(mock_client, mock_config):
    profile = PolicyProfile(
        policies=[Policy(policy_concept="Treatment", concept_definition="Medical treatment policy")],
    )
    mock_client.chat.completions.create.return_value = _DomainDetection(domain="Healthcare")
    result = detect_domain(profile, mock_client, mock_config)
    assert result == ["healthcare"]


def test_detect_domain_falls_back_to_general(mock_client, mock_config):
    profile = PolicyProfile(
        policies=[Policy(policy_concept="Test", concept_definition="Test")],
    )
    mock_client.chat.completions.create.return_value = _DomainDetection(domain="underwater_basketry")
    result = detect_domain(profile, mock_client, mock_config)
    assert result == ["general"]


def test_detect_domain_emits_report_events(mock_client, mock_config):
    profile = PolicyProfile(
        domain="energy",
        policies=[Policy(policy_concept="Test", concept_definition="Test")],
    )
    report = _make_report()
    detect_domain(profile, mock_client, mock_config, report=report)
    events = [e for e in report.events if e["event"] == "domain_detected"]
    assert len(events) == 1
    assert events[0]["domain"] == "energy"
    assert events[0]["source"] == "profile"
