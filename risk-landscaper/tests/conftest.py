import pytest
from unittest.mock import MagicMock
from risk_landscaper.llm import LLMConfig


@pytest.fixture
def mock_config():
    return LLMConfig(base_url="http://localhost:8000/v1", model="test-model")


@pytest.fixture
def mock_client():
    client = MagicMock()
    return client


@pytest.fixture
def mock_risk_handlers():
    return {
        "search_risks": MagicMock(return_value=[]),
        "get_risk_details": MagicMock(return_value=None),
        "get_related_risks": MagicMock(return_value=[]),
        "get_related_actions": MagicMock(return_value=[]),
    }
