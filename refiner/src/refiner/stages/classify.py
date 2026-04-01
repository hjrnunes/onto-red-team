import logging

import instructor
from refiner.llm import LLMConfig
from refiner.models import Policy, PolicyClassification

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are classifying client content policies for an LLM deployment.

Classify each policy into exactly one type:
- A (Safety): Harmful content, violence, illegal activity, hate speech, self-harm, etc.
- B (Confidentiality): Protecting sensitive, proprietary, or personal information
- C (Scope/Regulatory): Regulatory compliance, scope limitations, sanctions, jurisdiction
- D (Routing): Redirecting certain queries to humans or other systems

For each policy, return the policy_concept, concept_definition, policy_type, and a brief justification."""


def classify(
    policies: list[Policy],
    client: instructor.Instructor,
    config: LLMConfig,
) -> list[PolicyClassification]:
    if not policies:
        return []

    policy_lines = []
    for i, p in enumerate(policies, 1):
        policy_lines.append(f"{i}. {p.policy_concept}: {p.concept_definition}")
    user_content = "Classify these policies:\n\n" + "\n".join(policy_lines)

    result = client.chat.completions.create(
        model=config.model,
        response_model=list[PolicyClassification],
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=config.temperature,
        max_retries=config.max_retries,
        max_tokens=config.max_tokens,
    )
    return result
