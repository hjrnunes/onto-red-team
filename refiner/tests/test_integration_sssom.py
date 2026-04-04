"""End-to-end integration test for the SSSOM-based pipeline."""
import pytest
from pathlib import Path
from unittest.mock import MagicMock
from refiner.ontology_seeds import SSSOMIndex


@pytest.fixture
def real_layer1():
    path = Path(__file__).parent.parent / "data" / "risk-to-vocabulary.sssom.tsv"
    if not path.exists():
        pytest.skip("SSSOM seed files not found")
    return SSSOMIndex.from_tsv(path)


@pytest.fixture
def real_layer2():
    path = Path(__file__).parent.parent / "data" / "vocabulary-to-ontology.sssom.tsv"
    if not path.exists():
        pytest.skip("SSSOM seed files not found")
    return SSSOMIndex.from_tsv(path)


def test_real_sssom_files_load(real_layer1, real_layer2):
    """Verify the actual SSSOM seed files parse correctly."""
    assert len(real_layer1.mappings) > 0
    assert len(real_layer2.mappings) > 0
    # All layer1 subjects should be RiskGroup or Risk IDs
    for m in real_layer1.mappings:
        assert m.subject_id.startswith("ibm-risk-atlas")
    # All layer2 subjects should be AIRO/DPV concepts or direct fallbacks
    for m in real_layer2.mappings:
        prefix = m.subject_id.split(":")[0]
        assert prefix in (
            "pd", "eu-aiact", "eu-rights", "risk", "justifications",
            "sector-finance", "sector-health", "sector-law",
        ) or m.subject_id.startswith("ibm-risk-atlas")


def test_privacy_risk_resolves_seeds(real_layer1, real_layer2):
    """Privacy RiskGroup should resolve to biometric/person ontology branches."""
    from refiner.ontology_seeds import resolve_seeds
    mock_nexus = {
        "get_risk_details": MagicMock(return_value={"group": "ibm-risk-atlas-privacy"}),
        "get_related_risks": MagicMock(return_value=[]),
    }
    vocab_ctx, onto_seeds = resolve_seeds(
        risk_id="atlas-test-privacy-risk",
        risk_group_id="ibm-risk-atlas-privacy",
        nexus_handlers=mock_nexus,
        layer1_mappings=real_layer1,
        layer2_mappings=real_layer2,
    )
    # Should have stakeholder and data sensitivity context
    assert len(vocab_ctx["stakeholders"]) > 0
    assert len(vocab_ctx["data_sensitivity"]) > 0
    # Should have ontology seeds
    onto_uris = {s["object_id"] for s in onto_seeds}
    assert len(onto_uris) > 0


def test_fairness_risk_resolves_to_hancestro_gsso(real_layer1, real_layer2):
    """Fairness should route through pd:EthnicOrigin/Gender to HANCESTRO/GSSO."""
    from refiner.ontology_seeds import resolve_seeds
    mock_nexus = {
        "get_risk_details": MagicMock(return_value={"group": "ibm-risk-atlas-fairness"}),
        "get_related_risks": MagicMock(return_value=[]),
    }
    _, onto_seeds = resolve_seeds(
        risk_id="atlas-test-fairness-risk",
        risk_group_id="ibm-risk-atlas-fairness",
        nexus_handlers=mock_nexus,
        layer1_mappings=real_layer1,
        layer2_mappings=real_layer2,
    )
    onto_uris = {s["object_id"] for s in onto_seeds}
    assert "obo:HANCESTRO_0001" in onto_uris
    assert "obo:GSSO_000000" in onto_uris


def test_robustness_has_direct_fallback_seeds(real_layer1, real_layer2):
    """Robustness should have direct fallback seeds (ibm-risk-atlas-robustness-* in layer 2)."""
    from refiner.ontology_seeds import resolve_seeds
    mock_nexus = {
        "get_risk_details": MagicMock(return_value={"group": "ibm-risk-atlas-robustness"}),
        "get_related_risks": MagicMock(return_value=[]),
    }
    vocab_ctx, onto_seeds = resolve_seeds(
        risk_id="atlas-test-robustness-risk",
        risk_group_id="ibm-risk-atlas-robustness",
        nexus_handlers=mock_nexus,
        layer1_mappings=real_layer1,
        layer2_mappings=real_layer2,
    )
    # Should have D3FEND/CSO ontology seeds via Threat/Vulnerability
    onto_uris = {s["object_id"] for s in onto_seeds}
    assert len(onto_uris) > 0
    # Should have risk concepts in vocabulary
    assert len(vocab_ctx["risk_concepts"]) > 0


def test_effective_confidence_within_bounds(real_layer1, real_layer2):
    """All effective confidences should be between 0 and 1."""
    from refiner.ontology_seeds import resolve_seeds
    mock_nexus = {
        "get_risk_details": MagicMock(return_value={"group": "ibm-risk-atlas-privacy"}),
        "get_related_risks": MagicMock(return_value=[]),
    }
    _, onto_seeds = resolve_seeds(
        risk_id="atlas-test",
        risk_group_id="ibm-risk-atlas-privacy",
        nexus_handlers=mock_nexus,
        layer1_mappings=real_layer1,
        layer2_mappings=real_layer2,
    )
    for seed in onto_seeds:
        assert 0 < seed["effective_confidence"] <= 1.0, f"Bad confidence: {seed}"


def test_misuse_categorizes_deepfake_as_prohibited(real_layer1, real_layer2):
    """DeepFake from Misuse risk should be categorized as prohibited practice."""
    from refiner.ontology_seeds import resolve_seeds
    mock_nexus = {
        "get_risk_details": MagicMock(return_value={"group": "ibm-risk-atlas-misuse"}),
        "get_related_risks": MagicMock(return_value=[]),
    }
    vocab_ctx, _ = resolve_seeds(
        risk_id="atlas-test-misuse-risk",
        risk_group_id="ibm-risk-atlas-misuse",
        nexus_handlers=mock_nexus,
        layer1_mappings=real_layer1,
        layer2_mappings=real_layer2,
    )
    prohibited = [c["concept_id"] for c in vocab_ctx.get("prohibited_practices", [])]
    assert "eu-aiact:DeepFake" in prohibited
