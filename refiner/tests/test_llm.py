from unittest.mock import MagicMock, patch
from refiner.llm import LLMConfig, TokenTracker, create_client


def test_config_defaults():
    cfg = LLMConfig(base_url="http://localhost:8000/v1", model="test-model")
    assert cfg.api_key == "none"
    assert cfg.temperature == 0.3
    assert cfg.max_retries == 3

def test_config_custom():
    cfg = LLMConfig(base_url="http://host:9000/v1", model="granite-3.1-8b", api_key="secret", temperature=0.7, max_retries=5)
    assert cfg.base_url == "http://host:9000/v1"
    assert cfg.api_key == "secret"

def test_create_client_returns_instructor_instance(monkeypatch):
    cfg = LLMConfig(base_url="http://localhost:8000/v1", model="test-model")
    client = create_client(cfg)
    assert hasattr(client, "chat")


def test_token_tracker_add():
    tracker = TokenTracker()
    usage = MagicMock(prompt_tokens=100, completion_tokens=50, total_tokens=150)
    tracker.add(usage)
    assert tracker.prompt_tokens == 100
    assert tracker.completion_tokens == 50
    assert tracker.total_tokens == 150
    assert tracker.calls == 1


def test_token_tracker_add_with_stage():
    tracker = TokenTracker()
    usage1 = MagicMock(prompt_tokens=100, completion_tokens=50, total_tokens=150)
    usage2 = MagicMock(prompt_tokens=200, completion_tokens=80, total_tokens=280)
    tracker.add(usage1, stage="classify")
    tracker.add(usage2, stage="anchor")
    assert tracker.total_tokens == 430
    assert tracker.calls == 2
    assert tracker.per_stage["classify"]["total_tokens"] == 150
    assert tracker.per_stage["anchor"]["total_tokens"] == 280


def test_token_tracker_add_none():
    tracker = TokenTracker()
    tracker.add(None)
    assert tracker.calls == 0
    assert tracker.total_tokens == 0


def test_token_tracker_to_dict():
    tracker = TokenTracker()
    usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    tracker.add(usage, stage="classify")
    d = tracker.to_dict()
    assert d["prompt_tokens"] == 10
    assert d["calls"] == 1
    assert "classify" in d["per_stage"]


def test_create_client_with_tracker_wraps_create():
    cfg = LLMConfig(base_url="http://localhost:8000/v1", model="test-model")
    tracker = TokenTracker()

    with patch("refiner.llm.instructor") as mock_instructor:
        mock_client = MagicMock()
        mock_completion = MagicMock()
        mock_completion.usage.prompt_tokens = 100
        mock_completion.usage.completion_tokens = 50
        mock_completion.usage.total_tokens = 150
        mock_model = MagicMock()
        mock_client.chat.completions.create_with_completion.return_value = (mock_model, mock_completion)
        mock_instructor.from_openai.return_value = mock_client
        mock_instructor.Mode.JSON = "json"

        client = create_client(cfg, tracker=tracker)
        result = client.chat.completions.create(model="test", response_model=str, messages=[])

        assert result == mock_model
        assert tracker.prompt_tokens == 100
        assert tracker.completion_tokens == 50
        assert tracker.total_tokens == 150
        assert tracker.calls == 1
