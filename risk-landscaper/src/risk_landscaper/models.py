from typing import Literal
from dataclasses import dataclass, field
from pydantic import BaseModel, field_validator, model_validator


class BoundaryExample(BaseModel):
    prohibited: str
    acceptable: str


class NamedEntity(BaseModel):
    name: str
    role: str


# --- AIRO-grounded envelope types ---


class Stakeholder(BaseModel):
    name: str
    roles: list[str] = []        # CURIEs: "airo:AIProvider", "airo:AIDeployer",
                                  #         "airo:AIUser", "airo:AISubject"
    description: str | None = None


class AiSystem(BaseModel):
    name: str
    description: str | None = None
    purpose: list[str] = []
    risk_level: Literal["high", "limited", "minimal", "unclassified"] | None = None


# Backward-compatible alias
GovernedSystem = AiSystem


class RegulatoryReference(BaseModel):
    name: str
    jurisdiction: str | None = None
    reference: str | None = None   # URI or document identifier


# --- Per-policy decomposition ---


class PolicyDecomposition(BaseModel):
    agent: str | None = None       # Who acts (CURIE or label)
    activity: str | None = None    # What is done
    entity: str | None = None      # What is acted upon


class Policy(BaseModel):
    policy_concept: str
    concept_definition: str
    boundary_examples: list[BoundaryExample] = []
    acceptable_uses: list[str] = []
    risk_controls: list[str] = []
    human_involvement: str | None = None
    decomposition: PolicyDecomposition | None = None


class PolicyProfile(BaseModel):
    airo_version: str = "0.2"
    organization: Stakeholder | None = None
    domain: str | None = None
    purpose: list[str] = []
    ai_systems: list[AiSystem] = []
    stakeholders: list[Stakeholder] = []
    regulations: list[RegulatoryReference] = []
    policies: list[Policy] = []

    @field_validator("organization", mode="before")
    @classmethod
    def _coerce_organization(cls, v):
        if isinstance(v, str):
            return Stakeholder(name=v) if v else None
        return v

    @model_validator(mode="before")
    @classmethod
    def _migrate_governed_systems(cls, data):
        if isinstance(data, dict) and "governed_systems" in data and "ai_systems" not in data:
            data["ai_systems"] = data.pop("governed_systems")
        return data


class RiskMatch(BaseModel):
    risk_id: str
    risk_name: str
    relevance: Literal["primary", "supporting", "tangential"]
    justification: str
    match_distance: float | None = None


class PolicyRiskMapping(BaseModel):
    policy_concept: str
    matched_risks: list[RiskMatch]


class PolicySourceRef(BaseModel):
    organization: str | None = None
    domain: str | None = None
    policy_count: int = 0


class KnowledgeBaseRef(BaseModel):
    nexus_commit: str = ""
    nexus_risk_count: int = 0
    ontology_index_hash: str = ""
    ontology_domains: dict[str, int] = {}
    indexed_at: str = ""


class RiskDetail(BaseModel):
    risk_id: str
    risk_name: str
    risk_description: str | None = ""
    risk_concern: str | None = ""
    risk_framework: str | None = ""
    cross_mappings: list[dict] = []
    related_actions: list[str] = []


class WeakMatch(BaseModel):
    risk_id: str
    policy_concept: str
    distance: float


class CoverageGap(BaseModel):
    policy_concept: str
    concept_definition: str
    gap_type: Literal["domain_specialization", "compositional", "novel"]
    confidence: float
    nearest_risks: list[dict]
    reasoning: str
    decomposition: PolicyDecomposition | None = None


class RiskLandscape(BaseModel):
    version: str = "0.1"
    model: str = ""
    timestamp: str = ""
    run_slug: str = ""
    selected_domains: list[str] = []
    policy_source: PolicySourceRef | None = None
    knowledge_base: KnowledgeBaseRef | None = None
    risks: list[RiskDetail] = []
    policy_mappings: list[PolicyRiskMapping] = []
    framework_coverage: dict[str, int] = {}
    weak_matches: list[WeakMatch] = []
    coverage_gaps: list[CoverageGap] = []


@dataclass
class RunReport:
    model: str
    policy_set: str
    timestamp: str
    stages_completed: list[str] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    token_usage: dict | None = None

    def to_dict(self) -> dict:
        d = {
            "model": self.model,
            "policy_set": self.policy_set,
            "timestamp": self.timestamp,
            "stages_completed": self.stages_completed,
            "events": self.events,
        }
        if self.token_usage:
            d["token_usage"] = self.token_usage
        return d
