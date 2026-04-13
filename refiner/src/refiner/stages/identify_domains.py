import logging
from typing import Literal

import instructor
from pydantic import BaseModel
from refiner.llm import LLMConfig
from refiner.models import Policy
from refiner import debug

logger = logging.getLogger(__name__)

# Domain ontologies available for selection by the LLM
DOMAIN_OPTIONS = {
    "FIBO": "Financial services — banking, securities, insurance, loans, regulatory compliance",
    "OBO": "Healthcare — diseases, drugs, anatomy, medical procedures, adverse events",
    "IOF": "Manufacturing — supply chain, maintenance, industrial processes, engineering",
}

# Always included regardless of LLM selection (domain-independent)
ALWAYS_INCLUDED = ["CCO", "Commons", "D3FEND", "CSO", "LKIF"]

SYSTEM_PROMPT = """\
You are identifying which domain ontologies are relevant for a set of client content policies.

Given the classified policies, select which domain ontologies should be used for grounding risk concepts. Pick ONLY domains that are directly relevant to the client's industry — do not select domains just because they might be tangentially useful.

Available domain ontologies:
{domain_list}

Return the relevant domain keys ordered by importance."""


class _DomainSelection(BaseModel):
    domains: list[str]
    justification: str


def derive_source_ontology(uri: str) -> str:
    """Map a class URI to its source ontology key.

    Delegates to ontoquery.index.derive_domain for the canonical mapping.
    """
    from ontoquery.index import derive_domain
    return derive_domain(uri)


def identify_domains(
    policies: list[Policy],
    client: instructor.Instructor,
    config: LLMConfig,
    report=None,
) -> list[str]:
    if not policies:
        return list(ALWAYS_INCLUDED)

    domain_list = "\n".join(f"- {key}: {desc}" for key, desc in DOMAIN_OPTIONS.items())
    system_content = SYSTEM_PROMPT.format(domain_list=domain_list)

    policy_lines = []
    for p in policies:
        policy_lines.append(f"- {p.policy_concept}: {p.concept_definition}")
    user_content = "Policies:\n\n" + "\n".join(policy_lines)

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]
    result = client.chat.completions.create(
        model=config.model,
        response_model=_DomainSelection,
        messages=messages,
        temperature=config.temperature,
        max_retries=config.max_retries,
        max_tokens=config.max_tokens,
    )
    debug.log_call("identify_domains", messages, result)

    # Validate returned keys, drop any the LLM hallucinated
    valid_domains = []
    for d in result.domains:
        if d in DOMAIN_OPTIONS:
            valid_domains.append(d)
        else:
            logger.warning("Filtering unknown domain key: %s", d)
            if report:
                report.events.append({"stage": "identify_domains", "event": "invalid_domain_key", "raw_key": d})

    selected = list(ALWAYS_INCLUDED) + valid_domains
    logger.info("Selected domains: %s (justification: %s)", selected, result.justification)

    if report:
        report.events.append({"stage": "identify_domains", "event": "selected_domains", "domains": selected})

    return selected
