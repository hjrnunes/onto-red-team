"""BFO/CCO category map, constitutive patterns, and property-URI matching.

Shared foundation for both ontoquery indexing and refiner anchor stages.
Centralises the BFO-to-category mapping (previously _BFO_CATEGORIES in
anchor.py) and the constitutive-pattern table that drives category-aware
structural navigation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ConstitutivePattern:
    """One navigable relationship within a BFO category.

    Attributes:
        role_prefix: Human-readable label for this group of relationships
                     (e.g. "Participants", "Bears role").
        property_patterns: Local-name fragments that identify matching OWL
                           properties (matched via ``match_property``).
        inverse: If True, the relationship is read in the inverse direction
                 (e.g. "inheres_in" describes the *dependent* entity rather
                 than the bearer).
    """
    role_prefix: str
    property_patterns: list[str]
    inverse: bool = False


# ---------------------------------------------------------------------------
# BFO / CCO URI  →  human-readable category label
# ---------------------------------------------------------------------------

BFO_CATEGORY_MAP: dict[str, str] = {
    # BFO classes
    "http://purl.obolibrary.org/obo/BFO_0000040": "MaterialEntity",
    "http://purl.obolibrary.org/obo/BFO_0000015": "Process",
    "http://purl.obolibrary.org/obo/BFO_0000031": "GenericallyDependentContinuant",
    "http://purl.obolibrary.org/obo/BFO_0000020": "Quality",
    "http://purl.obolibrary.org/obo/BFO_0000023": "Role",
    "http://purl.obolibrary.org/obo/BFO_0000016": "Disposition",
    "http://purl.obolibrary.org/obo/BFO_0000017": "RealizableEntity",
    "http://purl.obolibrary.org/obo/BFO_0000029": "Site",
    "http://purl.obolibrary.org/obo/BFO_0000006": "SpatialRegion",
    "http://purl.obolibrary.org/obo/BFO_0000141": "ImmaterialEntity",
    "http://purl.obolibrary.org/obo/BFO_0000008": "TemporalRegion",
    "http://purl.obolibrary.org/obo/BFO_0000019": "Quality",
    # CCO shortcuts
    "https://www.commoncoreontologies.org/ont00000958": "InformationContentEntity",
    "https://www.commoncoreontologies.org/ont00001017": "Agent",
    "https://www.commoncoreontologies.org/ont00000995": "MaterialArtifact",
    "https://www.commoncoreontologies.org/ont00000192": "Facility",
    "https://www.commoncoreontologies.org/ont00000005": "Act",
    # CCO direct mappings
    "https://www.commoncoreontologies.org/ont00001262": "Agent",           # Person
    "https://www.commoncoreontologies.org/ont00001180": "Agent",           # Organization
    "https://www.commoncoreontologies.org/ont00000740": "MaterialEntity",  # Resource
}


# ---------------------------------------------------------------------------
# Constitutive patterns per BFO category
# ---------------------------------------------------------------------------

CATEGORY_PATTERNS: dict[str, list[ConstitutivePattern]] = {
    "Process": [
        ConstitutivePattern("Participants", [
            "has_participant", "has_agent", "has_patient", "involves",
            "BFO_0000057"]),
        ConstitutivePattern("Realizes", ["realizes", "is_realization_of"]),
        ConstitutivePattern("Inputs/Outputs", [
            "has_input", "has_output", "transforms"]),
    ],
    "Quality": [
        ConstitutivePattern("Characterizes", [
            "inheres_in", "bearer_of", "quality_of", "characterizes",
            "BFO_0000052"],
            inverse=True),
    ],
    "Role": [
        ConstitutivePattern("Borne by", [
            "inheres_in", "role_of", "BFO_0000052"], inverse=True),
        ConstitutivePattern("Realized in", ["realized_in", "realizes"]),
    ],
    "Disposition": [
        ConstitutivePattern("Borne by", [
            "inheres_in", "disposition_of", "BFO_0000052"], inverse=True),
        ConstitutivePattern("Triggered by", ["realized_in", "has_realization"]),
    ],
    "InformationContentEntity": [
        ConstitutivePattern("About", [
            "is_about", "describes", "represents", "denotes"]),
        ConstitutivePattern("Carried by", [
            "generically_depends_on", "concretized_by"]),
    ],
    "MaterialEntity": [
        ConstitutivePattern("Parts", ["has_part", "has_component"]),
        ConstitutivePattern("Bears", [
            "bearer_of", "has_role", "has_disposition", "has_quality"]),
    ],
    "Agent": [
        ConstitutivePattern("Participates in", [
            "participates_in", "agent_in", "performs"]),
        ConstitutivePattern("Bears role", ["bearer_of", "has_role"]),
    ],
    "MaterialArtifact": [
        ConstitutivePattern("Parts", ["has_part", "has_component"]),
        ConstitutivePattern("Function", ["has_function", "has_disposition"]),
    ],
    "Act": [
        ConstitutivePattern("Participants", [
            "has_participant", "has_agent", "has_patient", "BFO_0000057"]),
        ConstitutivePattern("Realizes", ["realizes"]),
    ],
    "Facility": [
        ConstitutivePattern("Located in", ["located_in", "has_site"]),
        ConstitutivePattern("Houses", ["has_part", "contains"]),
    ],
    "GenericallyDependentContinuant": [
        ConstitutivePattern("About", ["is_about", "describes"]),
        ConstitutivePattern("Concretized by", [
            "concretized_by", "generically_depends_on"]),
    ],
}


# ---------------------------------------------------------------------------
# Property-URI matching
# ---------------------------------------------------------------------------

def _tokenize(name: str) -> list[str]:
    """Split a local name into lowercase tokens on underscores and camelCase boundaries."""
    underscored = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    return [t.lower() for t in underscored.split("_") if t]


def match_property(property_uri: str, patterns: list[str]) -> bool:
    """Return True if the local part of *property_uri* matches any pattern.

    Matching rules:
    - Extract the local name (after ``#`` or last ``/``).
    - BFO numeric identifiers (e.g. ``BFO_0000057``) are matched literally,
      case-insensitively.
    - Other patterns are tokenised on underscores and camelCase boundaries,
      then matched as a contiguous subsequence of the URI's tokens.
    """
    local = property_uri.rsplit("#", 1)[-1].rsplit("/", 1)[-1]
    local_lower = local.lower()
    local_tokens = _tokenize(local)

    for pat in patterns:
        pat_lower = pat.lower()
        # BFO numeric ID — exact match only
        if pat_lower.startswith("bfo_") and pat_lower == local_lower:
            return True
        # Token-based subsequence match
        pat_tokens = _tokenize(pat)
        if not pat_tokens:
            continue
        for i in range(len(local_tokens) - len(pat_tokens) + 1):
            if local_tokens[i:i + len(pat_tokens)] == pat_tokens:
                return True
    return False
