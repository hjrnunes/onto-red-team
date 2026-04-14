from refiner.models import (
    PolicyDocument,
    PolicyRiskMapping,
    PolicySourceRef,
    RiskDetail,
    RiskLandscape,
    KnowledgeBaseRef,
    WeakMatch,
)

WEAK_MATCH_THRESHOLD = 0.6

FRAMEWORK_PREFIXES = {
    "atlas-": "ibm-risk-atlas",
    "nist-": "nist-ai-rmf",
    "owasp-": "owasp-llm",
    "llm0": "owasp-llm",
    "air-": "air-2024",
    "mit-ai-risk": "mit-ai-risk",
    "ailuminate-": "ailuminate",
    "credo-": "credo",
    "aiuc-": "aiuc",
    "csiro-": "csiro",
}


def _detect_framework(risk_id: str) -> str:
    for prefix, framework in FRAMEWORK_PREFIXES.items():
        if risk_id.startswith(prefix):
            return framework
    return "unknown"


def build_risk_landscape(
    mappings: list[PolicyRiskMapping],
    risk_details_cache: dict[str, dict],
    related_risks: dict[str, list[dict]] | None = None,
    risk_actions: dict[str, list[str]] | None = None,
    selected_domains: list[str] | None = None,
    model: str = "",
    run_slug: str = "",
    timestamp: str = "",
    doc_context: PolicyDocument | None = None,
    knowledge_base: KnowledgeBaseRef | None = None,
) -> RiskLandscape:
    related_risks = related_risks or {}
    risk_actions = risk_actions or {}

    # Build normalized risk registry (deduplicated)
    seen_risk_ids: set[str] = set()
    risks: list[RiskDetail] = []
    framework_counts: dict[str, int] = {}
    weak_matches: list[WeakMatch] = []

    for mapping in mappings:
        for rm in mapping.matched_risks:
            # Collect weak matches
            if rm.match_distance is not None and rm.match_distance > WEAK_MATCH_THRESHOLD:
                weak_matches.append(WeakMatch(
                    risk_id=rm.risk_id,
                    policy_concept=mapping.policy_concept,
                    distance=rm.match_distance,
                ))

            if rm.risk_id in seen_risk_ids:
                continue
            seen_risk_ids.add(rm.risk_id)

            details = risk_details_cache.get(rm.risk_id, {})
            framework = _detect_framework(rm.risk_id)
            risks.append(RiskDetail(
                risk_id=rm.risk_id,
                risk_name=details.get("name", rm.risk_name),
                risk_description=details.get("description", ""),
                risk_concern=details.get("concern", ""),
                risk_framework=framework,
                cross_mappings=related_risks.get(rm.risk_id, []),
                related_actions=risk_actions.get(rm.risk_id, []),
            ))

            framework_counts[framework] = framework_counts.get(framework, 0) + 1

    # Build policy source from PolicyDocument
    policy_source = None
    if doc_context:
        policy_source = PolicySourceRef(
            organization=doc_context.organization.name if doc_context.organization else None,
            domain=doc_context.domain,
            policy_count=len(doc_context.policies),
        )

    return RiskLandscape(
        model=model,
        timestamp=timestamp,
        run_slug=run_slug,
        selected_domains=selected_domains or [],
        policy_source=policy_source,
        knowledge_base=knowledge_base,
        risks=risks,
        policy_mappings=mappings,
        framework_coverage=framework_counts,
        weak_matches=weak_matches,
    )
