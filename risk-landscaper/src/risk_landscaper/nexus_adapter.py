"""Nexus adapter — converts AI Atlas Nexus payloads to ORT pipeline inputs.

Implements the UGA-ORT semantic bridge (Layer A: input projection).
See docs/superpowers/specs/2026-04-16-uga-ort-bridge-design.md
"""
from risk_landscaper.models import (
    AiSystem,
    Policy,
    PolicyProfile,
    Stakeholder,
)

# Nexus EuAiRiskCategory enum → ORT risk_level Literal
_EU_RISK_MAP = {
    "HIGH_RISK": "high",
    "HIGH_RISK_EXCEPTION": "high",
    "LIMITED_OR_LOW_RISK": "limited",
    "EXCLUDED": "minimal",
    "PROHIBITED": "high",
}


def detect_nexus_format(raw: dict | list) -> bool:
    """Detect whether a parsed JSON payload is in nexus format.

    Nexus format is a dict with 'risks' key (list of Risk entities)
    and optionally 'ai_system'. Distinguished from PolicyProfile
    (which has 'policies') and flat arrays.
    """
    if isinstance(raw, list):
        return False
    if not isinstance(raw, dict):
        return False
    if "policies" in raw:
        return False
    return "risks" in raw


def project_risk_to_policy(risk: dict) -> Policy:
    """Project a nexus Risk entity into an ORT Policy.

    Uses Risk.concern as the policy definition (default), falling back
    to Risk.description, then Risk.name.
    """
    name = risk.get("name", "")
    concern = risk.get("concern", "")
    description = risk.get("description", "")
    definition = concern if concern else (description if description else name)
    return Policy(policy_concept=name, concept_definition=definition)


def nexus_to_policy_profile(payload: dict) -> PolicyProfile:
    """Convert a nexus-format payload to an ORT PolicyProfile.

    Expected payload structure:
        ai_system: dict (nexus AiSystem fields)
        risks: list[dict] (nexus Risk entities, each with id/name/concern)
        risk_controls: list[dict] (optional, nexus RiskControl entities)
    """
    ai_system_data = payload.get("ai_system", {})
    risks = payload.get("risks", [])
    risk_controls = payload.get("risk_controls", [])

    control_descriptions = [
        rc.get("description", rc.get("name", ""))
        for rc in risk_controls
        if rc.get("description") or rc.get("name")
    ]

    organization = None
    dev = ai_system_data.get("isDevelopedBy")
    if dev:
        org_name = dev if isinstance(dev, str) else dev.get("name", "")
        if org_name:
            organization = Stakeholder(name=org_name, roles=["airo:AIDeveloper"])

    ai_systems = []
    if ai_system_data and ai_system_data.get("name"):
        purpose_raw = ai_system_data.get("hasPurpose", [])
        if isinstance(purpose_raw, str):
            purpose_raw = [purpose_raw]
        ai_systems.append(AiSystem(
            name=ai_system_data.get("name", ""),
            description=ai_system_data.get("description"),
            purpose=purpose_raw,
            risk_level=_EU_RISK_MAP.get(
                ai_system_data.get("hasEuRiskCategory", ""),
                ai_system_data.get("hasEuRiskCategory"),
            ),
        ))

    domain_raw = ai_system_data.get("isAppliedWithinDomain")
    domain = domain_raw if isinstance(domain_raw, str) else (
        domain_raw.get("name", "") if isinstance(domain_raw, dict) else None
    )

    stakeholders = []
    deployer = ai_system_data.get("isDeployedBy")
    if deployer:
        dep_name = deployer if isinstance(deployer, str) else deployer.get("name", "")
        if dep_name:
            stakeholders.append(Stakeholder(name=dep_name, roles=["airo:AIDeployer"]))

    for user in ai_system_data.get("hasAIUser", []):
        u_name = user if isinstance(user, str) else user.get("name", "")
        if u_name:
            stakeholders.append(Stakeholder(name=u_name, roles=["airo:AIUser"]))

    for subject in ai_system_data.get("hasAISubject", []):
        s_name = subject if isinstance(subject, str) else subject.get("name", "")
        if s_name:
            stakeholders.append(Stakeholder(name=s_name, roles=["airo:AISubject"]))

    policies = [project_risk_to_policy(r) for r in risks]

    if control_descriptions:
        policies = [
            Policy(
                policy_concept=p.policy_concept,
                concept_definition=p.concept_definition,
                risk_controls=control_descriptions,
            )
            for p in policies
        ]

    purpose = ai_system_data.get("hasPurpose", [])
    if isinstance(purpose, str):
        purpose = [purpose]

    return PolicyProfile(
        organization=organization,
        domain=domain,
        purpose=purpose,
        ai_systems=ai_systems,
        stakeholders=stakeholders,
        policies=policies,
    )
