# Advisory System Prototype Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a staged prototype that reads refiner pipeline output, queries AIROO for matching probes/guardrails/benchmarks, computes coverage gaps, generates Garak + NeMo config files, and renders an SA-facing advisory report.

**Architecture:** Three composable scripts in `prototypes/advisory/` — `analyze.py` (coverage analysis), `configure.py` (config generation), `report.py` (markdown report) — chained by a thin `advise.py` wrapper. AIROO imported as a path dependency. No LLM calls.

**Tech Stack:** Python 3.11+, uv, PyYAML, Jinja2, AIROO OntologyQuery (path dep)

**Spec:** `docs/superpowers/specs/2026-04-14-advisory-prototype-design.md`

---

## File Structure

```
prototypes/
  advisory/
    pyproject.toml              # uv project with path deps
    analyze.py                  # Stage 1: read refiner output, query AIROO, compute coverage
    configure.py                # Stage 2: generate garak.yaml + NeMo config.yml + rails.co
    report.py                   # Stage 3: render advisory-report.md
    advise.py                   # Wrapper: chain all stages
    templates/
      garak.yaml.j2             # Garak config Jinja2 template
      nemo_config.yml.j2        # NeMo config.yml template
      nemo_rails.co.j2          # NeMo Colang flow template
      report.md.j2              # Advisory report template
    scenarios/
      healthcare_chat.json      # Canned fallback scenario
    tests/
      test_analyze.py           # Stage 1 tests
      test_configure.py         # Stage 2 tests
      test_report.py            # Stage 3 tests
      fixtures/
        mini_taxonomy.yaml      # Minimal taxonomy fixture
        mini_domain_context.yaml # Minimal domain context fixture
    README.md
```

---

### Task 1: Project Scaffold

**Files:**
- Create: `prototypes/advisory/pyproject.toml`
- Create: `prototypes/advisory/templates/` (empty dir via .gitkeep)
- Create: `prototypes/advisory/scenarios/` (empty dir via .gitkeep)
- Create: `prototypes/advisory/tests/__init__.py`
- Create: `prototypes/advisory/tests/fixtures/` (empty dir via .gitkeep)

- [ ] **Step 1: Create pyproject.toml**

```toml
[project]
name = "advisory-prototype"
version = "0.1.0"
description = "Advisory system prototype: refiner output → AIROO coverage → Garak/NeMo configs"
requires-python = ">=3.11,<3.13"
dependencies = [
    "pyyaml>=6.0",
    "jinja2>=3.1",
]

[tool.uv.sources]
ai-risk-operational-ontology = { path = "../../trustyai-explainability/ai-risk-operational-ontology", editable = true }

[project.optional-dependencies]
airoo = ["ai-risk-operational-ontology"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

Note: AIROO is at `/Users/hjrnunes/workspace/redhat/trustyai-explainability/ai-risk-operational-ontology`. The path in `tool.uv.sources` is relative from `prototypes/advisory/`. Adjust if the relative path doesn't resolve — it may need to be `../../../trustyai-explainability/ai-risk-operational-ontology`.

- [ ] **Step 2: Create directory structure**

```bash
cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner
mkdir -p prototypes/advisory/templates
mkdir -p prototypes/advisory/scenarios
mkdir -p prototypes/advisory/tests/fixtures
touch prototypes/advisory/tests/__init__.py
touch prototypes/advisory/templates/.gitkeep
touch prototypes/advisory/scenarios/.gitkeep
touch prototypes/advisory/tests/fixtures/.gitkeep
```

- [ ] **Step 3: Initialize venv and sync**

```bash
cd prototypes/advisory
uv sync --extra airoo
```

Expected: venv created, pyyaml + jinja2 + AIROO installed. If the AIROO path dep fails, adjust the relative path in `pyproject.toml` and retry.

- [ ] **Step 4: Verify AIROO import works**

```bash
cd prototypes/advisory
uv run python -c "from ontology.query import OntologyQuery; oq = OntologyQuery(); print(oq.get_stats())"
```

Expected: prints stats dict with dimensions, probes, benchmarks, guardrails counts.

- [ ] **Step 5: Commit**

```bash
git add prototypes/advisory/pyproject.toml prototypes/advisory/tests/__init__.py prototypes/advisory/templates/.gitkeep prototypes/advisory/scenarios/.gitkeep prototypes/advisory/tests/fixtures/.gitkeep
git commit -m "feat(advisory): scaffold prototype project with AIROO path dep"
```

---

### Task 2: Test Fixtures

**Files:**
- Create: `prototypes/advisory/tests/fixtures/mini_taxonomy.yaml`
- Create: `prototypes/advisory/tests/fixtures/mini_domain_context.yaml`
- Create: `prototypes/advisory/scenarios/healthcare_chat.json`

These fixtures provide minimal but realistic data for testing all three stages without needing a real refiner run.

- [ ] **Step 1: Create mini taxonomy fixture**

```yaml
curie_map:
  airo: https://w3id.org/airo#
  cco: https://www.commoncoreontologies.org/
  cso: http://taxonomy-refiner.io/ontologies/cso#
  fibo: https://spec.edmcouncil.org/fibo/ontology/
  lkif: http://www.estrellaproject.org/lkif-core/
taxonomies:
- id: client-test
  name: Client TEST Policy Taxonomy
  type: RiskTaxonomy
  class_uri: airo:RiskConcept
groups:
- id: client-test-fraud
  name: Fraud
  type: RiskGroup
  class_uri: airo:RiskConcept
  isDefinedByTaxonomy: client-test
- id: client-test-data-privacy
  name: Data Privacy
  type: RiskGroup
  class_uri: airo:RiskConcept
  isDefinedByTaxonomy: client-test
entries:
- id: client-test-social-engineering
  name: Social engineering
  type: Risk
  class_uri: airo:Risk
  isDefinedByTaxonomy: client-test
  isPartOf: client-test-fraud
  tag: social-engineering
  related_mappings:
  - atlas-social-engineering
  - atlas-prompt-injection
  - granite-jailbreak
  domain_context_summary:
    axis_count: 2
    enumeration_count: 16
    source_ontologies:
    - generated
    axes:
    - class: Person
      uri: https://www.commoncoreontologies.org/ont00001262
      roles: []
      enumeration_count: 8
    - class: Act of Deceptive Communication
      uri: https://www.commoncoreontologies.org/ont00000971
      roles: []
      enumeration_count: 8
- id: client-test-pii-exposure
  name: PII exposure
  type: Risk
  class_uri: airo:Risk
  isDefinedByTaxonomy: client-test
  isPartOf: client-test-data-privacy
  tag: pii-exposure
  related_mappings:
  - atlas-exposing-personal-information
  - nist-data-privacy
  domain_context_summary:
    axis_count: 1
    enumeration_count: 8
    source_ontologies:
    - generated
    axes:
    - class: Financial Data Exposure
      uri: http://taxonomy-refiner.io/ontologies/cso#FinancialDataExposure
      roles: []
      enumeration_count: 8
- id: client-test-novel-risk
  name: Novel domain-specific risk
  type: Risk
  class_uri: airo:Risk
  isDefinedByTaxonomy: client-test
  isPartOf: client-test-fraud
  tag: novel-risk
  domain_context_summary:
    axis_count: 1
    enumeration_count: 6
    source_ontologies:
    - generated
    axes:
    - class: Organization
      uri: https://www.commoncoreontologies.org/ont00001180
      roles: []
      enumeration_count: 6
```

Write to `prototypes/advisory/tests/fixtures/mini_taxonomy.yaml`.

- [ ] **Step 2: Create mini domain context fixture**

```yaml
profiles:
- risk_id: client-test-social-engineering
  risk_name: Social engineering
  policy_concept: Fraud
  axes:
  - cco_class_uri: https://www.commoncoreontologies.org/ont00001262
    cco_class_label: Person
    bfo_category: Agent
    vocabulary_concept: eu-aiact:AISubject
    vocabulary_label: AI Subject
    vocabulary_context:
      stakeholders:
      - concept_id: eu-aiact:AISubject
        label: AI Subject
        confidence: 0.95
      data_sensitivity: []
      rights: []
      justifications: []
      sector_purposes: []
      risk_concepts: []
      prohibited_practices: []
    enumerations:
    - class_uri: generated:bank_customer
      class_label: Bank customer
      source_ontology: generated
      relevance: high
      provenance: generated
    - class_uri: generated:loan_officer
      class_label: Loan officer
      source_ontology: generated
      relevance: high
      provenance: generated
    - class_uri: generated:financial_advisor
      class_label: Financial advisor
      source_ontology: generated
      relevance: high
      provenance: generated
  - cco_class_uri: https://www.commoncoreontologies.org/ont00000971
    cco_class_label: Act of Deceptive Communication
    bfo_category: Process
    vocabulary_concept: risk:SocialEngineering
    vocabulary_label: Social Engineering
    vocabulary_context:
      stakeholders: []
      data_sensitivity: []
      rights: []
      justifications: []
      sector_purposes: []
      risk_concepts:
      - concept_id: risk:SocialEngineering
        label: Social Engineering
        confidence: 0.9
      prohibited_practices: []
    enumerations:
    - class_uri: generated:phishing_email
      class_label: Phishing email
      source_ontology: generated
      relevance: high
      provenance: generated
    - class_uri: generated:pretexting_call
      class_label: Pretexting call
      source_ontology: generated
      relevance: high
      provenance: generated
- risk_id: client-test-pii-exposure
  risk_name: PII exposure
  policy_concept: Data Privacy
  axes:
  - cco_class_uri: http://taxonomy-refiner.io/ontologies/cso#FinancialDataExposure
    cco_class_label: Financial Data Exposure
    bfo_category: InformationContentEntity
    vocabulary_concept: pd:Financial
    vocabulary_label: Financial
    vocabulary_context:
      stakeholders:
      - concept_id: eu-aiact:AISubject
        label: AI Subject
        confidence: 0.95
      data_sensitivity:
      - concept_id: pd:Financial
        label: Financial
        confidence: 0.85
      rights: []
      justifications: []
      sector_purposes: []
      risk_concepts: []
      prohibited_practices: []
    enumerations:
    - class_uri: generated:account_number
      class_label: Account number
      source_ontology: generated
      relevance: high
      provenance: generated
    - class_uri: generated:credit_card_number
      class_label: Credit card number
      source_ontology: generated
      relevance: high
      provenance: generated
- risk_id: client-test-novel-risk
  risk_name: Novel domain-specific risk
  policy_concept: Fraud
  axes:
  - cco_class_uri: https://www.commoncoreontologies.org/ont00001180
    cco_class_label: Organization
    bfo_category: Agent
    vocabulary_concept: cco:Organization
    vocabulary_label: Organization
    vocabulary_context:
      stakeholders: []
      data_sensitivity: []
      rights: []
      justifications: []
      sector_purposes: []
      risk_concepts: []
      prohibited_practices: []
    enumerations:
    - class_uri: generated:shell_company
      class_label: Shell company
      source_ontology: generated
      relevance: high
      provenance: generated
```

Write to `prototypes/advisory/tests/fixtures/mini_domain_context.yaml`.

- [ ] **Step 3: Create canned healthcare scenario**

```json
{
  "client": "healthcare-demo",
  "domain": "healthcare",
  "source_type": "scenario",
  "risks": [
    {
      "risk_id": "atlas-harmful-output",
      "risk_name": "Harmful Output",
      "policy_concept": "Clinical Safety",
      "policy_type": "A",
      "alternative_framings": [
        {"risk_id": "nist-dangerous-violent-or-hateful-content", "taxonomy": "nist-ai-rmf", "mapping_type": "close"},
        {"risk_id": "granite-guardian-harm", "taxonomy": "granite-guardian", "mapping_type": "related"}
      ],
      "attack_dimensions": [
        {"cco_class": "Person", "role": "Patient or clinician", "term_count": 5, "terms": ["Patient", "Nurse", "Physician", "Pharmacist", "Surgeon"]},
        {"cco_class": "ClinicalProcedure", "role": "Medical procedure discussed", "term_count": 4, "terms": ["Surgery", "Prescription", "Diagnosis", "Triage"]}
      ]
    },
    {
      "risk_id": "atlas-exposing-personal-information",
      "risk_name": "Exposing Personal Information",
      "policy_concept": "Patient Privacy",
      "policy_type": "A",
      "alternative_framings": [
        {"risk_id": "nist-data-privacy", "taxonomy": "nist-ai-rmf", "mapping_type": "close"}
      ],
      "attack_dimensions": [
        {"cco_class": "InformationBearingArtifact", "role": "Medical records and documents", "term_count": 4, "terms": ["Patient Record", "Lab Result", "Prescription", "Discharge Summary"]}
      ]
    },
    {
      "risk_id": "atlas-hallucination",
      "risk_name": "Hallucination",
      "policy_concept": "Clinical Accuracy",
      "policy_type": "A",
      "alternative_framings": [
        {"risk_id": "nist-confabulation", "taxonomy": "nist-ai-rmf", "mapping_type": "exact"}
      ],
      "attack_dimensions": [
        {"cco_class": "Drug", "role": "Medications discussed", "term_count": 5, "terms": ["Aspirin", "Metformin", "Insulin", "Lisinopril", "Amoxicillin"]},
        {"cco_class": "MedicalDevice", "role": "Clinical devices mentioned", "term_count": 3, "terms": ["Ventilator", "Pacemaker", "MRI Scanner"]}
      ]
    },
    {
      "risk_id": "atlas-decision-bias",
      "risk_name": "Decision Bias",
      "policy_concept": "Equitable Care",
      "policy_type": "B",
      "alternative_framings": [
        {"risk_id": "nist-harmful-bias-or-homogenization", "taxonomy": "nist-ai-rmf", "mapping_type": "close"}
      ],
      "attack_dimensions": [
        {"cco_class": "Person", "role": "Patient demographics", "term_count": 6, "terms": ["Elderly patient", "Pediatric patient", "Pregnant woman", "Disabled person", "Non-English speaker", "Low-income patient"]}
      ]
    },
    {
      "risk_id": "atlas-clinical-terminology-ambiguity",
      "risk_name": "Clinical Terminology Ambiguity",
      "policy_concept": "Clinical Safety",
      "policy_type": "C",
      "alternative_framings": [],
      "attack_dimensions": [
        {"cco_class": "ClinicalTerm", "role": "Ambiguous medical terms", "term_count": 4, "terms": ["Acute", "Chronic", "Benign", "Malignant"]}
      ]
    }
  ]
}
```

Write to `prototypes/advisory/scenarios/healthcare_chat.json`.

- [ ] **Step 4: Commit**

```bash
git add prototypes/advisory/tests/fixtures/ prototypes/advisory/scenarios/
git commit -m "feat(advisory): add test fixtures and canned healthcare scenario"
```

---

### Task 3: Stage 1 — `analyze.py` (Tests First)

**Files:**
- Create: `prototypes/advisory/tests/test_analyze.py`

- [ ] **Step 1: Write tests for refiner output parsing**

```python
"""Tests for analyze.py — Stage 1: coverage analysis."""
import json
from pathlib import Path

import pytest
import yaml

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name):
    with open(FIXTURES / name) as f:
        return yaml.safe_load(f)


class TestExtractRisks:
    """Test extraction of risks from refiner taxonomy + domain context."""

    def test_extracts_risk_ids_from_taxonomy(self):
        from analyze import extract_risks

        taxonomy = _load_fixture("mini_taxonomy.yaml")
        domain_ctx = _load_fixture("mini_domain_context.yaml")
        risks = extract_risks(taxonomy, domain_ctx)
        ids = [r["risk_id"] for r in risks]
        assert "client-test-social-engineering" in ids
        assert "client-test-pii-exposure" in ids
        assert "client-test-novel-risk" in ids

    def test_includes_policy_concept_from_group(self):
        from analyze import extract_risks

        taxonomy = _load_fixture("mini_taxonomy.yaml")
        domain_ctx = _load_fixture("mini_domain_context.yaml")
        risks = extract_risks(taxonomy, domain_ctx)
        se = next(r for r in risks if r["risk_id"] == "client-test-social-engineering")
        assert se["policy_concept"] == "Fraud"

    def test_includes_cross_mappings_as_alternative_framings(self):
        from analyze import extract_risks

        taxonomy = _load_fixture("mini_taxonomy.yaml")
        domain_ctx = _load_fixture("mini_domain_context.yaml")
        risks = extract_risks(taxonomy, domain_ctx)
        se = next(r for r in risks if r["risk_id"] == "client-test-social-engineering")
        framing_ids = [f["risk_id"] for f in se["alternative_framings"]]
        assert "atlas-social-engineering" in framing_ids

    def test_includes_attack_dimensions_from_domain_context(self):
        from analyze import extract_risks

        taxonomy = _load_fixture("mini_taxonomy.yaml")
        domain_ctx = _load_fixture("mini_domain_context.yaml")
        risks = extract_risks(taxonomy, domain_ctx)
        se = next(r for r in risks if r["risk_id"] == "client-test-social-engineering")
        assert len(se["attack_dimensions"]) == 2
        labels = [d["cco_class"] for d in se["attack_dimensions"]]
        assert "Person" in labels

    def test_risk_without_cross_mappings_has_empty_framings(self):
        from analyze import extract_risks

        taxonomy = _load_fixture("mini_taxonomy.yaml")
        domain_ctx = _load_fixture("mini_domain_context.yaml")
        risks = extract_risks(taxonomy, domain_ctx)
        novel = next(r for r in risks if r["risk_id"] == "client-test-novel-risk")
        assert novel["alternative_framings"] == []


class TestExtractFromScenario:
    """Test extraction from canned scenario JSON."""

    def test_loads_scenario_risks(self):
        from analyze import extract_risks_from_scenario

        scenario_path = Path(__file__).parent.parent / "scenarios" / "healthcare_chat.json"
        risks = extract_risks_from_scenario(scenario_path)
        assert len(risks) == 5
        ids = [r["risk_id"] for r in risks]
        assert "atlas-harmful-output" in ids

    def test_scenario_risks_have_required_fields(self):
        from analyze import extract_risks_from_scenario

        scenario_path = Path(__file__).parent.parent / "scenarios" / "healthcare_chat.json"
        risks = extract_risks_from_scenario(scenario_path)
        for risk in risks:
            assert "risk_id" in risk
            assert "risk_name" in risk
            assert "policy_concept" in risk
            assert "alternative_framings" in risk
            assert "attack_dimensions" in risk


class TestQueryCoverage:
    """Test AIROO coverage queries."""

    def test_risk_with_airoo_match_has_probes(self):
        from analyze import query_coverage

        # atlas-exposing-personal-information is in AIROO's pii_leakage dimension
        coverage = query_coverage("atlas-exposing-personal-information")
        assert len(coverage["probes"]) > 0

    def test_risk_with_airoo_match_has_guardrails(self):
        from analyze import query_coverage

        coverage = query_coverage("atlas-exposing-personal-information")
        assert len(coverage["guardrails"]) > 0

    def test_unknown_risk_has_empty_coverage(self):
        from analyze import query_coverage

        coverage = query_coverage("nonexistent-risk-id")
        assert coverage["probes"] == []
        assert coverage["guardrails"] == []
        assert coverage["benchmarks"] == []

    def test_coverage_includes_mapping_source(self):
        from analyze import query_coverage

        coverage = query_coverage("atlas-jailbreaking")
        if coverage["probes"]:
            assert "mapping_source" in coverage["probes"][0]


class TestBuildAnalysis:
    """Test full analysis pipeline."""

    def test_analysis_has_summary(self):
        from analyze import build_analysis

        scenario_path = Path(__file__).parent.parent / "scenarios" / "healthcare_chat.json"
        analysis = build_analysis(scenario=scenario_path)
        assert "summary" in analysis
        assert "total_risks" in analysis["summary"]
        assert analysis["summary"]["total_risks"] == 5

    def test_analysis_classifies_coverage_gaps(self):
        from analyze import build_analysis

        scenario_path = Path(__file__).parent.parent / "scenarios" / "healthcare_chat.json"
        analysis = build_analysis(scenario=scenario_path)
        summary = analysis["summary"]
        assert summary["fully_covered"] + summary["partial_gaps"] + summary["no_coverage"] == summary["total_risks"]
```

Write to `prototypes/advisory/tests/test_analyze.py`.

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd prototypes/advisory
uv run pytest tests/test_analyze.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'analyze'`

- [ ] **Step 3: Commit test file**

```bash
git add prototypes/advisory/tests/test_analyze.py
git commit -m "test(advisory): add Stage 1 analyze tests (red)"
```

---

### Task 4: Stage 1 — `analyze.py` (Implementation)

**Files:**
- Create: `prototypes/advisory/analyze.py`

- [ ] **Step 1: Implement analyze.py**

```python
"""Stage 1: Read refiner output or canned scenario, query AIROO, compute coverage."""
import argparse
import json
import sys
from pathlib import Path

import yaml

try:
    from ontology.query import OntologyQuery
    _oq = None

    def _get_oq():
        global _oq
        if _oq is None:
            _oq = OntologyQuery()
        return _oq
except ImportError:
    def _get_oq():
        raise RuntimeError("AIROO not installed. Install with: uv sync --extra airoo")


def extract_risks(taxonomy: dict, domain_context: dict) -> list[dict]:
    """Extract risks from refiner taxonomy + domain context files."""
    # Build group_id -> group_name lookup
    group_names = {g["id"]: g["name"] for g in taxonomy.get("groups", [])}

    # Build risk_id -> domain context profile lookup
    dc_profiles = {}
    for profile in domain_context.get("profiles", []):
        dc_profiles[profile["risk_id"]] = profile

    risks = []
    for entry in taxonomy.get("entries", []):
        risk_id = entry["id"]
        group_id = entry.get("isPartOf", "")
        policy_concept = group_names.get(group_id, "Unknown")

        # Cross-mappings become alternative framings
        alternative_framings = []
        for mapping_type in ("related_mappings", "close_mappings", "broad_mappings", "exact_mappings", "narrow_mappings"):
            for mapped_id in entry.get(mapping_type, []):
                alternative_framings.append({
                    "risk_id": mapped_id,
                    "taxonomy": _infer_taxonomy(mapped_id),
                    "mapping_type": mapping_type.replace("_mappings", ""),
                })

        # Attack dimensions from domain context
        attack_dimensions = []
        dc_summary = entry.get("domain_context_summary", {})
        dc_profile = dc_profiles.get(risk_id)
        if dc_profile:
            for axis in dc_profile.get("axes", []):
                enum_count = len(axis.get("enumerations", []))
                terms = [e["class_label"] for e in axis.get("enumerations", [])]
                attack_dimensions.append({
                    "cco_class": axis["cco_class_label"],
                    "cco_class_uri": axis["cco_class_uri"],
                    "role": axis.get("bfo_category", ""),
                    "term_count": enum_count,
                    "terms": terms,
                })
        elif dc_summary:
            for axis in dc_summary.get("axes", []):
                attack_dimensions.append({
                    "cco_class": axis["class"],
                    "cco_class_uri": axis.get("uri", ""),
                    "role": "",
                    "term_count": axis.get("enumeration_count", 0),
                    "terms": [],
                })

        risks.append({
            "risk_id": risk_id,
            "risk_name": entry["name"],
            "policy_concept": policy_concept,
            "alternative_framings": alternative_framings,
            "attack_dimensions": attack_dimensions,
        })

    return risks


def _infer_taxonomy(risk_id: str) -> str:
    """Infer taxonomy from risk ID prefix."""
    prefixes = {
        "atlas-": "ibm-risk-atlas",
        "nist-": "nist-ai-rmf",
        "granite-": "granite-guardian",
        "llm0": "owasp-llm",
        "ail-": "ai-luminiate",
        "air-": "air-2024",
        "mit-": "mit-ai-risk",
        "credo-": "credo-ai",
    }
    for prefix, taxonomy in prefixes.items():
        if risk_id.startswith(prefix):
            return taxonomy
    return "unknown"


def extract_risks_from_scenario(scenario_path: Path) -> list[dict]:
    """Load risks from a canned scenario JSON file."""
    with open(scenario_path) as f:
        scenario = json.load(f)
    return scenario["risks"]


def query_coverage(risk_id: str) -> dict:
    """Query AIROO for probes, guardrails, and benchmarks matching a risk ID."""
    oq = _get_oq()

    probes = []
    for p in oq.get_probes_for_risk(risk_id):
        probes.append({
            "probe_id": p.get("probe_name", p.get("id", "")),
            "platform": "garak",
            "mapping_source": _infer_mapping_source("probe", p),
            "description": p.get("description", ""),
            "garak_tier": p.get("garak_tier", ""),
        })

    guardrails = []
    for g in oq.get_guardrails_for_risk(risk_id):
        guardrails.append({
            "guardrail_id": g.get("id", ""),
            "detector_name": g.get("detector_name", ""),
            "platform": g.get("platform", ""),
            "mapping_source": _infer_mapping_source("guardrail", g),
            "description": g.get("description", ""),
        })

    benchmarks = []
    for b in oq.get_evals_for_risk(risk_id):
        benchmarks.append({
            "benchmark_id": b.get("id", ""),
            "task_name": b.get("task_name", ""),
            "platform": b.get("provider", ""),
            "mapping_source": _infer_mapping_source("benchmark", b),
            "description": b.get("description", ""),
        })

    return {"probes": probes, "guardrails": guardrails, "benchmarks": benchmarks}


def _infer_mapping_source(entity_type: str, entity: dict) -> str:
    """Infer mapping source from entity type and metadata.

    AIROO uses: garak_tags (probes), platform_docs (guardrails),
    benchmark_scope or garak_tags (benchmarks).
    """
    if entity_type == "probe":
        return "garak_tags"
    elif entity_type == "guardrail":
        return "platform_docs"
    elif entity_type == "benchmark":
        provider = entity.get("provider", "")
        return "garak_tags" if provider == "garak" else "benchmark_scope"
    return "unknown"


def _classify_coverage(coverage: dict, attack_dimensions: list[dict]) -> dict:
    """Classify coverage gaps for a risk."""
    has_probes = len(coverage["probes"]) > 0
    has_guardrails = len(coverage["guardrails"]) > 0
    has_benchmarks = len(coverage["benchmarks"]) > 0

    # All dimensions are "uncovered" at the probe level for now —
    # AIROO maps at risk level, not dimension level
    uncovered_dimensions = [d["cco_class"] for d in attack_dimensions]

    return {
        "has_probes": has_probes,
        "has_guardrails": has_guardrails,
        "has_benchmarks": has_benchmarks,
        "uncovered_dimensions": uncovered_dimensions,
    }


def build_analysis(
    run_dir: Path | None = None,
    policy_file: Path | None = None,
    scenario: Path | None = None,
) -> dict:
    """Build full coverage analysis from refiner output or canned scenario."""
    if scenario:
        with open(scenario) as f:
            scenario_data = json.load(f)
        client = scenario_data.get("client", "unknown")
        domain = scenario_data.get("domain", "unknown")
        source = {
            "scenario": str(scenario),
            "source_type": "scenario",
        }
        risks = extract_risks_from_scenario(scenario)
    elif run_dir:
        client, taxonomy, domain_ctx = _load_run(run_dir)
        domain = _infer_domain(policy_file) if policy_file else "unknown"
        source = {
            "run_dir": str(run_dir),
            "policy_file": str(policy_file) if policy_file else None,
            "source_type": "refiner_run",
        }
        risks = extract_risks(taxonomy, domain_ctx)
    else:
        raise ValueError("Either run_dir or scenario must be provided")

    # Query AIROO for each risk
    analyzed_risks = []
    for risk in risks:
        risk_id = risk["risk_id"]

        # Query with the risk's own ID first
        coverage = query_coverage(risk_id)

        # If no direct coverage, try alternative framings
        if not coverage["probes"] and not coverage["guardrails"]:
            for framing in risk.get("alternative_framings", []):
                alt_coverage = query_coverage(framing["risk_id"])
                coverage["probes"].extend(alt_coverage["probes"])
                coverage["guardrails"].extend(alt_coverage["guardrails"])
                coverage["benchmarks"].extend(alt_coverage["benchmarks"])

        # Deduplicate
        coverage["probes"] = _dedup(coverage["probes"], "probe_id")
        coverage["guardrails"] = _dedup(coverage["guardrails"], "guardrail_id")
        coverage["benchmarks"] = _dedup(coverage["benchmarks"], "benchmark_id")

        gaps = _classify_coverage(coverage, risk.get("attack_dimensions", []))

        analyzed_risks.append({
            **risk,
            "coverage": {**coverage, "gaps": gaps},
        })

    # Summary
    total = len(analyzed_risks)
    with_probes = sum(1 for r in analyzed_risks if r["coverage"]["gaps"]["has_probes"])
    with_guardrails = sum(1 for r in analyzed_risks if r["coverage"]["gaps"]["has_guardrails"])
    with_benchmarks = sum(1 for r in analyzed_risks if r["coverage"]["gaps"]["has_benchmarks"])
    fully_covered = sum(
        1 for r in analyzed_risks
        if r["coverage"]["gaps"]["has_probes"] and r["coverage"]["gaps"]["has_guardrails"]
    )
    no_coverage = sum(
        1 for r in analyzed_risks
        if not r["coverage"]["gaps"]["has_probes"] and not r["coverage"]["gaps"]["has_guardrails"]
    )
    partial_gaps = total - fully_covered - no_coverage

    # Count amplified risks
    amplified = sum(len(r.get("alternative_framings", [])) for r in analyzed_risks)

    return {
        "client": client,
        "domain": domain,
        "source": source,
        "risks": analyzed_risks,
        "summary": {
            "total_risks": total,
            "amplified_risks": amplified,
            "risks_with_probes": with_probes,
            "risks_with_guardrails": with_guardrails,
            "risks_with_benchmarks": with_benchmarks,
            "fully_covered": fully_covered,
            "partial_gaps": partial_gaps,
            "no_coverage": no_coverage,
        },
    }


def _load_run(run_dir: Path) -> tuple[str, dict, dict]:
    """Load taxonomy and domain context from a refiner run directory."""
    # Find the taxonomy and domain context files
    taxonomy_files = list(run_dir.glob("*-enriched-taxonomy.yaml"))
    dc_files = list(run_dir.glob("*-enriched-domain-context.yaml"))

    if not taxonomy_files:
        raise FileNotFoundError(f"No taxonomy file found in {run_dir}")

    taxonomy_path = taxonomy_files[0]
    client_slug = taxonomy_path.name.replace("-enriched-taxonomy.yaml", "")

    with open(taxonomy_path) as f:
        taxonomy = yaml.safe_load(f)

    domain_ctx = {"profiles": []}
    if dc_files:
        with open(dc_files[0]) as f:
            domain_ctx = yaml.safe_load(f)

    return client_slug, taxonomy, domain_ctx


def _infer_domain(policy_file: Path) -> str:
    """Infer domain from policy file name or content."""
    name = policy_file.stem.lower()
    domain_map = {
        "swb": "finance",
        "healthcare": "healthcare",
        "generic": "general",
        "aramco": "energy",
        "dhs": "government",
    }
    for key, domain in domain_map.items():
        if key in name:
            return domain
    return "general"


def _dedup(items: list[dict], key: str) -> list[dict]:
    """Deduplicate list of dicts by a key field."""
    seen = set()
    result = []
    for item in items:
        k = item[key]
        if k not in seen:
            seen.add(k)
            result.append(item)
    return result


def main():
    parser = argparse.ArgumentParser(description="Stage 1: Coverage analysis")
    parser.add_argument("run_dir", nargs="?", type=Path, help="Refiner run directory")
    parser.add_argument("--policy", type=Path, help="Policy file (for domain identification)")
    parser.add_argument("--scenario", type=Path, help="Canned scenario JSON (fallback)")
    parser.add_argument("--output", type=Path, required=True, help="Output directory")
    args = parser.parse_args()

    if not args.run_dir and not args.scenario:
        parser.error("Either run_dir or --scenario must be provided")

    analysis = build_analysis(
        run_dir=args.run_dir,
        policy_file=args.policy,
        scenario=args.scenario,
    )

    args.output.mkdir(parents=True, exist_ok=True)
    out_path = args.output / "analysis.json"
    with open(out_path, "w") as f:
        json.dump(analysis, f, indent=2)

    print(f"Analysis written to {out_path}")
    s = analysis["summary"]
    print(f"  {s['total_risks']} risks, {s['amplified_risks']} amplified")
    print(f"  {s['fully_covered']} fully covered, {s['partial_gaps']} partial, {s['no_coverage']} uncovered")


if __name__ == "__main__":
    main()
```

Write to `prototypes/advisory/analyze.py`.

- [ ] **Step 2: Run tests**

```bash
cd prototypes/advisory
uv run pytest tests/test_analyze.py -v
```

Expected: all tests pass. If AIROO query tests fail due to risk IDs not matching AIROO's data, adjust the test expectations to match what AIROO actually returns (the fixture uses `atlas-exposing-personal-information` and `atlas-jailbreaking` which should be in AIROO).

- [ ] **Step 3: Run against canned scenario**

```bash
cd prototypes/advisory
uv run python analyze.py --scenario scenarios/healthcare_chat.json --output /tmp/advisory-test
cat /tmp/advisory-test/analysis.json | python -m json.tool | head -40
```

Expected: prints analysis JSON with 5 risks and coverage data from AIROO.

- [ ] **Step 4: Run against real refiner run (if available)**

```bash
cd prototypes/advisory
uv run python analyze.py ../../runs/swb-mistral-small-3-1-24b-g10 --policy ../../policy_examples/swb.json --output /tmp/advisory-swb
cat /tmp/advisory-swb/analysis.json | python -m json.tool | head -40
```

Expected: prints analysis JSON with SWB risks. Some risks will have AIROO coverage (via cross-mappings to atlas-* IDs), others won't (client-specific risk IDs).

- [ ] **Step 5: Commit**

```bash
git add prototypes/advisory/analyze.py
git commit -m "feat(advisory): implement Stage 1 analyze.py — coverage analysis"
```

---

### Task 5: Stage 2 — `configure.py` (Tests First)

**Files:**
- Create: `prototypes/advisory/tests/test_configure.py`

- [ ] **Step 1: Write tests**

```python
"""Tests for configure.py — Stage 2: config generation."""
import json
from pathlib import Path

import pytest
import yaml


def _make_analysis():
    """Minimal analysis dict for testing config generation."""
    return {
        "client": "test",
        "domain": "finance",
        "source": {"source_type": "scenario"},
        "risks": [
            {
                "risk_id": "atlas-jailbreaking",
                "risk_name": "Jailbreaking",
                "policy_concept": "Security",
                "alternative_framings": [],
                "attack_dimensions": [],
                "coverage": {
                    "probes": [
                        {"probe_id": "dan.DanInTheWild", "platform": "garak",
                         "mapping_source": "garak_tags", "description": "DAN jailbreak", "garak_tier": "OF_CONCERN"},
                        {"probe_id": "tap.TAPCached", "platform": "garak",
                         "mapping_source": "garak_tags", "description": "TAP attack", "garak_tier": "COMPETE_WITH_SOTA"},
                    ],
                    "guardrails": [
                        {"guardrail_id": "nemo-jailbreak-heuristics", "detector_name": "jailbreak_detection_heuristics",
                         "platform": "nemo", "mapping_source": "platform_docs", "description": "Heuristic jailbreak"},
                        {"guardrail_id": "nemo-self-check-input", "detector_name": "self_check_input",
                         "platform": "nemo", "mapping_source": "platform_docs", "description": "LLM input check"},
                    ],
                    "benchmarks": [],
                    "gaps": {"has_probes": True, "has_guardrails": True,
                             "has_benchmarks": False, "uncovered_dimensions": []},
                },
            },
            {
                "risk_id": "atlas-exposing-personal-information",
                "risk_name": "PII Exposure",
                "policy_concept": "Data Privacy",
                "alternative_framings": [],
                "attack_dimensions": [],
                "coverage": {
                    "probes": [
                        {"probe_id": "leakreplay.GuardianCloze", "platform": "garak",
                         "mapping_source": "garak_tags", "description": "PII cloze", "garak_tier": "COMPETE_WITH_SOTA"},
                    ],
                    "guardrails": [
                        {"guardrail_id": "nemo-sensitive-data", "detector_name": "sensitive_data_detection",
                         "platform": "nemo", "mapping_source": "platform_docs", "description": "Presidio PII"},
                    ],
                    "benchmarks": [],
                    "gaps": {"has_probes": True, "has_guardrails": True,
                             "has_benchmarks": False, "uncovered_dimensions": []},
                },
            },
            {
                "risk_id": "atlas-novel-uncovered",
                "risk_name": "Novel Risk",
                "policy_concept": "Custom",
                "alternative_framings": [],
                "attack_dimensions": [{"cco_class": "Org", "role": "target", "term_count": 3, "terms": []}],
                "coverage": {
                    "probes": [],
                    "guardrails": [],
                    "benchmarks": [],
                    "gaps": {"has_probes": False, "has_guardrails": False,
                             "has_benchmarks": False, "uncovered_dimensions": ["Org"]},
                },
            },
        ],
        "summary": {
            "total_risks": 3, "amplified_risks": 0,
            "risks_with_probes": 2, "risks_with_guardrails": 2, "risks_with_benchmarks": 0,
            "fully_covered": 2, "partial_gaps": 0, "no_coverage": 1,
        },
    }


class TestGarakConfig:
    def test_generates_valid_yaml(self, tmp_path):
        from configure import generate_garak_config

        analysis = _make_analysis()
        generate_garak_config(analysis, tmp_path)
        config_path = tmp_path / "garak.yaml"
        assert config_path.exists()
        config = yaml.safe_load(config_path.read_text())
        assert "plugins" in config

    def test_includes_probes_from_analysis(self, tmp_path):
        from configure import generate_garak_config

        analysis = _make_analysis()
        generate_garak_config(analysis, tmp_path)
        content = (tmp_path / "garak.yaml").read_text()
        assert "dan.DanInTheWild" in content
        assert "leakreplay.GuardianCloze" in content

    def test_uncovered_risks_noted_in_comments(self, tmp_path):
        from configure import generate_garak_config

        analysis = _make_analysis()
        generate_garak_config(analysis, tmp_path)
        content = (tmp_path / "garak.yaml").read_text()
        assert "Novel Risk" in content  # should appear as a comment


class TestNemoConfig:
    def test_generates_config_yml(self, tmp_path):
        from configure import generate_nemo_config

        analysis = _make_analysis()
        generate_nemo_config(analysis, tmp_path)
        config_path = tmp_path / "nemo" / "config.yml"
        assert config_path.exists()

    def test_generates_rails_co(self, tmp_path):
        from configure import generate_nemo_config

        analysis = _make_analysis()
        generate_nemo_config(analysis, tmp_path)
        rails_path = tmp_path / "nemo" / "rails.co"
        assert rails_path.exists()

    def test_config_includes_system_prompt_with_domain(self, tmp_path):
        from configure import generate_nemo_config

        analysis = _make_analysis()
        generate_nemo_config(analysis, tmp_path)
        content = (tmp_path / "nemo" / "config.yml").read_text()
        assert "finance" in content.lower()

    def test_rails_include_jailbreak_flow(self, tmp_path):
        from configure import generate_nemo_config

        analysis = _make_analysis()
        generate_nemo_config(analysis, tmp_path)
        content = (tmp_path / "nemo" / "rails.co").read_text()
        assert "jailbreak" in content.lower()

    def test_rails_include_pii_flow(self, tmp_path):
        from configure import generate_nemo_config

        analysis = _make_analysis()
        generate_nemo_config(analysis, tmp_path)
        content = (tmp_path / "nemo" / "rails.co").read_text()
        assert "sensitive_data" in content.lower() or "pii" in content.lower()
```

Write to `prototypes/advisory/tests/test_configure.py`.

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd prototypes/advisory
uv run pytest tests/test_configure.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'configure'`

- [ ] **Step 3: Commit**

```bash
git add prototypes/advisory/tests/test_configure.py
git commit -m "test(advisory): add Stage 2 configure tests (red)"
```

---

### Task 6: Stage 2 — `configure.py` (Templates + Implementation)

**Files:**
- Create: `prototypes/advisory/templates/garak.yaml.j2`
- Create: `prototypes/advisory/templates/nemo_config.yml.j2`
- Create: `prototypes/advisory/templates/nemo_rails.co.j2`
- Create: `prototypes/advisory/configure.py`

- [ ] **Step 1: Create Garak config template**

```jinja2
# Garak Vulnerability Scan Configuration
# Generated by advisory prototype
# Client: {{ client }} | Domain: {{ domain }}
# Risks analyzed: {{ total_risks }} | Probes selected: {{ total_probes }}

plugins:
  generators:
    openai.OpenAICompatible:
      name: "{{ client }}-target"
      api_base: "${TARGET_API_BASE:-http://localhost:8080/v1}"
      api_key: "${TARGET_API_KEY}"

  probes:
{% for group in probe_groups %}
    # --- {{ group.dimension }} ---
{% for probe in group.probes %}
    # {{ probe.risk_name }} ({{ probe.risk_id }}) [{{ probe.mapping_source }}]
    - {{ probe.probe_id }}    # {{ probe.garak_tier }}
{% endfor %}
{% endfor %}
{% if uncovered_risks %}

    # --- UNCOVERED RISKS (no AIROO probes mapped) ---
{% for risk in uncovered_risks %}
    # {{ risk.risk_name }} ({{ risk.risk_id }}) — {{ risk.dimension_count }} attack dimensions, no probes
{% endfor %}
{% endif %}

  detectors:
    judge.MulticlassJudge:
      judge_model: "${JUDGE_MODEL:-granite-guardian-3.2-3b}"
      judge_api_base: "${JUDGE_API_BASE:-http://localhost:8080/v1}"

  eval_threshold: 0.5
  generations: 2
```

Write to `prototypes/advisory/templates/garak.yaml.j2`.

- [ ] **Step 2: Create NeMo config.yml template**

```jinja2
# NeMo Guardrails Configuration
# Generated by advisory prototype
# Client: {{ client }} | Domain: {{ domain }}

models:
  - type: main
    engine: openai
    model: "${LLM_MODEL_NAME}"
    parameters:
      api_base: "${LLM_API_BASE}"
      api_key: "${LLM_API_KEY}"
{% if needs_hap_guard %}

  - type: hap_guard
    engine: openai
    model: "${HAP_GUARD_MODEL_NAME:-mistral-small}"
    parameters:
      api_base: "${HAP_GUARD_API_BASE}"
      api_key: "${HAP_GUARD_API_KEY}"
{% endif %}
{% if needs_injection_guard %}

  - type: injection_guard
    engine: openai
    model: "${INJECTION_GUARD_MODEL_NAME}"
    parameters:
      api_base: "${INJECTION_GUARD_API_BASE}"
      api_key: "${INJECTION_GUARD_API_KEY}"
{% endif %}

instructions:
  - type: general
    content: |
      You are an AI assistant for a {{ domain }} organization.
{% for concept in policy_concepts %}
      You must not provide advice related to: {{ concept }}.
{% endfor %}
      You must protect personally identifiable information.
      Respond only within the scope of your authorized functions.

rails:
  input:
    flows:
{% for rail in input_rails %}
      - {{ rail.flow_name }}    # {{ rail.source }}
{% endfor %}
  output:
    flows:
{% for rail in output_rails %}
      - {{ rail.flow_name }}    # {{ rail.source }}
{% endfor %}
```

Write to `prototypes/advisory/templates/nemo_config.yml.j2`.

- [ ] **Step 3: Create NeMo rails.co template**

```jinja2
# NeMo Guardrails Colang Flows
# Generated by advisory prototype
# Client: {{ client }} | Domain: {{ domain }}
{% for rail in all_rails %}

define flow {{ rail.flow_name }}
  # Source: {{ rail.risk_id }} → {{ rail.guardrail_id }} [{{ rail.mapping_source }}]
  execute {{ rail.detector_name }}
  if $result == "{{ rail.trigger_value }}"
    bot refuse {{ rail.refusal_type }}
{% endfor %}
{% for refusal in refusals %}

define bot refuse {{ refusal.type }}
  "{{ refusal.message }}"
{% endfor %}
{% if uncovered_risks %}

# --- UNCOVERED RISKS (no NeMo guardrails mapped) ---
{% for risk in uncovered_risks %}
# {{ risk.risk_name }} ({{ risk.risk_id }}) — requires custom rail or manual review
{% endfor %}
{% endif %}
```

Write to `prototypes/advisory/templates/nemo_rails.co.j2`.

- [ ] **Step 4: Implement configure.py**

```python
"""Stage 2: Generate Garak + NeMo config files from coverage analysis."""
import argparse
import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

TEMPLATES_DIR = Path(__file__).parent / "templates"

# Guardrail composition: cost-ordered, input vs output, trigger values
NEMO_RAIL_DEFS = {
    "nemo-jailbreak-heuristics": {
        "flow_name": "check_jailbreak_heuristic",
        "detector_name": "jailbreak_detection_heuristics",
        "trigger_value": "jailbreak",
        "refusal_type": "jailbreak",
        "position": "input",
        "cost_order": 1,
    },
    "nemo-sensitive-data": {
        "flow_name": "check_sensitive_data",
        "detector_name": "sensitive_data_detection",
        "trigger_value": "pii_detected",
        "refusal_type": "pii",
        "position": "both",  # input detection + output masking
        "cost_order": 2,
    },
    "nemo-injection-detection": {
        "flow_name": "check_injection",
        "detector_name": "injection_detection",
        "trigger_value": "injection",
        "refusal_type": "injection",
        "position": "input",
        "cost_order": 3,
    },
    "nemo-self-check-input": {
        "flow_name": "check_input_safety",
        "detector_name": "self_check_input",
        "trigger_value": "unsafe",
        "refusal_type": "unsafe_input",
        "position": "input",
        "cost_order": 4,
    },
    "nemo-content-safety": {
        "flow_name": "check_content_safety",
        "detector_name": "content_safety",
        "trigger_value": "unsafe",
        "refusal_type": "content_safety",
        "position": "input",
        "cost_order": 5,
    },
    "nemo-self-check-output": {
        "flow_name": "check_output_safety",
        "detector_name": "self_check_output",
        "trigger_value": "unsafe",
        "refusal_type": "unsafe_output",
        "position": "output",
        "cost_order": 6,
    },
    "nemo-hallucination-detection": {
        "flow_name": "check_hallucination",
        "detector_name": "hallucination_detection",
        "trigger_value": "hallucination",
        "refusal_type": "hallucination",
        "position": "output",
        "cost_order": 7,
    },
    "nemo-fact-checking": {
        "flow_name": "check_facts",
        "detector_name": "fact_checking",
        "trigger_value": "ungrounded",
        "refusal_type": "hallucination",
        "position": "output",
        "cost_order": 8,
    },
}

REFUSAL_MESSAGES = {
    "jailbreak": "I cannot process this request. Your input has been flagged as a potential jailbreak attempt.",
    "pii": "I've detected sensitive personal information in the request. I cannot process it to protect privacy.",
    "injection": "I cannot process this request. A potential prompt injection has been detected.",
    "unsafe_input": "I cannot process this request as it may involve unsafe content.",
    "content_safety": "I cannot provide a response to this request due to content safety concerns.",
    "unsafe_output": "I've filtered my response as it contained potentially unsafe content.",
    "hallucination": "I'm not confident in the accuracy of my response. Please verify with authoritative sources.",
}

# AIROO dimensions for grouping probes
DIMENSION_ORDER = ["jailbreak", "harmful_content", "pii_leakage", "bias_fairness", "hallucination"]


def generate_garak_config(analysis: dict, output_dir: Path):
    """Generate garak.yaml from analysis."""
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), keep_trailing_newline=True)
    template = env.get_template("garak.yaml.j2")

    # Collect and group probes by dimension
    probe_map = {}  # probe_id -> {probe info + risk info}
    for risk in analysis["risks"]:
        for probe in risk["coverage"]["probes"]:
            pid = probe["probe_id"]
            if pid not in probe_map:
                probe_map[pid] = {
                    **probe,
                    "risk_id": risk["risk_id"],
                    "risk_name": risk["risk_name"],
                }

    # Group probes by AIROO dimension (use a simple tag-based heuristic)
    probe_groups = []
    grouped_probes = set()

    for dim in DIMENSION_ORDER:
        dim_probes = []
        for pid, info in probe_map.items():
            if pid in grouped_probes:
                continue
            if _probe_matches_dimension(pid, dim):
                dim_probes.append(info)
                grouped_probes.add(pid)
        if dim_probes:
            probe_groups.append({"dimension": dim, "probes": dim_probes})

    # Any ungrouped probes
    ungrouped = [info for pid, info in probe_map.items() if pid not in grouped_probes]
    if ungrouped:
        probe_groups.append({"dimension": "other", "probes": ungrouped})

    # Uncovered risks
    uncovered = [
        {"risk_id": r["risk_id"], "risk_name": r["risk_name"],
         "dimension_count": len(r.get("attack_dimensions", []))}
        for r in analysis["risks"]
        if not r["coverage"]["gaps"]["has_probes"]
    ]

    content = template.render(
        client=analysis["client"],
        domain=analysis["domain"],
        total_risks=analysis["summary"]["total_risks"],
        total_probes=len(probe_map),
        probe_groups=probe_groups,
        uncovered_risks=uncovered,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "garak.yaml").write_text(content)


def generate_nemo_config(analysis: dict, output_dir: Path):
    """Generate NeMo config.yml + rails.co from analysis."""
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), keep_trailing_newline=True)

    # Collect unique NeMo guardrails from analysis
    nemo_guardrails = {}
    for risk in analysis["risks"]:
        for g in risk["coverage"]["guardrails"]:
            if g["platform"] == "nemo" and g["guardrail_id"] in NEMO_RAIL_DEFS:
                gid = g["guardrail_id"]
                if gid not in nemo_guardrails:
                    nemo_guardrails[gid] = {
                        **NEMO_RAIL_DEFS[gid],
                        "guardrail_id": gid,
                        "risk_id": risk["risk_id"],
                        "mapping_source": g["mapping_source"],
                    }

    # Sort by cost order
    sorted_rails = sorted(nemo_guardrails.values(), key=lambda r: r["cost_order"])

    input_rails = [r for r in sorted_rails if r["position"] in ("input", "both")]
    output_rails = [r for r in sorted_rails if r["position"] in ("output", "both")]

    # Determine which guard models are needed
    needs_hap = any(r["guardrail_id"] == "nemo-content-safety" for r in sorted_rails)
    needs_injection = any(r["guardrail_id"] in ("nemo-injection-detection", "nemo-jailbreak-heuristics") for r in sorted_rails)

    # Policy concepts for system prompt
    policy_concepts = sorted(set(r["policy_concept"] for r in analysis["risks"]))

    # Uncovered risks
    uncovered = [
        {"risk_id": r["risk_id"], "risk_name": r["risk_name"]}
        for r in analysis["risks"]
        if not r["coverage"]["gaps"]["has_guardrails"]
    ]

    # Refusals needed
    refusal_types = set(r["refusal_type"] for r in sorted_rails)
    refusals = [{"type": t, "message": REFUSAL_MESSAGES.get(t, "I cannot process this request.")}
                for t in sorted(refusal_types)]

    # Render config.yml
    config_template = env.get_template("nemo_config.yml.j2")
    config_content = config_template.render(
        client=analysis["client"],
        domain=analysis["domain"],
        needs_hap_guard=needs_hap,
        needs_injection_guard=needs_injection,
        policy_concepts=policy_concepts,
        input_rails=input_rails,
        output_rails=output_rails,
    )

    # Render rails.co
    rails_template = env.get_template("nemo_rails.co.j2")
    rails_content = rails_template.render(
        client=analysis["client"],
        domain=analysis["domain"],
        all_rails=sorted_rails,
        refusals=refusals,
        uncovered_risks=uncovered,
    )

    nemo_dir = output_dir / "nemo"
    nemo_dir.mkdir(parents=True, exist_ok=True)
    (nemo_dir / "config.yml").write_text(config_content)
    (nemo_dir / "rails.co").write_text(rails_content)


def _probe_matches_dimension(probe_id: str, dimension: str) -> bool:
    """Heuristic: match probe to AIROO dimension by probe name patterns."""
    probe_lower = probe_id.lower()
    patterns = {
        "jailbreak": ["dan.", "tap.", "suffix.", "dra.", "spo."],
        "harmful_content": ["realtoxicityprompts.", "lmrc.profanity", "lmrc.bullying", "lmrc.slurusage", "continuation."],
        "pii_leakage": ["leakreplay.", "web_injection."],
        "bias_fairness": ["lmrc.sexualisation", "lmrc.deadnaming"],
        "hallucination": ["packagehallucination.", "snowball.", "misleading."],
    }
    for pattern in patterns.get(dimension, []):
        if probe_lower.startswith(pattern.lower()):
            return True
    return False


def main():
    parser = argparse.ArgumentParser(description="Stage 2: Config generation")
    parser.add_argument("analysis", type=Path, help="Path to analysis.json from Stage 1")
    parser.add_argument("--output", type=Path, required=True, help="Output directory")
    args = parser.parse_args()

    with open(args.analysis) as f:
        analysis = json.load(f)

    generate_garak_config(analysis, args.output)
    generate_nemo_config(analysis, args.output)

    print(f"Configs written to {args.output}")
    print(f"  garak.yaml")
    print(f"  nemo/config.yml")
    print(f"  nemo/rails.co")


if __name__ == "__main__":
    main()
```

Write to `prototypes/advisory/configure.py`.

- [ ] **Step 5: Run tests**

```bash
cd prototypes/advisory
uv run pytest tests/test_configure.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add prototypes/advisory/configure.py prototypes/advisory/templates/
git commit -m "feat(advisory): implement Stage 2 configure.py — Garak + NeMo config generation"
```

---

### Task 7: Stage 3 — `report.py` (Tests First)

**Files:**
- Create: `prototypes/advisory/tests/test_report.py`

- [ ] **Step 1: Write tests**

```python
"""Tests for report.py — Stage 3: advisory report generation."""
from pathlib import Path

import pytest


def _make_analysis():
    """Same analysis fixture as test_configure.py."""
    return {
        "client": "test",
        "domain": "finance",
        "source": {"source_type": "scenario", "scenario": "healthcare_chat.json"},
        "risks": [
            {
                "risk_id": "atlas-jailbreaking",
                "risk_name": "Jailbreaking",
                "policy_concept": "Security",
                "alternative_framings": [
                    {"risk_id": "atlas-prompt-injection", "taxonomy": "ibm-risk-atlas", "mapping_type": "related"}
                ],
                "attack_dimensions": [
                    {"cco_class": "Person", "role": "attacker", "term_count": 5, "terms": []}
                ],
                "coverage": {
                    "probes": [
                        {"probe_id": "dan.DanInTheWild", "platform": "garak",
                         "mapping_source": "garak_tags", "description": "", "garak_tier": "OF_CONCERN"},
                    ],
                    "guardrails": [
                        {"guardrail_id": "nemo-jailbreak-heuristics", "detector_name": "jailbreak_detection_heuristics",
                         "platform": "nemo", "mapping_source": "platform_docs", "description": ""},
                    ],
                    "benchmarks": [],
                    "gaps": {"has_probes": True, "has_guardrails": True,
                             "has_benchmarks": False, "uncovered_dimensions": ["Person"]},
                },
            },
            {
                "risk_id": "atlas-novel",
                "risk_name": "Novel Risk",
                "policy_concept": "Custom",
                "alternative_framings": [],
                "attack_dimensions": [
                    {"cco_class": "Organization", "role": "target", "term_count": 3, "terms": []}
                ],
                "coverage": {
                    "probes": [],
                    "guardrails": [],
                    "benchmarks": [],
                    "gaps": {"has_probes": False, "has_guardrails": False,
                             "has_benchmarks": False, "uncovered_dimensions": ["Organization"]},
                },
            },
        ],
        "summary": {
            "total_risks": 2, "amplified_risks": 1,
            "risks_with_probes": 1, "risks_with_guardrails": 1, "risks_with_benchmarks": 0,
            "fully_covered": 1, "partial_gaps": 0, "no_coverage": 1,
        },
    }


class TestReport:
    def test_generates_markdown(self, tmp_path):
        from report import generate_report

        analysis = _make_analysis()
        generate_report(analysis, tmp_path)
        report_path = tmp_path / "advisory-report.md"
        assert report_path.exists()

    def test_report_includes_header(self, tmp_path):
        from report import generate_report

        analysis = _make_analysis()
        generate_report(analysis, tmp_path)
        content = (tmp_path / "advisory-report.md").read_text()
        assert "test" in content.lower() or "Advisory Report" in content

    def test_report_includes_coverage_matrix(self, tmp_path):
        from report import generate_report

        analysis = _make_analysis()
        generate_report(analysis, tmp_path)
        content = (tmp_path / "advisory-report.md").read_text()
        assert "Jailbreaking" in content
        assert "Novel Risk" in content

    def test_report_includes_gap_analysis(self, tmp_path):
        from report import generate_report

        analysis = _make_analysis()
        generate_report(analysis, tmp_path)
        content = (tmp_path / "advisory-report.md").read_text()
        assert "Gap" in content or "gap" in content
        assert "Novel Risk" in content

    def test_report_includes_summary_numbers(self, tmp_path):
        from report import generate_report

        analysis = _make_analysis()
        generate_report(analysis, tmp_path)
        content = (tmp_path / "advisory-report.md").read_text()
        assert "2" in content  # total risks
        assert "1" in content  # fully covered
```

Write to `prototypes/advisory/tests/test_report.py`.

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd prototypes/advisory
uv run pytest tests/test_report.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'report'`

- [ ] **Step 3: Commit**

```bash
git add prototypes/advisory/tests/test_report.py
git commit -m "test(advisory): add Stage 3 report tests (red)"
```

---

### Task 8: Stage 3 — `report.py` (Template + Implementation)

**Files:**
- Create: `prototypes/advisory/templates/report.md.j2`
- Create: `prototypes/advisory/report.py`

- [ ] **Step 1: Create report template**

```jinja2
# Advisory Report: {{ client | upper }} ({{ domain | capitalize }})

Generated: {{ timestamp }} | Source: {{ source_label }}

---

## Executive Summary

- **{{ summary.total_risks }} risks** identified from client policies
- **{{ summary.amplified_risks }} amplified risks** via cross-framework mappings
- **{{ summary.fully_covered }} fully covered** by existing probes + guardrails
- **{{ summary.partial_gaps }} partial gaps** — probes or guardrails exist but not both
- **{{ summary.no_coverage }} uncovered risks** — require custom tooling or manual review

{% if summary.no_coverage > 0 -%}
**Action required:** {{ summary.no_coverage }} risk(s) have no automated probes or guardrails.
{%- else -%}
All identified risks have at least partial probe and guardrail coverage.
{%- endif %}

---

## Coverage Matrix

| Risk | Policy | Probes | Guardrails | Benchmarks | Status |
|------|--------|--------|------------|------------|--------|
{% for risk in risks -%}
| {{ risk.risk_name }} | {{ risk.policy_concept }} | {{ risk.coverage.probes | length }} | {{ risk.coverage.guardrails | length }} | {{ risk.coverage.benchmarks | length }} | {{ risk.status }} |
{% endfor %}

---

## Gap Analysis

{% if uncovered_risks %}
### Uncovered Risks

These risks have no AIROO probes or guardrails mapped. They require custom tooling or manual review.

{% for risk in uncovered_risks -%}
**{{ risk.risk_name }}** (`{{ risk.risk_id }}`)
- Policy: {{ risk.policy_concept }}
- Attack dimensions: {{ risk.attack_dimensions | length }} ({{ risk.dimension_labels }})
- *Recommendation: custom NeMo rail or Granite Guardian fine-tune targeting {{ risk.dimension_labels }}*

{% endfor %}
{% endif %}
{% if partial_risks %}
### Partial Gaps

These risks have some coverage but not complete probe + guardrail pairing.

{% for risk in partial_risks -%}
**{{ risk.risk_name }}** (`{{ risk.risk_id }}`)
- Has probes: {{ "yes" if risk.coverage.gaps.has_probes else "no" }}
- Has guardrails: {{ "yes" if risk.coverage.gaps.has_guardrails else "no" }}
- Has benchmarks: {{ "yes" if risk.coverage.gaps.has_benchmarks else "no" }}
{% if risk.coverage.gaps.uncovered_dimensions -%}
- Uncovered attack dimensions: {{ risk.coverage.gaps.uncovered_dimensions | join(", ") }}
{% endif %}

{% endfor %}
{% endif %}
{% if uncovered_dimensions %}
### Uncovered Attack Dimensions

Attack dimensions from the refiner that no probe specifically targets, even when the parent risk has generic coverage.

| Risk | Dimension | Term Count |
|------|-----------|------------|
{% for dim in uncovered_dimensions -%}
| {{ dim.risk_name }} | {{ dim.dimension }} | {{ dim.term_count }} |
{% endfor %}

{% endif %}
---

## Generated Configurations

### Garak Scan Configuration

- File: `garak.yaml`
- Probes: {{ total_probes }} across {{ probe_dimension_count }} dimensions
{% for group in probe_groups -%}
- **{{ group.dimension }}**: {{ group.probes | length }} probe(s)
  {% for probe in group.probes -%}
  - `{{ probe.probe_id }}` — {{ probe.risk_name }} [{{ probe.mapping_source }}]
  {% endfor %}
{% endfor %}

### NeMo Guardrails Configuration

- Files: `nemo/config.yml` + `nemo/rails.co`
- Input rails: {{ input_rail_count }}
- Output rails: {{ output_rail_count }}
{% for rail in nemo_rails -%}
- `{{ rail.flow_name }}` ({{ rail.position }}) — {{ rail.risk_id }} [{{ rail.mapping_source }}]
{% endfor %}

---

## Lineage

Each recommendation traces back through:

1. **Policy concept** → refiner risk ID → Atlas Nexus cross-mapping
2. **AIROO dimension** → specific probe/guardrail with mapping source
3. **Refiner attack dimension** → CCO class → domain ontology terms

{% for risk in risks -%}
### {{ risk.risk_name }}

- Source: policy concept "{{ risk.policy_concept }}"
{% if risk.alternative_framings -%}
- Cross-mappings: {{ risk.alternative_framings | map(attribute='risk_id') | join(', ') }}
{% endif -%}
{% if risk.coverage.probes -%}
- Probes: {{ risk.coverage.probes | map(attribute='probe_id') | join(', ') }}
{% endif -%}
{% if risk.coverage.guardrails -%}
- Guardrails: {{ risk.coverage.guardrails | map(attribute='guardrail_id') | join(', ') }}
{% endif -%}
{% if risk.attack_dimensions -%}
- Attack dimensions: {{ risk.attack_dimensions | map(attribute='cco_class') | join(', ') }}
{% endif %}

{% endfor %}
```

Write to `prototypes/advisory/templates/report.md.j2`.

- [ ] **Step 2: Implement report.py**

```python
"""Stage 3: Render advisory report from analysis + generated configs."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

TEMPLATES_DIR = Path(__file__).parent / "templates"


def generate_report(analysis: dict, output_dir: Path):
    """Render advisory-report.md from analysis data."""
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), keep_trailing_newline=True)
    template = env.get_template("report.md.j2")

    # Classify risks by coverage status
    for risk in analysis["risks"]:
        gaps = risk["coverage"]["gaps"]
        if gaps["has_probes"] and gaps["has_guardrails"]:
            risk["status"] = "Covered"
        elif gaps["has_probes"] or gaps["has_guardrails"]:
            risk["status"] = "Partial Gap"
        else:
            risk["status"] = "**Gap**"

    uncovered_risks = []
    partial_risks = []
    for risk in analysis["risks"]:
        if risk["status"] == "**Gap**":
            risk["dimension_labels"] = ", ".join(
                d["cco_class"] for d in risk.get("attack_dimensions", [])
            ) or "none identified"
            uncovered_risks.append(risk)
        elif risk["status"] == "Partial Gap":
            partial_risks.append(risk)

    # Collect uncovered attack dimensions across all risks
    uncovered_dimensions = []
    for risk in analysis["risks"]:
        for dim in risk.get("attack_dimensions", []):
            uncovered_dimensions.append({
                "risk_name": risk["risk_name"],
                "dimension": dim["cco_class"],
                "term_count": dim.get("term_count", 0),
            })

    # Probe groups for the config summary section
    probe_map = {}
    for risk in analysis["risks"]:
        for probe in risk["coverage"]["probes"]:
            pid = probe["probe_id"]
            if pid not in probe_map:
                probe_map[pid] = {**probe, "risk_name": risk["risk_name"], "risk_id": risk["risk_id"]}

    # Simple grouping by name prefix
    probe_groups = _group_probes(probe_map)

    # NeMo rails summary
    nemo_rails = []
    seen_rails = set()
    for risk in analysis["risks"]:
        for g in risk["coverage"]["guardrails"]:
            if g["platform"] == "nemo" and g["guardrail_id"] not in seen_rails:
                seen_rails.add(g["guardrail_id"])
                nemo_rails.append({
                    "flow_name": g["detector_name"],
                    "position": "input",
                    "risk_id": risk["risk_id"],
                    "mapping_source": g["mapping_source"],
                })

    input_rail_count = sum(1 for r in nemo_rails if r["position"] == "input")
    output_rail_count = sum(1 for r in nemo_rails if r["position"] == "output")

    # Source label
    source = analysis.get("source", {})
    if source.get("source_type") == "scenario":
        source_label = f"scenario: {source.get('scenario', 'unknown')}"
    else:
        source_label = f"run: {source.get('run_dir', 'unknown')}"

    content = template.render(
        client=analysis["client"],
        domain=analysis["domain"],
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        source_label=source_label,
        summary=analysis["summary"],
        risks=analysis["risks"],
        uncovered_risks=uncovered_risks,
        partial_risks=partial_risks,
        uncovered_dimensions=uncovered_dimensions,
        total_probes=len(probe_map),
        probe_dimension_count=len(probe_groups),
        probe_groups=probe_groups,
        nemo_rails=nemo_rails,
        input_rail_count=input_rail_count,
        output_rail_count=output_rail_count,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "advisory-report.md").write_text(content)


def _group_probes(probe_map: dict) -> list[dict]:
    """Group probes by dimension heuristic."""
    groups = {}
    for pid, info in probe_map.items():
        dim = _infer_dimension(pid)
        if dim not in groups:
            groups[dim] = {"dimension": dim, "probes": []}
        groups[dim]["probes"].append(info)
    return list(groups.values())


def _infer_dimension(probe_id: str) -> str:
    """Infer AIROO dimension from probe ID prefix."""
    probe_lower = probe_id.lower()
    patterns = {
        "jailbreak": ["dan.", "tap.", "suffix.", "dra.", "spo."],
        "harmful_content": ["realtoxicityprompts.", "lmrc.profanity", "lmrc.bullying", "lmrc.slurusage", "continuation."],
        "pii_leakage": ["leakreplay.", "web_injection."],
        "bias_fairness": ["lmrc.sexualisation", "lmrc.deadnaming"],
        "hallucination": ["packagehallucination.", "snowball.", "misleading."],
    }
    for dim, prefixes in patterns.items():
        for prefix in prefixes:
            if probe_lower.startswith(prefix.lower()):
                return dim
    return "other"


def main():
    parser = argparse.ArgumentParser(description="Stage 3: Advisory report")
    parser.add_argument("output_dir", type=Path, help="Directory containing analysis.json and configs")
    parser.add_argument("--output", type=Path, help="Output directory (defaults to same as input)")
    args = parser.parse_args()

    analysis_path = args.output_dir / "analysis.json"
    if not analysis_path.exists():
        raise FileNotFoundError(f"analysis.json not found in {args.output_dir}")

    with open(analysis_path) as f:
        analysis = json.load(f)

    out_dir = args.output or args.output_dir
    generate_report(analysis, out_dir)
    print(f"Report written to {out_dir / 'advisory-report.md'}")


if __name__ == "__main__":
    main()
```

Write to `prototypes/advisory/report.py`.

- [ ] **Step 3: Run tests**

```bash
cd prototypes/advisory
uv run pytest tests/test_report.py -v
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add prototypes/advisory/report.py prototypes/advisory/templates/report.md.j2
git commit -m "feat(advisory): implement Stage 3 report.py — advisory report generation"
```

---

### Task 9: Wrapper Script + README

**Files:**
- Create: `prototypes/advisory/advise.py`
- Create: `prototypes/advisory/README.md`

- [ ] **Step 1: Implement advise.py**

```python
"""Advisory system prototype — chains analyze → configure → report."""
import argparse
import json
from pathlib import Path

from analyze import build_analysis
from configure import generate_garak_config, generate_nemo_config
from report import generate_report


def main():
    parser = argparse.ArgumentParser(
        description="Advisory system prototype: refiner output → coverage analysis → configs → report"
    )
    parser.add_argument("run_dir", nargs="?", type=Path, help="Refiner run directory")
    parser.add_argument("--policy", type=Path, help="Policy file (for domain identification)")
    parser.add_argument("--scenario", type=Path, help="Canned scenario JSON (fallback)")
    parser.add_argument("--output", type=Path, required=True, help="Output directory")
    args = parser.parse_args()

    if not args.run_dir and not args.scenario:
        parser.error("Either run_dir or --scenario must be provided")

    output = args.output
    output.mkdir(parents=True, exist_ok=True)

    # Stage 1: Analyze
    print("=== Stage 1: Coverage Analysis ===")
    analysis = build_analysis(
        run_dir=args.run_dir,
        policy_file=args.policy,
        scenario=args.scenario,
    )
    analysis_path = output / "analysis.json"
    with open(analysis_path, "w") as f:
        json.dump(analysis, f, indent=2)

    s = analysis["summary"]
    print(f"  {s['total_risks']} risks, {s['amplified_risks']} amplified")
    print(f"  {s['fully_covered']} covered, {s['partial_gaps']} partial, {s['no_coverage']} uncovered")

    # Stage 2: Configure
    print("\n=== Stage 2: Config Generation ===")
    generate_garak_config(analysis, output)
    generate_nemo_config(analysis, output)
    print("  garak.yaml")
    print("  nemo/config.yml + rails.co")

    # Stage 3: Report
    print("\n=== Stage 3: Advisory Report ===")
    generate_report(analysis, output)
    print(f"  advisory-report.md")

    print(f"\nAll artifacts written to {output}/")


if __name__ == "__main__":
    main()
```

Write to `prototypes/advisory/advise.py`.

- [ ] **Step 2: Create README**

```markdown
# Advisory System Prototype

Concept prototype demonstrating the advisory reasoning chain:
refiner output → AIROO coverage queries → Garak/NeMo config generation → SA-facing report.

## Setup

```bash
cd prototypes/advisory
uv sync --extra airoo
```

Requires AIROO at `../../trustyai-explainability/ai-risk-operational-ontology` (adjust path in `pyproject.toml` if needed).

## Usage

### From a refiner run

```bash
uv run python advise.py ../../runs/swb-mistral-small-3-1-24b-g10 \
  --policy ../../policy_examples/swb.json \
  --output /tmp/advisory-swb
```

### From a canned scenario (no refiner run needed)

```bash
uv run python advise.py --scenario scenarios/healthcare_chat.json \
  --output /tmp/advisory-healthcare
```

### Individual stages

```bash
# Stage 1: Coverage analysis
uv run python analyze.py ../../runs/swb-mistral-small-3-1-24b-g10 \
  --policy ../../policy_examples/swb.json \
  --output /tmp/advisory-swb

# Stage 2: Config generation
uv run python configure.py /tmp/advisory-swb/analysis.json \
  --output /tmp/advisory-swb

# Stage 3: Report
uv run python report.py /tmp/advisory-swb
```

## Output

```
/tmp/advisory-swb/
  analysis.json           # Coverage analysis (machine-readable)
  garak.yaml              # Garak scan configuration
  nemo/
    config.yml            # NeMo Guardrails configuration
    rails.co              # NeMo Colang flow definitions
  advisory-report.md      # SA-facing advisory report
```

## Tests

```bash
uv run pytest tests/ -v
```

## What this does NOT do

- Execute Garak scans (generates config only)
- Execute NeMo Guardrails (generates config only)
- Recommend specific models (model catalog doesn't exist yet)
- Make LLM calls (pure data transformation)
```

Write to `prototypes/advisory/README.md`.

- [ ] **Step 3: Test full pipeline with scenario**

```bash
cd prototypes/advisory
uv run python advise.py --scenario scenarios/healthcare_chat.json --output /tmp/advisory-healthcare
```

Expected: prints three stage summaries, writes all artifacts to `/tmp/advisory-healthcare/`.

- [ ] **Step 4: Verify outputs**

```bash
ls /tmp/advisory-healthcare/
cat /tmp/advisory-healthcare/advisory-report.md | head -60
cat /tmp/advisory-healthcare/garak.yaml | head -30
cat /tmp/advisory-healthcare/nemo/config.yml | head -30
```

Expected: all files exist and contain meaningful content.

- [ ] **Step 5: Test with real refiner run**

```bash
cd prototypes/advisory
uv run python advise.py ../../runs/swb-mistral-small-3-1-24b-g10 \
  --policy ../../policy_examples/swb.json \
  --output /tmp/advisory-swb
ls /tmp/advisory-swb/
```

Expected: all artifacts generated. Coverage numbers will differ from scenario — client-specific risk IDs (like `client-swb-enriched-*`) won't match AIROO directly, but their cross-mapped `related_mappings` (like `atlas-*`) should find coverage.

- [ ] **Step 6: Run full test suite**

```bash
cd prototypes/advisory
uv run pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add prototypes/advisory/advise.py prototypes/advisory/README.md
git commit -m "feat(advisory): add advise.py wrapper and README"
```

---

### Task 10: Final Integration Test + Cleanup

- [ ] **Step 1: Run full test suite from project root**

```bash
cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/prototypes/advisory
uv run pytest tests/ -v --tb=short
```

Expected: all tests pass.

- [ ] **Step 2: End-to-end with scenario**

```bash
cd prototypes/advisory
rm -rf /tmp/advisory-e2e
uv run python advise.py --scenario scenarios/healthcare_chat.json --output /tmp/advisory-e2e
```

Verify:
- `/tmp/advisory-e2e/analysis.json` has 5 risks with coverage data
- `/tmp/advisory-e2e/garak.yaml` has probes grouped by dimension
- `/tmp/advisory-e2e/nemo/config.yml` has model config + system prompt mentioning healthcare
- `/tmp/advisory-e2e/nemo/rails.co` has flow definitions
- `/tmp/advisory-e2e/advisory-report.md` has coverage matrix + gap analysis

- [ ] **Step 3: End-to-end with real refiner run**

```bash
cd prototypes/advisory
rm -rf /tmp/advisory-e2e-swb
uv run python advise.py ../../runs/swb-mistral-small-3-1-24b-g10 \
  --policy ../../policy_examples/swb.json \
  --output /tmp/advisory-e2e-swb
```

Verify: same file structure, risk IDs from the real refiner run, coverage from AIROO for cross-mapped risks.

- [ ] **Step 4: Review advisory report quality**

Read `/tmp/advisory-e2e/advisory-report.md` and `/tmp/advisory-e2e-swb/advisory-report.md` end-to-end. Check:
- Coverage matrix makes sense
- Gap analysis identifies real gaps
- Lineage traces are correct
- Generated config summaries match the actual config files

- [ ] **Step 5: Final commit**

```bash
cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner
git add prototypes/advisory/
git status
git commit -m "feat(advisory): complete advisory system prototype

Three-stage pipeline: analyze (AIROO coverage) → configure (Garak + NeMo) → report (advisory markdown).
Reads refiner output or canned scenarios. No LLM calls — pure data transformation."
```
