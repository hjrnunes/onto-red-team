import logging

import instructor
from pydantic import BaseModel

from risk_landscaper.llm import LLMConfig
from risk_landscaper.models import PolicyProfile, RunReport
from risk_landscaper import debug

logger = logging.getLogger(__name__)

DOMAIN_MENU = {
    "healthcare": ["health", "medical", "clinical", "hospital", "patient", "pharma", "biomedical"],
    "financial_services": ["finance", "banking", "insurance", "investment", "trading", "loan", "credit"],
    "energy": ["energy", "oil", "gas", "power", "utility", "renewable", "petroleum"],
    "government": ["government", "public sector", "defense", "military", "intelligence", "civic"],
    "legal": ["legal", "law", "compliance", "regulatory", "judicial", "litigation"],
    "manufacturing": ["manufacturing", "industrial", "supply chain", "logistics", "engineering"],
    "technology": ["technology", "software", "cyber", "data", "cloud", "ai", "computing"],
    "education": ["education", "academic", "university", "school", "training", "research"],
    "general": [],
}

SYSTEM_PROMPT = """\
You are detecting the primary industry domain of a set of client content policies.

Given the policies below, identify the single most relevant domain from this list:
{domain_list}

Return just the domain key. If none fits well, return "general"."""


class _DomainDetection(BaseModel):
    domain: str


def normalize_domain(raw: str) -> str:
    lower = raw.lower().strip()
    if lower in DOMAIN_MENU:
        return lower
    for domain, keywords in DOMAIN_MENU.items():
        if domain == "general":
            continue
        for kw in keywords:
            if kw in lower:
                return domain
    return "general"


def detect_domain(
    profile: PolicyProfile,
    client: instructor.Instructor,
    config: LLMConfig,
    report: RunReport | None = None,
) -> list[str]:
    if profile.domain:
        normalized = normalize_domain(profile.domain)
        logger.info("Domain from profile: %s (normalized: %s)", profile.domain, normalized)
        if report:
            report.events.append({
                "stage": "detect_domain",
                "event": "domain_detected",
                "domain": normalized,
                "source": "profile",
            })
        return [normalized]

    if not profile.policies:
        if report:
            report.events.append({
                "stage": "detect_domain",
                "event": "domain_detected",
                "domain": "general",
                "source": "default",
            })
        return ["general"]

    domain_list = "\n".join(f"- {key}" for key in DOMAIN_MENU if key != "general")
    system_content = SYSTEM_PROMPT.format(domain_list=domain_list)

    policy_lines = [f"- {p.policy_concept}: {p.concept_definition}" for p in profile.policies]
    user_content = "Policies:\n\n" + "\n".join(policy_lines)

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]
    result = client.chat.completions.create(
        model=config.model,
        response_model=_DomainDetection,
        messages=messages,
        temperature=config.temperature,
        max_retries=config.max_retries,
        max_tokens=config.max_tokens,
    )
    debug.log_call("detect_domain", messages, result)

    normalized = normalize_domain(result.domain)
    logger.info("Detected domain: %s (raw: %s, normalized: %s)", result.domain, result.domain, normalized)

    if report:
        report.events.append({
            "stage": "detect_domain",
            "event": "domain_detected",
            "domain": normalized,
            "source": "llm",
            "raw": result.domain,
        })

    return [normalized]
