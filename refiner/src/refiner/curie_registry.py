"""Shared CURIE prefix registry for consistent URI handling across the pipeline.

Convention: internal data structures and outputs use CURIEs (compact).
Outputs include a curie_map so downstream consumers can expand to full URIs.
LLM prompts use labels only, never URIs.
"""

# Canonical prefix → URI mapping, aligned with SSSOM curie_maps and AIRO/Nexus schemas.
CURIE_MAP: dict[str, str] = {
    "airo": "https://w3id.org/airo#",
    "eu-aiact": "https://w3id.org/dpv/legal/eu/aiact#",
    "pd": "https://w3id.org/dpv/pd#",
    "risk": "https://w3id.org/dpv/risk#",
    "eu-rights": "https://w3id.org/dpv/legal/eu/rights#",
    "justifications": "https://w3id.org/dpv/justifications#",
    "tech": "https://w3id.org/dpv/tech#",
    "sector-finance": "https://w3id.org/dpv/sector/finance#",
    "sector-health": "https://w3id.org/dpv/sector/health#",
    "sector-law": "https://w3id.org/dpv/sector/law#",
    "sector-education": "https://w3id.org/dpv/sector/education#",
    "sector-infra": "https://w3id.org/dpv/sector/infra#",
    "sector-publicservices": "https://w3id.org/dpv/sector/publicservices#",
    "cco": "https://www.commoncoreontologies.org/",
    "bfo": "http://purl.obolibrary.org/obo/BFO_",
    "fibo": "https://spec.edmcouncil.org/fibo/ontology/",
    "obo": "http://purl.obolibrary.org/obo/",
    "d3fend": "http://d3fend.mitre.org/ontologies/d3fend.owl#",
    "cso": "http://taxonomy-refiner.io/ontologies/cso#",
    "lkif": "http://www.estrellaproject.org/lkif-core/",
}


def expand_curie(curie: str) -> str:
    """Expand a CURIE to a full URI. Returns unchanged if already a URI or unknown prefix."""
    if not curie or curie.startswith("http://") or curie.startswith("https://"):
        return curie
    if ":" not in curie:
        return curie
    prefix, _, local = curie.partition(":")
    if prefix in CURIE_MAP:
        return CURIE_MAP[prefix] + local
    return curie


def compact_uri(uri: str) -> str:
    """Compact a full URI to a CURIE. Returns unchanged if no matching prefix."""
    if not uri:
        return uri
    for prefix, base in CURIE_MAP.items():
        if uri.startswith(base):
            return f"{prefix}:{uri[len(base):]}"
    return uri
