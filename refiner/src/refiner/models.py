from typing import Literal
from dataclasses import dataclass, field
from pydantic import BaseModel


class BoundaryExample(BaseModel):
    prohibited: str
    acceptable: str


class NamedEntity(BaseModel):
    name: str
    role: str


class Policy(BaseModel):
    policy_concept: str
    concept_definition: str
    boundary_examples: list[BoundaryExample] = []
    acceptable_uses: list[str] = []
    risk_controls: list[str] = []
    human_involvement: str | None = None


class PolicyDocument(BaseModel):
    airo_version: str = "0.2"
    organization: str = ""
    domain: str = ""
    purpose: list[str] = []
    ai_systems: list[str] = []
    ai_users: list[str] = []
    ai_subjects: list[str] = []
    governing_regulations: list[str] = []
    named_entities: list[NamedEntity] = []
    policies: list[Policy] = []


class PolicyClassification(BaseModel):
    policy_concept: str
    concept_definition: str
    policy_type: Literal["A", "B", "C", "D"]
    justification: str


class RiskMatch(BaseModel):
    risk_id: str
    risk_name: str
    relevance: Literal["primary", "supporting", "tangential"]
    justification: str
    match_distance: float | None = None


class PolicyRiskMapping(BaseModel):
    policy_concept: str
    policy_type: str
    matched_risks: list[RiskMatch]


class VariationAxis(BaseModel):
    cco_class_uri: str
    cco_class_label: str
    roles: list[str]
    rationale: str


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
    provenance: Literal["subclass", "sibling"] = "subclass"


class DomainContextAxis(BaseModel):
    cco_class_uri: str
    cco_class_label: str
    roles: list[str]
    enumerations: list[AxisEnumeration]


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
    roles: list[str]
    sampled_uri: str
    sampled_label: str
    source_ontology: str
    relevance: Literal["high", "medium", "low"]


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
