import pytest
from pathlib import Path
from refiner.ontology_seeds import SSSOMMapping, SSSOMIndex, categorize_vocabulary, resolve_seeds


SAMPLE_TSV = """\
# curie_map:
#   ibm-risk-atlas: https://example.com/
#   pd: https://w3id.org/dpv/pd#
#   eu-aiact: https://w3id.org/dpv/legal/eu/aiact#
#   skos: http://www.w3.org/2004/02/skos/core#
# mapping_set_id: test
subject_id\tsubject_label\tpredicate_id\tobject_id\tobject_label\tmapping_justification\tconfidence
ibm-risk-atlas-privacy\tPrivacy\tskos:relatedMatch\tpd:Biometric\tBiometric\tsemapv:ManualMappingCuration\t0.90
ibm-risk-atlas-privacy\tPrivacy\tskos:relatedMatch\teu-aiact:AISubject\tAI Subject\tsemapv:ManualMappingCuration\t0.95
ibm-risk-atlas-fairness\tFairness\tskos:relatedMatch\tpd:EthnicOrigin\tEthnic Origin\tsemapv:ManualMappingCuration\t0.95
"""


@pytest.fixture
def sample_tsv(tmp_path):
    p = tmp_path / "test.sssom.tsv"
    p.write_text(SAMPLE_TSV)
    return p


class TestSSSOMIndex:
    def test_load_from_tsv(self, sample_tsv):
        idx = SSSOMIndex.from_tsv(sample_tsv)
        assert len(idx.mappings) == 3

    def test_get_by_subject(self, sample_tsv):
        idx = SSSOMIndex.from_tsv(sample_tsv)
        privacy = idx.get_by_subject("ibm-risk-atlas-privacy")
        assert len(privacy) == 2
        assert {m.object_id for m in privacy} == {"pd:Biometric", "eu-aiact:AISubject"}

    def test_get_by_subject_missing(self, sample_tsv):
        idx = SSSOMIndex.from_tsv(sample_tsv)
        assert idx.get_by_subject("nonexistent") == []

    def test_confidence_parsed(self, sample_tsv):
        idx = SSSOMIndex.from_tsv(sample_tsv)
        biometric = [m for m in idx.get_by_subject("ibm-risk-atlas-privacy")
                     if m.object_id == "pd:Biometric"][0]
        assert biometric.confidence == 0.90

    def test_skips_comments_and_header(self, sample_tsv):
        idx = SSSOMIndex.from_tsv(sample_tsv)
        # Should not include comment lines or header as mappings
        for m in idx.mappings:
            assert not m.subject_id.startswith("#")
            assert m.subject_id != "subject_id"


class TestCategorizeVocabulary:
    def test_categorizes_by_namespace(self, sample_tsv):
        idx = SSSOMIndex.from_tsv(sample_tsv)
        seeds = idx.get_by_subject("ibm-risk-atlas-privacy")
        cats = categorize_vocabulary(seeds)
        assert "pd:Biometric" in [c["concept_id"] for c in cats["data_sensitivity"]]
        assert "eu-aiact:AISubject" in [c["concept_id"] for c in cats["stakeholders"]]

    def test_empty_categories_for_no_matches(self):
        cats = categorize_vocabulary([])
        assert cats["stakeholders"] == []
        assert cats["data_sensitivity"] == []
        assert cats["rights"] == []


class TestResolveSeeds:
    @pytest.fixture
    def layer1(self, sample_tsv):
        return SSSOMIndex.from_tsv(sample_tsv)

    @pytest.fixture
    def layer2_tsv(self, tmp_path):
        content = """\
# mapping_set_id: test-l2
subject_id\tsubject_label\tpredicate_id\tobject_id\tobject_label\tmapping_justification\tconfidence
pd:Biometric\tBiometric\tskos:broadMatch\tcco:BiometricIdentifier\tBiometric Identifier\tsemapv:ManualMappingCuration\t0.85
pd:EthnicOrigin\tEthnic Origin\tskos:broadMatch\tobo:HANCESTRO_0001\tAncestry\tsemapv:ManualMappingCuration\t0.95
eu-aiact:AISubject\tAI Subject\tskos:relatedMatch\tcco:Person\tPerson\tsemapv:ManualMappingCuration\t0.90
"""
        p = tmp_path / "l2.sssom.tsv"
        p.write_text(content)
        return p

    @pytest.fixture
    def layer2(self, layer2_tsv):
        return SSSOMIndex.from_tsv(layer2_tsv)

    @pytest.fixture
    def mock_nexus(self):
        from unittest.mock import MagicMock
        return {
            "get_risk_details": MagicMock(return_value={"group": "ibm-risk-atlas-privacy"}),
            "get_related_risks": MagicMock(return_value=[]),
            "get_risk_group": MagicMock(return_value={"id": "ibm-risk-atlas-privacy", "name": "Privacy"}),
        }

    def test_resolves_group_level(self, layer1, layer2, mock_nexus):
        vocab_ctx, onto_seeds = resolve_seeds(
            risk_id="atlas-some-privacy-risk",
            risk_group_id="ibm-risk-atlas-privacy",
            nexus_handlers=mock_nexus,
            layer1_mappings=layer1,
            layer2_mappings=layer2,
        )
        onto_uris = {s["object_id"] for s in onto_seeds}
        assert "cco:BiometricIdentifier" in onto_uris
        assert "cco:Person" in onto_uris

    def test_effective_confidence_is_product(self, layer1, layer2, mock_nexus):
        _, onto_seeds = resolve_seeds(
            risk_id="atlas-some-privacy-risk",
            risk_group_id="ibm-risk-atlas-privacy",
            nexus_handlers=mock_nexus,
            layer1_mappings=layer1,
            layer2_mappings=layer2,
        )
        biometric_seed = [s for s in onto_seeds if s["object_id"] == "cco:BiometricIdentifier"][0]
        # Layer 1: pd:Biometric confidence=0.90, Layer 2: cco:BiometricIdentifier confidence=0.85
        assert abs(biometric_seed["effective_confidence"] - 0.90 * 0.85) < 0.001

    def test_vocabulary_context_populated(self, layer1, layer2, mock_nexus):
        vocab_ctx, _ = resolve_seeds(
            risk_id="atlas-some-privacy-risk",
            risk_group_id="ibm-risk-atlas-privacy",
            nexus_handlers=mock_nexus,
            layer1_mappings=layer1,
            layer2_mappings=layer2,
        )
        assert len(vocab_ctx["data_sensitivity"]) > 0
        assert len(vocab_ctx["stakeholders"]) > 0

    def test_cross_taxonomy_fallback(self, layer1, layer2, mock_nexus):
        mock_nexus["get_related_risks"].return_value = [
            {"id": "atlas-privacy-risk", "mapping_type": "exact",
             "taxonomy": "ibm-risk-atlas", "name": "Privacy risk", "description": ""}
        ]
        mock_nexus["get_risk_details"].return_value = {"group": "ibm-risk-atlas-privacy"}
        vocab_ctx, onto_seeds = resolve_seeds(
            risk_id="owasp-some-risk",
            risk_group_id=None,
            nexus_handlers=mock_nexus,
            layer1_mappings=layer1,
            layer2_mappings=layer2,
        )
        # Should have resolved via IBM fallback
        assert len(onto_seeds) > 0

    def test_deduplicates_by_object_id(self, layer1, layer2, mock_nexus):
        _, onto_seeds = resolve_seeds(
            risk_id="atlas-some-privacy-risk",
            risk_group_id="ibm-risk-atlas-privacy",
            nexus_handlers=mock_nexus,
            layer1_mappings=layer1,
            layer2_mappings=layer2,
        )
        uris = [s["object_id"] for s in onto_seeds]
        assert len(uris) == len(set(uris))
