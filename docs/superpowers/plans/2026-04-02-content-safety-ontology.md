# Content Safety Ontology (CSO) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a ~195-class OWL ontology for content safety harm categories and integrate it as an always-included domain in the refiner pipeline.

**Architecture:** Single Turtle file (`ontologies/cso/cso.ttl`) with 9 top-level categories under a `cso:ContentSafetyHazard` root. Pure `rdfs:subClassOf` hierarchy, `rdfs:label` for labels, `rdfs:comment` for definitions. Pipeline integration via two changes: add `"CSO"` to `ALWAYS_INCLUDED` and add CSO namespace to `derive_source_ontology()` in `identify_domains.py`.

**Tech Stack:** OWL/Turtle (hand-authored), rdflib + pyoxigraph (validation), pytest (testing)

**Spec:** `docs/superpowers/specs/2026-04-02-content-safety-ontology-design.md`

---

### Task 1: Create CSO Turtle file — ontology header and Violence category

**Files:**
- Create: `ontologies/cso/cso.ttl`

This task creates the ontology file with the header, root class, and the first category (Violence, 29 classes). Subsequent tasks append the remaining 8 categories.

- [ ] **Step 1: Create the ontology file with header, root class, and Violence category**

Create `ontologies/cso/cso.ttl` with the ontology declaration, prefixes, `cso:ContentSafetyHazard` root, and all Violence classes as specified in the spec (Section "Category Structure", item 1).

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

# --- Root ---

cso:ContentSafetyHazard a owl:Class ;
    rdfs:label "Content Safety Hazard" ;
    rdfs:comment "Root class for content safety harm categories relevant to adversarial prompt generation against LLM deployments." .

# --- 1. Violence (29 classes) ---

cso:Violence a owl:Class ;
    rdfs:label "Violence" ;
    rdfs:subClassOf cso:ContentSafetyHazard ;
    rdfs:comment "Content involving physical force or threat of physical force intended to cause harm, injury, or death." .

cso:PhysicalAssault a owl:Class ;
    rdfs:label "Physical Assault" ;
    rdfs:subClassOf cso:Violence ;
    rdfs:comment "Direct physical attack on a person causing bodily harm, distinct from threats or armed violence." .

cso:AggravatedAssault a owl:Class ;
    rdfs:label "Aggravated Assault" ;
    rdfs:subClassOf cso:PhysicalAssault ;
    rdfs:comment "Physical assault involving a deadly weapon or resulting in serious bodily injury." .

cso:DomesticViolence a owl:Class ;
    rdfs:label "Domestic Violence" ;
    rdfs:subClassOf cso:PhysicalAssault ;
    rdfs:comment "Physical assault or abuse occurring within a household or intimate partner relationship." .

cso:AssaultAgainstMinors a owl:Class ;
    rdfs:label "Assault Against Minors" ;
    rdfs:subClassOf cso:PhysicalAssault ;
    rdfs:comment "Physical violence directed specifically at children or minors." .
```

Continue with Homicide, Mass Violence, Terrorism, Threats of Violence, Weapons Use subcategories and their children, plus the 3 direct Violence leaves (Torture, Animal Cruelty, Glorification of Violence). Each class gets:
- CamelCase URI fragment
- Natural language `rdfs:label`
- 1-2 sentence `rdfs:comment` distinguishing it from siblings

Hierarchy from the spec:
```
Violence
├── PhysicalAssault → AggravatedAssault, DomesticViolence, AssaultAgainstMinors
├── Homicide → Murder, Manslaughter, Assassination
├── MassViolence → MassShooting, BombingAttack, VehicularAttack
├── Terrorism → DomesticTerrorism, InternationalTerrorism, Cyberterrorism
├── ThreatsOfViolence → DeathThreat, Intimidation, Stalking
├── WeaponsUse → FirearmsUse, BladedWeaponsUse, ImprovisedWeaponsUse, ExplosiveUse
├── Torture
├── AnimalCruelty
└── GlorificationOfViolence
```

Total: 1 (Violence) + 6 (subcategories) + 19 (children) + 3 (leaves) = 29 classes.

- [ ] **Step 2: Validate the file parses correctly**

Run from the `ontoquery` directory:

```bash
cd ontoquery && uv run python3 -c "
from rdflib import Graph, OWL, RDF
g = Graph()
g.parse('../ontologies/cso/cso.ttl', format='turtle')
classes = [s for s in g.subjects(RDF.type, OWL.Class)]
print(f'{len(classes)} classes parsed')
assert len(classes) >= 30  # 29 Violence + 1 root
"
```

Expected: `30 classes parsed` (or similar), no parse errors.

- [ ] **Step 3: Commit**

```bash
git add ontologies/cso/cso.ttl
git commit -m "feat(cso): add ontology header, root class, and Violence category (29 classes)"
```

---

### Task 2: Add Hate and Discrimination category (26 classes)

**Files:**
- Modify: `ontologies/cso/cso.ttl`

- [ ] **Step 1: Append Hate and Discrimination classes to cso.ttl**

Add all classes from spec Section "Category Structure", item 2:

```
HateAndDiscrimination
├── IdentityBasedHate → RacialHate, ReligiousHate, GenderBasedHate, AntiLGBTQHate, DisabilityBasedHate, EthnicHate, AgeBasedHate
├── Dehumanization → DehumanizingComparison, DenialOfHumanity, EliminationistRhetoric
├── Harassment → TargetedHarassment, CoordinatedHarassment, SexualHarassment, WorkplaceHarassment
├── DiscriminatoryPractices → DiscriminatoryDenialOfService, EmploymentDiscrimination, HousingDiscrimination, AlgorithmicDiscrimination
├── SlursAndEpithets
├── Stereotyping
└── IncitementToHatred
```

Each class: CamelCase URI, natural `rdfs:label`, distinguishing `rdfs:comment`.

- [ ] **Step 2: Validate parse and class count**

```bash
cd ontoquery && uv run python3 -c "
from rdflib import Graph, OWL, RDF
g = Graph()
g.parse('../ontologies/cso/cso.ttl', format='turtle')
classes = [s for s in g.subjects(RDF.type, OWL.Class)]
print(f'{len(classes)} classes parsed')
assert len(classes) >= 56  # 30 + 26
"
```

- [ ] **Step 3: Commit**

```bash
git add ontologies/cso/cso.ttl
git commit -m "feat(cso): add Hate and Discrimination category (26 classes)"
```

---

### Task 3: Add Self-Harm and Sexual Exploitation categories (39 classes)

**Files:**
- Modify: `ontologies/cso/cso.ttl`

- [ ] **Step 1: Append Self-Harm classes (17 classes)**

```
SelfHarm
├── SuicidalIdeation → PassiveSuicidalIdeation, ActiveSuicidalPlanning
├── SuicideMethods → SuicideMethodInstruction, SuicidePactFacilitation
├── NonSuicidalSelfInjury → Cutting, Burning, SelfPoisoning
├── EatingDisorders → AnorexiaPromotion, BulimiaPromotion, ProAnaContent
├── SelfHarmGlorification
└── SelfHarmCommunityFacilitation
```

- [ ] **Step 2: Append Sexual Exploitation classes (22 classes)**

```
SexualExploitation
├── SexualAssault → Rape, DrugFacilitatedAssault, CoercedSexualActs
├── ChildSexualExploitation → CSAMProduction, ChildGrooming, MinorSexualization, ChildTrafficking
├── SexTrafficking → ForcedProstitution, CommercialExploitation
├── NonConsensualIntimateImagery → RevengePornography, DeepfakePornography, VoyeuristicContent
├── SexualExploitationHarassment → UnwantedSexualSolicitation, Sextortion
├── Bestiality
└── SexualCoercion
```

Note: `cso:SexualHarassment` already exists under Hate/Harassment. The Sexual Exploitation subcategory that groups Unwanted Sexual Solicitation and Sextortion uses the distinct URI `cso:SexualExploitationHarassment` (label: "Sexual Exploitation Harassment") to avoid collision. The Harassment version is harassment-framed (pattern of unwanted behavior); the exploitation version is exploitation-framed (coercion for sexual ends).

- [ ] **Step 3: Validate parse and class count**

```bash
cd ontoquery && uv run python3 -c "
from rdflib import Graph, OWL, RDF
g = Graph()
g.parse('../ontologies/cso/cso.ttl', format='turtle')
classes = [s for s in g.subjects(RDF.type, OWL.Class)]
print(f'{len(classes)} classes parsed')
assert len(classes) >= 95  # 56 + 39
"
```

- [ ] **Step 4: Commit**

```bash
git add ontologies/cso/cso.ttl
git commit -m "feat(cso): add Self-Harm (17) and Sexual Exploitation (22) categories"
```

---

### Task 4: Add Sexual Content and Fraud and Deception categories (40 classes)

**Files:**
- Modify: `ontologies/cso/cso.ttl`

- [ ] **Step 1: Append Sexual Content classes (11 classes)**

All leaf classes directly under `cso:SexualContent`:
`ExplicitSexualDescription`, `EroticFictionGeneration`, `SexualFetishContent`, `PornographicContentDescription`, `SexualRolePlay`, `SexEducationBoundary`, `ReproductiveHealthBoundary`, `ClinicalSexualDescription`, `NudityDescription`, `SexualInnuendo`.

- [ ] **Step 2: Append Fraud and Deception classes (29 classes)**

```
FraudAndDeception
├── FinancialFraud → InvestmentScam, PonziScheme, InsuranceFraud, CreditCardFraud, IdentityTheft
├── SocialEngineeringFraud → RomanceScam, Impersonation, Pretexting, ConfidenceTrick
├── Misinformation → HealthMisinformation, PoliticalMisinformation, ScientificMisinformation, ElectionMisinformation
├── Disinformation → StateSponsoredPropaganda, ConspiracyTheoryPromotion, DeepfakeDisinformation
├── Manipulation → EmotionalManipulation, Gaslighting, CoerciveControl
├── Counterfeiting → DocumentForgery, CurrencyCounterfeiting
└── AcademicDishonesty
```

- [ ] **Step 3: Validate parse and class count**

```bash
cd ontoquery && uv run python3 -c "
from rdflib import Graph, OWL, RDF
g = Graph()
g.parse('../ontologies/cso/cso.ttl', format='turtle')
classes = [s for s in g.subjects(RDF.type, OWL.Class)]
print(f'{len(classes)} classes parsed')
assert len(classes) >= 135  # 95 + 40
"
```

- [ ] **Step 4: Commit**

```bash
git add ontologies/cso/cso.ttl
git commit -m "feat(cso): add Sexual Content (11) and Fraud and Deception (29) categories"
```

---

### Task 5: Add Dangerous Information, Intellectual Property, and Privacy Violation categories (59 classes)

**Files:**
- Modify: `ontologies/cso/cso.ttl`

- [ ] **Step 1: Append Dangerous Information classes (18 classes)**

```
DangerousInformation
├── WeaponsManufacturing → FirearmsManufacturing, ExplosiveSynthesis, ChemicalWeaponsSynthesis
├── DrugSynthesis → IllicitDrugManufacturing, PrecursorChemicalAcquisition, DrugAdministrationMethods
├── CBRNInformation → BiologicalAgentProduction, RadiologicalDeviceConstruction, NuclearMaterialAcquisition
├── HarmfulHowTo → LockPickingAndBypassing, SabotageInstructions, ArsonMethods
└── DualUseResearchConcern
```

- [ ] **Step 2: Append Intellectual Property classes (18 classes)**

```
IntellectualProperty
├── CopyrightInfringement → LiteraryWorkReproduction, MusicalWorkReproduction, SoftwareCodeReproduction, VisualArtReproduction, DatabaseExtraction
├── TrademarkViolation → BrandNameMisuse, LogoReproduction, TradeDressImitation
├── TradeSecretDisclosure → FormulaDisclosure, ProcessDisclosure, CustomerListDisclosure
└── Plagiarism → AcademicPlagiarism, CreativePlagiarism
```

- [ ] **Step 3: Append Privacy Violation classes (23 classes)**

```
PrivacyViolation
├── DirectIdentifierExposure → NameAndAddressExposure, NationalIDExposure, BiometricDataExposure, PhotoAndLikenessExposure
├── FinancialDataExposure → AccountNumberExposure, CreditScoreExposure, TransactionHistoryExposure
├── HealthDataExposure → MedicalRecordExposure, PrescriptionExposure, DiagnosisExposure
├── DigitalFootprintExposure → BrowsingHistoryExposure, LocationDataExposure, CommunicationMetadataExposure, DeviceFingerprintExposure
├── EmploymentDataExposure → SalaryExposure, PerformanceRecordExposure
└── UnauthorizedSurveillance
```

- [ ] **Step 4: Validate parse and final class count**

```bash
cd ontoquery && uv run python3 -c "
from rdflib import Graph, OWL, RDF, RDFS
g = Graph()
g.parse('../ontologies/cso/cso.ttl', format='turtle')
classes = [s for s in g.subjects(RDF.type, OWL.Class)]
print(f'{len(classes)} classes parsed')

# Check every class has a label and definition
missing_label = []
missing_def = []
for cls in classes:
    labels = list(g.objects(cls, RDFS.label))
    comments = list(g.objects(cls, RDFS.comment))
    if not labels:
        missing_label.append(str(cls))
    if not comments:
        missing_def.append(str(cls))
if missing_label:
    print(f'MISSING LABELS: {missing_label}')
if missing_def:
    print(f'MISSING DEFINITIONS: {missing_def}')
assert not missing_label, f'Classes without labels: {missing_label}'
assert not missing_def, f'Classes without definitions: {missing_def}'
assert len(classes) >= 194  # ~195 total
print('All classes have labels and definitions')
"
```

Expected: ~195 classes, all with labels and definitions, no parse errors.

- [ ] **Step 5: Commit**

```bash
git add ontologies/cso/cso.ttl
git commit -m "feat(cso): add Dangerous Information (18), IP (18), and Privacy Violation (23) categories"
```

---

### Task 6: Pipeline integration — add CSO to derive_source_ontology and ALWAYS_INCLUDED

**Files:**
- Modify: `refiner/src/refiner/stages/identify_domains.py:20` (ALWAYS_INCLUDED) and `:38-52` (derive_source_ontology)
- Test: `refiner/tests/test_identify_domains.py`

- [ ] **Step 1: Write the failing tests for derive_source_ontology with CSO and D3FEND URIs**

Add to `refiner/tests/test_identify_domains.py`, inside the existing `test_derive_source_ontology` function:

```python
# Add these assertions to test_derive_source_ontology():
assert derive_source_ontology("http://d3fend.mitre.org/ontologies/d3fend.owl#Phishing") == "D3FEND"
assert derive_source_ontology("http://taxonomy-refiner.io/ontologies/cso#RacialHate") == "CSO"
```

Note: D3FEND was already added to `derive_source_ontology()` but the test was never updated. Fix both gaps together.

- [ ] **Step 2: Run test to verify it fails**

```bash
cd refiner && uv run pytest tests/test_identify_domains.py::test_derive_source_ontology -v
```

Expected: FAIL — returns `"unknown"` for CSO URI.

- [ ] **Step 3: Add CSO to derive_source_ontology()**

In `refiner/src/refiner/stages/identify_domains.py`, add before the `return "unknown"` line:

```python
    if "taxonomy-refiner.io/ontologies/cso" in uri:
        return "CSO"
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd refiner && uv run pytest tests/test_identify_domains.py::test_derive_source_ontology -v
```

Expected: PASS

- [ ] **Step 5: Add CSO to ALWAYS_INCLUDED**

In `refiner/src/refiner/stages/identify_domains.py`, change line 20:

```python
# Before:
ALWAYS_INCLUDED = ["CCO", "Commons", "D3FEND"]

# After:
ALWAYS_INCLUDED = ["CCO", "Commons", "D3FEND", "CSO"]
```

- [ ] **Step 6: Add CSO and D3FEND membership assertions to test_identify_domains_returns_selected_domains**

In `refiner/tests/test_identify_domains.py`, add to `test_identify_domains_returns_selected_domains` (after the existing `assert "Commons" in result`):

```python
assert "D3FEND" in result
assert "CSO" in result
```

This ensures all `ALWAYS_INCLUDED` entries appear in the result when domains are selected.

- [ ] **Step 7: Run existing tests to check what breaks**

```bash
cd refiner && uv run pytest tests/test_identify_domains.py -v
```

Expected: All tests pass. `test_identify_domains_empty_classifications` uses `list(ALWAYS_INCLUDED)` dynamically. The new membership assertions verify CSO and D3FEND are present.

- [ ] **Step 8: Run full refiner test suite to catch any ripple effects**

```bash
cd refiner && uv run pytest tests/ -v
```

Expected: All 221+ tests pass. If any fail due to the new ALWAYS_INCLUDED entry, fix them (likely tests hardcoding expected domain lists).

- [ ] **Step 9: Commit**

```bash
cd refiner && git add src/refiner/stages/identify_domains.py tests/test_identify_domains.py
git commit -m "feat(refiner): add CSO to derive_source_ontology and ALWAYS_INCLUDED"
```

---

### Task 7: Validate CSO with ontoquery — parse, extract, and search quality

This task validates the ontology end-to-end: oxigraph parse, class extraction, and semantic search ranking.

**Files:**
- No code changes — validation only

- [ ] **Step 1: Validate oxigraph can parse the CSO file**

```bash
cd ontoquery && uv run python3 -c "
import pyoxigraph as ox
store = ox.Store()
store.bulk_load('../ontologies/cso/cso.ttl', format=ox.RdfFormat.TURTLE)
OWL_CLASS = ox.NamedNode('http://www.w3.org/2002/07/owl#Class')
RDF_TYPE = ox.NamedNode('http://www.w3.org/1999/02/22-rdf-syntax-ns#type')
classes = list(store.quads_for_pattern(None, RDF_TYPE, OWL_CLASS, None))
print(f'{len(classes)} classes in oxigraph store')
assert len(classes) >= 194
"
```

Expected: ~195 classes, no parse errors.

- [ ] **Step 2: Validate the backend extracts all classes with labels and definitions**

```bash
cd ontoquery && uv run python3 -c "
from pathlib import Path
from ontoquery.backend import create_index_backend
files = list(Path('../ontologies/cso').rglob('*.ttl'))
backend = create_index_backend(files, Path('/tmp/cso-test-index'))
classes = backend.extract_classes()
print(f'{len(classes)} classes extracted')
missing = [c for c in classes if not c.get('definition')]
if missing:
    print(f'Classes without definitions: {[c[\"label\"] for c in missing]}')
assert len(classes) >= 194
assert not missing, 'All classes must have definitions'
del backend  # Release RocksDB lock
"
```

Expected: All ~195 classes extracted, each with label and definition.

- [ ] **Step 3: Clean up temp index**

```bash
rm -rf /tmp/cso-test-index
```

- [ ] **Step 4: Commit (no code changes — validation step only)**

No commit needed. This is a validation gate.

---

### Task 8: Validate search quality — CSO classes outrank CCO for safety queries

This validates spec item 3: CSO classes should dominate top-3 results for safety-related queries. Requires a combined index with at least CCO + CSO.

**Files:**
- No code changes — validation only

- [ ] **Step 1: Build a combined CSO + CCO index and test search ranking**

```bash
cd ontoquery && uv run python3 -c "
from pathlib import Path
from ontoquery.backend import create_index_backend
from ontoquery.index import OntologyIndex

# Build combined index with CCO + CSO
cco_files = list(Path('../ontologies/CommonCoreOntologies/src/cco-modules').rglob('*.ttl'))
cso_files = list(Path('../ontologies/cso').rglob('*.ttl'))
all_files = cco_files + cso_files

idx_dir = Path('/tmp/cso-search-test')
backend = create_index_backend(all_files, idx_dir)
classes = backend.extract_classes()
print(f'{len(classes)} classes extracted')

index = OntologyIndex(str(idx_dir))
index.build(classes)
print(f'Index built with {len(classes)} classes')

# Test the four queries from the spec
CSO_NS = 'http://taxonomy-refiner.io/ontologies/cso#'
queries = [
    'hate speech categories',
    'types of fraud and scams',
    'violence against people',
    'self harm methods',
]
for q in queries:
    results = index.search(q, top_k=3)
    cso_count = sum(1 for r in results if r.get('uri', '').startswith(CSO_NS))
    labels = [r.get('label', '?') for r in results]
    status = 'PASS' if cso_count >= 2 else 'FAIL'
    print(f'{status}: \"{q}\" → {cso_count}/3 CSO results: {labels}')

del backend
"
```

Expected: For each query, at least 2 of the top-3 results are CSO classes (not CCO). This confirms CSO definitions are more specific than CCO's shallow safety vocabulary.

- [ ] **Step 2: Clean up temp index**

```bash
rm -rf /tmp/cso-search-test
```

- [ ] **Step 3: Validation gate — no commit needed**

If any query returns fewer than 2 CSO results in top-3, review the definitions for those classes — they may need to be more specific or distinctive.

---

### Task 9: Validate end-to-end pipeline run (manual)

This validates spec items 4 and 5. Requires a running LLM endpoint. If no LLM is available, skip this task — it is a manual verification gate, not an automated test.

**Files:**
- No code changes — validation only

**Prerequisites:** `REFINER_BASE_URL`, `REFINER_MODEL`, `REFINER_API_KEY` env vars configured. ChromaDB index rebuilt with CSO included (`ontoquery index` with `../ontologies/cso/` added).

- [ ] **Step 1: Re-index ontologies with CSO included**

```bash
cd ontoquery && uv run ontoquery index \
  ../ontologies/CommonCoreOntologies/src/cco-modules/ \
  ../ontologies/commons/ \
  ../ontologies/fibo/ \
  ../ontologies/obo/ \
  ../ontologies/d3fend-ontology/src/ontology/ \
  ../ontologies/cso/
```

Expected: ~90,230 classes indexed (90,034 previous + ~195 CSO).

- [ ] **Step 2: Run pipeline against generic.json**

```bash
cd refiner && uv run refiner run ../policy_examples/generic.json --output /tmp/cso-generic-run --debug /tmp/cso-generic-debug
```

Verify in the output `*-domain-context.yaml`: every policy should produce at least 1 non-empty variation axis. Check that CSO classes appear as axis sources (look for `taxonomy-refiner.io/ontologies/cso` URIs). The "zero axes" problem for malware/obscene content risks should be eliminated.

- [ ] **Step 3: Run pipeline against swb.json (regression check)**

```bash
cd refiner && uv run refiner run ../policy_examples/swb.json --output /tmp/cso-swb-run --debug /tmp/cso-swb-debug
```

Verify the run completes successfully and produces at least as many non-empty axes as before CSO integration. SWB runs should maintain or improve effective prompt rates.

- [ ] **Step 4: Validation gate — no commit needed**

Compare results qualitatively against previous runs in `runs/`. If regression is observed, investigate whether CSO classes are displacing useful CCO/FIBO classes in search results.

---

### Task 10: Update CLAUDE.md and project memory

**Files:**
- Modify: `CLAUDE.md` — add CSO to the ontologies section and ALWAYS_INCLUDED docs
- Modify: `~/.claude/projects/-Users-hjrnunes-workspace-redhat-hjrnunes-taxonomy-refiner/memory/MEMORY.md` — update index sizes, add CSO entry

- [ ] **Step 1: Update CLAUDE.md**

In the Directory Structure section, add under `ontologies/`:
```
  cso/                     # Content Safety Ontology (CSO) — ~195 classes
                           # 9 harm categories: Violence, Hate/Discrimination, Self-Harm,
                           # Sexual Exploitation, Sexual Content, Fraud/Deception,
                           # Dangerous Information, Intellectual Property, Privacy Violation
                           # Standalone (not BFO-aligned), rdfs:comment for definitions
                           # Namespace: http://taxonomy-refiner.io/ontologies/cso#
```

In the Domain Ontologies table, add a row:
```
| Content Safety (cross-domain) | **CSO** (~195 classes) | No (standalone) | N/A | Always-included. Covers harm categories CCO lacks. |
```

In the "Domain Filtering" notes, update `ALWAYS_INCLUDED` reference:
```
ALWAYS_INCLUDED = ["CCO", "Commons", "D3FEND", "CSO"]
```

- [ ] **Step 2: Update project memory**

Update `MEMORY.md`:
- Add CSO entry under "Ontology Files Downloaded"
- Update tested index sizes to include CSO (~90,230 classes)
- Update ALWAYS_INCLUDED reference

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add CSO to CLAUDE.md"
```
