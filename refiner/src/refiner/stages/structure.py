import logging
import re

from refiner.models import (
    PolicyClassification,
    PolicyRiskMapping,
    DomainContextProfile,
)

logger = logging.getLogger(__name__)

POLICY_TYPE_GROUPS = {
    "A": ("safety", "Safety Policies"),
    "B": ("confidentiality", "Confidentiality Policies"),
    "C": ("scope-regulatory", "Scope & Regulatory Policies"),
    "D": ("routing", "Routing Policies"),
}


def slugify(text: str) -> str:
    slug = text.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug)
    return slug


def structure(
    client_slug: str,
    classifications: list[PolicyClassification],
    risk_mappings: list[PolicyRiskMapping],
    domain_context: list[DomainContextProfile],
    valid_risk_ids: set[str] | None = None,
) -> tuple[dict, dict]:
    taxonomy_id = f"client-{client_slug}"

    # Determine which policy types are present
    policy_types_present = {c.policy_type for c in classifications}

    # Build groups
    groups = []
    for ptype in sorted(policy_types_present):
        slug, name = POLICY_TYPE_GROUPS[ptype]
        groups.append({
            "id": f"{taxonomy_id}-{slug}",
            "name": name,
            "type": "RiskGroup",
            "isDefinedByTaxonomy": taxonomy_id,
        })

    # Build entries from risk mappings
    entries = []
    for mapping in risk_mappings:
        ptype = mapping.policy_type
        group_slug = POLICY_TYPE_GROUPS.get(ptype, ("unknown", "Unknown"))[0]
        group_id = f"{taxonomy_id}-{group_slug}"

        for rm in mapping.matched_risks:
            entry = {
                "id": f"{taxonomy_id}-{slugify(rm.risk_name)}",
                "name": rm.risk_name,
                "type": "Risk",
                "isDefinedByTaxonomy": taxonomy_id,
                "isPartOf": group_id,
                "tag": slugify(rm.risk_name),
            }
            # Add cross-mappings for this risk's source
            for cm in mapping.cross_mappings:
                if cm.source_risk_id == rm.risk_id:
                    # Validate target exists if valid_risk_ids provided
                    if valid_risk_ids is not None and cm.target_risk_id not in valid_risk_ids:
                        logger.warning("Skipping unknown cross-mapping target: %s", cm.target_risk_id)
                        continue
                    key = f"{cm.mapping_type}_mappings"
                    entry.setdefault(key, []).append(cm.target_risk_id)
            entries.append(entry)

    taxonomy = {
        "taxonomies": [
            {
                "id": taxonomy_id,
                "name": f"Client {client_slug.upper()} Policy Taxonomy",
                "type": "RiskTaxonomy",
            },
        ],
        "groups": groups,
        "entries": entries,
    }

    # Build domain context profiles output
    profiles = {
        "profiles": [p.model_dump() for p in domain_context],
    }

    return taxonomy, profiles
