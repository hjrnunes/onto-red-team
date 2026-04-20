from risk_landscaper.models import (
    CoverageGap,
    PolicyProfile,
    PolicyRiskMapping,
    PolicySourceRef,
    RiskDetail,
    RiskLandscape,
    KnowledgeBaseRef,
    WeakMatch,
)

WEAK_MATCH_THRESHOLD = 0.6

FRAMEWORK_PREFIXES = {
    "atlas-": "IBM Risk Atlas",
    "nist-": "NIST AI RMF",
    "owasp-": "OWASP LLM Top 10",
    "llm0": "OWASP LLM Top 10",
    "ai-risk-taxonomy-": "AIR 2024",
    "air-": "AIR 2024",
    "mit-ai-risk": "MIT AI Risk Repository",
    "ail-": "AILuminate",
    "credo-": "Credo AI",
    "aiuc-": "AIUC-1",
    "csiro-": "CSIRO",
    "shieldgemma-": "ShieldGemma",
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
    policy_profile: PolicyProfile | None = None,
    knowledge_base: KnowledgeBaseRef | None = None,
    coverage_gaps: list[CoverageGap] | None = None,
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
                risk_name=details.get("name") or rm.risk_name or rm.risk_id,
                risk_description=details.get("description") or "",
                risk_concern=details.get("concern") or "",
                risk_framework=framework,
                cross_mappings=related_risks.get(rm.risk_id, []),
                related_actions=risk_actions.get(rm.risk_id, []),
            ))

            framework_counts[framework] = framework_counts.get(framework, 0) + 1

    # Build policy source from PolicyProfile
    policy_source = None
    if policy_profile:
        policy_source = PolicySourceRef(
            organization=policy_profile.organization.name if policy_profile.organization else None,
            domain=policy_profile.domain,
            policy_count=len(policy_profile.policies),
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
        coverage_gaps=coverage_gaps or [],
    )
