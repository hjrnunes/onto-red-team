"""Ingest report: confidence computation and HTML generation."""

import json
from pathlib import Path

from refiner.models import PolicyDocument, RunReport


_AIRO_ROLES = {"airo:AIUser", "airo:AISubject", "airo:AIProvider", "airo:AIDeployer"}


def _context_confidence(doc: PolicyDocument) -> dict:
    """Compute green/amber/red for each context-level field."""
    ctx = {}
    ctx["organization"] = "green" if doc.organization and doc.organization.name else "red"
    ctx["domain"] = "green" if doc.domain else "red"
    ctx["purpose"] = "green" if doc.purpose else "red"
    ctx["governed_systems"] = "green" if doc.governed_systems else "red"

    if not doc.stakeholders:
        ctx["stakeholders"] = "red"
    else:
        has_governance = any(
            role and role not in _AIRO_ROLES
            for s in doc.stakeholders
            for role in s.roles
        )
        ctx["stakeholders"] = "green" if has_governance else "amber"

    if not doc.regulations:
        ctx["regulations"] = "red"
    else:
        all_complete = all(r.jurisdiction or r.reference for r in doc.regulations)
        ctx["regulations"] = "green" if all_complete else "amber"

    return ctx


def _policy_confidence(doc: PolicyDocument) -> list[dict]:
    """Compute green/amber/red for each per-policy field."""
    results = []
    for p in doc.policies:
        pc = {"policy_concept": p.policy_concept}
        pc["boundary_examples"] = "green" if p.boundary_examples else "red"
        pc["acceptable_uses"] = "green" if p.acceptable_uses else "amber"
        pc["risk_controls"] = "green" if p.risk_controls else "amber"
        pc["human_involvement"] = "green" if p.human_involvement else "amber"

        if p.decomposition is None:
            pc["decomposition"] = "red"
        else:
            filled = sum(1 for f in [p.decomposition.agent, p.decomposition.activity, p.decomposition.entity] if f)
            if filled == 3:
                pc["decomposition"] = "green"
            elif filled >= 1:
                pc["decomposition"] = "amber"
            else:
                pc["decomposition"] = "red"

        results.append(pc)
    return results


def _summary(doc: PolicyDocument, report: RunReport) -> dict:
    """Compute aggregate summary stats."""
    policies_enriched = sum(
        1 for p in doc.policies if p.boundary_examples or p.acceptable_uses or p.risk_controls
    )
    boundary_pairs_total = sum(len(p.boundary_examples) for p in doc.policies)
    policies_with_zero_pairs = sum(1 for p in doc.policies if not p.boundary_examples)

    weak_inferences = []
    for ev in report.events:
        if ev.get("event") == "context_weak_inference":
            weak_inferences.extend(ev.get("missing_fields", []))

    return {
        "policies_total": len(doc.policies),
        "policies_enriched": policies_enriched,
        "boundary_pairs_total": boundary_pairs_total,
        "policies_with_zero_pairs": policies_with_zero_pairs,
        "weak_inferences": weak_inferences,
    }


def build_report_data(
    doc: PolicyDocument,
    report: RunReport,
    meta: dict,
) -> dict:
    """Combine PolicyDocument + RunReport events into report payload."""
    return {
        "meta": meta,
        "document": doc.model_dump(),
        "confidence": {
            "context": _context_confidence(doc),
            "policies": _policy_confidence(doc),
            "summary": _summary(doc, report),
        },
    }
