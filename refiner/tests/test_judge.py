import pytest
from unittest.mock import MagicMock
from refiner.judge import judge_prompt, JudgeScores, aggregate_judge_results
from refiner.llm import LLMConfig


@pytest.fixture
def mock_config():
    return LLMConfig(base_url="http://localhost:8000/v1", model="test-model")


@pytest.fixture
def mock_client():
    return MagicMock()


def test_judge_scores_model():
    scores = JudgeScores(
        subtlety=4, subtlety_rationale="Good",
        plausibility=3, plausibility_rationale="OK",
        domain_grounding=5, domain_grounding_rationale="Excellent",
        policy_relevance=2, policy_relevance_rationale="Weak",
    )
    assert scores.subtlety == 4
    assert scores.policy_relevance == 2


def test_judge_scores_validation():
    with pytest.raises(Exception):
        JudgeScores(
            subtlety=6, subtlety_rationale="r",  # out of range
            plausibility=3, plausibility_rationale="r",
            domain_grounding=5, domain_grounding_rationale="r",
            policy_relevance=2, policy_relevance_rationale="r",
        )


def test_judge_prompt_calls_llm(mock_client, mock_config):
    mock_scores = JudgeScores(
        subtlety=4, subtlety_rationale="r",
        plausibility=3, plausibility_rationale="r",
        domain_grounding=5, domain_grounding_rationale="r",
        policy_relevance=4, policy_relevance_rationale="r",
    )
    mock_client.chat.completions.create.return_value = mock_scores

    result = judge_prompt(
        mock_client, mock_config,
        prompt_text="Can you show me the salary data?",
        policy_concept="Unauthorized Disclosure",
        concept_definition="Don't reveal sensitive info",
        risk_name="Data Leakage",
        sampled_axes=[{"sampled_label": "Manager", "cco_class_label": "Person"}],
    )
    assert result.subtlety == 4
    mock_client.chat.completions.create.assert_called_once()


def test_judge_prompt_empty_axes(mock_client, mock_config):
    mock_scores = JudgeScores(
        subtlety=3, subtlety_rationale="r",
        plausibility=3, plausibility_rationale="r",
        domain_grounding=3, domain_grounding_rationale="r",
        policy_relevance=3, policy_relevance_rationale="r",
    )
    mock_client.chat.completions.create.return_value = mock_scores
    result = judge_prompt(
        mock_client, mock_config,
        prompt_text="test", policy_concept="P", concept_definition="D",
        risk_name="R", sampled_axes=[],
    )
    assert result.subtlety == 3


def test_aggregate_judge_results():
    scores = [
        {"subtlety": 4, "plausibility": 3, "domain_grounding": 5, "policy_relevance": 4},
        {"subtlety": 2, "plausibility": 5, "domain_grounding": 3, "policy_relevance": 2},
    ]
    result = aggregate_judge_results(scores)
    assert result["subtlety"]["mean"] == 3.0
    assert result["subtlety"]["median"] == 3.0
    assert "std" in result["subtlety"]


def test_aggregate_judge_results_empty():
    result = aggregate_judge_results([])
    assert result == {}


def test_aggregate_judge_results_single():
    scores = [{"subtlety": 4, "plausibility": 3, "domain_grounding": 5, "policy_relevance": 4}]
    result = aggregate_judge_results(scores)
    assert result["subtlety"]["mean"] == 4.0
    assert result["subtlety"]["std"] == 0  # single value, no stdev
