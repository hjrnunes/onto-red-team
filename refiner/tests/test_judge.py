import pytest
from unittest.mock import MagicMock
from refiner.judge import (
    judge_prompt,
    JudgeScores,
    aggregate_judge_results,
    UtilityJudgeScores,
    judge_utility_prompt,
    UTILITY_DIMENSIONS,
)
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


def test_utility_judge_scores_model():
    scores = UtilityJudgeScores(
        legitimacy=5, legitimacy_rationale="Clearly acceptable",
        boundary_proximity=4, boundary_proximity_rationale="Close to boundary",
        domain_grounding=5, domain_grounding_rationale="Good terminology",
        policy_relevance=3, policy_relevance_rationale="Relevant",
    )
    assert scores.legitimacy == 5
    assert scores.boundary_proximity == 4


def test_utility_judge_scores_validation():
    with pytest.raises(Exception):
        UtilityJudgeScores(
            legitimacy=6, legitimacy_rationale="r",  # out of range
            boundary_proximity=3, boundary_proximity_rationale="r",
            domain_grounding=5, domain_grounding_rationale="r",
            policy_relevance=2, policy_relevance_rationale="r",
        )


def test_utility_dimensions_tuple():
    assert UTILITY_DIMENSIONS == ("legitimacy", "boundary_proximity", "domain_grounding", "policy_relevance")


def test_judge_utility_prompt_calls_llm(mock_client, mock_config):
    mock_scores = UtilityJudgeScores(
        legitimacy=5, legitimacy_rationale="r",
        boundary_proximity=4, boundary_proximity_rationale="r",
        domain_grounding=4, domain_grounding_rationale="r",
        policy_relevance=3, policy_relevance_rationale="r",
    )
    mock_client.chat.completions.create.return_value = mock_scores

    result = judge_utility_prompt(
        mock_client, mock_config,
        prompt_text="What are the standard drug interaction categories?",
        policy_concept="Clinical Decisions",
        concept_definition="No clinical diagnoses",
        risk_name="Misdiagnosis",
        sampled_axes=[{"sampled_label": "drug interaction", "cco_class_label": "pharmacological process"}],
    )
    assert result.legitimacy == 5
    assert result.boundary_proximity == 4
    mock_client.chat.completions.create.assert_called_once()


def test_aggregate_judge_results_with_utility_dimensions():
    scores = [
        {"legitimacy": 5, "boundary_proximity": 4, "domain_grounding": 5, "policy_relevance": 3},
        {"legitimacy": 4, "boundary_proximity": 3, "domain_grounding": 4, "policy_relevance": 4},
    ]
    result = aggregate_judge_results(scores, dimensions=UTILITY_DIMENSIONS)
    assert "legitimacy" in result
    assert "boundary_proximity" in result
    assert result["legitimacy"]["mean"] == 4.5


def test_aggregate_judge_results_default_dimensions_unchanged():
    scores = [
        {"subtlety": 4, "plausibility": 3, "domain_grounding": 5, "policy_relevance": 4},
    ]
    result = aggregate_judge_results(scores)
    assert "subtlety" in result
    assert "legitimacy" not in result
