"""Tests for hybrid ontology + LLM enumeration in contextualize."""
import pytest
from unittest.mock import MagicMock, patch
from refiner.models import (
    RiskVariationAxes, VariationAxis, AxisEnumeration,
)
from refiner.llm import LLMConfig
from refiner.stages.contextualize import (
    contextualize, _Variation, _ContextResponse, _collect_ontology_enumerations,
)


class TestCollectOntologyEnumerations:
    def _make_handlers(self, subclasses=None, siblings=None, definitions=None):
        defn_map = definitions or {}
        return {
            "get_subclasses": MagicMock(return_value=subclasses or []),
            "get_siblings": MagicMock(return_value=siblings or []),
            "get_class_definition": MagicMock(
                side_effect=lambda uri: defn_map.get(uri, {"label": uri.rsplit("/", 1)[-1]})
            ),
        }

    def test_subclasses_become_enumerations(self):
        handlers = self._make_handlers(
            subclasses=[
                {"uri": "http://ex.org/Sub1", "label": "Sub One", "depth": 1},
                {"uri": "http://ex.org/Sub2", "label": "Sub Two", "depth": 1},
            ],
            definitions={
                "http://ex.org/Sub1": {"label": "Sub One"},
                "http://ex.org/Sub2": {"label": "Sub Two"},
            },
        )
        result = _collect_ontology_enumerations("http://ex.org/Parent", handlers, selected_domains=None)
        assert len(result) == 2
        assert result[0].class_uri == "http://ex.org/Sub1"
        assert result[0].class_label == "Sub One"
        assert result[0].provenance == "subclass"
        assert result[0].relevance == "high"
        assert result[0].source_ontology != "generated"

    def test_sibling_fallback_for_leaf_nodes(self):
        handlers = self._make_handlers(
            subclasses=[],
            siblings=[
                {"uri": "http://ex.org/InsuranceFraud", "label": "Insurance Fraud"},
                {"uri": "http://ex.org/InvestmentFraud", "label": "Investment Fraud"},
                {"uri": "http://ex.org/Fraud", "label": "Fraud"},
            ],
            definitions={
                "http://ex.org/Fraud": {"label": "Fraud"},
                "http://ex.org/InsuranceFraud": {"label": "Insurance Fraud"},
                "http://ex.org/InvestmentFraud": {"label": "Investment Fraud"},
            },
        )
        result = _collect_ontology_enumerations("http://ex.org/Fraud", handlers, selected_domains=None)
        assert len(result) == 2
        assert all(e.provenance == "sibling" for e in result)
        assert all(e.relevance == "medium" for e in result)
        assert all(e.class_uri != "http://ex.org/Fraud" for e in result)

    def test_caps_at_max_enumerations(self):
        subclasses = [{"uri": f"http://ex.org/Sub{i}", "label": f"Sub {i}", "depth": 1} for i in range(20)]
        handlers = self._make_handlers(subclasses=subclasses)
        result = _collect_ontology_enumerations("http://ex.org/Parent", handlers, selected_domains=None, max_enumerations=5)
        assert len(result) == 5

    def test_filters_invalid_definitions(self):
        handlers = self._make_handlers(subclasses=[
            {"uri": "http://ex.org/Valid", "label": "Valid", "depth": 1},
            {"uri": "http://ex.org/Invalid", "label": "Invalid", "depth": 1},
        ])
        handlers["get_class_definition"] = MagicMock(
            side_effect=lambda uri: {"label": "Valid"} if "Valid" in uri else None,
        )
        result = _collect_ontology_enumerations("http://ex.org/Parent", handlers, selected_domains=None)
        assert len(result) == 1
        assert result[0].class_uri == "http://ex.org/Valid"

    @patch("refiner.stages.contextualize.derive_source_ontology")
    def test_domain_filtering(self, mock_derive):
        mock_derive.side_effect = lambda uri: "FIBO" if "fibo" in uri else "OBO"
        handlers = self._make_handlers(subclasses=[
            {"uri": "http://fibo.org/LendingOfficer", "label": "Lending Officer", "depth": 1},
            {"uri": "http://obo.org/Patient", "label": "Patient", "depth": 1},
        ])
        result = _collect_ontology_enumerations("http://ex.org/Parent", handlers, selected_domains=["OBO"])
        assert len(result) == 1
        assert result[0].class_uri == "http://obo.org/Patient"
        assert result[0].source_ontology == "OBO"

    def test_cco_military_person_uris_blocked(self):
        from refiner.stages.contextualize import _CCO_MILITARY_PERSON_URIS
        handlers = self._make_handlers(
            subclasses=[
                {"uri": "https://www.commoncoreontologies.org/ont00000860", "label": "Allied Person", "depth": 1},
                {"uri": "https://www.commoncoreontologies.org/ont00000697", "label": "Enemy Person", "depth": 1},
                {"uri": "http://ex.org/ValidSub", "label": "Valid Sub", "depth": 1},
            ],
            definitions={
                "https://www.commoncoreontologies.org/ont00000860": {"label": "Allied Person"},
                "https://www.commoncoreontologies.org/ont00000697": {"label": "Enemy Person"},
                "http://ex.org/ValidSub": {"label": "Valid Sub"},
            },
        )
        result = _collect_ontology_enumerations(
            "https://www.commoncoreontologies.org/ont00001262", handlers, selected_domains=None,
        )
        assert len(result) == 1
        assert result[0].class_uri == "http://ex.org/ValidSub"

    def test_sibling_relevance_filters_unrelated(self):
        handlers = self._make_handlers(
            subclasses=[],
            siblings=[
                {"uri": "http://ex.org/Treaty", "label": "Treaty"},
                {"uri": "http://ex.org/Decree", "label": "Decree"},
                {"uri": "http://ex.org/ConductGuideline", "label": "Conduct Guideline"},
                {"uri": "http://ex.org/CodeOfConduct", "label": "Code of Conduct"},
            ],
            definitions={
                "http://ex.org/CodeOfConduct": {"label": "Code of Conduct"},
                "http://ex.org/Treaty": {"label": "Treaty"},
                "http://ex.org/Decree": {"label": "Decree"},
                "http://ex.org/ConductGuideline": {"label": "Conduct Guideline"},
            },
        )
        result = _collect_ontology_enumerations(
            "http://ex.org/CodeOfConduct", handlers, selected_domains=None,
        )
        assert len(result) == 1
        assert result[0].class_label == "Conduct Guideline"

    def test_sibling_relevance_passes_when_axis_label_empty(self):
        handlers = self._make_handlers(
            subclasses=[],
            siblings=[
                {"uri": "http://ex.org/Sib1", "label": "Sib One"},
            ],
            definitions={
                "http://ex.org/Unknown": None,
                "http://ex.org/Sib1": {"label": "Sib One"},
            },
        )
        result = _collect_ontology_enumerations(
            "http://ex.org/Unknown", handlers, selected_domains=None,
        )
        assert len(result) == 1

    def test_empty_ontology_returns_empty(self):
        handlers = self._make_handlers(subclasses=[], siblings=[])
        result = _collect_ontology_enumerations("http://ex.org/Isolated", handlers, selected_domains=None)
        assert result == []


class TestHybridEnumerations:
    def _make_rva(self, risk_id="r1", axis_uri="http://ex.org/Axis1", axis_label="Axis One"):
        return RiskVariationAxes(
            risk_id=risk_id, risk_name="Test Risk", policy_concept="Test Policy",
            axes=[VariationAxis(cco_class_uri=axis_uri, cco_class_label=axis_label, rationale="test rationale")],
        )

    def test_rich_ontology_skips_llm(self):
        subclasses = [{"uri": f"http://ex.org/Sub{i}", "label": f"Sub {i}", "depth": 1} for i in range(10)]
        handlers = {
            "get_subclasses": MagicMock(return_value=subclasses),
            "get_siblings": MagicMock(return_value=[]),
            "get_class_definition": MagicMock(side_effect=lambda uri: {"label": uri.rsplit("/", 1)[-1]}),
        }
        mock_client = MagicMock()
        result = contextualize(
            [self._make_rva()], mock_client, LLMConfig(base_url="http://test", model="test"),
            handlers, enumerations_per_axis=8,
        )
        mock_client.chat.completions.create.assert_not_called()
        axes = result.policy_contexts[0].risk_groundings[0].axes
        assert len(axes) == 1
        assert all(e.provenance in ("subclass", "sibling") for e in axes[0].enumerations)

    def test_sparse_ontology_supplements_with_llm(self):
        handlers = {
            "get_subclasses": MagicMock(return_value=[{"uri": "http://ex.org/Sub1", "label": "Sub One", "depth": 1}]),
            "get_siblings": MagicMock(return_value=[]),
            "get_class_definition": MagicMock(side_effect=lambda uri: {"label": uri.rsplit("/", 1)[-1]}),
        }
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _ContextResponse(
            variations=[_Variation(instance="LLM Value 1", relevance="high"), _Variation(instance="LLM Value 2", relevance="high")]
        )
        result = contextualize(
            [self._make_rva()], mock_client, LLMConfig(base_url="http://test", model="test"),
            handlers, enumerations_per_axis=3,
        )
        axes = result.policy_contexts[0].risk_groundings[0].axes
        enums = axes[0].enumerations
        onto_enums = [e for e in enums if e.provenance != "generated"]
        llm_enums = [e for e in enums if e.provenance == "generated"]
        assert len(onto_enums) == 1
        assert len(llm_enums) == 2

    def test_empty_ontology_uses_full_llm(self):
        handlers = {
            "get_subclasses": MagicMock(return_value=[]),
            "get_siblings": MagicMock(return_value=[]),
            "get_class_definition": MagicMock(return_value={"label": "Test"}),
        }
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _ContextResponse(
            variations=[_Variation(instance=f"Val {i}", relevance="high") for i in range(5)]
        )
        result = contextualize(
            [self._make_rva()], mock_client, LLMConfig(base_url="http://test", model="test"),
            handlers, enumerations_per_axis=5,
        )
        axes = result.policy_contexts[0].risk_groundings[0].axes
        assert all(e.provenance == "generated" for e in axes[0].enumerations)
        assert all(e.generated_by == "test" for e in axes[0].enumerations)

    def test_axis_groups_propagated(self):
        handlers = {
            "get_subclasses": MagicMock(return_value=[]),
            "get_siblings": MagicMock(return_value=[]),
            "get_class_definition": MagicMock(return_value={"label": "Test"}),
        }
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _ContextResponse(
            variations=[_Variation(instance="V", relevance="high")]
        )
        rva = RiskVariationAxes(
            risk_id="r1", risk_name="R", policy_concept="P",
            axes=[
                VariationAxis(cco_class_uri="http://ex.org/A", cco_class_label="A", rationale="r"),
                VariationAxis(cco_class_uri="http://ex.org/B", cco_class_label="B", rationale="r"),
            ],
            axis_groups=[["http://ex.org/A", "http://ex.org/B"]],
        )
        result = contextualize(
            [rva], mock_client, LLMConfig(base_url="http://test", model="test"), handlers,
        )
        grounding = result.policy_contexts[0].risk_groundings[0]
        assert grounding.axis_groups == [["http://ex.org/A", "http://ex.org/B"]]
