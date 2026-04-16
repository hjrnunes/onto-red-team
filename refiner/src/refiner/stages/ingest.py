import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Literal

import instructor
from pydantic import BaseModel
from refiner.llm import LLMConfig
from refiner.models import (
    BoundaryExample,
    AiSystem,
    Policy,
    PolicyDecomposition,
    PolicyProfile,
    RegulatoryReference,
    RunReport,
    Stakeholder,
)
from refiner import debug

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Slim response models (private, no docstrings)
# ---------------------------------------------------------------------------

class _SlimNamedEntity(BaseModel):
    name: str
    role: str


class _SlimContext(BaseModel):
    organization: str
    domain: str
    purpose: list[str]
    ai_systems: list[str]
    ai_users: list[str]
    ai_subjects: list[str]
    governing_regulations: list[str]
    named_entities: list[_SlimNamedEntity]


class _SlimPolicy(BaseModel):
    policy_concept: str
    concept_definition: str


class _SlimPolicyList(BaseModel):
    policies: list[_SlimPolicy]


class _SlimBoundaryExample(BaseModel):
    prohibited: str
    acceptable: str


class _SlimEnrichment(BaseModel):
    policy_concept: str
    boundary_examples: list[_SlimBoundaryExample]
    acceptable_uses: list[str]
    risk_controls: list[str]
    human_involvement: str = ""
    agent: str = ""
    activity: str = ""
    entity: str = ""


class _SlimEnrichmentList(BaseModel):
    enrichments: list[_SlimEnrichment]


# ---------------------------------------------------------------------------
# CoT loading
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _load_cot() -> dict:
    cot_path = Path(__file__).parent.parent / "templates" / "ingest_cot.json"
    with open(cot_path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _build_context_prompt(document_text: str) -> str:
    cot = _load_cot()
    lines = [
        "Extract organizational context from this policy document.",
        "",
        "Return: organization name, domain/industry, purpose of AI use, "
        "AI systems mentioned, AI users, AI subjects, governing regulations, "
        "and named entities (people, products, departments with their roles).",
        "",
    ]

    examples = cot.get("context_examples", [])
    if examples:
        lines.append("=== EXAMPLE ===")
        for ex in examples:
            lines.append(f"Input excerpt:\n{ex['input_excerpt']}")
            lines.append(f"Extracted:\n{json.dumps(ex['extracted'], indent=2)}")
        lines.append("=== END EXAMPLE ===")
        lines.append("")

    lines.append("=== DOCUMENT ===")
    lines.append(document_text)
    lines.append("=== END DOCUMENT ===")

    return "\n".join(lines)


def _build_policies_prompt(document_text: str, context: _SlimContext) -> str:
    cot = _load_cot()
    lines = [
        "Extract individual policy rules from this document.",
        "",
        f"Organization: {context.organization}",
        f"Domain: {context.domain}",
        "",
        "For each distinct policy rule, return the policy_concept (short name) "
        "and concept_definition (detailed description of what is prohibited or controlled).",
        "",
    ]

    examples = cot.get("policy_examples", [])
    if examples:
        lines.append("=== EXAMPLE ===")
        for ex in examples:
            lines.append(f"Input excerpt:\n{ex['input_excerpt']}")
            lines.append(f"Extracted:\n{json.dumps(ex['extracted'], indent=2)}")
        lines.append("=== END EXAMPLE ===")
        lines.append("")

    lines.append("=== DOCUMENT ===")
    lines.append(document_text)
    lines.append("=== END DOCUMENT ===")

    return "\n".join(lines)


def _build_enrichment_prompt(
    document_text: str,
    context: _SlimContext,
    policies: list[Policy],
) -> str:
    cot = _load_cot()
    lines = [
        "Enrich each policy with boundary examples, acceptable uses, "
        "risk controls, and human involvement requirements.",
        "",
        f"Organization: {context.organization}",
        f"Domain: {context.domain}",
        "",
        "Policies to enrich:",
    ]
    for p in policies:
        lines.append(f"- {p.policy_concept}: {p.concept_definition}")
    lines.append("")

    lines.append(
        "For each policy, provide:\n"
        "- boundary_examples: pairs of prohibited vs acceptable use\n"
        "- acceptable_uses: list of explicitly permitted uses\n"
        "- risk_controls: mitigations or guardrails mentioned\n"
        "- human_involvement: any human oversight requirement\n"
        "- agent: who performs the governed action (e.g. 'AI assistant', 'clinician', 'the system')\n"
        "- activity: what action is being governed (e.g. 'diagnose', 'disclose', 'recommend')\n"
        "- entity: what is acted upon (e.g. 'patient data', 'financial records', 'personal information')"
    )
    lines.append("")

    examples = cot.get("enrichment_examples", [])
    if examples:
        lines.append("=== EXAMPLE ===")
        for ex in examples:
            lines.append(f"Policy: {ex['policy_concept']}")
            lines.append(f"Input excerpt:\n{ex['input_excerpt']}")
            lines.append(f"Extracted:\n{json.dumps(ex['extracted'], indent=2)}")
        lines.append("=== END EXAMPLE ===")
        lines.append("")

    lines.append("=== DOCUMENT ===")
    lines.append(document_text)
    lines.append("=== END DOCUMENT ===")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Pass 1: Context extraction
# ---------------------------------------------------------------------------

def extract_context(
    document_text: str,
    client: instructor.Instructor,
    config: LLMConfig,
    report: RunReport | None = None,
) -> _SlimContext:
    prompt = _build_context_prompt(document_text)
    messages = [{"role": "user", "content": prompt}]

    result = client.chat.completions.create(
        model=config.model,
        response_model=_SlimContext,
        messages=messages,
        temperature=config.temperature,
        max_retries=config.max_retries,
        max_tokens=config.max_tokens,
    )
    debug.log_call("ingest_context", messages, result)

    if report:
        # Count populated fields
        fields_populated = sum(1 for v in [
            result.organization, result.domain, result.purpose,
            result.ai_systems, result.ai_users, result.ai_subjects,
            result.governing_regulations, result.named_entities,
        ] if v)
        report.events.append({
            "stage": "ingest",
            "event": "context_extracted",
            "organization": result.organization,
            "domain": result.domain,
            "fields_populated": fields_populated,
        })

        # Warn on missing critical fields
        missing = []
        if not result.organization:
            missing.append("organization")
        if not result.domain:
            missing.append("domain")
        if missing:
            report.events.append({
                "stage": "ingest",
                "event": "context_weak_inference",
                "missing_fields": missing,
            })

    return result


# ---------------------------------------------------------------------------
# Pass 2: Policy extraction
# ---------------------------------------------------------------------------

def extract_policies(
    document_text: str,
    context: _SlimContext,
    client: instructor.Instructor,
    config: LLMConfig,
    report: RunReport | None = None,
) -> list[Policy]:
    prompt = _build_policies_prompt(document_text, context)
    messages = [{"role": "user", "content": prompt}]

    result = client.chat.completions.create(
        model=config.model,
        response_model=_SlimPolicyList,
        messages=messages,
        temperature=config.temperature,
        max_retries=config.max_retries,
        max_tokens=config.max_tokens,
    )
    debug.log_call("ingest_policies", messages, result)

    policies = [
        Policy(
            policy_concept=p.policy_concept,
            concept_definition=p.concept_definition,
        )
        for p in result.policies
    ]

    if report:
        report.events.append({
            "stage": "ingest",
            "event": "policies_extracted",
            "count": len(policies),
        })

    return policies


# ---------------------------------------------------------------------------
# JSON array parser (pure function, no LLM)
# ---------------------------------------------------------------------------

def parse_json_policies(json_text: str) -> list[Policy]:
    raw = json.loads(json_text)
    return [
        Policy(
            policy_concept=entry.get("policy_concept", ""),
            concept_definition=entry.get("concept_definition", ""),
        )
        for entry in raw
    ]


# ---------------------------------------------------------------------------
# Pass 3: Policy enrichment
# ---------------------------------------------------------------------------

def enrich_policies(
    document_text: str,
    context: _SlimContext,
    policies: list[Policy],
    client: instructor.Instructor,
    config: LLMConfig,
    report: RunReport | None = None,
) -> list[Policy]:
    prompt = _build_enrichment_prompt(document_text, context, policies)
    messages = [{"role": "user", "content": prompt}]

    result = client.chat.completions.create(
        model=config.model,
        response_model=_SlimEnrichmentList,
        messages=messages,
        temperature=config.temperature,
        max_retries=config.max_retries,
        max_tokens=config.max_tokens,
    )
    debug.log_call("ingest_enrichment", messages, result)

    # Build lookup by policy_concept
    enrichment_map: dict[str, _SlimEnrichment] = {}
    for e in result.enrichments:
        enrichment_map[e.policy_concept] = e

    # Create new Policy objects (don't mutate inputs)
    enriched: list[Policy] = []
    policies_enriched = 0
    boundary_pairs_total = 0
    policies_with_zero_pairs = 0

    for p in policies:
        e = enrichment_map.get(p.policy_concept)
        if e is not None:
            policies_enriched += 1
            boundary_pairs_total += len(e.boundary_examples)
            if not e.boundary_examples:
                policies_with_zero_pairs += 1
            decomposition = None
            if e.agent or e.activity or e.entity:
                decomposition = PolicyDecomposition(
                    agent=e.agent or None,
                    activity=e.activity or None,
                    entity=e.entity or None,
                )
            enriched.append(Policy(
                policy_concept=p.policy_concept,
                concept_definition=p.concept_definition,
                boundary_examples=[
                    BoundaryExample(prohibited=b.prohibited, acceptable=b.acceptable)
                    for b in e.boundary_examples
                ],
                acceptable_uses=e.acceptable_uses,
                risk_controls=e.risk_controls,
                human_involvement=e.human_involvement if e.human_involvement else None,
                decomposition=decomposition,
            ))
        else:
            policies_with_zero_pairs += 1
            enriched.append(Policy(
                policy_concept=p.policy_concept,
                concept_definition=p.concept_definition,
            ))

    if report:
        report.events.append({
            "stage": "ingest",
            "event": "enrichment_stats",
            "policies_enriched": policies_enriched,
            "boundary_pairs_total": boundary_pairs_total,
            "policies_with_zero_pairs": policies_with_zero_pairs,
        })

    return enriched


# ---------------------------------------------------------------------------
# Helper: build PolicyProfile from context + policies
# ---------------------------------------------------------------------------

def _build_document(context: _SlimContext, policies: list[Policy]) -> PolicyProfile:
    stakeholders: list[Stakeholder] = []
    for u in context.ai_users:
        stakeholders.append(Stakeholder(name=u, roles=["airo:AIUser"]))
    for s in context.ai_subjects:
        stakeholders.append(Stakeholder(name=s, roles=["airo:AISubject"]))
    for ne in context.named_entities:
        stakeholders.append(Stakeholder(name=ne.name, roles=[ne.role]))
    return PolicyProfile(
        organization=Stakeholder(name=context.organization) if context.organization else None,
        domain=context.domain,
        purpose=context.purpose,
        ai_systems=[AiSystem(name=s) for s in context.ai_systems],
        stakeholders=stakeholders,
        regulations=[RegulatoryReference(name=r) for r in context.governing_regulations],
        policies=policies,
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def ingest(
    document_text: str,
    input_format: Literal["markdown", "json_array"],
    client: instructor.Instructor,
    config: LLMConfig,
    skip_enrichment: bool = False,
    until: str | None = None,
    domain_override: str | None = None,
    organization_override: str | None = None,
    report: RunReport | None = None,
) -> PolicyProfile:
    if report:
        report.events.append({
            "stage": "ingest",
            "event": "input_format_detected",
            "format": input_format,
        })

    # Pass 1: Context extraction (always)
    context = extract_context(document_text, client, config, report=report)

    # Apply overrides
    if domain_override:
        context = context.model_copy(update={"domain": domain_override})
    if organization_override:
        context = context.model_copy(update={"organization": organization_override})

    if until == "context":
        return _build_document(context, [])

    # Pass 2: Policy extraction
    if input_format == "json_array":
        policies = parse_json_policies(document_text)
        if report:
            report.events.append({
                "stage": "ingest",
                "event": "policies_extracted",
                "count": len(policies),
                "skipped": True,
            })
    else:
        policies = extract_policies(document_text, context, client, config, report=report)

    if until == "policies":
        return _build_document(context, policies)

    # Pass 3: Enrichment
    if not skip_enrichment:
        policies = enrich_policies(
            document_text, context, policies, client, config, report=report,
        )
    else:
        if report:
            report.events.append({
                "stage": "ingest",
                "event": "enrichment_skipped",
            })

    return _build_document(context, policies)
