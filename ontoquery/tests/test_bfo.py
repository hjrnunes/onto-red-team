"""Tests for ontoquery.bfo — BFO category map, constitutive patterns, and property matching."""
from ontoquery.bfo import match_property, ConstitutivePattern, CATEGORY_PATTERNS, BFO_CATEGORY_MAP, classify_bfo_categories
from ontoquery.owl2vec import ProjectedGraph, SUBCLASS_OF


class TestMatchProperty:
    def test_exact_local_name_match(self):
        assert match_property("http://example.org/ont#has_participant", ["has_participant"]) is True

    def test_fragment_after_hash(self):
        assert match_property("http://d3fend.mitre.org/ontologies/d3fend.owl#has_participant", ["has_participant"]) is True

    def test_fragment_after_slash(self):
        assert match_property("http://example.org/ontology/has_participant", ["has_participant"]) is True

    def test_no_match(self):
        assert match_property("http://example.org/ont#worksFor", ["has_participant"]) is False

    def test_does_not_false_positive_has_part_vs_has_participant(self):
        assert match_property("http://example.org/ont#has_participant", ["has_part"]) is False

    def test_has_part_matches_has_part(self):
        assert match_property("http://example.org/ont#has_part", ["has_part"]) is True

    def test_case_insensitive(self):
        assert match_property("http://example.org/ont#Has_Participant", ["has_participant"]) is True

    def test_bfo_numeric_uri(self):
        assert match_property("http://purl.obolibrary.org/obo/BFO_0000057", ["BFO_0000057", "has_participant"]) is True

    def test_multiple_patterns(self):
        assert match_property("http://example.org/ont#realizes", ["has_participant", "realizes"]) is True

    def test_camel_case_token_boundary(self):
        assert match_property("http://example.org/ont#hasParticipant", ["has_participant"]) is True


class TestCategoryPatternsComplete:
    def test_all_categories_have_patterns(self):
        expected = {
            "Process", "Quality", "Role", "Disposition",
            "InformationContentEntity", "MaterialEntity", "Agent",
            "MaterialArtifact", "Act", "Facility", "GenericallyDependentContinuant",
        }
        assert set(CATEGORY_PATTERNS.keys()) == expected

    def test_each_pattern_has_role_prefix(self):
        for cat, patterns in CATEGORY_PATTERNS.items():
            for p in patterns:
                assert p.role_prefix, f"{cat} has pattern with empty role_prefix"
                assert p.property_patterns, f"{cat}/{p.role_prefix} has empty property_patterns"


class TestBfoCategoryMap:
    def test_known_bfo_entries(self):
        assert BFO_CATEGORY_MAP["http://purl.obolibrary.org/obo/BFO_0000015"] == "Process"
        assert BFO_CATEGORY_MAP["http://purl.obolibrary.org/obo/BFO_0000040"] == "MaterialEntity"
        assert BFO_CATEGORY_MAP["http://purl.obolibrary.org/obo/BFO_0000023"] == "Role"

    def test_cco_shortcuts(self):
        assert BFO_CATEGORY_MAP["https://www.commoncoreontologies.org/ont00000958"] == "InformationContentEntity"
        assert BFO_CATEGORY_MAP["https://www.commoncoreontologies.org/ont00001017"] == "Agent"


class TestClassifyBfoCategories:
    def _make_graph(self, edges):
        g = ProjectedGraph()
        for s, o in edges:
            g.edges.append((s, SUBCLASS_OF, o))
            g.classes.add(s)
            g.classes.add(o)
        return g

    def test_direct_bfo_child(self):
        graph = self._make_graph([
            ("http://example.org/MyProcess", "http://purl.obolibrary.org/obo/BFO_0000015"),
        ])
        result = classify_bfo_categories(graph)
        assert result["http://example.org/MyProcess"] == "Process"

    def test_indirect_via_chain(self):
        graph = self._make_graph([
            ("http://example.org/DataCollection", "http://example.org/InformationProcessing"),
            ("http://example.org/InformationProcessing", "http://purl.obolibrary.org/obo/BFO_0000015"),
        ])
        result = classify_bfo_categories(graph)
        assert result["http://example.org/DataCollection"] == "Process"
        assert result["http://example.org/InformationProcessing"] == "Process"

    def test_cco_shortcut(self):
        graph = self._make_graph([
            ("http://example.org/Report", "https://www.commoncoreontologies.org/ont00000958"),
        ])
        result = classify_bfo_categories(graph)
        assert result["http://example.org/Report"] == "InformationContentEntity"

    def test_no_bfo_ancestor(self):
        graph = self._make_graph([
            ("http://example.org/Thing", "http://example.org/OtherThing"),
        ])
        result = classify_bfo_categories(graph)
        assert "http://example.org/Thing" not in result

    def test_bfo_class_itself_not_included(self):
        graph = ProjectedGraph()
        graph.classes.add("http://purl.obolibrary.org/obo/BFO_0000015")
        result = classify_bfo_categories(graph)
        assert "http://purl.obolibrary.org/obo/BFO_0000015" not in result

    def test_most_specific_category_wins(self):
        """Role is more specific than RealizableEntity — Role should win."""
        graph = self._make_graph([
            ("http://example.org/DataControllerRole", "http://purl.obolibrary.org/obo/BFO_0000023"),
            ("http://purl.obolibrary.org/obo/BFO_0000023", "http://purl.obolibrary.org/obo/BFO_0000017"),
        ])
        result = classify_bfo_categories(graph)
        assert result["http://example.org/DataControllerRole"] == "Role"
