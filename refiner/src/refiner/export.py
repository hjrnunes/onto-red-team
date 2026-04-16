"""Export layer — projections from DomainContext to various formats.

The DomainContext is the canonical artifact. These functions produce
views/projections for specific consumers (AIRO taxonomy, SSSOM, etc.).
"""
from refiner.stages.structure import structure, slugify


def export_taxonomy(
    client_slug: str,
    domain_context,
    risk_mappings=None,
    risk_landscape=None,
    related_risks=None,
    valid_risk_ids=None,
    report=None,
):
    """Export DomainContext as AIRO-compatible LinkML taxonomy.

    Accepts either risk_mappings (legacy) or risk_landscape (new).
    Returns (taxonomy_dict, domain_context_dict).
    """
    if risk_mappings is None and risk_landscape is not None:
        risk_mappings = risk_landscape.policy_mappings
        if related_risks is None:
            related_risks = {
                r.risk_id: r.cross_mappings
                for r in risk_landscape.risks if r.cross_mappings
            }
        if valid_risk_ids is None:
            valid_risk_ids = {r.risk_id for r in risk_landscape.risks}

    return structure(
        client_slug=client_slug,
        risk_mappings=risk_mappings or [],
        domain_context=domain_context,
        related_risks=related_risks,
        valid_risk_ids=valid_risk_ids,
        report=report,
    )
