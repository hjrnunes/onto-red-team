# Ontology Integration Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace text-similarity-based ontology discovery with a two-layer SSSOM mapping architecture (Risk→AIRO/DPV→Domain Ontology) in the anchor and contextualize pipeline stages.

**Architecture:** Two SSSOM TSV files define the mapping layers. Layer 1 maps IBM RiskGroups to AIRO/DPV vocabulary concepts (stakeholder roles, data sensitivity, rights). Layer 2 maps those AIRO/DPV concepts to domain ontology branch URIs for structural graph navigation. The anchor stage resolves seeds through both layers, navigates the ontology graph structurally, and presents candidates with vocabulary context to the LLM. The contextualize stage uses policy-driven LLM generation instead of subclass enumeration.

**Tech Stack:** Python 3.11+, Pydantic 2, Instructor, pytest, uv (each subproject has own .venv)

**Spec:** `docs/superpowers/specs/2026-04-04-ontology-integration-redesign.md`

**Branch:** `experimental/sssom-ontology-redesign` (no merge to master)

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `refiner/data/risk-to-vocabulary.sssom.tsv` | Layer 1 SSSOM: RiskGroup → AIRO/DPV concepts |
| `refiner/data/vocabulary-to-ontology.sssom.tsv` | Layer 2 SSSOM: AIRO/DPV → Domain Ontology branches |
| `refiner/src/refiner/ontology_seeds.py` | SSSOM loader, seed resolution, vocabulary categorization |
| `refiner/tests/test_ontology_seeds.py` | Tests for SSSOM loading and seed resolution |

### Modified Files

| File | What Changes |
|------|-------------|
| `nexus-mcp/src/nexus_mcp/server.py` | Add `get_risk_group(risk_id)` handler |
| `nexus-mcp/tests/test_server.py` | Add tests for `get_risk_group` |
| `refiner/src/refiner/models.py` | Update `VariationAxis` (bfo_category, vocabulary_concept), `AxisEnumeration` (provenance values), `DomainContextAxis` (vocabulary_context) |
| `refiner/src/refiner/stages/anchor.py` | Rewrite: remove merge strategies + `_CATEGORY_ROLES` + `derive_roles()`, add structural navigation + tiered merge + vocabulary context prompt |
| `refiner/src/refiner/stages/contextualize.py` | Rewrite: policy-driven LLM generation replaces subclass enumeration |
| `refiner/src/refiner/pipeline.py` | Load SSSOM seeds at startup, pass to anchor, pass policy content to contextualize |
| `refiner/src/refiner/cli.py` | Remove `--search-strategy` option, add SSSOM file paths |
| `refiner/tests/conftest.py` | Add `mock_layer1_mappings`, `mock_layer2_mappings` fixtures, add `get_risk_group` to `mock_risk_handlers` |
| `refiner/tests/test_anchor.py` | Rewrite tests for new navigation/merge/prompt approach |
| `refiner/tests/test_contextualize.py` | Rewrite tests for policy-driven generation |

---

## Task 1: Branch Setup + SSSOM Seed Data Files

**Files:**
- Create: `refiner/data/risk-to-vocabulary.sssom.tsv`
- Create: `refiner/data/vocabulary-to-ontology.sssom.tsv`

- [ ] **Step 1: Create experimental branch**

```bash
cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner
git checkout -b experimental/sssom-ontology-redesign
```

- [ ] **Step 2: Create data directory**

```bash
ls refiner/data 2>/dev/null || mkdir -p refiner/data
```

- [ ] **Step 3: Create Layer 1 SSSOM file (risk-to-vocabulary)**

Write `refiner/data/risk-to-vocabulary.sssom.tsv`:

```tsv
# curie_map:
#   ibm-risk-atlas: https://www.ibm.com/docs/en/watsonx/saas?topic=
#   airo: https://delaramglp.github.io/airo#
#   eu-aiact: https://w3id.org/dpv/legal/eu/aiact#
#   pd: https://w3id.org/dpv/pd#
#   risk: https://w3id.org/dpv/risk#
#   eu-rights: https://w3id.org/dpv/legal/eu/rights#
#   justifications: https://w3id.org/dpv/justifications#
#   sector-finance: https://w3id.org/dpv/sector/finance#
#   sector-health: https://w3id.org/dpv/sector/health#
#   sector-law: https://w3id.org/dpv/sector/law#
#   tech: https://w3id.org/dpv/tech#
#   semapv: https://w3id.org/semapv/vocab/
#   skos: http://www.w3.org/2004/02/skos/core#
# mapping_set_id: risk-to-vocabulary
# mapping_set_description: Maps AI risk concepts to AIRO/DPV vocabulary for structured LLM context
# license: https://www.apache.org/licenses/LICENSE-2.0.html
subject_id	subject_label	predicate_id	object_id	object_label	mapping_justification	confidence
ibm-risk-atlas-fairness	Fairness	skos:relatedMatch	eu-aiact:AISubject	AI Subject	semapv:ManualMappingCuration	0.95
ibm-risk-atlas-fairness	Fairness	skos:relatedMatch	eu-aiact:AIDeployer	AI Deployer	semapv:ManualMappingCuration	0.85
ibm-risk-atlas-fairness	Fairness	skos:relatedMatch	pd:EthnicOrigin	Ethnic Origin	semapv:ManualMappingCuration	0.95
ibm-risk-atlas-fairness	Fairness	skos:relatedMatch	pd:Gender	Gender	semapv:ManualMappingCuration	0.95
ibm-risk-atlas-fairness	Fairness	skos:relatedMatch	pd:CreditScore	Credit Score	semapv:ManualMappingCuration	0.80
ibm-risk-atlas-fairness	Fairness	skos:relatedMatch	eu-rights:T3-Equality	Equality	semapv:ManualMappingCuration	0.90
ibm-risk-atlas-fairness	Fairness	skos:relatedMatch	sector-finance:CreditChecking	Credit Checking	semapv:ManualMappingCuration	0.75
ibm-risk-atlas-privacy	Privacy	skos:relatedMatch	eu-aiact:AISubject	AI Subject	semapv:ManualMappingCuration	0.95
ibm-risk-atlas-privacy	Privacy	skos:relatedMatch	eu-aiact:AIDeployer	AI Deployer	semapv:ManualMappingCuration	0.85
ibm-risk-atlas-privacy	Privacy	skos:relatedMatch	pd:Biometric	Biometric	semapv:ManualMappingCuration	0.90
ibm-risk-atlas-privacy	Privacy	skos:relatedMatch	pd:MedicalHealth	Medical Health	semapv:ManualMappingCuration	0.85
ibm-risk-atlas-privacy	Privacy	skos:relatedMatch	pd:Financial	Financial	semapv:ManualMappingCuration	0.80
ibm-risk-atlas-privacy	Privacy	skos:relatedMatch	justifications:LegitimateInterestOverride	Legitimate Interest Override	semapv:ManualMappingCuration	0.70
ibm-risk-atlas-privacy	Privacy	skos:relatedMatch	eu-rights:T2-DataProtection	Data Protection	semapv:ManualMappingCuration	0.90
ibm-risk-atlas-misuse	Misuse	skos:relatedMatch	eu-aiact:AIUser	AI User	semapv:ManualMappingCuration	0.90
ibm-risk-atlas-misuse	Misuse	skos:relatedMatch	eu-aiact:DeepFake	Deep Fake	semapv:ManualMappingCuration	0.80
ibm-risk-atlas-misuse	Misuse	skos:relatedMatch	risk:Threat	Threat	semapv:ManualMappingCuration	0.85
ibm-risk-atlas-misuse	Misuse	skos:relatedMatch	sector-law:CriminalLawEnforcement	Criminal Law Enforcement	semapv:ManualMappingCuration	0.70
ibm-risk-atlas-robustness	Robustness	skos:relatedMatch	eu-aiact:AIProvider	AI Provider	semapv:ManualMappingCuration	0.85
ibm-risk-atlas-robustness	Robustness	skos:relatedMatch	risk:Vulnerability	Vulnerability	semapv:ManualMappingCuration	0.90
ibm-risk-atlas-robustness	Robustness	skos:relatedMatch	risk:Threat	Threat	semapv:ManualMappingCuration	0.85
ibm-risk-atlas-legal-compliance	Legal Compliance	skos:relatedMatch	eu-aiact:AIProvider	AI Provider	semapv:ManualMappingCuration	0.90
ibm-risk-atlas-legal-compliance	Legal Compliance	skos:relatedMatch	eu-aiact:ConformityAssessment	Conformity Assessment	semapv:ManualMappingCuration	0.85
ibm-risk-atlas-legal-compliance	Legal Compliance	skos:relatedMatch	eu-aiact:MarketSurveillanceAuthority	Market Surveillance Authority	semapv:ManualMappingCuration	0.75
ibm-risk-atlas-value-alignment	Value Alignment	skos:relatedMatch	eu-aiact:AISubject	AI Subject	semapv:ManualMappingCuration	0.90
ibm-risk-atlas-value-alignment	Value Alignment	skos:relatedMatch	pd:EthnicOrigin	Ethnic Origin	semapv:ManualMappingCuration	0.85
ibm-risk-atlas-value-alignment	Value Alignment	skos:relatedMatch	eu-rights:T3-Equality	Equality	semapv:ManualMappingCuration	0.85
ibm-risk-atlas-explainability	Explainability	skos:relatedMatch	eu-aiact:AIDeployer	AI Deployer	semapv:ManualMappingCuration	0.85
ibm-risk-atlas-explainability	Explainability	skos:relatedMatch	eu-aiact:AISubject	AI Subject	semapv:ManualMappingCuration	0.80
ibm-risk-atlas-transparency	Transparency	skos:relatedMatch	eu-aiact:AIProvider	AI Provider	semapv:ManualMappingCuration	0.85
ibm-risk-atlas-transparency	Transparency	skos:relatedMatch	eu-aiact:AIDeployer	AI Deployer	semapv:ManualMappingCuration	0.80
ibm-risk-atlas-governance	Governance	skos:relatedMatch	eu-aiact:AIProvider	AI Provider	semapv:ManualMappingCuration	0.90
ibm-risk-atlas-governance	Governance	skos:relatedMatch	eu-aiact:ConformityAssessment	Conformity Assessment	semapv:ManualMappingCuration	0.80
ibm-risk-atlas-intellectual-property	Intellectual Property	skos:relatedMatch	eu-aiact:AIProvider	AI Provider	semapv:ManualMappingCuration	0.80
ibm-risk-atlas-societal-impact	Societal Impact	skos:relatedMatch	eu-aiact:AISubject	AI Subject	semapv:ManualMappingCuration	0.90
ibm-risk-atlas-societal-impact	Societal Impact	skos:relatedMatch	pd:EthnicOrigin	Ethnic Origin	semapv:ManualMappingCuration	0.80
ibm-risk-atlas-societal-impact	Societal Impact	skos:relatedMatch	eu-rights:T3-Equality	Equality	semapv:ManualMappingCuration	0.80
```

- [ ] **Step 4: Create Layer 2 SSSOM file (vocabulary-to-ontology)**

Write `refiner/data/vocabulary-to-ontology.sssom.tsv`:

```tsv
# curie_map:
#   pd: https://w3id.org/dpv/pd#
#   eu-aiact: https://w3id.org/dpv/legal/eu/aiact#
#   eu-rights: https://w3id.org/dpv/legal/eu/rights#
#   risk: https://w3id.org/dpv/risk#
#   justifications: https://w3id.org/dpv/justifications#
#   sector-finance: https://w3id.org/dpv/sector/finance#
#   sector-law: https://w3id.org/dpv/sector/law#
#   cso: http://taxonomy-refiner.io/ontologies/cso#
#   d3f: http://d3fend.mitre.org/ontologies/d3fend.owl#
#   cco: https://www.commoncoreontologies.org/
#   obo: http://purl.obolibrary.org/obo/
#   lkif: http://www.estrellaproject.org/lkif-core/
#   fibo: https://spec.edmcouncil.org/fibo/ontology/
#   semapv: https://w3id.org/semapv/vocab/
#   skos: http://www.w3.org/2004/02/skos/core#
# mapping_set_id: vocabulary-to-ontology
# mapping_set_description: Maps AIRO/DPV vocabulary concepts to domain ontology branches for structural navigation
# license: https://www.apache.org/licenses/LICENSE-2.0.html
subject_id	subject_label	predicate_id	object_id	object_label	mapping_justification	confidence
pd:EthnicOrigin	Ethnic Origin	skos:broadMatch	obo:HANCESTRO_0001	Ancestry	semapv:ManualMappingCuration	0.95
pd:Gender	Gender	skos:broadMatch	obo:GSSO_000000	Gender Sex and Sexual Orientation	semapv:ManualMappingCuration	0.95
pd:CreditScore	Credit Score	skos:relatedMatch	fibo:FBC/CreditRatings	Credit Ratings	semapv:ManualMappingCuration	0.90
pd:Biometric	Biometric	skos:broadMatch	cco:BiometricIdentifier	Biometric Identifier	semapv:ManualMappingCuration	0.85
pd:MedicalHealth	Medical Health	skos:broadMatch	obo:OGMS_0000031	Disease	semapv:ManualMappingCuration	0.85
pd:MedicalHealth	Medical Health	skos:broadMatch	obo:MAXO_0000001	Medical Action	semapv:ManualMappingCuration	0.80
pd:Financial	Financial	skos:broadMatch	fibo:FBC/FinancialProducts	Financial Products	semapv:ManualMappingCuration	0.85
eu-aiact:AISubject	AI Subject	skos:relatedMatch	cco:Person	Person	semapv:ManualMappingCuration	0.90
eu-aiact:AISubject	AI Subject	skos:relatedMatch	obo:OMRSE_00000000	Social Entities	semapv:ManualMappingCuration	0.80
eu-aiact:AIDeployer	AI Deployer	skos:relatedMatch	cco:Organization	Organization	semapv:ManualMappingCuration	0.85
eu-aiact:AIProvider	AI Provider	skos:relatedMatch	cco:Organization	Organization	semapv:ManualMappingCuration	0.85
risk:Threat	Threat	skos:broadMatch	d3f:OffensiveTechnique	Offensive Technique	semapv:ManualMappingCuration	0.90
risk:Threat	Threat	skos:broadMatch	cso:FraudAndDeception	Fraud and Deception	semapv:ManualMappingCuration	0.85
risk:Vulnerability	Vulnerability	skos:relatedMatch	d3f:DigitalArtifact	Digital Artifact	semapv:ManualMappingCuration	0.75
eu-aiact:ConformityAssessment	Conformity Assessment	skos:relatedMatch	lkif:norm.owl#Regulation	Regulation	semapv:ManualMappingCuration	0.80
eu-aiact:ConformityAssessment	Conformity Assessment	skos:relatedMatch	fibo:FBC/RegulatoryAgency	Regulatory Agency	semapv:ManualMappingCuration	0.75
eu-rights:T3-Equality	Equality	skos:relatedMatch	obo:GSSO_000000	Gender Sex and Sexual Orientation	semapv:ManualMappingCuration	0.85
eu-rights:T3-Equality	Equality	skos:relatedMatch	obo:HANCESTRO_0001	Ancestry	semapv:ManualMappingCuration	0.85
eu-rights:T2-DataProtection	Data Protection	skos:broadMatch	cso:PrivacyViolation	Privacy Violation	semapv:ManualMappingCuration	0.90
eu-rights:T2-DataProtection	Data Protection	skos:relatedMatch	d3f:DataExfiltration	Data Exfiltration	semapv:ManualMappingCuration	0.80
sector-finance:CreditChecking	Credit Checking	skos:relatedMatch	fibo:FBC/CreditRatings	Credit Ratings	semapv:ManualMappingCuration	0.85
sector-law:CriminalLawEnforcement	Criminal Law Enforcement	skos:relatedMatch	lkif:norm.owl#Regulation	Regulation	semapv:ManualMappingCuration	0.70
ibm-risk-atlas-robustness-model-behavior-manipulation	Robustness	skos:relatedMatch	d3f:OffensiveTechnique	Offensive Technique	semapv:ManualMappingCuration	0.85
ibm-risk-atlas-intellectual-property	Intellectual Property	skos:broadMatch	cso:IntellectualProperty	Intellectual Property	semapv:ManualMappingCuration	0.90
```

- [ ] **Step 5: Commit seed data files**

```bash
git add refiner/data/risk-to-vocabulary.sssom.tsv refiner/data/vocabulary-to-ontology.sssom.tsv
git commit -m "feat: add two-layer SSSOM seed mapping files

Layer 1: RiskGroup → AIRO/DPV vocabulary concepts
Layer 2: AIRO/DPV → Domain Ontology branches
Direct fallback seeds for robustness and IP"
```

---

## Task 2: SSSOM Loader Module + Tests

**Files:**
- Create: `refiner/src/refiner/ontology_seeds.py`
- Create: `refiner/tests/test_ontology_seeds.py`

- [ ] **Step 1: Write failing tests for SSSOM loading**

Write `refiner/tests/test_ontology_seeds.py`:

```python
import pytest
from pathlib import Path
from refiner.ontology_seeds import SSSOMMapping, SSSOMIndex, categorize_vocabulary, resolve_seeds


SAMPLE_TSV = """\
# curie_map:
#   ibm-risk-atlas: https://example.com/
#   pd: https://w3id.org/dpv/pd#
#   eu-aiact: https://w3id.org/dpv/legal/eu/aiact#
#   skos: http://www.w3.org/2004/02/skos/core#
# mapping_set_id: test
subject_id\tsubject_label\tpredicate_id\tobject_id\tobject_label\tmapping_justification\tconfidence
ibm-risk-atlas-privacy\tPrivacy\tskos:relatedMatch\tpd:Biometric\tBiometric\tsemapv:ManualMappingCuration\t0.90
ibm-risk-atlas-privacy\tPrivacy\tskos:relatedMatch\teu-aiact:AISubject\tAI Subject\tsemapv:ManualMappingCuration\t0.95
ibm-risk-atlas-fairness\tFairness\tskos:relatedMatch\tpd:EthnicOrigin\tEthnic Origin\tsemapv:ManualMappingCuration\t0.95
"""


@pytest.fixture
def sample_tsv(tmp_path):
    p = tmp_path / "test.sssom.tsv"
    p.write_text(SAMPLE_TSV)
    return p


class TestSSSOMIndex:
    def test_load_from_tsv(self, sample_tsv):
        idx = SSSOMIndex.from_tsv(sample_tsv)
        assert len(idx.mappings) == 3

    def test_get_by_subject(self, sample_tsv):
        idx = SSSOMIndex.from_tsv(sample_tsv)
        privacy = idx.get_by_subject("ibm-risk-atlas-privacy")
        assert len(privacy) == 2
        assert {m.object_id for m in privacy} == {"pd:Biometric", "eu-aiact:AISubject"}

    def test_get_by_subject_missing(self, sample_tsv):
        idx = SSSOMIndex.from_tsv(sample_tsv)
        assert idx.get_by_subject("nonexistent") == []

    def test_confidence_parsed(self, sample_tsv):
        idx = SSSOMIndex.from_tsv(sample_tsv)
        biometric = [m for m in idx.get_by_subject("ibm-risk-atlas-privacy")
                     if m.object_id == "pd:Biometric"][0]
        assert biometric.confidence == 0.90

    def test_skips_comments_and_header(self, sample_tsv):
        idx = SSSOMIndex.from_tsv(sample_tsv)
        # Should not include comment lines or header as mappings
        for m in idx.mappings:
            assert not m.subject_id.startswith("#")
            assert m.subject_id != "subject_id"


class TestCategorizeVocabulary:
    def test_categorizes_by_namespace(self, sample_tsv):
        idx = SSSOMIndex.from_tsv(sample_tsv)
        seeds = idx.get_by_subject("ibm-risk-atlas-privacy")
        cats = categorize_vocabulary(seeds)
        assert "pd:Biometric" in [c["concept_id"] for c in cats["data_sensitivity"]]
        assert "eu-aiact:AISubject" in [c["concept_id"] for c in cats["stakeholders"]]

    def test_empty_categories_for_no_matches(self):
        cats = categorize_vocabulary([])
        assert cats["stakeholders"] == []
        assert cats["data_sensitivity"] == []
        assert cats["rights"] == []


class TestResolveSeeds:
    @pytest.fixture
    def layer1(self, sample_tsv):
        return SSSOMIndex.from_tsv(sample_tsv)

    @pytest.fixture
    def layer2_tsv(self, tmp_path):
        content = """\
# mapping_set_id: test-l2
subject_id\tsubject_label\tpredicate_id\tobject_id\tobject_label\tmapping_justification\tconfidence
pd:Biometric\tBiometric\tskos:broadMatch\tcco:BiometricIdentifier\tBiometric Identifier\tsemapv:ManualMappingCuration\t0.85
pd:EthnicOrigin\tEthnic Origin\tskos:broadMatch\tobo:HANCESTRO_0001\tAncestry\tsemapv:ManualMappingCuration\t0.95
eu-aiact:AISubject\tAI Subject\tskos:relatedMatch\tcco:Person\tPerson\tsemapv:ManualMappingCuration\t0.90
"""
        p = tmp_path / "l2.sssom.tsv"
        p.write_text(content)
        return p

    @pytest.fixture
    def layer2(self, layer2_tsv):
        return SSSOMIndex.from_tsv(layer2_tsv)

    @pytest.fixture
    def mock_nexus(self):
        from unittest.mock import MagicMock
        return {
            "get_risk_details": MagicMock(return_value={"group": "ibm-risk-atlas-privacy"}),
            "get_related_risks": MagicMock(return_value=[]),
            "get_risk_group": MagicMock(return_value={"id": "ibm-risk-atlas-privacy", "name": "Privacy"}),
        }

    def test_resolves_group_level(self, layer1, layer2, mock_nexus):
        vocab_ctx, onto_seeds = resolve_seeds(
            risk_id="atlas-some-privacy-risk",
            risk_group_id="ibm-risk-atlas-privacy",
            nexus_handlers=mock_nexus,
            layer1_mappings=layer1,
            layer2_mappings=layer2,
        )
        onto_uris = {s["object_id"] for s in onto_seeds}
        assert "cco:BiometricIdentifier" in onto_uris
        assert "cco:Person" in onto_uris

    def test_effective_confidence_is_product(self, layer1, layer2, mock_nexus):
        _, onto_seeds = resolve_seeds(
            risk_id="atlas-some-privacy-risk",
            risk_group_id="ibm-risk-atlas-privacy",
            nexus_handlers=mock_nexus,
            layer1_mappings=layer1,
            layer2_mappings=layer2,
        )
        biometric_seed = [s for s in onto_seeds if s["object_id"] == "cco:BiometricIdentifier"][0]
        # Layer 1: pd:Biometric confidence=0.90, Layer 2: cco:BiometricIdentifier confidence=0.85
        assert abs(biometric_seed["effective_confidence"] - 0.90 * 0.85) < 0.001

    def test_vocabulary_context_populated(self, layer1, layer2, mock_nexus):
        vocab_ctx, _ = resolve_seeds(
            risk_id="atlas-some-privacy-risk",
            risk_group_id="ibm-risk-atlas-privacy",
            nexus_handlers=mock_nexus,
            layer1_mappings=layer1,
            layer2_mappings=layer2,
        )
        assert len(vocab_ctx["data_sensitivity"]) > 0
        assert len(vocab_ctx["stakeholders"]) > 0

    def test_cross_taxonomy_fallback(self, layer1, layer2, mock_nexus):
        mock_nexus["get_related_risks"].return_value = [
            {"id": "atlas-privacy-risk", "mapping_type": "exact",
             "taxonomy": "ibm-risk-atlas", "name": "Privacy risk", "description": ""}
        ]
        mock_nexus["get_risk_details"].return_value = {"group": "ibm-risk-atlas-privacy"}
        vocab_ctx, onto_seeds = resolve_seeds(
            risk_id="owasp-some-risk",
            risk_group_id=None,
            nexus_handlers=mock_nexus,
            layer1_mappings=layer1,
            layer2_mappings=layer2,
        )
        # Should have resolved via IBM fallback
        assert len(onto_seeds) > 0

    def test_deduplicates_by_object_id(self, layer1, layer2, mock_nexus):
        _, onto_seeds = resolve_seeds(
            risk_id="atlas-some-privacy-risk",
            risk_group_id="ibm-risk-atlas-privacy",
            nexus_handlers=mock_nexus,
            layer1_mappings=layer1,
            layer2_mappings=layer2,
        )
        uris = [s["object_id"] for s in onto_seeds]
        assert len(uris) == len(set(uris))
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/refiner
uv run pytest tests/test_ontology_seeds.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'refiner.ontology_seeds'`

- [ ] **Step 3: Implement ontology_seeds.py**

Write `refiner/src/refiner/ontology_seeds.py`:

```python
"""Two-layer SSSOM seed mapping loader and resolver.

Layer 1: RiskGroup → AIRO/DPV vocabulary concepts (structured LLM context)
Layer 2: AIRO/DPV → Domain Ontology branches (structural navigation targets)
"""

import csv
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Namespace → vocabulary category mapping
_VOCAB_CATEGORIES = {
    "eu-aiact": "stakeholders",
    "tech": "stakeholders",
    "airo": "risk_concepts",
    "pd": "data_sensitivity",
    "eu-rights": "rights",
    "justifications": "justifications",
    "sector-finance": "sector_purposes",
    "sector-health": "sector_purposes",
    "sector-law": "sector_purposes",
    "sector-education": "sector_purposes",
    "sector-infra": "sector_purposes",
    "sector-publicservices": "sector_purposes",
    "risk": "risk_concepts",
}

# EU AI Act concepts that are prohibited practices, not stakeholder roles
_PROHIBITED_PRACTICES = {"eu-aiact:DeepFake", "eu-aiact:EmotionRecognition"}


@dataclass(frozen=True)
class SSSOMMapping:
    subject_id: str
    subject_label: str
    predicate_id: str
    object_id: str
    object_label: str
    mapping_justification: str
    confidence: float


class SSSOMIndex:
    """Index of SSSOM mappings, keyed by subject_id for fast lookup."""

    def __init__(self, mappings: list[SSSOMMapping]):
        self.mappings = mappings
        self._by_subject: dict[str, list[SSSOMMapping]] = {}
        for m in mappings:
            self._by_subject.setdefault(m.subject_id, []).append(m)

    @classmethod
    def from_tsv(cls, path: Path) -> "SSSOMIndex":
        mappings = []
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter="\t")
            header_seen = False
            for row in reader:
                if not row or row[0].startswith("#"):
                    continue
                if not header_seen:
                    header_seen = True
                    continue  # skip header row
                if len(row) < 7:
                    continue
                mappings.append(SSSOMMapping(
                    subject_id=row[0].strip(),
                    subject_label=row[1].strip(),
                    predicate_id=row[2].strip(),
                    object_id=row[3].strip(),
                    object_label=row[4].strip(),
                    mapping_justification=row[5].strip(),
                    confidence=float(row[6].strip()),
                ))
        return cls(mappings)

    def get_by_subject(self, subject_id: str) -> list[SSSOMMapping]:
        return list(self._by_subject.get(subject_id, []))


def categorize_vocabulary(vocab_seeds: list[SSSOMMapping]) -> dict[str, list[dict]]:
    """Categorize AIRO/DPV vocabulary seeds by namespace for structured LLM context."""
    categories: dict[str, list[dict]] = {
        "stakeholders": [],
        "data_sensitivity": [],
        "rights": [],
        "justifications": [],
        "sector_purposes": [],
        "risk_concepts": [],
        "prohibited_practices": [],
    }
    seen = set()
    for seed in vocab_seeds:
        concept_id = seed.object_id
        if concept_id in seen:
            continue
        seen.add(concept_id)

        entry = {
            "concept_id": concept_id,
            "label": seed.object_label,
            "confidence": seed.confidence,
        }

        # Check for prohibited practices first (override namespace-based categorization)
        if concept_id in _PROHIBITED_PRACTICES:
            categories["prohibited_practices"].append(entry)
            continue

        prefix = concept_id.split(":")[0] if ":" in concept_id else ""
        category = _VOCAB_CATEGORIES.get(prefix, "risk_concepts")
        categories[category].append(entry)

    return categories


def _deduplicate_seeds(seeds: list[dict], key: str = "object_id") -> list[dict]:
    """Deduplicate seed dicts, keeping highest effective_confidence per key."""
    best: dict[str, dict] = {}
    for s in seeds:
        k = s[key]
        if k not in best or s.get("effective_confidence", 0) > best[k].get("effective_confidence", 0):
            best[k] = s
    return list(best.values())


def resolve_seeds(
    risk_id: str,
    risk_group_id: str | None,
    nexus_handlers: dict,
    layer1_mappings: SSSOMIndex,
    layer2_mappings: SSSOMIndex,
) -> tuple[dict[str, list[dict]], list[dict]]:
    """Resolve two-layer SSSOM seed mappings for a risk.

    Returns:
        vocabulary_context: categorized AIRO/DPV concepts for LLM context
        ontology_seeds: domain ontology branch URIs for structural navigation
    """
    # --- Layer 1: Risk → AIRO/DPV vocabulary ---
    vocab_seeds: list[SSSOMMapping] = []

    # 1. Direct risk-level vocabulary mappings
    vocab_seeds += layer1_mappings.get_by_subject(risk_id)

    # 2. RiskGroup-level vocabulary mappings
    if risk_group_id:
        vocab_seeds += layer1_mappings.get_by_subject(risk_group_id)

    # 3. Cross-taxonomy fallback: resolve non-IBM risks to IBM equivalents
    if not vocab_seeds and not risk_id.startswith("ibm-risk-atlas"):
        related = nexus_handlers["get_related_risks"](risk_id)
        for rel in related:
            rel_id = rel["id"]
            rel_taxonomy = rel.get("taxonomy", "")
            if rel_taxonomy == "ibm-risk-atlas" or rel_id.startswith("atlas-"):
                details = nexus_handlers["get_risk_details"](rel_id)
                if details and details.get("group"):
                    ibm_group = details["group"]
                    vocab_seeds += layer1_mappings.get_by_subject(ibm_group)
                    vocab_seeds += layer1_mappings.get_by_subject(rel_id)
                break

    # Deduplicate vocab seeds by object_id, keeping highest confidence
    seen_vocab: dict[str, SSSOMMapping] = {}
    for vs in vocab_seeds:
        if vs.object_id not in seen_vocab or vs.confidence > seen_vocab[vs.object_id].confidence:
            seen_vocab[vs.object_id] = vs
    vocab_seeds = list(seen_vocab.values())

    # --- Layer 2: AIRO/DPV → Domain Ontology ---
    ontology_seeds: list[dict] = []
    for vs in vocab_seeds:
        layer2_hits = layer2_mappings.get_by_subject(vs.object_id)
        for hit in layer2_hits:
            ontology_seeds.append({
                "subject_id": hit.subject_id,
                "subject_label": hit.subject_label,
                "predicate_id": hit.predicate_id,
                "object_id": hit.object_id,
                "object_label": hit.object_label,
                "confidence": hit.confidence,
                "effective_confidence": vs.confidence * hit.confidence,
                "vocabulary_concept": vs.object_id,
                "vocabulary_label": vs.object_label,
            })

    # Direct fallback seeds (RiskGroup → Ontology, no intermediate)
    if risk_group_id:
        direct = layer2_mappings.get_by_subject(risk_group_id)
        for ds in direct:
            ontology_seeds.append({
                "subject_id": ds.subject_id,
                "subject_label": ds.subject_label,
                "predicate_id": ds.predicate_id,
                "object_id": ds.object_id,
                "object_label": ds.object_label,
                "confidence": ds.confidence,
                "effective_confidence": ds.confidence,
                "vocabulary_concept": None,
                "vocabulary_label": None,
            })

    ontology_seeds = _deduplicate_seeds(ontology_seeds)

    # --- Build vocabulary context for LLM ---
    vocabulary_context = categorize_vocabulary(vocab_seeds)

    return vocabulary_context, ontology_seeds
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/refiner
uv run pytest tests/test_ontology_seeds.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner
git add refiner/src/refiner/ontology_seeds.py refiner/tests/test_ontology_seeds.py
git commit -m "feat: add two-layer SSSOM loader and seed resolution

SSSOMIndex loads TSV files, indexes by subject_id.
resolve_seeds() resolves Layer 1 (Risk→AIRO/DPV) then
Layer 2 (AIRO/DPV→Ontology) with cross-taxonomy fallback.
categorize_vocabulary() groups concepts by namespace for LLM context."
```

---

## Task 3: Add `get_risk_group` Handler to nexus-mcp

**Files:**
- Modify: `nexus-mcp/src/nexus_mcp/server.py:130-148`
- Modify: `nexus-mcp/tests/test_server.py`
- Modify: `nexus-mcp/tests/conftest.py`

- [ ] **Step 1: Write failing test**

Add to `nexus-mcp/tests/test_server.py`:

```python
def test_get_risk_group_returns_group_for_risk(tools):
    result = tools["get_risk_group"]("atlas-prompt-injection")
    assert result is not None
    assert result["id"] == "ibm-risk-atlas-robustness"
    assert result["name"] == "Robustness"


def test_get_risk_group_returns_none_for_unknown(tools):
    result = tools["get_risk_group"]("nonexistent-risk")
    assert result is None


def test_get_risk_group_works_with_tag(tools):
    result = tools["get_risk_group"]("prompt-injection")
    assert result is not None
    assert result["id"] == "ibm-risk-atlas-robustness"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/nexus-mcp
uv run pytest tests/test_server.py::test_get_risk_group_returns_group_for_risk -v
```

Expected: FAIL — `KeyError: 'get_risk_group'`

- [ ] **Step 3: Implement get_risk_group handler**

In `nexus-mcp/src/nexus_mcp/server.py`, add the handler function inside `create_tool_handlers()` (after `list_risk_groups` around line 148) and add it to the return dict:

```python
    def get_risk_group(risk_id: str) -> dict | None:
        """Return the RiskGroup containing the given risk."""
        risk = risks_by_id.get(risk_id) or risks_by_tag.get(risk_id)
        if risk is None:
            return None
        group_id = getattr(risk, "isPartOf", "")
        if not group_id:
            return None
        for g in groups:
            if not _is_risk_group(g):
                continue
            if g.id == group_id:
                return {
                    "id": g.id,
                    "name": g.name,
                    "taxonomy": getattr(g, "isDefinedByTaxonomy", ""),
                }
        return None
```

Add `"get_risk_group": get_risk_group,` to the return dict at line ~203.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/nexus-mcp
uv run pytest tests/test_server.py -v
```

Expected: All tests PASS (including new ones)

- [ ] **Step 5: Commit**

```bash
cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner
git add nexus-mcp/src/nexus_mcp/server.py nexus-mcp/tests/test_server.py
git commit -m "feat(nexus-mcp): add get_risk_group handler

Looks up the RiskGroup containing a given risk by ID or tag.
Returns group id, name, and taxonomy. Used by SSSOM seed
resolution for cross-taxonomy fallback."
```

---

## Task 4: Update Data Models

**Files:**
- Modify: `refiner/src/refiner/models.py`

- [ ] **Step 1: Update VariationAxis model**

In `refiner/src/refiner/models.py`, replace the `VariationAxis` class (lines 59-63):

```python
class VariationAxis(BaseModel):
    cco_class_uri: str
    cco_class_label: str
    bfo_category: str = ""
    vocabulary_concept: str = ""
    vocabulary_label: str = ""
    rationale: str
    # Kept for backward compatibility with emit stage
    roles: list[str] = []
```

- [ ] **Step 2: Update AxisEnumeration provenance**

In `refiner/src/refiner/models.py`, replace the `AxisEnumeration` class (lines 73-78):

```python
class AxisEnumeration(BaseModel):
    class_uri: str
    class_label: str
    source_ontology: str
    relevance: Literal["high", "medium", "low"]
    provenance: str = "generated"  # "generated", "subclass", "sibling"
```

- [ ] **Step 3: Update DomainContextAxis**

In `refiner/src/refiner/models.py`, replace the `DomainContextAxis` class (lines 81-85):

```python
class DomainContextAxis(BaseModel):
    cco_class_uri: str
    cco_class_label: str
    bfo_category: str = ""
    vocabulary_context: dict = {}
    enumerations: list[AxisEnumeration]
    # Kept for backward compatibility with emit stage
    roles: list[str] = []
```

- [ ] **Step 4: Update SampledAxis**

In `refiner/src/refiner/models.py`, replace the `SampledAxis` class (lines 99-106):

```python
class SampledAxis(BaseModel):
    cco_class_uri: str
    cco_class_label: str
    bfo_category: str = ""
    sampled_uri: str
    sampled_label: str
    source_ontology: str
    relevance: Literal["high", "medium", "low"]
    # Kept for backward compatibility with emit stage
    roles: list[str] = []
```

- [ ] **Step 5: Run existing model tests**

```bash
cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/refiner
uv run pytest tests/test_models.py -v
```

Expected: PASS (new fields have defaults, backward compatible)

- [ ] **Step 6: Commit**

```bash
cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner
git add refiner/src/refiner/models.py
git commit -m "feat: update data models for SSSOM redesign

VariationAxis: add bfo_category, vocabulary_concept/label fields
AxisEnumeration: generalize provenance from literal to str
DomainContextAxis: add bfo_category, vocabulary_context fields
All changes backward compatible via defaults."
```

---

## Task 5: Structural Navigation + BFO Category Derivation

**Files:**
- Modify: `refiner/src/refiner/stages/anchor.py`
- Create: `refiner/tests/test_structural_navigation.py`

This task adds the new navigation functions to anchor.py without removing existing code yet. The old code will be removed in Task 9 when the main `anchor()` function is rewritten.

- [ ] **Step 1: Write failing tests**

Write `refiner/tests/test_structural_navigation.py`:

```python
import pytest
from unittest.mock import MagicMock
from refiner.stages.anchor import (
    navigate_from_seeds,
    constrained_search,
    check_structural_connection,
    merge_tiered,
    derive_bfo_category,
)


@pytest.fixture
def mock_onto():
    handlers = {
        "get_subclasses": MagicMock(return_value=[]),
        "get_siblings": MagicMock(return_value=[]),
        "get_restrictions": MagicMock(return_value=[]),
        "get_class_definition": MagicMock(return_value=None),
        "get_superclasses": MagicMock(return_value=[]),
        "search_domains": MagicMock(return_value={}),
    }
    return handlers


class TestDeriveBfoCategory:
    def test_returns_bfo_category(self, mock_onto):
        mock_onto["get_superclasses"].side_effect = [
            [{"uri": "http://purl.obolibrary.org/obo/BFO_0000040", "label": "material entity"}],
        ]
        result = derive_bfo_category("http://example.org/Person", mock_onto)
        assert result == "MaterialEntity"

    def test_walks_chain(self, mock_onto):
        mock_onto["get_superclasses"].side_effect = [
            [{"uri": "http://example.org/Mid", "label": "Mid"}],
            [{"uri": "http://purl.obolibrary.org/obo/BFO_0000015", "label": "process"}],
        ]
        result = derive_bfo_category("http://example.org/SomeProcess", mock_onto)
        assert result == "Process"

    def test_returns_empty_on_no_match(self, mock_onto):
        mock_onto["get_superclasses"].return_value = []
        result = derive_bfo_category("http://example.org/Unknown", mock_onto)
        assert result == ""


class TestNavigateFromSeeds:
    def test_broad_match_navigates_down(self, mock_onto):
        mock_onto["get_subclasses"].return_value = [
            {"uri": "http://example.org/Sub1", "label": "Sub1", "depth": 1},
            {"uri": "http://example.org/Sub2", "label": "Sub2", "depth": 2},
        ]
        seeds = [{
            "object_id": "http://example.org/Parent",
            "object_label": "Parent",
            "predicate_id": "skos:broadMatch",
            "effective_confidence": 0.9,
            "vocabulary_concept": "pd:Biometric",
            "vocabulary_label": "Biometric",
        }]
        result = navigate_from_seeds(seeds, mock_onto, selected_domains=None)
        assert len(result) >= 2
        assert all(c["source"] == "structural" for c in result)

    def test_exact_match_uses_directly(self, mock_onto):
        mock_onto["get_class_definition"].return_value = {
            "uri": "http://example.org/Exact", "label": "Exact", "definition": "test"
        }
        seeds = [{
            "object_id": "http://example.org/Exact",
            "object_label": "Exact",
            "predicate_id": "skos:exactMatch",
            "effective_confidence": 0.95,
            "vocabulary_concept": "pd:Biometric",
            "vocabulary_label": "Biometric",
        }]
        result = navigate_from_seeds(seeds, mock_onto, selected_domains=None)
        assert len(result) == 1
        assert result[0]["uri"] == "http://example.org/Exact"

    def test_related_match_navigates_around(self, mock_onto):
        mock_onto["get_restrictions"].return_value = [
            {"type": "someValuesFrom", "property": "http://example.org/prop",
             "filler": "http://example.org/Filler"}
        ]
        mock_onto["get_class_definition"].side_effect = lambda uri: (
            {"uri": uri, "label": uri.split("/")[-1], "definition": "test"}
            if uri != "invalid" else None
        )
        mock_onto["get_siblings"].return_value = [
            {"uri": "http://example.org/Sibling", "label": "Sibling"}
        ]
        seeds = [{
            "object_id": "http://example.org/Related",
            "object_label": "Related",
            "predicate_id": "skos:relatedMatch",
            "effective_confidence": 0.8,
            "vocabulary_concept": "risk:Threat",
            "vocabulary_label": "Threat",
        }]
        result = navigate_from_seeds(seeds, mock_onto, selected_domains=None)
        uris = {c["uri"] for c in result}
        # Should include seed, filler from restriction, sibling
        assert "http://example.org/Related" in uris
        assert "http://example.org/Filler" in uris


class TestCheckStructuralConnection:
    def test_connected_via_common_ancestor(self, mock_onto):
        mock_onto["get_superclasses"].side_effect = lambda uri: (
            [{"uri": "http://example.org/Ancestor", "label": "Ancestor"}]
        )
        result = check_structural_connection(
            "http://example.org/A", ["http://example.org/B"], mock_onto
        )
        assert result["connected"] is True

    def test_not_connected(self, mock_onto):
        mock_onto["get_superclasses"].return_value = []
        result = check_structural_connection(
            "http://example.org/A", ["http://example.org/B"], mock_onto
        )
        assert result["connected"] is False


class TestMergeTiered:
    def test_tier1_first(self):
        structural = [
            {"uri": "s1", "effective_confidence": 0.9, "path": ["a", "s1"],
             "vocabulary_concept": "pd:X"},
            {"uri": "s2", "effective_confidence": 0.8, "path": ["a", "s2"],
             "vocabulary_concept": "eu-aiact:Y"},
        ]
        search_connected = [{"uri": "sc1", "best_distance": 0.3, "vocabulary_concept": "pd:X"}]
        search_only = [{"uri": "so1", "best_distance": 0.2, "vocabulary_concept": None}]
        result = merge_tiered(structural, search_connected, search_only)
        assert result[0]["uri"] == "s1"
        assert result[1]["uri"] == "s2"

    def test_deduplicates(self):
        structural = [
            {"uri": "dup", "effective_confidence": 0.9, "path": ["a"],
             "vocabulary_concept": "pd:X"},
        ]
        search_connected = [{"uri": "dup", "best_distance": 0.3, "vocabulary_concept": "pd:X"}]
        result = merge_tiered(structural, search_connected, [])
        assert len([r for r in result if r["uri"] == "dup"]) == 1

    def test_caps_at_max(self):
        structural = [
            {"uri": f"s{i}", "effective_confidence": 0.9 - i*0.01, "path": ["a"],
             "vocabulary_concept": f"pd:X{i}"}
            for i in range(15)
        ]
        result = merge_tiered(structural, [], [], max_total=12)
        assert len(result) <= 12
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/refiner
uv run pytest tests/test_structural_navigation.py -v
```

Expected: FAIL — `ImportError: cannot import name 'navigate_from_seeds'`

- [ ] **Step 3: Implement the new functions in anchor.py**

Add the following functions to `refiner/src/refiner/stages/anchor.py` (after `build_generic_safety_uris`, before the `anchor()` function):

```python
# --- BFO category labels (lightweight replacement for _CATEGORY_ROLES) ---

_BFO_CATEGORIES: dict[str, str] = {
    "http://purl.obolibrary.org/obo/BFO_0000040": "MaterialEntity",
    "http://purl.obolibrary.org/obo/BFO_0000015": "Process",
    "http://purl.obolibrary.org/obo/BFO_0000031": "GenericallyDependentContinuant",
    "http://purl.obolibrary.org/obo/BFO_0000020": "Quality",
    "http://purl.obolibrary.org/obo/BFO_0000023": "Role",
    "http://purl.obolibrary.org/obo/BFO_0000016": "Disposition",
    "http://purl.obolibrary.org/obo/BFO_0000017": "RealizableEntity",
    "http://purl.obolibrary.org/obo/BFO_0000029": "Site",
    "http://purl.obolibrary.org/obo/BFO_0000006": "SpatialRegion",
    "http://purl.obolibrary.org/obo/BFO_0000141": "ImmaterialEntity",
    "http://purl.obolibrary.org/obo/BFO_0000008": "TemporalRegion",
    "http://purl.obolibrary.org/obo/BFO_0000019": "Quality",
    # CCO shortcuts
    "https://www.commoncoreontologies.org/ont00000958": "InformationContentEntity",
    "https://www.commoncoreontologies.org/ont00001017": "Agent",
    "https://www.commoncoreontologies.org/ont00000995": "MaterialArtifact",
    "https://www.commoncoreontologies.org/ont00000192": "Facility",
    "https://www.commoncoreontologies.org/ont00000005": "Act",
}


def derive_bfo_category(class_uri: str, onto_handlers: dict, max_depth: int = 10) -> str:
    """Walk superclass chain to find BFO/CCO category name. Returns '' if not found."""
    visited = set()
    current = class_uri
    for _ in range(max_depth):
        if current in _BFO_CATEGORIES:
            return _BFO_CATEGORIES[current]
        if current in visited:
            break
        visited.add(current)
        supers = onto_handlers["get_superclasses"](current)
        named = [s for s in supers if s.get("uri") and s["uri"] not in visited]
        if not named:
            break
        current = named[0]["uri"]
    return ""


def navigate_from_seeds(
    seed_mappings: list[dict],
    onto_handlers: dict,
    selected_domains: list[str] | None,
    generic_safety_uris: set[str] | None = None,
) -> list[dict]:
    """Structural navigation from SSSOM seed URIs. Returns candidate dicts."""
    candidates = []
    safety = generic_safety_uris or set()

    for mapping in seed_mappings:
        seed_uri = mapping["object_id"]
        predicate = mapping["predicate_id"]
        confidence = mapping.get("effective_confidence", mapping.get("confidence", 0.5))
        vocab_concept = mapping.get("vocabulary_concept")
        vocab_label = mapping.get("vocabulary_label")

        if predicate == "skos:broadMatch":
            discovered = onto_handlers["get_subclasses"](seed_uri, depth=2)
            for cls in discovered:
                uri = cls["uri"]
                if _is_excluded_uri(uri, safety):
                    continue
                if selected_domains:
                    domain = derive_source_ontology(uri)
                    if domain and domain not in selected_domains:
                        continue
                candidates.append({
                    "uri": uri,
                    "label": cls.get("label", ""),
                    "source": "structural",
                    "path": [seed_uri, uri],
                    "seed_uri": seed_uri,
                    "effective_confidence": confidence,
                    "predicate": predicate,
                    "vocabulary_concept": vocab_concept,
                    "vocabulary_label": vocab_label,
                })

        elif predicate == "skos:relatedMatch":
            # Seed itself is a candidate
            defn = onto_handlers["get_class_definition"](seed_uri)
            if defn:
                candidates.append({
                    "uri": seed_uri,
                    "label": defn.get("label", mapping.get("object_label", "")),
                    "source": "structural",
                    "path": [seed_uri],
                    "seed_uri": seed_uri,
                    "effective_confidence": confidence,
                    "predicate": predicate,
                    "vocabulary_concept": vocab_concept,
                    "vocabulary_label": vocab_label,
                })
            # Navigate restrictions
            if onto_handlers.get("get_restrictions"):
                for r in onto_handlers["get_restrictions"](seed_uri):
                    filler = r.get("filler", "")
                    if not filler or _is_excluded_uri(filler, safety):
                        continue
                    filler_defn = onto_handlers["get_class_definition"](filler)
                    if filler_defn:
                        candidates.append({
                            "uri": filler,
                            "label": filler_defn.get("label", ""),
                            "source": "structural",
                            "path": [seed_uri, filler],
                            "seed_uri": seed_uri,
                            "effective_confidence": confidence * 0.9,
                            "predicate": predicate,
                            "vocabulary_concept": vocab_concept,
                            "vocabulary_label": vocab_label,
                            "restriction_property": r.get("property", ""),
                        })
            # Navigate siblings
            for s in onto_handlers["get_siblings"](seed_uri):
                s_uri = s["uri"]
                if _is_excluded_uri(s_uri, safety):
                    continue
                if selected_domains:
                    domain = derive_source_ontology(s_uri)
                    if domain and domain not in selected_domains:
                        continue
                candidates.append({
                    "uri": s_uri,
                    "label": s.get("label", ""),
                    "source": "structural",
                    "path": [seed_uri, s_uri],
                    "seed_uri": seed_uri,
                    "effective_confidence": confidence * 0.8,
                    "predicate": predicate,
                    "vocabulary_concept": vocab_concept,
                    "vocabulary_label": vocab_label,
                })

        elif predicate in ("skos:exactMatch", "skos:closeMatch"):
            defn = onto_handlers["get_class_definition"](seed_uri)
            if defn:
                candidates.append({
                    "uri": seed_uri,
                    "label": defn.get("label", mapping.get("object_label", "")),
                    "source": "structural",
                    "path": [seed_uri],
                    "seed_uri": seed_uri,
                    "effective_confidence": confidence,
                    "predicate": predicate,
                    "vocabulary_concept": vocab_concept,
                    "vocabulary_label": vocab_label,
                })
            if predicate == "skos:closeMatch":
                for sub in onto_handlers["get_subclasses"](seed_uri, depth=1):
                    candidates.append({
                        "uri": sub["uri"],
                        "label": sub.get("label", ""),
                        "source": "structural",
                        "path": [seed_uri, sub["uri"]],
                        "seed_uri": seed_uri,
                        "effective_confidence": confidence * 0.9,
                        "predicate": predicate,
                        "vocabulary_concept": vocab_concept,
                        "vocabulary_label": vocab_label,
                    })

    # Deduplicate by URI, keep highest confidence
    seen: dict[str, dict] = {}
    for c in candidates:
        uri = c["uri"]
        if uri not in seen or c["effective_confidence"] > seen[uri]["effective_confidence"]:
            seen[uri] = c
    return list(seen.values())


def constrained_search(
    risk_description: str,
    seed_mappings: list[dict],
    onto_handlers: dict,
    selected_domains: list[str] | None,
    top_k: int = 8,
) -> list[dict]:
    """ChromaDB search scoped to domains containing seed URIs."""
    if not onto_handlers.get("search_domains") or not selected_domains:
        return []

    seed_domains = set()
    for m in seed_mappings:
        domain = derive_source_ontology(m["object_id"])
        if domain:
            seed_domains.add(domain)
    search_domains = list(seed_domains & set(selected_domains))
    if not search_domains:
        return []

    raw = onto_handlers["search_domains"](risk_description, search_domains, top_k_per_domain=top_k)
    results = []
    for domain, hits in raw.items():
        if not isinstance(hits, list):
            continue
        for hit in hits:
            results.append({
                "uri": hit["uri"],
                "label": hit.get("label", ""),
                "source": "search",
                "best_distance": hit.get("distance", 1.0),
                "domain": domain,
                "vocabulary_concept": None,
                "vocabulary_label": None,
            })
    return results


def check_structural_connection(
    candidate_uri: str,
    seed_uris: list[str],
    onto_handlers: dict,
    max_hops: int = 3,
) -> dict:
    """Check if candidate shares a common ancestor with any seed URI."""
    def _walk(uri, depth):
        ancestors = set()
        visited = set()
        frontier = [uri]
        for _ in range(depth):
            next_frontier = []
            for u in frontier:
                if u in visited:
                    continue
                visited.add(u)
                supers = onto_handlers["get_superclasses"](u)
                for s in supers:
                    s_uri = s["uri"]
                    ancestors.add(s_uri)
                    next_frontier.append(s_uri)
            frontier = next_frontier
        return ancestors

    cand_ancestors = _walk(candidate_uri, max_hops)
    cand_ancestors.add(candidate_uri)
    for seed_uri in seed_uris:
        seed_ancestors = _walk(seed_uri, max_hops)
        seed_ancestors.add(seed_uri)
        common = cand_ancestors & seed_ancestors
        if common:
            return {"connected": True, "common_ancestor": next(iter(common))}
    return {"connected": False}


def merge_tiered(
    structural: list[dict],
    search_connected: list[dict],
    search_only: list[dict],
    max_total: int = 12,
) -> list[dict]:
    """Three-tier merge with vocabulary diversity check."""
    result = []
    seen = set()

    # Tier 1: structural, sorted by effective confidence then path length
    for c in sorted(structural, key=lambda c: (-c.get("effective_confidence", 0), len(c.get("path", [])))):
        if c["uri"] not in seen and len(result) < 8:
            result.append(c)
            seen.add(c["uri"])

    # Tier 2: search-connected, sorted by distance
    for c in sorted(search_connected, key=lambda c: c.get("best_distance", 1.0)):
        if c["uri"] not in seen and len(result) < 10:
            result.append(c)
            seen.add(c["uri"])

    # Tier 3: search-only, sorted by distance
    for c in sorted(search_only, key=lambda c: c.get("best_distance", 1.0)):
        if c["uri"] not in seen and len(result) < max_total:
            result.append(c)
            seen.add(c["uri"])

    # Vocabulary diversity check
    vocab_categories = {
        c.get("vocabulary_concept", "").split(":")[0]
        for c in result if c.get("vocabulary_concept")
    }
    if len(vocab_categories) < 2:
        all_remaining = [
            c for pool in [structural, search_connected, search_only]
            for c in pool if c["uri"] not in seen and c.get("vocabulary_concept")
        ]
        for c in all_remaining:
            cat = c["vocabulary_concept"].split(":")[0]
            if cat not in vocab_categories:
                result.append(c)
                seen.add(c["uri"])
                vocab_categories.add(cat)
                if len(vocab_categories) >= 2:
                    break

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/refiner
uv run pytest tests/test_structural_navigation.py -v
```

Expected: All PASS

- [ ] **Step 5: Run existing anchor tests to ensure no regressions**

```bash
cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/refiner
uv run pytest tests/test_anchor.py -v
```

Expected: All existing tests PASS (new functions added alongside old ones)

- [ ] **Step 6: Commit**

```bash
cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner
git add refiner/src/refiner/stages/anchor.py refiner/tests/test_structural_navigation.py
git commit -m "feat(anchor): add structural navigation, tiered merge, BFO category derivation

navigate_from_seeds: graph walk from SSSOM seed URIs
constrained_search: ChromaDB scoped to seed domains
check_structural_connection: common ancestor check
merge_tiered: three-tier merge with vocabulary diversity
derive_bfo_category: lightweight BFO category from superclass chain"
```

---

## Task 6: Rewrite Anchor Stage Main Function

**Files:**
- Modify: `refiner/src/refiner/stages/anchor.py`
- Modify: `refiner/tests/test_anchor.py`

This is the core rewrite. The `anchor()` function signature changes to accept SSSOM mappings instead of a merge strategy. The old merge strategies and `_CATEGORY_ROLES`/`derive_roles()` are removed.

- [ ] **Step 1: Write key tests for the new anchor behavior**

Add a new test file `refiner/tests/test_anchor_v2.py` for the rewritten anchor function:

```python
"""Tests for the SSSOM-based anchor stage (v2 redesign)."""
import pytest
from unittest.mock import MagicMock
from refiner.models import PolicyRiskMapping, RiskMatch, RiskVariationAxes
from refiner.ontology_seeds import SSSOMIndex, SSSOMMapping
from refiner.stages.anchor import anchor


@pytest.fixture
def mock_config():
    from refiner.llm import LLMConfig
    return LLMConfig(base_url="http://localhost:8000/v1", model="test-model")


@pytest.fixture
def mock_client():
    client = MagicMock()
    return client


@pytest.fixture
def mock_onto_handlers():
    return {
        "search_classes": MagicMock(return_value=[]),
        "search_domains": MagicMock(return_value={}),
        "get_class_definition": MagicMock(side_effect=lambda uri: {
            "uri": uri, "label": uri.split("/")[-1].split("#")[-1],
            "definition": f"Definition of {uri.split('/')[-1]}",
            "superclasses": [],
        }),
        "get_subclasses": MagicMock(return_value=[]),
        "get_superclasses": MagicMock(return_value=[]),
        "get_siblings": MagicMock(return_value=[]),
        "get_properties": MagicMock(return_value=[]),
        "explore_class": MagicMock(return_value=None),
        "get_restrictions": MagicMock(return_value=[]),
        "get_disjoint_classes": MagicMock(return_value=[]),
        "get_equivalent_axioms": MagicMock(return_value=[]),
    }


@pytest.fixture
def mock_nexus_handlers():
    return {
        "get_risk_details": MagicMock(return_value={"group": "ibm-risk-atlas-privacy"}),
        "get_related_risks": MagicMock(return_value=[]),
        "get_related_actions": MagicMock(return_value=[]),
        "get_risk_group": MagicMock(return_value={"id": "ibm-risk-atlas-privacy", "name": "Privacy"}),
    }


@pytest.fixture
def layer1():
    return SSSOMIndex([
        SSSOMMapping("ibm-risk-atlas-privacy", "Privacy", "skos:relatedMatch",
                     "pd:Biometric", "Biometric", "semapv:ManualMappingCuration", 0.90),
        SSSOMMapping("ibm-risk-atlas-privacy", "Privacy", "skos:relatedMatch",
                     "eu-aiact:AISubject", "AI Subject", "semapv:ManualMappingCuration", 0.95),
    ])


@pytest.fixture
def layer2():
    return SSSOMIndex([
        SSSOMMapping("pd:Biometric", "Biometric", "skos:broadMatch",
                     "http://example.org/BiometricId", "Biometric Identifier",
                     "semapv:ManualMappingCuration", 0.85),
        SSSOMMapping("eu-aiact:AISubject", "AI Subject", "skos:relatedMatch",
                     "http://example.org/Person", "Person",
                     "semapv:ManualMappingCuration", 0.90),
    ])


@pytest.fixture
def sample_mapping():
    return PolicyRiskMapping(
        policy_concept="Do not disclose biometric data",
        policy_type="A",
        matched_risks=[RiskMatch(
            risk_id="atlas-biometric-exposure",
            risk_name="Biometric exposure",
            relevance="primary",
            justification="Direct match",
        )],
    )


@pytest.fixture
def sample_risk_details():
    return {
        "atlas-biometric-exposure": {
            "id": "atlas-biometric-exposure",
            "name": "Biometric exposure",
            "description": "Risk of biometric data being exposed",
            "concern": "Biometric identifiers leaked",
            "group": "ibm-risk-atlas-privacy",
        }
    }


def test_anchor_uses_sssom_seeds(
    mock_client, mock_config, mock_onto_handlers, mock_nexus_handlers,
    layer1, layer2, sample_mapping, sample_risk_details
):
    """Anchor should resolve seeds via two-layer SSSOM and call navigate_from_seeds."""
    from refiner.stages.anchor import _AnchorResponse, _SlimAxis

    mock_onto_handlers["get_subclasses"].return_value = [
        {"uri": "http://example.org/FacialPrint", "label": "Facial Print", "depth": 1}
    ]
    mock_client.chat.completions.create.return_value = _AnchorResponse(axes=[
        _SlimAxis(class_id="C1", class_label="Facial Print", role="object", rationale="relevant")
    ])
    result = anchor(
        risk_mappings=[sample_mapping],
        risk_details=sample_risk_details,
        client=mock_client,
        config=mock_config,
        onto_handlers=mock_onto_handlers,
        nexus_handlers=mock_nexus_handlers,
        layer1_mappings=layer1,
        layer2_mappings=layer2,
    )
    assert len(result) == 1
    assert len(result[0].axes) >= 1


def test_anchor_caches_by_risk_id(
    mock_client, mock_config, mock_onto_handlers, mock_nexus_handlers,
    layer1, layer2, sample_risk_details
):
    """Same risk from two policies should use cache."""
    from refiner.stages.anchor import _AnchorResponse, _SlimAxis
    mock_client.chat.completions.create.return_value = _AnchorResponse(axes=[])

    mapping1 = PolicyRiskMapping(
        policy_concept="Policy A", policy_type="A",
        matched_risks=[RiskMatch(risk_id="atlas-biometric-exposure", risk_name="Bio",
                                 relevance="primary", justification="test")],
    )
    mapping2 = PolicyRiskMapping(
        policy_concept="Policy B", policy_type="A",
        matched_risks=[RiskMatch(risk_id="atlas-biometric-exposure", risk_name="Bio",
                                 relevance="primary", justification="test")],
    )
    result = anchor(
        risk_mappings=[mapping1, mapping2],
        risk_details=sample_risk_details,
        client=mock_client,
        config=mock_config,
        onto_handlers=mock_onto_handlers,
        nexus_handlers=mock_nexus_handlers,
        layer1_mappings=layer1,
        layer2_mappings=layer2,
    )
    assert len(result) == 2
    # LLM should only be called once (second is cached)
    assert mock_client.chat.completions.create.call_count == 1
```

- [ ] **Step 2: Rewrite the anchor() function**

This is the main rewrite. In `refiner/src/refiner/stages/anchor.py`:

1. Update the imports to include `ontology_seeds` types
2. Update `_SlimAxis` to use `bfo_category` instead of `role`
3. Update `SYSTEM_PROMPT` with vocabulary context instructions
4. Rewrite `anchor()` to accept `nexus_handlers`, `layer1_mappings`, `layer2_mappings` instead of `merge_strategy`
5. Replace `expand_candidates()` call with `resolve_seeds()` → `navigate_from_seeds()` → `constrained_search()` → `merge_tiered()`
6. Build vocabulary context block in the LLM prompt
7. Remove `derive_roles()` call, use `derive_bfo_category()` instead

The new `anchor()` signature:

```python
def anchor(
    risk_mappings: list[PolicyRiskMapping],
    risk_details: dict[str, dict],
    client: instructor.Instructor,
    config: LLMConfig,
    onto_handlers: dict,
    selected_domains: list[str] | None = None,
    risk_actions: dict[str, list[str]] | None = None,
    related_risks: dict[str, list[dict]] | None = None,
    nexus_handlers: dict | None = None,
    layer1_mappings: "SSSOMIndex | None" = None,
    layer2_mappings: "SSSOMIndex | None" = None,
    report=None,
    generic_safety_uris: set[str] | None = None,
) -> list[RiskVariationAxes]:
```

The new system prompt:

```python
SYSTEM_PROMPT = """\
You are identifying variation axes for AI risk concepts using ontology classes.

A variation axis is an ontology class that represents a dimension along which
diverse prompts can be generated. Each candidate has a BFO category tag
(MaterialEntity, Process, InformationContentEntity, etc.) and provenance
showing how it was discovered.

You are also given vocabulary context describing:
- Stakeholders: who is involved in this AI risk
- Data sensitivity: what sensitive data categories are at stake
- Rights at stake: which fundamental rights may be violated
- Sector context: in which operational contexts this risk arises

Use this context to select the most semantically relevant classes.
Reference each selected class by its candidate ID (e.g. C1).

Return 2-3 axes max.
"""
```

The core loop in the rewritten `anchor()`:

```python
    for mapping in risk_mappings:
        for risk_match in mapping.matched_risks:
            risk_id = risk_match.risk_id
            if risk_id in axes_cache:
                # ... cache hit (same as before)
                continue

            details = risk_details.get(risk_id, {})
            description = details.get("description", "")
            concern = details.get("concern", "")
            risk_group_id = details.get("group", "")

            # --- SSSOM seed resolution ---
            if layer1_mappings and layer2_mappings:
                vocabulary_context, ontology_seeds = resolve_seeds(
                    risk_id, risk_group_id,
                    nexus_handlers or {},
                    layer1_mappings, layer2_mappings,
                )

                # Structural navigation
                structural = navigate_from_seeds(
                    ontology_seeds, onto_handlers, selected_domains, generic_safety_uris
                )

                # Constrained search
                search_results = constrained_search(
                    description, ontology_seeds, onto_handlers, selected_domains
                )

                # Classify search results
                seed_uris = [s["object_id"] for s in ontology_seeds]
                structural_uris = {c["uri"] for c in structural}
                search_connected = []
                search_only = []
                for sr in search_results:
                    if sr["uri"] in structural_uris:
                        continue
                    conn = check_structural_connection(sr["uri"], seed_uris, onto_handlers)
                    if conn["connected"]:
                        sr["common_ancestor"] = conn.get("common_ancestor")
                        search_connected.append(sr)
                    else:
                        search_only.append(sr)

                # Tiered merge
                candidates = merge_tiered(structural, search_connected, search_only)
            else:
                # Fallback: legacy expand_candidates (backward compat during migration)
                candidates, _ = expand_candidates(
                    description, concern, ..., onto_handlers, selected_domains,
                )
                vocabulary_context = {}

            # Enrich candidates
            enriched = []
            for i, c in enumerate(candidates):
                defn = onto_handlers["get_class_definition"](c["uri"])
                if not defn:
                    continue
                bfo_cat = derive_bfo_category(c["uri"], onto_handlers)
                siblings = onto_handlers["get_siblings"](c["uri"])
                enriched.append({
                    "id": f"C{i+1}",
                    "uri": c["uri"],
                    "label": defn.get("label", c.get("label", "")),
                    "definition": defn.get("definition", ""),
                    "bfo_category": bfo_cat,
                    "source": c.get("source", ""),
                    "vocabulary_concept": c.get("vocabulary_concept", ""),
                    "vocabulary_label": c.get("vocabulary_label", ""),
                    "path": c.get("path", []),
                    "siblings": [s.get("label", "") for s in siblings[:5]],
                })

            if not enriched:
                axes_cache[risk_id] = []
                # ... emit empty_axes event
                continue

            # Build vocabulary context block
            vocab_lines = _format_vocabulary_context(vocabulary_context)

            # Build candidate list
            candidate_lines = []
            id_to_uri = {}
            for e in enriched:
                id_to_uri[e["id"]] = e["uri"]
                via = f" (via {e['vocabulary_label']})" if e.get("vocabulary_label") else ""
                cat_tag = f" [{e['bfo_category']}]" if e['bfo_category'] else ""
                source_tag = f"-- {e['source']}{via}"
                block = f"## {e['id']}: {e['label']}{cat_tag} {source_tag}\n"
                if e["definition"]:
                    block += f"Definition: {e['definition'][:200]}\n"
                if e.get("path") and len(e["path"]) > 1:
                    path_labels = " > ".join(p.split("/")[-1].split("#")[-1] for p in e["path"])
                    block += f"Path: {path_labels}\n"
                if e["siblings"]:
                    block += f"Siblings: {', '.join(e['siblings'])}\n"
                candidate_lines.append(block)

            user_content = (
                f"Risk: {risk_match.risk_name}\n"
                f"Description: {description}\n"
                f"Concern: {concern}\n"
                f"Policy: {mapping.policy_concept}\n\n"
                f"{vocab_lines}\n"
                f"Candidate classes:\n\n"
                + "\n".join(candidate_lines)
            )

            # Call LLM
            result = client.chat.completions.create(
                model=config.model,
                response_model=_AnchorResponse,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                temperature=config.temperature,
                max_retries=config.max_retries,
            )

            # Post-process: map IDs to URIs, build VariationAxis objects
            axes = []
            for axis in result.axes:
                uri = id_to_uri.get(axis.class_id)
                if not uri:
                    continue
                enriched_match = next((e for e in enriched if e["id"] == axis.class_id), None)
                bfo_cat = enriched_match["bfo_category"] if enriched_match else ""
                vocab_c = enriched_match.get("vocabulary_concept", "") if enriched_match else ""
                vocab_l = enriched_match.get("vocabulary_label", "") if enriched_match else ""
                axes.append(VariationAxis(
                    cco_class_uri=uri,
                    cco_class_label=axis.class_label,
                    bfo_category=bfo_cat,
                    vocabulary_concept=vocab_c,
                    vocabulary_label=vocab_l,
                    rationale=axis.rationale,
                    roles=[],  # backward compat
                ))
            axes_cache[risk_id] = axes
            # ... build RiskVariationAxes (same as before)
```

Add helper for formatting vocabulary context:

```python
def _format_vocabulary_context(vocab_ctx: dict) -> str:
    """Format vocabulary context dict into LLM prompt block."""
    if not vocab_ctx:
        return ""
    lines = ["Vocabulary context:"]
    if vocab_ctx.get("stakeholders"):
        labels = ", ".join(c["label"] for c in vocab_ctx["stakeholders"])
        lines.append(f"  Stakeholders: {labels}")
    if vocab_ctx.get("data_sensitivity"):
        labels = ", ".join(c["label"] for c in vocab_ctx["data_sensitivity"])
        lines.append(f"  Data sensitivity: {labels}")
    if vocab_ctx.get("rights"):
        labels = ", ".join(c["label"] for c in vocab_ctx["rights"])
        lines.append(f"  Rights at stake: {labels}")
    if vocab_ctx.get("sector_purposes"):
        labels = ", ".join(c["label"] for c in vocab_ctx["sector_purposes"])
        lines.append(f"  Sector: {labels}")
    if vocab_ctx.get("justifications"):
        labels = ", ".join(c["label"] for c in vocab_ctx["justifications"])
        lines.append(f"  Justification patterns: {labels}")
    if vocab_ctx.get("prohibited_practices"):
        labels = ", ".join(c["label"] for c in vocab_ctx["prohibited_practices"])
        lines.append(f"  Prohibited practices: {labels}")
    return "\n".join(lines)
```

**Important:** Keep the old `expand_candidates()`, merge strategies, `_CATEGORY_ROLES`, and `derive_roles()` in the file for now — they serve as fallback during migration and keep existing tests passing. They will be cleaned up after the full pipeline is verified working.

- [ ] **Step 3: Run new tests**

```bash
cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/refiner
uv run pytest tests/test_anchor_v2.py -v
```

Expected: All PASS

- [ ] **Step 4: Run all existing anchor tests**

```bash
cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/refiner
uv run pytest tests/test_anchor.py -v
```

Expected: All existing tests still PASS (old code paths retained)

- [ ] **Step 5: Commit**

```bash
cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner
git add refiner/src/refiner/stages/anchor.py refiner/tests/test_anchor_v2.py
git commit -m "feat(anchor): rewrite anchor stage for two-layer SSSOM navigation

New anchor() accepts nexus_handlers, layer1/layer2 SSSOM mappings.
Resolves seeds via two-layer SSSOM, navigates structurally,
constrained search as complement, tiered merge.
Vocabulary context block replaces role labels in LLM prompt.
Old code paths retained for backward compatibility."
```

---

## Task 7: Rewrite Contextualize Stage

**Files:**
- Modify: `refiner/src/refiner/stages/contextualize.py`
- Create: `refiner/tests/test_contextualize_v2.py`

- [ ] **Step 1: Write tests for policy-driven generation**

Write `refiner/tests/test_contextualize_v2.py`:

```python
"""Tests for the policy-driven contextualize stage (v2 redesign)."""
import pytest
from unittest.mock import MagicMock
from refiner.models import (
    RiskVariationAxes, VariationAxis, DomainContextProfile
)
from refiner.stages.contextualize import contextualize, _Variation, _ContextResponse


@pytest.fixture
def mock_config():
    from refiner.llm import LLMConfig
    return LLMConfig(base_url="http://localhost:8000/v1", model="test-model")


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def mock_onto_handlers():
    return {
        "get_subclasses": MagicMock(return_value=[]),
        "get_class_definition": MagicMock(return_value=None),
        "get_siblings": MagicMock(return_value=[]),
        "get_restrictions": MagicMock(return_value=[]),
    }


@pytest.fixture
def sample_axes():
    return [RiskVariationAxes(
        risk_id="atlas-bio",
        risk_name="Biometric exposure",
        policy_concept="Do not disclose biometric data",
        axes=[VariationAxis(
            cco_class_uri="http://example.org/BiometricId",
            cco_class_label="Biometric Identifier",
            bfo_category="InformationContentEntity",
            vocabulary_concept="pd:Biometric",
            vocabulary_label="Biometric",
            rationale="Biometric data at risk",
        )],
    )]


@pytest.fixture
def sample_risk_details():
    return {
        "atlas-bio": {
            "description": "Risk of biometric data exposure",
            "concern": "Biometric identifiers leaked",
        }
    }


@pytest.fixture
def sample_policies():
    from refiner.models import Policy
    return [Policy(
        policy_concept="Do not disclose biometric data",
        concept_definition="Biometric identifiers must not be revealed",
        boundary_examples=[],
        acceptable_uses=["aggregate statistical reporting"],
        risk_controls=["biometric data masking"],
    )]


def test_generates_variations(
    mock_client, mock_config, mock_onto_handlers,
    sample_axes, sample_risk_details, sample_policies
):
    mock_client.chat.completions.create.return_value = _ContextResponse(
        variations=[
            _Variation(instance="Facial recognition template leaked", relevance="high"),
            _Variation(instance="Fingerprint hash exposed in logs", relevance="high"),
        ]
    )
    result = contextualize(
        sample_axes, mock_client, mock_config, mock_onto_handlers,
        risk_details=sample_risk_details,
        policies=sample_policies,
    )
    assert len(result) == 1
    assert len(result[0].axes[0].enumerations) == 2
    assert result[0].axes[0].enumerations[0].provenance == "generated"


def test_caches_by_risk_id(
    mock_client, mock_config, mock_onto_handlers,
    sample_risk_details, sample_policies
):
    mock_client.chat.completions.create.return_value = _ContextResponse(
        variations=[_Variation(instance="Test", relevance="high")]
    )
    axes = [
        RiskVariationAxes(
            risk_id="atlas-bio", risk_name="Bio", policy_concept="Policy A",
            axes=[VariationAxis(
                cco_class_uri="http://example.org/X", cco_class_label="X",
                rationale="test",
            )],
        ),
        RiskVariationAxes(
            risk_id="atlas-bio", risk_name="Bio", policy_concept="Policy B",
            axes=[VariationAxis(
                cco_class_uri="http://example.org/X", cco_class_label="X",
                rationale="test",
            )],
        ),
    ]
    result = contextualize(
        axes, mock_client, mock_config, mock_onto_handlers,
        risk_details=sample_risk_details,
        policies=sample_policies,
    )
    assert len(result) == 2
    assert mock_client.chat.completions.create.call_count == 1


def test_includes_vocabulary_context_in_prompt(
    mock_client, mock_config, mock_onto_handlers,
    sample_axes, sample_risk_details, sample_policies
):
    mock_client.chat.completions.create.return_value = _ContextResponse(variations=[])
    contextualize(
        sample_axes, mock_client, mock_config, mock_onto_handlers,
        risk_details=sample_risk_details,
        policies=sample_policies,
        vocabulary_contexts={"atlas-bio": {
            "stakeholders": [{"concept_id": "eu-aiact:AISubject", "label": "AI Subject", "confidence": 0.9}],
            "data_sensitivity": [{"concept_id": "pd:Biometric", "label": "Biometric", "confidence": 0.9}],
            "rights": [], "justifications": [], "sector_purposes": [],
            "risk_concepts": [], "prohibited_practices": [],
        }},
    )
    call_args = mock_client.chat.completions.create.call_args
    user_msg = [m for m in call_args.kwargs.get("messages", []) if m["role"] == "user"][0]
    assert "Biometric" in user_msg["content"]
    assert "AI Subject" in user_msg["content"]
```

- [ ] **Step 2: Rewrite contextualize.py**

Replace the core of `contextualize()` with policy-driven LLM generation. The new response models:

```python
class _Variation(BaseModel):
    instance: str
    relevance: Literal["high", "medium", "low"]


class _ContextResponse(BaseModel):
    variations: list[_Variation]
```

The new contextualize signature adds `policies` and `vocabulary_contexts`:

```python
def contextualize(
    variation_axes: list[RiskVariationAxes],
    client: instructor.Instructor,
    config: LLMConfig,
    onto_handlers: dict,
    selected_domains: list[str] | None = None,
    risk_details: dict[str, dict] | None = None,
    report: RunReport | None = None,
    policies: list[Policy] | None = None,
    vocabulary_contexts: dict[str, dict] | None = None,
) -> list[DomainContextProfile]:
```

The main loop generates variations per axis instead of filtering subclass lists. For each axis:
1. Find matching policy by `policy_concept`
2. Get optional subclass list as reference
3. Build prompt with vocabulary context + policy context + optional subclasses
4. LLM generates 5-8 variations
5. Build `AxisEnumeration` with `provenance="generated"`

- [ ] **Step 3: Run tests**

```bash
cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/refiner
uv run pytest tests/test_contextualize_v2.py -v
```

Expected: All PASS

- [ ] **Step 4: Commit**

```bash
cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner
git add refiner/src/refiner/stages/contextualize.py refiner/tests/test_contextualize_v2.py
git commit -m "feat(contextualize): rewrite for policy-driven LLM generation

Replace subclass enumeration with LLM-generated variations.
New prompt includes vocabulary context (stakeholders, data sensitivity,
rights) and policy context (boundaries, acceptable uses, controls).
Remove sibling fallback and disjointness filtering."
```

---

## Task 8: Wire Pipeline + Update CLI

**Files:**
- Modify: `refiner/src/refiner/pipeline.py`
- Modify: `refiner/src/refiner/cli.py`
- Modify: `refiner/tests/conftest.py`

- [ ] **Step 1: Update conftest.py fixtures**

Add to `refiner/tests/conftest.py`:

```python
@pytest.fixture
def mock_risk_handlers():
    """Mock nexus-mcp risk handlers dict."""
    return {
        "search_risks": MagicMock(return_value=[]),
        "get_risk_details": MagicMock(return_value=None),
        "get_related_risks": MagicMock(return_value=[]),
        "get_related_actions": MagicMock(return_value=[]),
        "list_taxonomies": MagicMock(return_value=[]),
        "list_risk_groups": MagicMock(return_value=[]),
        "explore_risk": MagicMock(return_value=None),
        "gap_analysis": MagicMock(return_value={}),
        "get_risk_group": MagicMock(return_value=None),
    }
```

- [ ] **Step 2: Update pipeline.py**

In `refiner/src/refiner/pipeline.py`:

1. Add imports for `SSSOMIndex` and `Path`
2. Add `layer1_mappings` and `layer2_mappings` parameters to `run_pipeline()`
3. Add `vocabulary_contexts` to `PipelineState`
4. Pass SSSOM mappings to `anchor()`, collect vocabulary contexts
5. Pass vocabulary contexts and policies to `contextualize()`

Updated `run_pipeline()` signature:

```python
def run_pipeline(
    policies: list[Policy],
    client: instructor.Instructor,
    config: LLMConfig,
    risk_handlers: dict,
    onto_handlers: dict,
    until: str | None = None,
    report: RunReport | None = None,
    merge_strategy: SearchMergeStrategy | None = None,
    layer1_mappings: "SSSOMIndex | None" = None,
    layer2_mappings: "SSSOMIndex | None" = None,
) -> PipelineState:
```

The anchor call becomes:

```python
    state.variation_axes = anchor(
        state.risk_mappings, state.risk_details, client, config, onto_handlers,
        selected_domains=state.selected_domains,
        risk_actions=state.risk_actions,
        related_risks=state.related_risks,
        nexus_handlers=risk_handlers,
        layer1_mappings=layer1_mappings,
        layer2_mappings=layer2_mappings,
        report=report,
        generic_safety_uris=generic_safety_uris,
    )
```

The contextualize call becomes:

```python
    state.domain_context = contextualize(
        state.variation_axes, client, config, onto_handlers,
        selected_domains=state.selected_domains,
        risk_details=state.risk_details,
        report=report,
        policies=policies,
        vocabulary_contexts=state.vocabulary_contexts,
    )
```

- [ ] **Step 3: Update cli.py**

In `refiner/src/refiner/cli.py`, at the point where `run_pipeline()` is called:

1. Load SSSOM files from `refiner/data/` directory
2. Pass `layer1_mappings` and `layer2_mappings` to `run_pipeline()`
3. Keep `--search-strategy` flag for backward compat but log a deprecation warning when used

```python
    # Load SSSOM seed mappings
    data_dir = Path(__file__).parent.parent.parent / "data"
    layer1_path = data_dir / "risk-to-vocabulary.sssom.tsv"
    layer2_path = data_dir / "vocabulary-to-ontology.sssom.tsv"

    layer1_mappings = None
    layer2_mappings = None
    if layer1_path.exists() and layer2_path.exists():
        from refiner.ontology_seeds import SSSOMIndex
        layer1_mappings = SSSOMIndex.from_tsv(layer1_path)
        layer2_mappings = SSSOMIndex.from_tsv(layer2_path)
        logger.info("Loaded SSSOM seeds: %d layer-1, %d layer-2 mappings",
                     len(layer1_mappings.mappings), len(layer2_mappings.mappings))
```

- [ ] **Step 4: Run pipeline tests**

```bash
cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/refiner
uv run pytest tests/test_pipeline.py -v
```

Expected: PASS (new parameters have defaults, backward compatible)

- [ ] **Step 5: Commit**

```bash
cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner
git add refiner/src/refiner/pipeline.py refiner/src/refiner/cli.py refiner/tests/conftest.py
git commit -m "feat: wire SSSOM seeds through pipeline and CLI

pipeline.py: accept and pass layer1/layer2 SSSOM mappings
cli.py: load SSSOM TSV files from refiner/data/
conftest.py: add get_risk_group to mock_risk_handlers"
```

---

## Task 9: Cleanup — Remove Old Code

**Files:**
- Modify: `refiner/src/refiner/stages/anchor.py`

This task removes the old code that was kept for backward compatibility during migration.

- [ ] **Step 1: Remove old merge strategies and role derivation**

From `refiner/src/refiner/stages/anchor.py`, remove:
- `_CATEGORY_ROLES` dict (lines 59-95)
- `derive_roles()` function (lines 98-123)
- `SearchMergeStrategy` protocol (lines 126-137)
- `WeightedMergeStrategy` class (lines 140-236)
- `GroupedMergeStrategy` class (lines 239-274)
- `_MergeSelection` model (lines 309-311)
- `LLMMergeStrategy` class (lines 313-412)
- `_DOMAIN_DISPLAY` dict (lines 287-296)
- `_search_per_domain()` function (lines 438-486)
- Old `expand_candidates()` function (lines 517-672)
- Old `SYSTEM_PROMPT` (lines 489-503)

Keep:
- `_BFO_URI_PREFIX`, `_LKIF_NORMATIVE_URIS`, `_is_excluded_uri()`
- `build_generic_safety_uris()`
- All new functions from Task 5-6
- Updated `anchor()` function

- [ ] **Step 2: Update pipeline.py imports**

Remove `SearchMergeStrategy` from the import in `pipeline.py` line 20. Remove the `merge_strategy` parameter from `run_pipeline()`.

- [ ] **Step 3: Run all tests**

```bash
cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/refiner
uv run pytest tests/test_structural_navigation.py tests/test_anchor_v2.py tests/test_contextualize_v2.py tests/test_ontology_seeds.py tests/test_pipeline.py -v
```

Expected: All PASS

- [ ] **Step 4: Commit**

```bash
cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner
git add refiner/src/refiner/stages/anchor.py refiner/src/refiner/pipeline.py
git commit -m "refactor(anchor): remove old merge strategies, _CATEGORY_ROLES, derive_roles

Cleanup after SSSOM redesign migration:
- Remove WeightedMergeStrategy, GroupedMergeStrategy, LLMMergeStrategy
- Remove _CATEGORY_ROLES (29-entry dict) and derive_roles()
- Remove _search_per_domain() and expand_candidates()
- Remove SearchMergeStrategy protocol
- Keep _is_excluded_uri(), build_generic_safety_uris()"
```

---

## Task 10: Integration Test

**Files:**
- Create: `refiner/tests/test_integration_sssom.py`

- [ ] **Step 1: Write end-to-end integration test**

Write `refiner/tests/test_integration_sssom.py`:

```python
"""End-to-end integration test for the SSSOM-based pipeline."""
import pytest
from pathlib import Path
from unittest.mock import MagicMock
from refiner.ontology_seeds import SSSOMIndex
from refiner.models import (
    Policy, PolicyClassification, PolicyRiskMapping, RiskMatch,
    RiskVariationAxes, VariationAxis,
)
from refiner.stages.anchor import anchor, _AnchorResponse, _SlimAxis
from refiner.stages.contextualize import contextualize, _ContextResponse, _Variation


@pytest.fixture
def real_layer1():
    path = Path(__file__).parent.parent / "data" / "risk-to-vocabulary.sssom.tsv"
    if not path.exists():
        pytest.skip("SSSOM seed files not found")
    return SSSOMIndex.from_tsv(path)


@pytest.fixture
def real_layer2():
    path = Path(__file__).parent.parent / "data" / "vocabulary-to-ontology.sssom.tsv"
    if not path.exists():
        pytest.skip("SSSOM seed files not found")
    return SSSOMIndex.from_tsv(path)


def test_real_sssom_files_load(real_layer1, real_layer2):
    """Verify the actual SSSOM seed files parse correctly."""
    assert len(real_layer1.mappings) > 0
    assert len(real_layer2.mappings) > 0
    # All layer1 subjects should be RiskGroup or Risk IDs
    for m in real_layer1.mappings:
        assert m.subject_id.startswith("ibm-risk-atlas")
    # All layer2 subjects should be AIRO/DPV concepts or direct fallbacks
    for m in real_layer2.mappings:
        prefix = m.subject_id.split(":")[0]
        assert prefix in (
            "pd", "eu-aiact", "eu-rights", "risk", "justifications",
            "sector-finance", "sector-health", "sector-law",
            "ibm-risk-atlas", "ibm-risk-atlas-robustness-model-behavior-manipulation",
            "ibm-risk-atlas-intellectual-property",
        ) or m.subject_id.startswith("ibm-risk-atlas")


def test_privacy_risk_resolves_seeds(real_layer1, real_layer2):
    """Privacy RiskGroup should resolve to biometric/person ontology branches."""
    from refiner.ontology_seeds import resolve_seeds
    mock_nexus = {
        "get_risk_details": MagicMock(return_value={"group": "ibm-risk-atlas-privacy"}),
        "get_related_risks": MagicMock(return_value=[]),
    }
    vocab_ctx, onto_seeds = resolve_seeds(
        risk_id="atlas-test-privacy-risk",
        risk_group_id="ibm-risk-atlas-privacy",
        nexus_handlers=mock_nexus,
        layer1_mappings=real_layer1,
        layer2_mappings=real_layer2,
    )
    # Should have stakeholder and data sensitivity context
    assert len(vocab_ctx["stakeholders"]) > 0
    assert len(vocab_ctx["data_sensitivity"]) > 0
    # Should have ontology seeds
    onto_uris = {s["object_id"] for s in onto_seeds}
    assert len(onto_uris) > 0


def test_fairness_risk_resolves_to_hancestro_gsso(real_layer1, real_layer2):
    """Fairness should route through pd:EthnicOrigin/Gender to HANCESTRO/GSSO."""
    from refiner.ontology_seeds import resolve_seeds
    mock_nexus = {
        "get_risk_details": MagicMock(return_value={"group": "ibm-risk-atlas-fairness"}),
        "get_related_risks": MagicMock(return_value=[]),
    }
    _, onto_seeds = resolve_seeds(
        risk_id="atlas-test-fairness-risk",
        risk_group_id="ibm-risk-atlas-fairness",
        nexus_handlers=mock_nexus,
        layer1_mappings=real_layer1,
        layer2_mappings=real_layer2,
    )
    onto_uris = {s["object_id"] for s in onto_seeds}
    assert "obo:HANCESTRO_0001" in onto_uris
    assert "obo:GSSO_000000" in onto_uris
```

- [ ] **Step 2: Run integration tests**

```bash
cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/refiner
uv run pytest tests/test_integration_sssom.py -v
```

Expected: All PASS

- [ ] **Step 3: Run full test suite**

```bash
cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/refiner
uv run pytest -v
```

Expected: The new tests PASS. Some old tests in `test_anchor.py` and `test_contextualize.py` may fail due to removed code — these should be updated or removed as they test the old code paths.

- [ ] **Step 4: Commit**

```bash
cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner
git add refiner/tests/test_integration_sssom.py
git commit -m "test: add end-to-end integration tests for SSSOM pipeline

Verifies real SSSOM seed files parse correctly.
Tests privacy → biometric/person and fairness → HANCESTRO/GSSO
resolution through both SSSOM layers."
```

---

## Task 11: Update Old Tests

**Files:**
- Modify: `refiner/tests/test_anchor.py`
- Modify: `refiner/tests/test_contextualize.py`

- [ ] **Step 1: Remove or update tests for removed code**

In `test_anchor.py`:
- Remove tests for `WeightedMergeStrategy`, `GroupedMergeStrategy`, `LLMMergeStrategy`
- Remove tests for `derive_roles()` and `_CATEGORY_ROLES`
- Remove tests for `expand_candidates()` (the old version)
- Keep tests for `_is_excluded_uri()` and `build_generic_safety_uris()`
- Update integration tests that call `anchor()` with old signature to use new signature

In `test_contextualize.py`:
- Remove tests for subclass/sibling enumeration, disjointness filtering
- Update remaining tests for new `contextualize()` signature

- [ ] **Step 2: Run full test suite**

```bash
cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/refiner
uv run pytest -v
```

Expected: All PASS

- [ ] **Step 3: Commit**

```bash
cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner
git add refiner/tests/test_anchor.py refiner/tests/test_contextualize.py
git commit -m "test: update old tests for SSSOM redesign

Remove tests for removed merge strategies, derive_roles, expand_candidates.
Update anchor/contextualize tests for new signatures.
Keep tests for _is_excluded_uri and build_generic_safety_uris."
```

---

## Task 12: Final Verification

- [ ] **Step 1: Run all test suites**

```bash
cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/refiner && uv run pytest -v
cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/nexus-mcp && uv run pytest -v
```

Expected: All PASS

- [ ] **Step 2: Verify branch state**

```bash
cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner
git log --oneline experimental/sssom-ontology-redesign ^master
```

Expected: 10-12 commits on the experimental branch

- [ ] **Step 3: Verify no merge to master**

```bash
git branch --show-current
```

Expected: `experimental/sssom-ontology-redesign` — do NOT merge to master.
