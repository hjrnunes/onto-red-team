import pytest
from unittest.mock import MagicMock
from refiner.llm import LLMConfig


@pytest.fixture
def mock_config():
    return LLMConfig(base_url="http://localhost:8000/v1", model="test-model")


@pytest.fixture
def mock_client():
    """Mock Instructor client. Tests set return_value on chat.completions.create."""
    client = MagicMock()
    return client


@pytest.fixture
def mock_risk_handlers():
    """Mock nexus-mcp risk handlers dict."""
    return {
        "search_risks": MagicMock(return_value=[]),
        "get_risk_details": MagicMock(return_value=None),
        "get_related_risks": MagicMock(return_value=[]),
        "get_related_actions": MagicMock(return_value=[]),
        "list_taxonomies": MagicMock(return_value=[]),
        "list_risk_groups": MagicMock(return_value=[]),
        "explore_risk": MagicMock(return_value=None),
        "gap_analysis": MagicMock(return_value={}),
    }


@pytest.fixture
def mock_onto_handlers():
    """Mock ontoquery ontology handlers dict."""
    return {
        "search_classes": MagicMock(return_value=[]),
        "get_class_definition": MagicMock(return_value=None),
        "get_subclasses": MagicMock(return_value=[]),
        "get_superclasses": MagicMock(return_value=[]),
        "get_siblings": MagicMock(return_value=[]),
        "get_properties": MagicMock(return_value=[]),
        "explore_class": MagicMock(return_value=None),
        "get_restrictions": MagicMock(return_value=[]),
        "get_disjoint_classes": MagicMock(return_value=[]),
        "get_equivalent_axioms": MagicMock(return_value=[]),
    }
