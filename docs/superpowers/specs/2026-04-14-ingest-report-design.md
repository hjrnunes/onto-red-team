# Ingest Report — Design Spec

**Date:** 2026-04-14
**Status:** Approved

## Purpose

The ingest stage produces a `PolicyDocument` JSON — a machine artifact consumed by downstream pipeline stages and other tools. This spec adds a companion HTML report — a human artifact for stakeholder validation. The report renders the same extraction data in a form that a governance team can review, annotate, and push back on: "here's what we understood from your policy document, does this match your intent?"

This is the first step toward extracting ingest as a standalone tool. The report ships inside the existing `refiner/` package; extraction into a separate package is a later concern.

## Design Decisions

- **Latest schema is canonical.** The `PolicyDocument` model with AIRO-envelope structure (Stakeholder objects with roles, GovernedSystem entries, RegulatoryReference entries) is the output contract. Older flat-field outputs are legacy.
- **Confidence signals.** The report surfaces quality indicators per field (green/amber/red) computed from simple rules, not LLM-generated.
- **Lewis et al. framing.** Stakeholders are grouped by the Entity/Activity/Agent categories from Lewis et al. 2021 (BFO + PROV-O). Policy decompositions are rendered as Agent → Activity → Entity flows. No AIMS activity extraction — just presentation framing.
- **HTML report.** Self-contained HTML using Tailwind CDN + Alpine.js, same pattern as `evaluation_report_template.html`. Data injected via `__REPORT_DATA__` replacement.
- **Always generated.** No opt-out flag. The report is a side effect of `refiner ingest`, written alongside the JSON.

## Data Payload

A `build_report_data()` function combines three inputs into a single JSON blob for template injection:

**Inputs:**
- `result: PolicyDocument` — the enriched document
- `report: RunReport` — the event log (has `context_weak_inference`, `enrichment_stats`, `input_format_detected`)
- `meta: dict` — model name, source document filename, timestamp

**Output structure:**

```json
{
  "meta": {
    "model": "gemma-4-26b-a4b-it",
    "source_document": "rdash-nhs.md",
    "timestamp": "2026-04-14T16:52:00Z",
    "input_format": "markdown",
    "passes_completed": ["context", "policies", "enrichment"]
  },
  "document": { "..." },
  "confidence": {
    "context": {
      "organization": "green",
      "domain": "green",
      "purpose": "green",
      "governed_systems": "green",
      "stakeholders": "green",
      "regulations": "amber"
    },
    "policies": [
      {
        "policy_concept": "Clinical Decision-Making and Care Planning",
        "boundary_examples": "green",
        "acceptable_uses": "green",
        "risk_controls": "green",
        "human_involvement": "green",
        "decomposition": "green"
      }
    ],
    "summary": {
      "policies_enriched": 5,
      "policies_total": 5,
      "boundary_pairs_total": 6,
      "policies_with_zero_pairs": 0,
      "weak_inferences": []
    }
  }
}
```

### Confidence Rules

**Context-level fields:**
- **Green:** field present and non-empty
- **Amber:** field present but incomplete (e.g. regulations with no `jurisdiction` or `reference`; stakeholders present but none with governance roles)
- **Red:** field missing or empty

**Per-policy fields:**
- `boundary_examples`: green if >= 1 pair, red if 0
- `acceptable_uses`: green if >= 1, amber if 0
- `risk_controls`: green if >= 1, amber if 0
- `human_involvement`: green if non-empty string, amber if empty/null
- `decomposition`: green if all 3 fields present (agent, activity, entity), amber if 1-2 present, red if missing entirely

## HTML Template Structure

Five sections, all rendered client-side by Alpine.js from the injected data blob.

### 1. Header

Dark bar with organisation name, domain, model, timestamp. Same visual weight as the evaluation report header.

### 2. Context Summary

Grid of cards, each with a confidence dot (green/amber/red circle):
- Organisation name + domain
- Purpose (list of AI use purposes)
- Governed Systems (named AI tools)
- Regulations (flagged amber/red if missing jurisdiction or reference URIs)

### 3. Stakeholders (Lewis et al. framing)

Stakeholders grouped into categories derived from Lewis et al. 2021 Agent subclasses:
- **Organisation** — the entity whose policy is being analysed
- **Governance** — stakeholders with governance/oversight roles (e.g. Caldicott Guardian, Clinical Safety Officer, DPO, SIRO). These map to the `directedBy`/`monitoredBy` governance relationships.
- **Users** — stakeholders with `airo:AIUser` role
- **Subjects** — stakeholders with `airo:AISubject` role

Each group is a card. Roles shown as small tags. This is where the Lewis et al. framing lives — the report shows governance structure, not a flat list.

**Grouping logic:** role string matching:
- `airo:AIUser` → Users
- `airo:AISubject` → Subjects
- Organisation stakeholder → Organisation
- Everything else → Governance

### 4. Policies

One expandable card per policy (Alpine.js `x-show` toggle). All expanded by default, collapsible for long documents.

Each card contains:
- **Header row:** concept name + confidence dots for each sub-field
- **Definition:** the full `concept_definition` text
- **Boundary Examples:** two-column table (Prohibited | Acceptable)
- **Acceptable Uses:** bulleted list
- **Risk Controls:** bulleted list
- **Human Involvement:** highlighted callout box (governance-relevant, deserves visual weight)
- **Decomposition:** rendered as `Agent → Activity → Entity` horizontal flow with the actual values (e.g. `clinician → diagnose and treat → patient care`)

### 5. Coverage Summary

Bottom section with aggregate stats:
- Policies extracted / enriched count
- Total boundary pairs
- Policies with zero boundary pairs (flagged red)
- Weak inferences (context fields the LLM couldn't populate)
- Pass completion status (context / policies / enrichment)

## File Layout

```
refiner/src/refiner/
  ingest_report.py                  # build_report_data() + build_ingest_report()
  ingest_report_template.html       # self-contained HTML template
```

## Integration

### `ingest_report.py`

Two functions:

```python
def build_report_data(
    doc: PolicyDocument,
    report: RunReport,
    meta: dict,
) -> dict:
    """Combine PolicyDocument + RunReport events into report payload."""

def build_ingest_report(
    doc: PolicyDocument,
    report: RunReport,
    output_path: Path,
    meta: dict,
) -> Path:
    """Build self-contained HTML report. Returns path to written file."""
```

### CLI change (`cli.py`)

After writing the enriched JSON (line ~94), add:

```python
from refiner.ingest_report import build_ingest_report
passes = ["context"]
if not until or until != "context":
    passes.append("policies")
if not until and not skip_enrichment:
    passes.append("enrichment")
meta = {"model": config.model, "source_document": document.name,
        "timestamp": report.timestamp, "input_format": input_format,
        "passes_completed": passes}
report_path = build_ingest_report(result, report, out_path.with_suffix(".html"), meta)
typer.echo(f"Ingest report written to {report_path}")
```

### Battery script

No changes. The report appears as a side effect of `refiner ingest`. The HTML file lands next to the enriched JSON in the run directory.

## Testing

- **Unit tests for `build_report_data()`:** given a PolicyDocument and RunReport with known events, assert confidence signals are correct (green/amber/red for each field)
- **Snapshot test:** generate the HTML for the RDaSH enriched JSON, check it's valid HTML with `__REPORT_DATA__` replaced by valid JSON
- **Stakeholder grouping test:** verify the Lewis et al. grouping logic correctly categorises stakeholders by role
