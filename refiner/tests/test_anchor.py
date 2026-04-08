"""Anchor stage tests — kept for _is_excluded_uri / build_generic_safety_uris.

Tests for removed code (derive_roles, merge strategies, expand_candidates,
_DOMAIN_DISPLAY, _truncate_definition) have been deleted.  New behaviour is
covered by test_anchor_v2.py and test_structural_navigation.py.
"""

from refiner.stages.anchor import (
    _BFO_URI_PREFIX,
    _is_excluded_uri,
    build_generic_safety_uris,
)


# --- BFO upper-ontology exclusion ---


def test_is_excluded_uri_bfo_prefix():
    """BFO URIs are always excluded regardless of generic_safety_uris."""
    assert _is_excluded_uri("http://purl.obolibrary.org/obo/BFO_0000040", set())
    assert _is_excluded_uri("http://purl.obolibrary.org/obo/BFO_0000031", set())
    assert _is_excluded_uri("http://purl.obolibrary.org/obo/BFO_0000015", {"http://other"})


def test_is_excluded_uri_safety_set():
    """generic_safety_uris still works through _is_excluded_uri."""
    assert _is_excluded_uri("http://cso/arson", {"http://cso/arson"})
    assert not _is_excluded_uri("http://cso/fraud", {"http://cso/arson"})


def test_is_excluded_uri_non_bfo_obo():
    """Non-BFO OBO URIs are NOT excluded (e.g. GSSO, HANCESTRO)."""
    assert not _is_excluded_uri("http://purl.obolibrary.org/obo/GSSO_000001", set())
    assert not _is_excluded_uri("http://purl.obolibrary.org/obo/HANCESTRO_0001", set())


# --- Generic safety URI building ---


def test_build_generic_safety_uris_with_subclasses():
    """build_generic_safety_uris returns parent + descendants."""
    handlers = {
        "get_subclasses": lambda uri, depth=1: [
            {"uri": "http://cso#WeaponsManufacturing", "label": "WM", "depth": 1},
            {"uri": "http://cso#DrugSynthesis", "label": "DS", "depth": 1},
            {"uri": "http://cso#FirearmsManufacturing", "label": "FM", "depth": 2},
        ],
    }
    uris = build_generic_safety_uris(handlers)
    assert "http://taxonomy-refiner.io/ontologies/cso#DangerousInformation" in uris
    assert "http://cso#WeaponsManufacturing" in uris
    assert "http://cso#DrugSynthesis" in uris
    assert "http://cso#FirearmsManufacturing" in uris
    assert len(uris) == 4  # parent + 3 descendants


def test_build_generic_safety_uris_no_handler():
    """Returns empty set when get_subclasses is unavailable."""
    uris = build_generic_safety_uris({})
    assert uris == set()


def test_build_generic_safety_uris_empty_descendants():
    """Returns just the parent URI when no descendants found."""
    handlers = {"get_subclasses": lambda uri, depth=1: []}
    uris = build_generic_safety_uris(handlers)
    assert uris == {"http://taxonomy-refiner.io/ontologies/cso#DangerousInformation"}
