# Content Safety Ontology (CSO)

**Date:** 2026-04-02
**Status:** Draft

---

## Overview

A lightweight, standalone OWL ontology providing enumeration depth for content safety harm categories. Addresses the #1 bottleneck identified in the global assessment across 12 pipeline runs: CCO's safety vocabulary is structurally shallow, funneling all deception through `Act of Propaganda` (1 child) and all violence through 3 terminal values (homicide, suicide, terrorism).

### Goals

1. Provide ~195 classes covering 9 content safety harm categories with 10-30 subcategories each
2. Give the pipeline enumeration diversity for safety-related risks that currently produce repetitive or off-domain prompts
3. Integrate as an always-included domain alongside CCO, Commons, and D3FEND

### Non-goals

- BFO/CCO alignment (standalone ontology, not a CCO extension)
- Comprehensive coverage of all possible harms (curated for prompt generation diversity)
- Replacing CCO for non-safety concepts (CCO remains the mid-level ontology for general concepts)
- Technical cybersecurity techniques and vulnerabilities (D3FEND covers this with 849 offensive techniques + 943 CWE weaknesses). CSO may include cyber-motivated harm categories (e.g., cyberterrorism as a violence type) where the focus is the harm, not the technical method.

---

## Problem

The global assessment found that CCO's safety vocabulary has two structural chokepoints:

```
Act of Deceptive Communication → Act of Propaganda (1 child, that's it)
Act of Violence → Act of Homicide, Act of Suicide, Act of Terrorism (3 children)
Deception Artifact Function → leaf node, siblings are physical-world:
  Sensor, Fluid Control, Impact Shielding, Imaging...
```

Every fraud, scam, misinformation, phishing, and social engineering risk across all 12 runs gets "Act of Propaganda" as its deception axis. Every violence, dangerous content, hate speech, and self-harm risk shares the same 3 Act of Violence children.

**Impact by policy set:**

| Policy Set | Effective Prompt Rate | CCO-bottlenecked prompts |
|---|---|---|
| SWB (banking) | ~50-65% | 25-33% |
| Generic safety | ~15-25% | 48-63% |
| Healthcare | ~55-60% | 11-15% |

No formal OWL/RDF ontology for content safety exists anywhere. Research taxonomies (MLCommons AILuminate, AEGIS 2.0, Banko et al. 2020) define rich category structures but only as classification schemes, not as machine-readable ontologies.

---

## Design

### Ontology Identity

| Property | Value |
|---|---|
| Name | Content Safety Ontology (CSO) |
| Namespace | `http://taxonomy-refiner.io/ontologies/cso#` |
| Prefix | `cso:` |
| Format | Single Turtle file |
| Location | `ontologies/cso/cso.ttl` |
| Definition predicate | `rdfs:comment` |
| License | CC-BY 4.0 |
| BFO alignment | None (standalone) |
| Imports | None |

### Structural Sources

The category structure is informed by three published taxonomies, curated for pipeline relevance:

- **MLCommons AILuminate v1.0** (primary) — 12 categories, 375 subcategories. Provides the top-level structure and hierarchical depth. CC-BY 4.0.
- **AEGIS 2.0 (NVIDIA)** (supplementary) — 22 categories. Fills subcategory gaps where AILuminate is thin.
- **Banko et al. 2020 "Unified Taxonomy of Harmful Content"** (supplementary) — 4 primary categories with subcategories.

Categories covered by D3FEND (cybercrimes) or irrelevant to prompt enumeration diversity (defamation, specialized advice) are excluded.

### Class Conventions

- **URIs:** CamelCase fragment identifiers (e.g., `cso:InvestmentScam`, `cso:RacialHate`)
- **Labels:** Natural language via `rdfs:label`, no ontology jargon. "Investment Scam" not "Act of Investment Scam" or "InvestmentScamHazard". This directly addresses the jargon leak issue (Issue #7 from global assessment).
- **Definitions:** Short, distinguishing, adversarial-context-aware via `rdfs:comment`. 1-2 sentences focused on what makes this harm category distinct from siblings. Definitions serve double duty: ChromaDB embedding for semantic search, and context for the generation model. Use `rdfs:comment` only — do not mix definition predicates (e.g., adding `skos:definition` would be silently preferred over `rdfs:comment` by the extraction chain).
- **Hierarchy:** Pure `rdfs:subClassOf` trees. No OWL restrictions, no properties, no individuals.

### Example

```turtle
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix cso: <http://taxonomy-refiner.io/ontologies/cso#> .
@prefix dc: <http://purl.org/dc/elements/1.1/> .

<http://taxonomy-refiner.io/ontologies/cso> a owl:Ontology ;
    dc:title "Content Safety Ontology" ;
    dc:creator "taxonomy-refiner project" ;
    owl:versionInfo "1.0.0" ;
    dc:rights "CC-BY 4.0" ;
    rdfs:comment "Lightweight ontology of content safety harm categories for adversarial prompt generation diversity." .

cso:RomanceScam a owl:Class ;
    rdfs:label "Romance Scam" ;
    rdfs:subClassOf cso:SocialEngineeringFraud ;
    rdfs:comment "A social engineering fraud in which the perpetrator feigns romantic interest to gain the victim's trust and extract money, personal information, or other assets." .
```

---

## Category Structure

Root class: `cso:ContentSafetyHazard` (9 direct subclasses, ~195 total classes including intermediate grouping nodes)

### 1. Violence (`cso:Violence`) — 29 classes

| Subcategory | Children |
|---|---|
| Physical Assault | Aggravated Assault, Domestic Violence, Assault Against Minors |
| Homicide | Murder, Manslaughter, Assassination |
| Mass Violence | Mass Shooting, Bombing Attack, Vehicular Attack |
| Terrorism | Domestic Terrorism, International Terrorism, Cyberterrorism |
| Threats of Violence | Death Threat, Intimidation, Stalking |
| Weapons Use | Firearms Use, Bladed Weapons Use, Improvised Weapons Use, Explosive Use |
| (leaves) | Torture, Animal Cruelty, Glorification of Violence |

### 2. Hate and Discrimination (`cso:HateAndDiscrimination`) — 26 classes

| Subcategory | Children |
|---|---|
| Identity-Based Hate | Racial Hate, Religious Hate, Gender-Based Hate, Anti-LGBTQ Hate, Disability-Based Hate, Ethnic Hate, Age-Based Hate |
| Dehumanization | Dehumanizing Comparison, Denial of Humanity, Eliminationist Rhetoric |
| Harassment | Targeted Harassment, Coordinated Harassment, Sexual Harassment, Workplace Harassment |
| Discriminatory Practices | Discriminatory Denial of Service, Employment Discrimination, Housing Discrimination, Algorithmic Discrimination |
| (leaves) | Slurs and Epithets, Stereotyping, Incitement to Hatred |

### 3. Self-Harm (`cso:SelfHarm`) — 17 classes

| Subcategory | Children |
|---|---|
| Suicidal Ideation | Passive Suicidal Ideation, Active Suicidal Planning |
| Suicide Methods | Suicide Method Instruction, Suicide Pact Facilitation |
| Non-Suicidal Self-Injury | Cutting, Burning, Self-Poisoning |
| Eating Disorders | Anorexia Promotion, Bulimia Promotion, Pro-Ana Content |
| (leaves) | Self-Harm Glorification, Self-Harm Community Facilitation |

### 4. Sexual Exploitation (`cso:SexualExploitation`) — 22 classes

| Subcategory | Children |
|---|---|
| Sexual Assault | Rape, Drug-Facilitated Assault, Coerced Sexual Acts |
| Child Sexual Exploitation | CSAM Production, Child Grooming, Minor Sexualization, Child Trafficking |
| Sex Trafficking | Forced Prostitution, Commercial Exploitation |
| Non-Consensual Intimate Imagery | Revenge Pornography, Deepfake Pornography, Voyeuristic Content |
| Sexual Harassment | Unwanted Sexual Solicitation, Sextortion |
| (leaves) | Bestiality, Sexual Coercion |

### 5. Sexual Content (`cso:SexualContent`) — 11 classes

Leaf classes under `cso:SexualContent`: Explicit Sexual Description, Erotic Fiction Generation, Sexual Fetish Content, Pornographic Content Description, Sexual Role-Play, Sex Education Boundary, Reproductive Health Boundary, Clinical Sexual Description, Nudity Description, Sexual Innuendo.

### 6. Fraud and Deception (`cso:FraudAndDeception`) — 29 classes

| Subcategory | Children |
|---|---|
| Financial Fraud | Investment Scam, Ponzi Scheme, Insurance Fraud, Credit Card Fraud, Identity Theft |
| Social Engineering (non-cyber) | Romance Scam, Impersonation, Pretexting, Confidence Trick |
| Misinformation | Health Misinformation, Political Misinformation, Scientific Misinformation, Election Misinformation |
| Disinformation | State-Sponsored Propaganda, Conspiracy Theory Promotion, Deepfake Disinformation |
| Manipulation | Emotional Manipulation, Gaslighting, Coercive Control |
| Counterfeiting | Document Forgery, Currency Counterfeiting |
| (leaf) | Academic Dishonesty |

### 7. Dangerous Information (`cso:DangerousInformation`) — 18 classes

| Subcategory | Children |
|---|---|
| Weapons Manufacturing | Firearms Manufacturing, Explosive Synthesis, Chemical Weapons Synthesis |
| Drug Synthesis | Illicit Drug Manufacturing, Precursor Chemical Acquisition, Drug Administration Methods |
| CBRN Information | Biological Agent Production, Radiological Device Construction, Nuclear Material Acquisition |
| Harmful How-To | Lock Picking and Bypassing, Sabotage Instructions, Arson Methods |
| (leaf) | Dual-Use Research Concern |

### 8. Intellectual Property (`cso:IntellectualProperty`) — 18 classes

| Subcategory | Children |
|---|---|
| Copyright Infringement | Literary Work Reproduction, Musical Work Reproduction, Software Code Reproduction, Visual Art Reproduction, Database Extraction |
| Trademark Violation | Brand Name Misuse, Logo Reproduction, Trade Dress Imitation |
| Trade Secret Disclosure | Formula Disclosure, Process Disclosure, Customer List Disclosure |
| Plagiarism | Academic Plagiarism, Creative Plagiarism |

### 9. Privacy Violation (`cso:PrivacyViolation`) — 23 classes

| Subcategory | Children |
|---|---|
| Direct Identifier Exposure | Name and Address Exposure, National ID Exposure, Biometric Data Exposure, Photo and Likeness Exposure |
| Financial Data Exposure | Account Number Exposure, Credit Score Exposure, Transaction History Exposure |
| Health Data Exposure | Medical Record Exposure, Prescription Exposure, Diagnosis Exposure |
| Digital Footprint Exposure | Browsing History Exposure, Location Data Exposure, Communication Metadata Exposure, Device Fingerprint Exposure |
| Employment Data Exposure | Salary Exposure, Performance Record Exposure |
| (leaf) | Unauthorized Surveillance |

---

## Pipeline Integration

### Domain Filtering

```python
# identify_domains.py
def derive_source_ontology(uri: str) -> str:
    ...
    if "taxonomy-refiner.io/ontologies/cso" in uri:
        return "CSO"
    ...

ALWAYS_INCLUDED = ["CCO", "Commons", "D3FEND", "CSO"]
```

CSO is always-included because content safety harms are relevant regardless of industry domain. Unlike FIBO (banking-specific) or OBO (healthcare-specific), safety categories apply to all policy sets.

### Indexing

```bash
uv run ontoquery index \
  ../ontologies/CommonCoreOntologies/src/cco-modules/ \
  ../ontologies/commons/ \
  ../ontologies/fibo/ \
  ../ontologies/obo/ \
  ../ontologies/d3fend-ontology/src/ontology/ \
  ../ontologies/cso/
```

Expected index size: ~90,230 classes (90,034 current + ~195 CSO).

### Semantic Search Behavior

CSO classes will outrank CCO for safety-related queries because their labels and definitions are more specific:

| Query | Before CSO | After CSO |
|---|---|---|
| "hate speech categories" | `cco:ActOfDeceptiveCommunication` (distant) | `cso:RacialHate`, `cso:ReligiousHate`, `cso:IdentityBasedHate` |
| "types of fraud and scams" | `cco:ActOfPropaganda` (only child) | `cso:InvestmentScam`, `cso:RomanceScam`, `cso:PonziScheme` |
| "violence against people" | `cco:ActOfHomicide`, `cco:ActOfSuicide` | `cso:PhysicalAssault`, `cso:DomesticViolence`, `cso:MassViolence` |
| "self harm methods" | `cco:ActOfSuicide` (only relevant) | `cso:Cutting`, `cso:SelfPoisoning`, `cso:AnorexiaPromotion` |

### Contextualize Stage

CSO leaf nodes have relevant siblings under their parent, solving the "Deception Artifact Function → physical-world siblings" problem:

- `cso:InvestmentScam` siblings: `PonziScheme`, `InsuranceFraud`, `CreditCardFraud`, `IdentityTheft`
- `cso:RacialHate` siblings: `ReligiousHate`, `GenderBasedHate`, `AntiLGBTQHate`, `DisabilityBasedHate`

### Role Derivation

CSO classes are not BFO-aligned, so `derive_roles()` in `anchor.py` will fall back to LLM-assigned roles. This is the same behavior as FIBO and Commons classes today and is acceptable — the role is less important than enumeration diversity.

### Overlap with D3FEND

Some CSO classes have semantic overlap with D3FEND concepts:

| CSO class | Overlapping D3FEND area |
|---|---|
| `cso:IdentityTheft` | ATT&CK credential theft techniques |
| `cso:Cyberterrorism` | Explicitly a cyber concept |
| `cso:DeepfakeDisinformation` | ATLAS AI attack techniques |
| `cso:DeepfakePornography` | ATLAS deepfake concepts |
| `cso:SocialEngineeringFraud` | ATT&CK social engineering techniques |

This is acceptable. CSO and D3FEND describe the same phenomena at different abstraction levels: CSO names the *harm category* (what the policy prohibits), D3FEND names the *attack technique* (how the harm is executed). Both can appear in search results for the same query. The anchor stage's top-k selection will naturally prefer whichever has a closer semantic match to the specific risk description. If both appear, they provide complementary framing — a CSO axis gives the harm framing, a D3FEND axis gives the technical framing.

No deduplication is needed. The pipeline already handles multiple ontology sources per risk.

### Evaluation Traceability

`derive_source_ontology()` is used by the contextualize stage to populate the `source_ontology` field on enumerations. CSO enumerations will correctly appear as `"CSO"` in evaluation output (`evaluate.py` tracks `source_ontology` in coverage metrics), enabling measurement of CSO's contribution vs other ontologies.

### Test Updates

Adding CSO to `ALWAYS_INCLUDED` and `derive_source_ontology()` requires updating tests in `refiner/tests/test_identify_domains.py`:

- `test_identify_domains_empty_classifications` — asserts `result == list(ALWAYS_INCLUDED)`, will need `"CSO"` in expected list
- `test_derive_source_ontology` — needs a CSO namespace test case
- Any tests asserting specific `ALWAYS_INCLUDED` contents

### Known Technical Debt

The `VariationAxis`, `DomainContextAxis`, and `SampledAxis` models in `models.py` use field names `cco_class_uri` and `cco_class_label`. These names are misleading for non-CCO sources (FIBO, D3FEND, CSO). This is pre-existing debt (FIBO URIs already go into `cco_class_uri`). A field rename to `axis_class_uri`/`axis_class_label` would improve clarity but is out of scope for this spec.

---

## Validation

1. **Parse** — rdflib/oxigraph parses `cso.ttl` without errors
2. **Extract** — `ontoquery index` extracts all ~195 classes, each with a label and definition
3. **Search** — For queries "hate speech categories", "types of fraud", "violence against people", "self harm methods": at least 2 of the top-3 results should be CSO classes (not CCO)
4. **Pipeline** — Run against `generic.json` policies. Every policy should produce at least 1 non-empty variation axis. The "zero axes" problem (malware, obscene content risks producing zero prompts) should be eliminated
5. **No regression** — SWB and healthcare runs maintain or improve their effective prompt rates

---

## Out of Scope

These are separate issues from the global assessment (`runs/global-assessment.md`), not addressed by CSO:

- **Enumeration-level domain filtering** (global-assessment #3) — FIBO contamination in healthcare runs
- **Low-relevance axis filtering** (global-assessment #4) — dropping axes where all enumerations are scored `low`
- **Ontology jargon stripping** (global-assessment #7) — CSO labels are clean by design, but CCO/D3FEND jargon persists
- **Generic policy fast path** (global-assessment #5) — structural limitation of domain-anchor-free policies
- **Weak match thresholds** (global-assessment #10) — hard or soft cutoff for match distances
