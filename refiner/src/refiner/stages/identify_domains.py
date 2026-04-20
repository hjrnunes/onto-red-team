# Domain constants and utilities retained after stage moved to risk-landscaper.

DOMAIN_OPTIONS = {
    "FIBO": "Financial services — banking, securities, insurance, loans, regulatory compliance",
    "OBO": "Healthcare — diseases, drugs, anatomy, medical procedures, adverse events",
    "IOF": "Manufacturing — supply chain, maintenance, industrial processes, engineering",
}

ALWAYS_INCLUDED = ["CCO", "Commons", "D3FEND", "CSO", "LKIF"]


def derive_source_ontology(uri: str) -> str:
    """Map a class URI to its source ontology key."""
    from ontoquery.index import derive_domain
    return derive_domain(uri)
