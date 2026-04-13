from typing import Literal
from dataclasses import dataclass, field
from pydantic import BaseModel, field_validator


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


class GovernedSystem(BaseModel):
    name: str
    description: str | None = None
    purpose: list[str] = []
    risk_level: Literal["high", "limited", "minimal", "unclassified"] | None = None


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


class PolicyDocument(BaseModel):
    airo_version: str = "0.2"
    organization: Stakeholder | None = None
    domain: str | None = None
    purpose: list[str] = []
    ai_systems: list[str] = []
    stakeholders: list[Stakeholder] = []
    governing_regulations: list[str] = []
    policies: list[Policy] = []

    @field_validator("organization", mode="before")
    @classmethod
    def _coerce_organization(cls, v):
        if isinstance(v, str):
            return Stakeholder(name=v) if v else None
        return v


class RiskMatch(BaseModel):
    risk_id: str
    risk_name: str
    relevance: Literal["primary", "supporting", "tangential"]
    justification: str
    match_distance: float | None = None


class PolicyRiskMapping(BaseModel):
    policy_concept: str
    matched_risks: list[RiskMatch]


class AxisDerivation(BaseModel):
    source: str = ""  # "structural" or "search"
    seed_uri: str = ""
    path: list[str] = []
    effective_confidence: float = 0.0
    best_distance: float | None = None
    domain: str = ""


class VariationAxis(BaseModel):
    cco_class_uri: str
    cco_class_label: str
    bfo_category: str = ""
    vocabulary_concept: str = ""
    vocabulary_label: str = ""
    rationale: str
    derivation: AxisDerivation | None = None
    # Kept for backward compatibility with emit stage
    roles: list[str] = []


class RiskVariationAxes(BaseModel):
    risk_id: str
    risk_name: str
    policy_concept: str
    axes: list[VariationAxis]


class AxisEnumeration(BaseModel):
    class_uri: str
    class_label: str
    source_ontology: str
    relevance: Literal["high", "medium", "low"]
    provenance: str = "generated"  # "generated", "subclass", "sibling"
    generated_by: str = ""  # model name when provenance is "generated"


class DomainContextAxis(BaseModel):
    cco_class_uri: str
    cco_class_label: str
    bfo_category: str = ""
    vocabulary_concept: str = ""
    vocabulary_label: str = ""
    vocabulary_context: dict = {}
    derivation: AxisDerivation | None = None
    enumerations: list[AxisEnumeration]
    # Kept for backward compatibility with emit stage
    roles: list[str] = []


class DomainContextProfile(BaseModel):
    risk_id: str
    risk_name: str
    policy_concept: str
    axes: list[DomainContextAxis]
    risk_description: str | None = ""
    risk_concern: str | None = ""
    risk_framework: str | None = ""
    cross_mappings: list[dict] = []


class SampledAxis(BaseModel):
    cco_class_uri: str
    cco_class_label: str
    bfo_category: str = ""
    vocabulary_concept: str = ""
    vocabulary_label: str = ""
    sampled_uri: str
    sampled_label: str
    source_ontology: str
    relevance: Literal["high", "medium", "low"]
    provenance: str = "generated"
    # Kept for backward compatibility with emit stage
    roles: list[str] = []


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
