# ORT-Enriched Garak Mock Data & Report — Design Spec

**Date:** 2026-04-15
**Status:** Draft
**Location:** `prototypes/garak/`

---

## Purpose

Mock a garak run as if it were produced by an ORT-enriched pipeline — where intents carry Nexus risk IDs, domain context references, and cross-framework mappings — then generate an enhanced ART report that surfaces the semantic richness.

This serves two goals:

1. **Demo artifact** — a concrete example of what the Shared Data Foundations proposal (Tiers 0-2) looks like in practice, using RDaSH NHS policy data
2. **Integration surface specification** — the mock makes the minimal garak changes explicit (what fields to add, what stays external) and defines the report-time join pattern

## What This Is Not

- Not a garak fork or patch — no changes to garak source
- Not a real garak scan — we re-key an existing run's data
- Not an end-to-end pipeline — the ORT metadata is loaded from existing Refiner outputs, not generated live
- Not a replacement for the existing ART report — extends it with additional semantic sections

---

## Data Architecture

Three data sources joined at report-generation time:

```
garak report.jsonl                    ORT Refiner outputs (RDaSH run)
  │ attempts with:                      │ domain-context.yaml
  │   intent: S001regulatorycompliance  │ taxonomy.yaml
  │   notes.stub.id: credo-risk-023:   │ risk-landscape.yaml
  │     narrative-framing:0             │ adversarial-prompts.jsonl
  │                                     │   (with id field added)
  └──────────┬──────────────────────────┘
             │
    intent-to-risk mapping
      S001regulatorycompliance →
        nexus_risk_id: credo-risk-023
             │
             ▼
    Report Generator
      │ base ART report (reuse existing parse_jsonl/vega_data)
      │ + cross-framework coverage matrix
      │ + domain vocabulary analysis
      │ + ontological risk grouping
      │ + provenance trail
      ▼
    Enhanced HTML report
```

### Principle: garak carries identifiers, not semantics

garak's report.jsonl gets two additions per attempt:

- `intent` re-keyed to S-number format mapped to ORT risks
- `notes.stub.id` — a stable stub identifier that joins to ORT adversarial prompt metadata

All semantic richness (cross-mappings, domain context, axes, provenance) lives in the ORT outputs and the mapping file. The report generator performs the join. This matches the Shared Data Foundations proposal: garak doesn't need to understand risk semantics, it just carries identifiers.

---

## Deliverable 1: Mock Data Generator

**File:** `prototypes/garak/mock_ort_garak_data.py`

### Inputs

| Source | Path |
|--------|------|
| Existing garak report | `prototypes/garak/garak_runs/garak.0e04280f-*.report.jsonl` |
| RDaSH adversarial prompts | `runs/rdash-nhs-gemma-4-26b-a4b-it-g12/rdash-nhs-adversarial-prompts.jsonl` |
| RDaSH domain context | `runs/rdash-nhs-gemma-4-26b-a4b-it-g12/rdash-nhs-domain-context.yaml` |
| RDaSH taxonomy | `runs/rdash-nhs-gemma-4-26b-a4b-it-g12/rdash-nhs-taxonomy.yaml` |
| RDaSH risk landscape | `runs/rdash-nhs-gemma-4-26b-a4b-it-g12/rdash-nhs-risk-landscape.yaml` |

### Intent Mapping

Map the 8 existing S00X intents to 8 RDaSH Nexus risk IDs:

| S-number intent | Nexus risk ID | Risk name | Framework |
|-----------------|---------------|-----------|-----------|
| `S001regulatorycompliance` | `credo-risk-023` | Regulatory compliance | Credo AI |
| `S002dataprivacy` | `nist-data-privacy` | Data Privacy | NIST AI RMF |
| `S003nondisclosure` | `atlas-non-disclosure` | Non-disclosure | IBM Risk Atlas |
| `S004personalinformation` | `atlas-personal-information-in-data` | Personal information in data | IBM Risk Atlas |
| `S005sensitiveinfo` | `credo-risk-037` | Compromised sensitive information | Credo AI |
| `S006accountability` | `atlas-accountability-agentic` | Accountability of AI agent actions | IBM Risk Atlas |
| `S007privacycompromise` | `mit-ai-risk-subdomain-2.1` | Compromise of privacy | MIT AI Risk Repository |
| `S008governancefailure` | `mit-ai-risk-subdomain-6.5` | Governance failure | MIT AI Risk Repository |

### Stub ID Generation

For each of the 135 RDaSH adversarial prompts, generate a stub ID:

```
{risk_id}:{technique}:{index}
```

Examples:
- `credo-risk-023:narrative-framing:0`
- `nist-data-privacy:pretexting:2`
- `atlas-non-disclosure:analytical-reframing:0`

The index is per risk-technique combination (38 unique combos across 135 prompts).

### Re-keying Logic

1. Parse the existing 1387 attempts
2. Map each attempt's old intent (`S001fraud`, etc.) to a new S-number intent via 1:1 mapping (8 old intents → 8 new intents, preserving the original per-intent attempt counts)
3. For each attempt within a risk, assign a stub ID by cycling through the stubs for that risk
4. Inject the stub ID into `notes.stub.id`
5. Update `intent` field to new S-number format
6. Preserve all other fields (probe_classname, detector_results, outputs, conversations, etc.)
7. Update `eval_intent` entries to use new intent IDs with recalculated scores
8. Leave `start_run setup`, `init`, `eval`, `completion`, `digest` entries largely intact (update metadata where relevant)

### Outputs

| File | Description |
|------|-------------|
| `prototypes/garak/mock_runs/ort-rdash.report.jsonl` | Re-keyed garak report |
| `prototypes/garak/mock_runs/ort-rdash.hitlog.jsonl` | Re-keyed hitlog |
| `prototypes/garak/mock_runs/ort_intent_mapping.json` | Intent-to-risk mapping |
| `prototypes/garak/mock_runs/ort_stubs.jsonl` | Adversarial prompts with `id` field added |

---

## Deliverable 2: Intent-to-Risk Mapping

**File:** `prototypes/garak/mock_runs/ort_intent_mapping.json`

```json
{
  "version": "0.1",
  "ort_run": "rdash-nhs-gemma-4-26b-a4b-it-g12",
  "policy_source": {
    "organization": "Rotherham Doncaster and South Humber NHS Foundation Trust (RDaSH)",
    "domain": "healthcare"
  },
  "curie_map": {
    "airo": "https://w3id.org/airo#",
    "cco": "https://www.commoncoreontologies.org/",
    "obo": "http://purl.obolibrary.org/obo/",
    "d3fend": "http://d3fend.mitre.org/ontologies/d3fend.owl#",
    "cso": "http://taxonomy-refiner.io/ontologies/cso#",
    "lkif": "http://www.estrellaproject.org/lkif-core/"
  },
  "intent_map": {
    "S001regulatorycompliance": {
      "nexus_risk_id": "credo-risk-023",
      "risk_name": "Regulatory compliance",
      "risk_framework": "Credo AI",
      "risk_group": "Governance & Compliance",
      "cross_mappings": [
        {
          "id": "granite-guardian-harm",
          "taxonomy": "ibm-granite-guardian",
          "mapping_type": "related"
        },
        {
          "id": "atlas-legal-accountability",
          "taxonomy": "ibm-risk-atlas",
          "mapping_type": "related"
        }
      ]
    }
  }
}
```

The `cross_mappings` are pulled from the RDaSH `domain-context.yaml` — each risk's full set of SKOS-typed cross-framework mappings. The `risk_group` is pulled from the `taxonomy.yaml` group structure.

---

## Deliverable 3: Enhanced Report Generator

**File:** `prototypes/garak/generate_ort_report.py`

### Data Loading

```python
def load_ort_context(
    report_path: Path,           # mock report.jsonl
    mapping_path: Path,          # ort_intent_mapping.json
    stubs_path: Path,            # ort_stubs.jsonl (adversarial prompts + IDs)
    domain_context_path: Path,   # rdash-nhs-domain-context.yaml
    taxonomy_path: Path,         # rdash-nhs-taxonomy.yaml
    risk_landscape_path: Path,   # rdash-nhs-risk-landscape.yaml
) -> OrtReportContext:
    ...
```

### Report Sections

#### Section A: Cross-Framework Coverage Matrix

For each tested risk, show all cross-mappings with SKOS types:

| Tested Risk | Framework | Cross-Mapped Risk | Mapping Type | Mapped Framework |
|-------------|-----------|-------------------|--------------|------------------|
| Regulatory compliance | Credo AI | Legal accountability | related | IBM Risk Atlas |
| Regulatory compliance | Credo AI | Data Privacy | related | NIST AI RMF |
| Data Privacy | NIST AI RMF | Attribute inference attack | broad | IBM Risk Atlas |
| Data Privacy | NIST AI RMF | Exposing personal information | broad | IBM Risk Atlas |

This is the Tier 1 story: "we tested 8 risks, but through SSSOM cross-mappings those tests also cover 57 related risks across 8 frameworks."

Visualization: a network/matrix heatmap showing risk-to-risk connections colored by mapping type (exact > close > broad > narrow > related).

#### Section B: Domain Vocabulary Analysis

Aggregate outcomes by variation axis (CCO/OBO/FIBO class) and source ontology:

| Axis (CCO class) | URI | Source Ontology | Stubs Using Axis | Complied | ASR |
|-------------------|-----|-----------------|------------------|----------|-----|
| regulatory compliance requirement | `lkif:...` | LKIF | 12 | 4 | 33% |
| medical data processing | `obo:GSSO_...` | OBO | 8 | 5 | 63% |
| information security control | `d3fend:...` | D3FEND | 6 | 1 | 17% |

This answers: "attacks grounded in clinical terminology (OBO) succeeded more than attacks grounded in legal terminology (LKIF)."

Visualization: horizontal bar chart, one bar per axis, colored by ASR.

#### Section C: Ontological Risk Grouping

Group results by the Refiner's taxonomy risk groups instead of flat intent IDs:

| Risk Group | Risks | Total Attempts | Complied | ASR |
|------------|-------|----------------|----------|-----|
| Data Protection & Privacy | nist-data-privacy, atlas-personal-information-in-data, credo-risk-037, mit-ai-risk-subdomain-2.1 | 690 | 62 | 9.0% |
| Governance & Compliance | credo-risk-023, mit-ai-risk-subdomain-6.5 | 350 | 22 | 6.3% |
| Transparency & Disclosure | atlas-accountability-agentic, atlas-non-disclosure | 348 | 15 | 4.3% |

Expandable: clicking a group shows the per-risk breakdown, clicking a risk shows the per-probe breakdown (the existing ART report's intent detail view).

Visualization: treemap or stacked bar grouped by risk group.

#### Section D: Provenance Trail

Per-attempt expandable detail row (in the probe details section):

```
Stub ID:    credo-risk-023:narrative-framing:0
Risk:       Regulatory compliance (credo-risk-023)
Framework:  Credo AI
Technique:  narrative_framing
Policy:     "AI systems must comply with NHS Digital's Data Security..."
Axes:
  - regulatory compliance requirement (lkif:RegulatoryComplianceRequirement)
  - data protection obligation (lkif:DataProtectionObligation)
  - healthcare data controller (obo:OMRSE_00000032)
Decomposition:
  Agent:    AI assistant
  Activity: process patient data
  Entity:   regulatory compliance status
```

This is the Tier 2 story: full E/A/A decomposition with PROV-O-style lineage from policy concept through ontology grounding to adversarial prompt.

### HTML Template

Extend the existing ART report template with four new navigation sections. Use PatternFly 6 (consistent with existing template). Vega-Lite for new visualizations.

The base ART sections (overview stats, behavior-by-probe, behavior-by-intent, probe details) remain — the new sections are additive.

---

## Taxonomy Group Assignment

The RDaSH taxonomy groups need to be mapped to the 8 risks. Based on the taxonomy structure:

| Risk Group (from taxonomy) | Risk IDs |
|---------------------------|----------|
| Data Protection & Privacy | `nist-data-privacy`, `atlas-personal-information-in-data`, `credo-risk-037`, `mit-ai-risk-subdomain-2.1` |
| Governance & Compliance | `credo-risk-023`, `mit-ai-risk-subdomain-6.5` |
| Transparency & Disclosure | `atlas-non-disclosure`, `atlas-accountability-agentic` |

---

## What This Tells Us About Garak Changes

The mock makes explicit the minimal changes needed in garak for real ORT integration:

| Change | Where | Effort |
|--------|-------|--------|
| `notes.stub.id` on Attempt | `Attempt` dataclass or notes dict | Trivial — notes is already a dict |
| Stub ID preservation through attack funnel | SPO/TAP harness | Needs investigation — does `notes` survive between stages? |
| S-number intent carries Nexus risk ID | CAS intent system | Already works — just a naming convention |
| Report generator loads external ORT data | New code, not in garak | Moderate — the prototype IS this code |

The open question from the Gap Analysis remains: **does garak's attack funnel preserve `Attempt.notes` when a stub survives between stages (SPO -> TAP)?** If notes get reset, the stub ID is lost. The mock sidesteps this by re-keying existing attempt data, but a real integration needs to verify this.

---

## File Layout

```
prototypes/garak/
  mock_ort_garak_data.py          # Mock data generator
  generate_ort_report.py          # Enhanced report generator
  ort_report_template.html        # Jinja2 template (extends ART)
  garak_runs/                     # Existing real garak run (unchanged)
    garak.0e04280f-*.report.jsonl
    garak.0e04280f-*.hitlog.jsonl
  mock_runs/                      # Mock outputs
    ort-rdash.report.jsonl
    ort-rdash.hitlog.jsonl
    ort_intent_mapping.json
    ort_stubs.jsonl
```

ORT source data remains in `runs/rdash-nhs-gemma-4-26b-a4b-it-g12/` — not copied.

---

## Dependencies

- Python 3.12+
- `pyyaml` — for reading Refiner YAML outputs
- `jinja2` — for HTML template rendering
- No garak dependency — the mock reads/writes JSONL directly
- Vega-Lite CDN (embedded in HTML, same as existing ART report)

---

## Success Criteria

1. `mock_ort_garak_data.py` produces a valid `report.jsonl` that the existing `generate_art_report()` can still render (backward compat — the new fields are additive)
2. `generate_ort_report.py` produces an HTML report with all four new sections populated from real RDaSH data
3. The provenance trail is end-to-end traceable: from an attempt's `notes.stub.id` through the stubs file to the adversarial prompt's `risk_id`, `technique`, `sampled_axes`, and `decomposition`
4. The cross-framework coverage matrix shows all 83 RDaSH cross-mappings across the 8 tested risks
