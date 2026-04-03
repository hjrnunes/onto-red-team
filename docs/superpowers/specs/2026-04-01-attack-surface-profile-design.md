# Attack Surface Profile — Design Spec

**Date:** 2026-04-01
**Status:** Draft

## Overview

A third output artifact from the refiner pipeline — the **attack surface profile** — that repackages existing pipeline data into a form consumable by defensive governance tools (e.g., GAF-Guard). It restructures cross-mappings, variation axes, and domain enumerations into three progressively granular layers: risk amplification, attack dimensions, and detection vocabulary.

This is a deterministic transform over data already computed in Stages 1–4. No additional LLM calls or retrieval.

## Motivation

The GAF-Guard paper (IBM Research, arxiv:2507.02986v2) builds on the same AI Atlas Nexus knowledge graph that our refiner pipeline uses. Our pipeline is the offensive side (red-team prompt generation); GAF-Guard is the defensive side (monitoring and governance). Both operate over the same risks, but our pipeline produces three kinds of insight that the defensive side lacks:

1. **Risk amplification** — cross-framework mappings expand a client's stated policies to all the alternative framings an adversary might use
2. **Attack dimensions** — CCO-grounded variation axes define the semantic space of possible attacks
3. **Detection vocabulary** — domain ontology enumerations give concrete terms that could appear in adversarial prompts

These insights are currently embedded in our taxonomy YAML (cross-mappings) and domain context profiles (axes + enumerations), which are structured for prompt generation. The attack surface profile restructures the same data for defensive consumption.

## Three Layers

### Layer 1: Risk Amplification (Alternative Framings)

**Source:** `PolicyRiskMapping.cross_mappings` (Stage 2)

A client states N policies. Stage 2 maps these to risks and cross-maps to related risks across 10 frameworks. The attack surface profile surfaces these cross-mappings as "alternative framings" — each one is a different angle an adversary might use to probe the same underlying policy violation.

Example: a "Fraud" policy maps to `social-engineering` (close), `identity-theft` (related), `financial-manipulation` (broad) across IBM Risk Atlas, NIST AI RMF, and OWASP.

The coverage summary at the top of the profile tells the defensive side: "your 6 policies expand to 28 risks across 6 frameworks."

### Layer 2: Attack Dimensions

**Source:** `DomainContextProfile.axes` (Stages 3–4)

For each risk, the variation axes identified in Stages 3–4 become attack dimensions — semantic dimensions along which monitoring should be sensitive. Each dimension is grounded in a CCO class with a role description.

Example: for fraud, the dimensions might be `Person` (who performs/is targeted), `FinancialInstrument` (what's used/targeted), `InformationBearingArtifact` (documents involved).

### Layer 3: Detection Vocabulary

**Source:** `DomainContextAxis.enumerations` (Stage 4)

For each attack dimension, the domain ontology enumerations provide specific terms that could appear in adversarial prompts. These are concrete, domain-specific concepts from FIBO, OBO, IOF, etc.

Example: under `FinancialInstrument`, the terms might be `CreditCard`, `MortgageLoan`, `DerivativeContract` from FIBO.

## Output Format

```yaml
# <client>-attack-surface.yaml

client: swb

coverage:
  source_policies: 6
  direct_risks: 12
  amplified_risks: 28
  frameworks:
    - taxonomy: ibm-risk-atlas
      risk_count: 8
    - taxonomy: nist-ai-rmf
      risk_count: 5
    - taxonomy: owasp-llm-top10
      risk_count: 4

risks:
  - risk_id: client-swb-fraud-assistance
    risk_name: "Fraud Assistance"
    policy_concept: "Fraud"
    policy_type: A

    alternative_framings:
      - risk_id: ibm-risk-atlas:social-engineering
        risk_name: "Social Engineering"
        taxonomy: ibm-risk-atlas
        mapping_type: close
      - risk_id: nist-ai-rmf:identity-theft
        risk_name: "Identity Theft"
        taxonomy: nist-ai-rmf
        mapping_type: related

    attack_dimensions:
      - cco_class_uri: "https://www.commoncoreontologies.org/ont00001262"
        cco_class_label: "Person"
        role: "Who performs or is targeted by fraudulent action"
        detection_terms:
          - uri: "https://spec.edmcouncil.org/fibo/..."
            label: "Corporate Officer"
            source: FIBO
          - uri: "https://spec.edmcouncil.org/fibo/..."
            label: "Board Member"
            source: FIBO

      - cco_class_uri: "https://www.commoncoreontologies.org/ont00000841"
        cco_class_label: "Financial Instrument"
        role: "Financial instrument used or targeted in fraud"
        detection_terms:
          - uri: "https://spec.edmcouncil.org/fibo/..."
            label: "Credit Card"
            source: FIBO
          - uri: "https://spec.edmcouncil.org/fibo/..."
            label: "Mortgage Loan"
            source: FIBO
```

## Pydantic Models

New models in `refiner/src/refiner/models.py`:

```python
class AlternativeFraming(BaseModel):
    risk_id: str
    risk_name: str
    taxonomy: str
    mapping_type: Literal["exact", "close", "broad", "narrow", "related"]


class DetectionTerm(BaseModel):
    uri: str
    label: str
    source: str


class AttackDimension(BaseModel):
    cco_class_uri: str
    cco_class_label: str
    role: str
    detection_terms: list[DetectionTerm]


class RiskAttackSurface(BaseModel):
    risk_id: str
    risk_name: str
    policy_concept: str
    policy_type: Literal["A", "B", "C", "D"]
    alternative_framings: list[AlternativeFraming]
    attack_dimensions: list[AttackDimension]


class FrameworkCoverage(BaseModel):
    taxonomy: str
    risk_count: int


class CoverageSummary(BaseModel):
    source_policies: int
    direct_risks: int
    amplified_risks: int
    frameworks: list[FrameworkCoverage]


class AttackSurfaceProfile(BaseModel):
    client: str
    coverage: CoverageSummary
    risks: list[RiskAttackSurface]
```

## Pipeline Integration

### Data flow

The `structure()` function in `structure.py` already receives all required inputs:

| Attack surface field | Source | Pipeline stage |
|---|---|---|
| `alternative_framings` | `PolicyRiskMapping.cross_mappings` | Stage 2 (map_risks) |
| `attack_dimensions` | `DomainContextProfile.axes` | Stage 3 (anchor) |
| `detection_terms` | `DomainContextAxis.enumerations` | Stage 4 (contextualize) |
| `policy_type` | `PolicyClassification.policy_type` | Stage 1 (classify) |
| `coverage` | Computed from the above | Derived |

### Function changes

A new `build_attack_surface()` function in `structure.py`. The existing `structure()` function's return type changes:

```python
def structure(...) -> tuple[dict, dict, AttackSurfaceProfile]:
    #                       ↑      ↑     ↑
    #                  taxonomy  profiles  attack surface (NEW)
```

### CLI changes

The `refiner run` command writes a third file:

```
refiner run policy_examples/swb.json --output output/

# Produces:
output/swb-taxonomy.yaml           # existing
output/swb-domain-context.yaml     # existing
output/swb-attack-surface.yaml     # NEW
```

The attack surface file is only produced when the pipeline runs to completion (all 5 stages). Running with `--until classify` through `--until contextualize` does not produce it.

## Edge Cases

- **Risks with no cross-mappings** — `alternative_framings` is `[]`. Layers 2+3 still provide value.
- **Risks with no domain context** — `attack_dimensions` is `[]`. Layer 1 still provides alternative framings.
- **Axes with no enumerations** — `detection_terms` is `[]`. The dimension still signals what kind of thing to monitor.
- **Policy types C and D** — Scope/Regulatory and Routing policies produce valid attack surface entries. The `policy_type` field signals the monitoring class.
- **Coverage deduplication** — `amplified_risks` counts unique risk IDs across all alternative framings plus direct risks. A target risk cross-mapped from two source risks counts once.

## Testing

Unit tests on `build_attack_surface()`:

- **Happy path** — full data → all three layers populated, coverage counts correct
- **Empty cross-mappings** — `alternative_framings` is `[]`, `amplified_risks == direct_risks`
- **Empty axes** — `attack_dimensions` is `[]`
- **Empty enumerations** — `detection_terms` is `[]`
- **Coverage deduplication** — same target from multiple sources counted once
- **Framework grouping** — `frameworks` correctly groups by taxonomy prefix
- **Round-trip** — `model_dump()` → YAML → load → verify

No mocking needed — function takes Pydantic models in, returns Pydantic model out.

## Future: Schema Proposal for AI Atlas Nexus

Once the attack surface profile proves useful, the concepts can be proposed as LinkML schema extensions:

| Attack surface concept | Proposed LinkML entity | Relationship |
|---|---|---|
| `AttackDimension` | `VariationAxis` | `Risk.has_variation_axis` |
| `DetectionTerm` | `DomainConcept` | `VariationAxis.has_enumeration` |
| `AlternativeFraming` | Already exists | `Risk.*_mappings` attributes |
| `AttackSurfaceProfile` | `AttackSurface` | Container linked to `RiskTaxonomy` |

The genuinely new concepts are `VariationAxis` (a semantic dimension grounded in an upper ontology class) and its domain enumerations. Cross-mappings are already representable in the existing schema.

AIRO's `RiskControl` subtypes (`detectsRiskConcept`, `mitigatesRiskConcept`) could inform how the nexus models the relationship between attack dimensions and defensive controls, but as vocabulary alignment — not a dependency.
