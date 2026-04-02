import logging
import re

from refiner.models import (
    PolicyClassification,
    PolicyRiskMapping,
    DomainContextProfile,
    RunReport,
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
    slug = re.sub(r"-+", "-", slug)
    return slug


def structure(
    client_slug: str,
    classifications: list[PolicyClassification],
    risk_mappings: list[PolicyRiskMapping],
    domain_context: list[DomainContextProfile],
    related_risks: dict[str, list[dict]] | None = None,
    valid_risk_ids: set[str] | None = None,
    report: RunReport | None = None,
) -> tuple[dict, dict]:
    taxonomy_id = f"client-{client_slug}"

    # Build lookup from risk_id to domain context profile
    dc_by_risk_id: dict[str, DomainContextProfile] = {}
    for p in domain_context:
        if p.risk_id not in dc_by_risk_id:
            dc_by_risk_id[p.risk_id] = p

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

    # Build entries from risk mappings, deduplicating by entry ID
    entries_by_id: dict[str, dict] = {}
    for mapping in risk_mappings:
        ptype = mapping.policy_type
        group_slug = POLICY_TYPE_GROUPS.get(ptype, ("unknown", "Unknown"))[0]
        group_id = f"{taxonomy_id}-{group_slug}"

        for rm in mapping.matched_risks:
            entry_id = f"{taxonomy_id}-{slugify(rm.risk_name)}"
            if entry_id not in entries_by_id:
                entries_by_id[entry_id] = {
                    "id": entry_id,
                    "name": rm.risk_name,
                    "type": "Risk",
                    "isDefinedByTaxonomy": taxonomy_id,
                    "isPartOf": group_id,
                    "tag": slugify(rm.risk_name),
                }
            entry = entries_by_id[entry_id]
            # Add cross-mappings from knowledge graph ground truth
            if related_risks:
                for rel in related_risks.get(rm.risk_id, []):
                    target_id = rel["id"]
                    if valid_risk_ids is not None and target_id not in valid_risk_ids:
                        logger.warning("Skipping unknown cross-mapping target: %s", target_id)
                        if report:
                            report.events.append({
                                "stage": "structure", "event": "cross_mapping_filtered",
                                "target_id": target_id,
                            })
                        continue
                    key = f"{rel['mapping_type']}_mappings"
                    existing = entry.get(key, [])
                    if target_id not in existing:
                        entry.setdefault(key, []).append(target_id)

            # Attach domain context summary (only on first encounter of this entry)
            if "domain_context_summary" not in entry:
                profile = dc_by_risk_id.get(rm.risk_id)
                if profile and profile.axes:
                    axes_summary = []
                    all_ontologies: set[str] = set()
                    total_enums = 0
                    for axis in profile.axes:
                        enum_count = len(axis.enumerations)
                        total_enums += enum_count
                        for e in axis.enumerations:
                            all_ontologies.add(e.source_ontology)
                        axes_summary.append({
                            "class": axis.cco_class_label,
                            "uri": axis.cco_class_uri,
                            "roles": axis.roles,
                            "enumeration_count": enum_count,
                        })
                    entry["domain_context_summary"] = {
                        "axis_count": len(axes_summary),
                        "enumeration_count": total_enums,
                        "source_ontologies": sorted(all_ontologies),
                        "axes": axes_summary,
                    }
    entries = list(entries_by_id.values())

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
