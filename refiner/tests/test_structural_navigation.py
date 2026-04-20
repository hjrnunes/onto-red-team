import pytest
from unittest.mock import MagicMock
from refiner.models import VariationAxis
from refiner.stages.anchor import (
    navigate_from_seeds,
    constrained_search,
    check_structural_connection,
    merge_tiered,
    derive_bfo_category,
    _resolve_axis_groups,
    derive_role,
)


class TestVariationAxisSemanticRole:
    def test_semantic_role_defaults_empty(self):
        axis = VariationAxis(
            cco_class_uri="http://example.org/X",
            cco_class_label="X",
            rationale="test",
        )
        assert axis.semantic_role == ""

    def test_semantic_role_set(self):
        axis = VariationAxis(
            cco_class_uri="http://example.org/X",
            cco_class_label="X",
            rationale="test",
            semantic_role="agent",
        )
        assert axis.semantic_role == "agent"


@pytest.fixture
def mock_onto():
    handlers = {
        "get_subclasses": MagicMock(return_value=[]),
        "get_siblings": MagicMock(return_value=[]),
        "get_restrictions": MagicMock(return_value=[]),
        "get_class_definition": MagicMock(return_value=None),
        "get_superclasses": MagicMock(return_value=[]),
        "search_domains": MagicMock(return_value={}),
    }
    return handlers


class TestDeriveBfoCategory:
    def test_returns_bfo_category(self, mock_onto):
        mock_onto["get_superclasses"].side_effect = [
            [{"uri": "http://purl.obolibrary.org/obo/BFO_0000040", "label": "material entity"}],
        ]
        result = derive_bfo_category("http://example.org/Person", mock_onto)
        assert result == "MaterialEntity"

    def test_walks_chain(self, mock_onto):
        mock_onto["get_superclasses"].side_effect = [
            [{"uri": "http://example.org/Mid", "label": "Mid"}],
            [{"uri": "http://purl.obolibrary.org/obo/BFO_0000015", "label": "process"}],
        ]
        result = derive_bfo_category("http://example.org/SomeProcess", mock_onto)
        assert result == "Process"

    def test_returns_empty_on_no_match(self, mock_onto):
        mock_onto["get_superclasses"].return_value = []
        result = derive_bfo_category("http://example.org/Unknown", mock_onto)
        assert result == ""

    def test_uses_bfo_fallback_when_walk_fails(self, mock_onto):
        mock_onto["get_superclasses"].return_value = []
        fallbacks = {"http://example.org/Unknown": "Act"}
        result = derive_bfo_category("http://example.org/Unknown", mock_onto, bfo_fallbacks=fallbacks)
        assert result == "Act"

    def test_walk_takes_precedence_over_fallback(self, mock_onto):
        mock_onto["get_superclasses"].side_effect = [
            [{"uri": "http://purl.obolibrary.org/obo/BFO_0000040", "label": "material entity"}],
        ]
        fallbacks = {"http://example.org/Person": "Act"}
        result = derive_bfo_category("http://example.org/Person", mock_onto, bfo_fallbacks=fallbacks)
        assert result == "MaterialEntity"

    def test_cco_direct_hit(self, mock_onto):
        """CCO Person/Organization URIs in BFO_CATEGORY_MAP should resolve without walking."""
        result = derive_bfo_category("https://www.commoncoreontologies.org/ont00001262", mock_onto)
        assert result == "Agent"


class TestNavigateFromSeeds:
    def test_broad_match_navigates_down(self, mock_onto):
        mock_onto["get_subclasses"].return_value = [
            {"uri": "http://example.org/Sub1", "label": "Sub1", "depth": 1},
            {"uri": "http://example.org/Sub2", "label": "Sub2", "depth": 2},
        ]
        seeds = [{
            "object_id": "http://example.org/Parent",
            "object_label": "Parent",
            "predicate_id": "skos:broadMatch",
            "effective_confidence": 0.9,
            "vocabulary_concept": "pd:Biometric",
            "vocabulary_label": "Biometric",
        }]
        result = navigate_from_seeds(seeds, mock_onto, selected_domains=None)
        assert len(result) >= 2
        assert all(c["source"] == "structural" for c in result)

    def test_exact_match_uses_directly(self, mock_onto):
        mock_onto["get_class_definition"].return_value = {
            "uri": "http://example.org/Exact", "label": "Exact", "definition": "test"
        }
        seeds = [{
            "object_id": "http://example.org/Exact",
            "object_label": "Exact",
            "predicate_id": "skos:exactMatch",
            "effective_confidence": 0.95,
            "vocabulary_concept": "pd:Biometric",
            "vocabulary_label": "Biometric",
        }]
        result = navigate_from_seeds(seeds, mock_onto, selected_domains=None)
        assert len(result) == 1
        assert result[0]["uri"] == "http://example.org/Exact"

    def test_related_match_navigates_around(self, mock_onto):
        mock_onto["get_restrictions"].return_value = [
            {"type": "someValuesFrom", "property": "http://example.org/prop",
             "filler": "http://example.org/Filler"}
        ]
        mock_onto["get_class_definition"].side_effect = lambda uri: (
            {"uri": uri, "label": uri.split("/")[-1], "definition": "test"}
            if uri != "invalid" else None
        )
        mock_onto["get_siblings"].return_value = [
            {"uri": "http://example.org/Sibling", "label": "Sibling"}
        ]
        seeds = [{
            "object_id": "http://example.org/Related",
            "object_label": "Related",
            "predicate_id": "skos:relatedMatch",
            "effective_confidence": 0.8,
            "vocabulary_concept": "risk:Threat",
            "vocabulary_label": "Threat",
        }]
        result = navigate_from_seeds(seeds, mock_onto, selected_domains=None)
        uris = {c["uri"] for c in result}
        # Should include seed, filler from restriction, sibling
        assert "http://example.org/Related" in uris
        assert "http://example.org/Filler" in uris


class TestCheckStructuralConnection:
    def test_connected_via_common_ancestor(self, mock_onto):
        mock_onto["get_superclasses"].side_effect = lambda uri: (
            [{"uri": "http://example.org/Ancestor", "label": "Ancestor"}]
        )
        result = check_structural_connection(
            "http://example.org/A", ["http://example.org/B"], mock_onto
        )
        assert result["connected"] is True

    def test_not_connected(self, mock_onto):
        mock_onto["get_superclasses"].return_value = []
        result = check_structural_connection(
            "http://example.org/A", ["http://example.org/B"], mock_onto
        )
        assert result["connected"] is False


class TestMergeTiered:
    def test_tier1_first(self):
        structural = [
            {"uri": "s1", "effective_confidence": 0.9, "path": ["a", "s1"],
             "vocabulary_concept": "pd:X"},
            {"uri": "s2", "effective_confidence": 0.8, "path": ["a", "s2"],
             "vocabulary_concept": "eu-aiact:Y"},
        ]
        search_connected = [{"uri": "sc1", "best_distance": 0.3, "vocabulary_concept": "pd:X"}]
        search_only = [{"uri": "so1", "best_distance": 0.2, "vocabulary_concept": None}]
        result = merge_tiered(structural, search_connected, search_only)
        assert result[0]["uri"] == "s1"
        assert result[1]["uri"] == "s2"

    def test_deduplicates(self):
        structural = [
            {"uri": "dup", "effective_confidence": 0.9, "path": ["a"],
             "vocabulary_concept": "pd:X"},
        ]
        search_connected = [{"uri": "dup", "best_distance": 0.3, "vocabulary_concept": "pd:X"}]
        result = merge_tiered(structural, search_connected, [])
        assert len([r for r in result if r["uri"] == "dup"]) == 1

    def test_caps_at_max(self):
        structural = [
            {"uri": f"s{i}", "effective_confidence": 0.9 - i*0.01, "path": ["a"],
             "vocabulary_concept": f"pd:X{i}"}
            for i in range(15)
        ]
        result = merge_tiered(structural, [], [], max_total=12)
        assert len(result) <= 12

    def test_ontology_diversity_injects_underrepresented(self):
        """High-confidence CSO candidates should not crowd out OBO candidates.

        Reproduces the rdash-nhs Data Privacy pattern: 8 CSO PrivacyViolation
        subclasses at 0.81 fill all structural slots, while OBO Disease
        subclasses at 0.72 never enter the candidate pool.
        """
        # 8 CSO candidates at high confidence
        cso_base = "http://taxonomy-refiner.io/ontologies/cso#"
        cso = [
            {"uri": f"{cso_base}Priv{i}", "effective_confidence": 0.81,
             "path": [f"{cso_base}PrivacyViolation", f"{cso_base}Priv{i}"],
             "vocabulary_concept": "eu-rights:T2-DataProtection"}
            for i in range(8)
        ]
        # 4 OBO candidates at lower confidence
        obo_base = "http://purl.obolibrary.org/obo/"
        obo = [
            {"uri": f"{obo_base}OGMS_{i:07d}", "effective_confidence": 0.72,
             "path": [f"{obo_base}OGMS_0000031", f"{obo_base}OGMS_{i:07d}"],
             "vocabulary_concept": "pd:MedicalHealth"}
            for i in range(4)
        ]
        # 1 CCO candidate at highest confidence
        cco = [
            {"uri": "https://www.commoncoreontologies.org/ont00001262",
             "effective_confidence": 0.855, "path": [],
             "vocabulary_concept": "eu-aiact:AISubject"}
        ]
        structural = cco + cso + obo

        result = merge_tiered(structural, [], [])
        result_uris = {c["uri"] for c in result}

        # At least one OBO candidate must appear despite lower confidence
        obo_in_result = {u for u in result_uris if obo_base in u}
        assert obo_in_result, (
            "OBO candidates crowded out by higher-confidence CSO/CCO; "
            "ontology diversity guarantee failed"
        )
        # CCO and CSO should still be present
        assert any("commoncoreontologies" in u for u in result_uris)
        assert any("taxonomy-refiner.io" in u for u in result_uris)

    def test_ontology_diversity_prefers_navigated_over_generic(self):
        """Diversity injection should pick structurally navigated candidates
        over generic direct seeds within the same ontology family.

        Reproduces the PHI/Consent pattern: OMRSE Human Social Role (generic,
        empty path, higher confidence) vs MAXO Medical Action subclasses
        (domain-specific, navigated path, lower confidence).  The navigated
        candidate should win because longer path = more specific.
        """
        obo_base = "http://purl.obolibrary.org/obo/"
        # Generic OBO candidate: high confidence, no structural navigation
        generic_obo = {
            "uri": f"{obo_base}OMRSE_00000001",
            "effective_confidence": 0.80,
            "path": [],  # direct relatedMatch seed
            "vocabulary_concept": "eu-aiact:AISubject",
        }
        # Domain-specific OBO candidates: lower confidence, navigated paths
        specific_obo = [
            {"uri": f"{obo_base}MAXO_000000{i}",
             "effective_confidence": 0.72,
             "path": [f"{obo_base}MAXO_0000001", f"{obo_base}MAXO_000000{i}"],
             "vocabulary_concept": "sector-health:ClinicalCare"}
            for i in range(1, 4)
        ]
        # CSO candidates fill structural slots
        cso_base = "http://taxonomy-refiner.io/ontologies/cso#"
        cso = [
            {"uri": f"{cso_base}Priv{i}", "effective_confidence": 0.81,
             "path": [f"{cso_base}PrivacyViolation", f"{cso_base}Priv{i}"],
             "vocabulary_concept": "eu-rights:T2-DataProtection"}
            for i in range(8)
        ]
        structural = cso + [generic_obo] + specific_obo

        result = merge_tiered(structural, [], [])
        result_uris = {c["uri"] for c in result}

        # The navigated MAXO candidate should be picked, not generic OMRSE
        assert any("MAXO" in u for u in result_uris), (
            "Diversity injection picked generic OMRSE over navigated MAXO"
        )
        assert f"{obo_base}OMRSE_00000001" not in result_uris, (
            "Generic OMRSE selected despite navigated MAXO candidates available"
        )

    def test_label_dedup_prefers_domain_specific(self):
        """When FIBO is in selected_domains, FIBO person wins over CCO Person."""
        structural = [
            {"uri": "https://www.commoncoreontologies.org/ont00001262",
             "label": "Person", "effective_confidence": 0.7, "path": [],
             "vocabulary_concept": "eu-aiact:AISubject"},
            {"uri": "https://spec.edmcouncil.org/fibo/ontology/FND/AgentsAndPeople/People/Person",
             "label": "person", "effective_confidence": 0.56,
             "path": ["ont00001262", "fibo-person"],
             "vocabulary_concept": "eu-aiact:AISubject"},
        ]
        result = merge_tiered(structural, [], [],
                              selected_domains=["CCO", "Commons", "D3FEND", "CSO", "LKIF", "FIBO"])
        person_results = [c for c in result if "person" in c.get("label", "").lower()]
        assert len(person_results) == 1
        assert "fibo" in person_results[0]["uri"].lower()

    def test_label_dedup_prefers_foundational_when_no_domain(self):
        """Without domain-specific ontologies, CCO Person wins over FIBO person."""
        structural = [
            {"uri": "https://www.commoncoreontologies.org/ont00001262",
             "label": "Person", "effective_confidence": 0.7, "path": [],
             "vocabulary_concept": "eu-aiact:AISubject"},
            {"uri": "https://spec.edmcouncil.org/fibo/ontology/FND/AgentsAndPeople/People/Person",
             "label": "person", "effective_confidence": 0.56,
             "path": ["ont00001262", "fibo-person"],
             "vocabulary_concept": "eu-aiact:AISubject"},
        ]
        result = merge_tiered(structural, [], [],
                              selected_domains=["CCO", "Commons", "D3FEND", "CSO", "LKIF"])
        person_results = [c for c in result if "person" in c.get("label", "").lower()]
        assert len(person_results) == 1
        assert "commoncoreontologies" in person_results[0]["uri"]

    def test_label_dedup_both_domain_specific_uses_confidence(self):
        """When both are domain-specific, higher confidence wins."""
        structural = [
            {"uri": "http://purl.obolibrary.org/obo/OBO_Person",
             "label": "Person", "effective_confidence": 0.8, "path": [],
             "vocabulary_concept": "pd:X"},
            {"uri": "https://spec.edmcouncil.org/fibo/ontology/FND/AgentsAndPeople/People/Person",
             "label": "person", "effective_confidence": 0.9, "path": [],
             "vocabulary_concept": "pd:X"},
        ]
        result = merge_tiered(structural, [], [],
                              selected_domains=["CCO", "Commons", "D3FEND", "CSO", "LKIF", "FIBO", "OBO"])
        person_results = [c for c in result if "person" in c.get("label", "").lower()]
        assert len(person_results) == 1
        assert "fibo" in person_results[0]["uri"].lower()

    def test_label_dedup_no_selected_domains(self):
        """With no selected_domains at all, higher confidence wins."""
        structural = [
            {"uri": "https://www.commoncoreontologies.org/ont00001262",
             "label": "Person", "effective_confidence": 0.7, "path": [],
             "vocabulary_concept": "eu-aiact:AISubject"},
            {"uri": "https://spec.edmcouncil.org/fibo/ontology/FND/AgentsAndPeople/People/Person",
             "label": "person", "effective_confidence": 0.9, "path": [],
             "vocabulary_concept": "eu-aiact:AISubject"},
        ]
        result = merge_tiered(structural, [], [], selected_domains=None)
        person_results = [c for c in result if "person" in c.get("label", "").lower()]
        assert len(person_results) == 1

    def test_label_dedup_different_labels_not_collapsed(self):
        """Candidates with genuinely different labels are not affected."""
        structural = [
            {"uri": "uri1", "label": "Person", "effective_confidence": 0.7,
             "path": [], "vocabulary_concept": "pd:X"},
            {"uri": "uri2", "label": "Organisation", "effective_confidence": 0.8,
             "path": [], "vocabulary_concept": "pd:X"},
        ]
        result = merge_tiered(structural, [], [])
        assert len(result) == 2


class TestResolveAxisGroups:
    def test_resolves_valid_groups(self):
        id_to_uri = {"C1": "http://ex/A", "C2": "http://ex/B", "C3": "http://ex/C"}
        valid_uris = {"http://ex/A", "http://ex/B", "http://ex/C"}
        raw_groups = [["C1", "C2"], ["C2", "C3"]]

        result = _resolve_axis_groups(raw_groups, id_to_uri, valid_uris)

        assert result == [["http://ex/A", "http://ex/B"], ["http://ex/B", "http://ex/C"]]

    def test_filters_invalid_ids(self):
        id_to_uri = {"C1": "http://ex/A", "C2": "http://ex/B"}
        valid_uris = {"http://ex/A", "http://ex/B"}
        raw_groups = [["C1", "C99"], ["C1", "C2"]]

        result = _resolve_axis_groups(raw_groups, id_to_uri, valid_uris)

        assert result == [["http://ex/A", "http://ex/B"]]

    def test_filters_invalid_uris(self):
        id_to_uri = {"C1": "http://ex/A", "C2": "http://ex/B"}
        valid_uris = {"http://ex/A"}
        raw_groups = [["C1", "C2"]]

        result = _resolve_axis_groups(raw_groups, id_to_uri, valid_uris)

        assert result == []

    def test_empty_groups(self):
        result = _resolve_axis_groups([], {}, set())
        assert result == []


class TestDeriveRole:
    def test_process_participant_agent(self):
        role = derive_role(
            candidate_category="Agent",
            seed_category="Process",
            restriction_property="http://example.org/has_participant",
        )
        assert role == "agent"

    def test_process_participant_material(self):
        role = derive_role(
            candidate_category="MaterialEntity",
            seed_category="Process",
            restriction_property="http://example.org/has_participant",
        )
        assert role == "patient"

    def test_process_participant_ice(self):
        role = derive_role(
            candidate_category="InformationContentEntity",
            seed_category="Process",
            restriction_property="http://example.org/has_participant",
        )
        assert role == "information"

    def test_process_realizes(self):
        role = derive_role(
            candidate_category="Disposition",
            seed_category="Process",
            restriction_property="http://example.org/realizes",
        )
        assert role == "obligation"

    def test_process_input(self):
        role = derive_role(
            candidate_category="MaterialEntity",
            seed_category="Process",
            restriction_property="http://example.org/has_input",
        )
        assert role == "input"

    def test_process_output(self):
        role = derive_role(
            candidate_category="InformationContentEntity",
            seed_category="Process",
            restriction_property="http://example.org/has_output",
        )
        assert role == "output"

    def test_quality_inheres_in(self):
        role = derive_role(
            candidate_category="MaterialEntity",
            seed_category="Quality",
            restriction_property="http://example.org/inheres_in",
        )
        assert role == "bearer"

    def test_role_inheres_in(self):
        role = derive_role(
            candidate_category="Agent",
            seed_category="Role",
            restriction_property="http://example.org/inheres_in",
        )
        assert role == "bearer"

    def test_role_realized_in(self):
        role = derive_role(
            candidate_category="Process",
            seed_category="Role",
            restriction_property="http://example.org/realized_in",
        )
        assert role == "realization"

    def test_ice_is_about(self):
        role = derive_role(
            candidate_category="Agent",
            seed_category="InformationContentEntity",
            restriction_property="http://example.org/is_about",
        )
        assert role == "subject"

    def test_ice_depends_on(self):
        role = derive_role(
            candidate_category="MaterialEntity",
            seed_category="InformationContentEntity",
            restriction_property="http://example.org/generically_depends_on",
        )
        assert role == "medium"

    def test_fallback_no_restriction(self):
        role = derive_role(
            candidate_category="Agent",
            seed_category="",
            restriction_property="",
        )
        assert role == "agent"

    def test_fallback_process_category(self):
        role = derive_role(
            candidate_category="Process",
            seed_category="",
            restriction_property="",
        )
        assert role == "process"

    def test_fallback_facility(self):
        role = derive_role(
            candidate_category="Facility",
            seed_category="",
            restriction_property="",
        )
        assert role == "location"

    def test_fallback_unknown_category(self):
        role = derive_role(
            candidate_category="",
            seed_category="",
            restriction_property="",
        )
        assert role == ""

    def test_unmatched_property_falls_back_to_category(self):
        role = derive_role(
            candidate_category="Agent",
            seed_category="Process",
            restriction_property="http://example.org/some_unknown_prop",
        )
        assert role == "agent"


class TestNavigateCategoryAware:
    def test_related_match_uses_category_dispatch(self, mock_onto):
        """When bfo_categories is provided, relatedMatch should use _expand_by_category."""
        mock_onto["get_restrictions"].return_value = [
            {"property": "http://ex.org/has_participant", "filler": "http://ex.org/Agent"},
        ]
        mock_onto["get_class_definition"].side_effect = lambda uri: {
            "uri": uri, "label": uri.split("/")[-1], "definition": "test"}
        mock_onto["get_siblings"].return_value = []

        seeds = [{
            "object_id": "http://ex.org/DataCollection",
            "object_label": "DataCollection",
            "predicate_id": "skos:relatedMatch",
            "effective_confidence": 0.9,
            "vocabulary_concept": "risk:X",
            "vocabulary_label": "X",
        }]
        bfo_cats = {"http://ex.org/DataCollection": "Process"}
        result = navigate_from_seeds(
            seeds, mock_onto, selected_domains=None,
            bfo_categories=bfo_cats)

        agent = [c for c in result if c["uri"] == "http://ex.org/Agent"]
        assert len(agent) == 1
        # Constitutive confidence: 0.9 * 0.95 = 0.855
        assert abs(agent[0]["effective_confidence"] - 0.855) < 0.01

    def test_broad_match_unchanged_with_categories(self, mock_onto):
        """broadMatch should be unaffected by bfo_categories."""
        mock_onto["get_subclasses"].return_value = [
            {"uri": "http://ex.org/Sub1", "label": "Sub1"},
        ]
        seeds = [{
            "object_id": "http://ex.org/Parent",
            "object_label": "Parent",
            "predicate_id": "skos:broadMatch",
            "effective_confidence": 0.9,
            "vocabulary_concept": None,
            "vocabulary_label": None,
        }]
        result = navigate_from_seeds(
            seeds, mock_onto, selected_domains=None,
            bfo_categories={"http://ex.org/Parent": "Process"})
        assert len(result) >= 1
        assert result[0]["effective_confidence"] == 0.9

    def test_backward_compat_no_categories(self, mock_onto):
        """Without bfo_categories, behavior should be identical to before."""
        mock_onto["get_restrictions"].return_value = [
            {"property": "http://ex.org/prop", "filler": "http://ex.org/Filler"},
        ]
        mock_onto["get_class_definition"].side_effect = lambda uri: {
            "uri": uri, "label": uri.split("/")[-1], "definition": "test"}
        mock_onto["get_siblings"].return_value = [
            {"uri": "http://ex.org/Sibling", "label": "Sibling"},
        ]
        seeds = [{
            "object_id": "http://ex.org/Related",
            "object_label": "Related",
            "predicate_id": "skos:relatedMatch",
            "effective_confidence": 0.8,
            "vocabulary_concept": None,
            "vocabulary_label": None,
        }]
        result = navigate_from_seeds(seeds, mock_onto, selected_domains=None)
        uris = {c["uri"] for c in result}
        assert "http://ex.org/Related" in uris
        assert "http://ex.org/Filler" in uris


from refiner.stages.anchor import _expand_by_category


class TestExpandByCategory:
    @pytest.fixture
    def base_kwargs(self):
        return dict(
            seed_label="TestSeed",
            confidence=0.9,
            predicate="skos:relatedMatch",
            vocab_concept=None,
            vocab_label=None,
            safety=set(),
            selected_domains=None,
        )

    def test_process_prioritizes_participant_restrictions(self, mock_onto, base_kwargs):
        mock_onto["get_restrictions"].return_value = [
            {"property": "http://ex.org/has_participant", "filler": "http://ex.org/Agent"},
            {"property": "http://ex.org/governed_by", "filler": "http://ex.org/Regulation"},
        ]
        mock_onto["get_class_definition"].side_effect = lambda uri: {
            "uri": uri, "label": uri.split("/")[-1], "definition": "test"}
        mock_onto["get_siblings"].return_value = []
        candidates = []
        _expand_by_category(
            category="Process",
            seed_uri="http://ex.org/DataCollection",
            onto_handlers=mock_onto,
            candidates=candidates,
            bfo_categories={"http://ex.org/Agent": "Agent"},
            seed_label="DataCollection",
            confidence=0.9,
            predicate="skos:relatedMatch",
            vocab_concept=None,
            vocab_label=None,
            safety=set(),
            selected_domains=None,
        )
        uris = {c["uri"] for c in candidates}
        assert "http://ex.org/Agent" in uris
        assert "http://ex.org/Regulation" in uris
        agent_c = next(c for c in candidates if c["uri"] == "http://ex.org/Agent")
        reg_c = next(c for c in candidates if c["uri"] == "http://ex.org/Regulation")
        assert agent_c["effective_confidence"] > reg_c["effective_confidence"]

    def test_ice_skips_siblings(self, mock_onto, base_kwargs):
        mock_onto["get_restrictions"].return_value = []
        mock_onto["get_siblings"].return_value = [
            {"uri": "http://ex.org/OtherDoc", "label": "OtherDoc"},
        ]
        mock_onto["get_class_definition"].return_value = None
        candidates = []
        _expand_by_category(
            category="InformationContentEntity",
            seed_uri="http://ex.org/Report",
            onto_handlers=mock_onto,
            candidates=candidates,
            bfo_categories={},
            seed_label="Report",
            confidence=0.9,
            predicate="skos:relatedMatch",
            vocab_concept=None,
            vocab_label=None,
            safety=set(),
            selected_domains=None,
        )
        uris = {c["uri"] for c in candidates}
        assert "http://ex.org/OtherDoc" not in uris

    def test_quality_expands_siblings_aggressively(self, mock_onto, base_kwargs):
        mock_onto["get_restrictions"].return_value = []
        mock_onto["get_siblings"].return_value = [
            {"uri": "http://ex.org/GoodQuality", "label": "GoodQuality"},
            {"uri": "http://ex.org/PoorQuality", "label": "PoorQuality"},
        ]
        candidates = []
        _expand_by_category(
            category="Quality",
            seed_uri="http://ex.org/ImageQuality",
            onto_handlers=mock_onto,
            candidates=candidates,
            bfo_categories={},
            seed_label="ImageQuality",
            confidence=0.9,
            predicate="skos:relatedMatch",
            vocab_concept=None,
            vocab_label=None,
            safety=set(),
            selected_domains=None,
        )
        uris = {c["uri"] for c in candidates}
        assert "http://ex.org/GoodQuality" in uris
        assert "http://ex.org/PoorQuality" in uris

    def test_fallback_for_unknown_category(self, mock_onto, base_kwargs):
        mock_onto["get_restrictions"].return_value = [
            {"property": "http://ex.org/some_prop", "filler": "http://ex.org/Target"},
        ]
        mock_onto["get_class_definition"].side_effect = lambda uri: {
            "uri": uri, "label": uri.split("/")[-1], "definition": "test"}
        mock_onto["get_siblings"].return_value = [
            {"uri": "http://ex.org/Sibling", "label": "Sibling"},
        ]
        candidates = []
        _expand_by_category(
            category="",
            seed_uri="http://ex.org/Unknown",
            onto_handlers=mock_onto,
            candidates=candidates,
            bfo_categories={},
            seed_label="Unknown",
            confidence=0.9,
            predicate="skos:relatedMatch",
            vocab_concept=None,
            vocab_label=None,
            safety=set(),
            selected_domains=None,
        )
        uris = {c["uri"] for c in candidates}
        assert "http://ex.org/Target" in uris
        assert "http://ex.org/Sibling" in uris
