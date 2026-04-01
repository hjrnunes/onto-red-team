from typing import Literal
from pydantic import BaseModel


class Policy(BaseModel):
    policy_concept: str
    concept_definition: str


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


class PolicyRiskMapping(BaseModel):
    policy_concept: str
    policy_type: str
    matched_risks: list[RiskMatch]


class VariationAxis(BaseModel):
    cco_class_uri: str
    cco_class_label: str
    role: str
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


class DomainContextAxis(BaseModel):
    cco_class_uri: str
    cco_class_label: str
    role: str
    enumerations: list[AxisEnumeration]


class DomainContextProfile(BaseModel):
    risk_id: str
    risk_name: str
    policy_concept: str
    axes: list[DomainContextAxis]


class SampledAxis(BaseModel):
    cco_class_uri: str
    cco_class_label: str
    role: str
    sampled_uri: str
    sampled_label: str
    source_ontology: str
    relevance: Literal["high", "medium", "low"]
