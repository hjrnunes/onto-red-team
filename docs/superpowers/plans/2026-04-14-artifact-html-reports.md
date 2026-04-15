# Artifact HTML Reports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add self-contained HTML reports for the 5 pipeline artifacts that currently lack them: Risk Landscape, Domain Context Document, Taxonomy, Run Report, and Dataset.

**Architecture:** Each report follows the existing pattern: a self-contained HTML template (Tailwind CSS + Alpine.js) with a `__REPORT_DATA__` placeholder, and a thin Python builder function that assembles the data dict, reads the template, substitutes, and writes. The CLI commands and battery script already write the YAML/JSON artifacts; we add an HTML write immediately after each one. No new dependencies.

**Tech Stack:** HTML (Tailwind CDN + Alpine.js CDN), Python (json, yaml, pathlib)

---

## File Structure

```
refiner/src/refiner/
  risk_landscape_report_template.html     # NEW — Risk Landscape HTML template
  domain_context_report_template.html     # NEW — Domain Context Document HTML template
  taxonomy_report_template.html           # NEW — Taxonomy HTML template
  run_report_template.html                # NEW — Run Report HTML template
  dataset_report_template.html            # NEW — Dataset HTML template
  artifact_reports.py                     # NEW — Builder functions for all 5 reports
  cli.py                                 # MODIFY — Call builders after writing artifacts
  tracking.py                            # MODIFY — Add new HTML patterns to _ARTIFACT_PATTERNS

refiner/tests/
  test_artifact_reports.py               # NEW — Tests for builder functions

scripts/
  run_battery.py                         # No changes needed — CLI handles HTML generation
```

## Template Convention

All templates follow the established pattern from `ingest_report_template.html` and `evaluation_report_template.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>REPORT_TITLE</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script defer src="https://unpkg.com/alpinejs@3.x.x/dist/cdn.min.js"></script>
  <style>[x-cloak] { display: none !important; }</style>
</head>
<body class="bg-gray-100 min-h-screen" x-data="reportApp()" x-cloak>
  <header class="bg-gray-900 text-white px-6 py-4 shadow-lg">
    <div class="max-w-screen-xl mx-auto">
      <h1 class="text-2xl font-bold tracking-tight">TITLE</h1>
      <p class="text-gray-400 text-sm mt-0.5">SUBTITLE</p>
    </div>
  </header>
  <div class="max-w-screen-xl mx-auto p-6 space-y-6">
    <!-- sections -->
  </div>
<script>
const DATA = __REPORT_DATA__;
function reportApp() { return { data: DATA }; }
</script>
</body>
</html>
```

---

### Task 1: artifact_reports.py — Builder module with all 5 builder functions

**Files:**
- Create: `refiner/src/refiner/artifact_reports.py`
- Test: `refiner/tests/test_artifact_reports.py`

- [ ] **Step 1: Write failing tests for all 5 builder functions**

```python
# refiner/tests/test_artifact_reports.py
import json
from pathlib import Path

import yaml

from refiner.artifact_reports import (
    build_risk_landscape_report,
    build_domain_context_report,
    build_taxonomy_report,
    build_run_report_html,
    build_dataset_report,
)


def test_build_risk_landscape_report(tmp_path):
    data = {
        "version": "0.1",
        "model": "test-model",
        "run_slug": "swb",
        "selected_domains": ["CCO", "FIBO"],
        "risks": [
            {"risk_id": "atlas-r1", "risk_name": "R1", "risk_framework": "IBM Risk Atlas",
             "cross_mappings": [{"id": "nist-r1", "mapping_type": "broad"}],
             "related_actions": ["action1"]},
        ],
        "policy_mappings": [
            {"policy_concept": "Fraud", "matched_risks": [
                {"risk_id": "atlas-r1", "risk_name": "R1", "relevance": "primary",
                 "justification": "j", "match_distance": 0.3}
            ]},
        ],
        "framework_coverage": {"IBM Risk Atlas": 1},
        "weak_matches": [],
    }
    out = tmp_path / "swb-risk-landscape.html"
    build_risk_landscape_report(data, out)
    assert out.exists()
    html = out.read_text()
    assert "Risk Landscape" in html
    assert "__REPORT_DATA__" not in html
    assert "atlas-r1" in html or "REPORT_DATA" not in html  # data is embedded


def test_build_domain_context_report(tmp_path):
    data = {
        "version": "0.1",
        "model": "test-model",
        "run_slug": "swb",
        "selected_domains": ["CCO"],
        "risks": [
            {"risk_id": "atlas-r1", "risk_name": "R1", "risk_framework": "IBM Risk Atlas",
             "cross_mappings": []},
        ],
        "policy_contexts": [
            {"policy_concept": "Fraud", "risk_groundings": [
                {"risk_id": "atlas-r1", "axes": [
                    {"cco_class_label": "Person", "cco_class_uri": "http://ex/Person",
                     "bfo_category": "Object", "roles": ["agent"],
                     "enumerations": [
                         {"class_label": "Employee", "source_ontology": "CCO",
                          "relevance": "high", "provenance": "subclass"},
                     ]},
                ]},
            ]},
        ],
    }
    out = tmp_path / "swb-domain-context.html"
    build_domain_context_report(data, out)
    assert out.exists()
    html = out.read_text()
    assert "Domain Context" in html
    assert "__REPORT_DATA__" not in html


def test_build_taxonomy_report(tmp_path):
    data = {
        "taxonomies": [{"id": "client-swb", "name": "Client SWB", "type": "RiskTaxonomy"}],
        "groups": [{"id": "g1", "name": "Fraud", "type": "RiskGroup", "isDefinedByTaxonomy": "client-swb"}],
        "entries": [
            {"id": "e1", "name": "Risk One", "type": "Risk", "isDefinedByTaxonomy": "client-swb",
             "broad_mappings": ["nist-r1"],
             "domain_context_summary": {"axis_count": 2, "enumeration_count": 5}},
        ],
        "curie_map": {"airo": "https://w3id.org/airo#"},
    }
    out = tmp_path / "swb-taxonomy.html"
    build_taxonomy_report(data, out)
    assert out.exists()
    html = out.read_text()
    assert "Taxonomy" in html
    assert "__REPORT_DATA__" not in html


def test_build_run_report_html(tmp_path):
    data = {
        "model": "gemma-3-12b-it",
        "policy_set": "swb-policy-document.json",
        "timestamp": "2026-04-14T20:00:00Z",
        "stages_completed": ["identify_domains", "map_risks", "anchor", "contextualize", "structure"],
        "events": [
            {"stage": "map_risks", "event": "match_count", "policy_concept": "Fraud", "count": 3},
            {"stage": "map_risks", "event": "weak_match", "risk_id": "atlas-r1", "distance": 0.72},
        ],
        "token_usage": {"prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500, "calls": 10},
    }
    out = tmp_path / "swb-run-report.html"
    build_run_report_html(data, out)
    assert out.exists()
    html = out.read_text()
    assert "Run Report" in html
    assert "__REPORT_DATA__" not in html


def test_build_dataset_report(tmp_path):
    rows = [
        {"policy_concept": "Fraud", "risk_id": "atlas-r1", "risk_name": "R1",
         "technique": "pretexting", "risk_framework": "IBM Risk Atlas",
         "sampled_axes": [
             {"cco_class_label": "Person", "sampled_label": "Employee",
              "source_ontology": "CCO", "relevance": "high", "roles": ["agent"]},
         ]},
        {"policy_concept": "Fraud", "risk_id": "atlas-r1", "risk_name": "R1",
         "technique": "analytical_reframing", "risk_framework": "IBM Risk Atlas",
         "sampled_axes": [
             {"cco_class_label": "Person", "sampled_label": "Manager",
              "source_ontology": "CCO", "relevance": "medium", "roles": ["agent"]},
         ]},
    ]
    out = tmp_path / "swb-dataset.html"
    build_dataset_report(rows, out)
    assert out.exists()
    html = out.read_text()
    assert "Dataset" in html
    assert "__REPORT_DATA__" not in html
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd refiner && uv run pytest tests/test_artifact_reports.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'refiner.artifact_reports'`

- [ ] **Step 3: Create artifact_reports.py with all 5 builders**

```python
# refiner/src/refiner/artifact_reports.py
"""HTML report builders for pipeline artifacts."""

import json
from collections import Counter
from pathlib import Path


def _render(template_name: str, data: dict | list, output_path: Path) -> Path:
    """Load template, substitute __REPORT_DATA__, write HTML."""
    template_path = Path(__file__).parent / template_name
    html = template_path.read_text().replace(
        "__REPORT_DATA__", json.dumps(data, default=str)
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html)
    return output_path


def build_risk_landscape_report(data: dict, output_path: Path) -> Path:
    """Build HTML report for a RiskLandscape YAML artifact."""
    return _render("risk_landscape_report_template.html", data, output_path)


def build_domain_context_report(data: dict, output_path: Path) -> Path:
    """Build HTML report for a DomainContextDocument YAML artifact."""
    return _render("domain_context_report_template.html", data, output_path)


def build_taxonomy_report(data: dict, output_path: Path) -> Path:
    """Build HTML report for a taxonomy YAML artifact."""
    return _render("taxonomy_report_template.html", data, output_path)


def build_run_report_html(data: dict, output_path: Path) -> Path:
    """Build HTML report for a run-report YAML artifact."""
    return _render("run_report_template.html", data, output_path)


def build_dataset_report(rows: list[dict], output_path: Path) -> Path:
    """Build HTML report for a dataset JSONL artifact.

    Computes summary statistics from the rows and embeds both
    the stats and the full row data into the template.
    """
    policies = Counter(r.get("policy_concept", "") for r in rows)
    techniques = Counter(r.get("technique", "") for r in rows)
    risks = Counter(r.get("risk_id", "") for r in rows)
    frameworks = Counter(r.get("risk_framework", "") for r in rows)

    all_axes = []
    for r in rows:
        for ax in r.get("sampled_axes", []):
            all_axes.append(ax)
    ontologies = Counter(ax.get("source_ontology", "") for ax in all_axes)
    roles = Counter(role for ax in all_axes for role in ax.get("roles", []))
    relevance = Counter(ax.get("relevance", "") for ax in all_axes)

    report_data = {
        "summary": {
            "total_rows": len(rows),
            "policies": dict(policies.most_common()),
            "techniques": dict(techniques.most_common()),
            "risks": dict(risks.most_common()),
            "frameworks": dict(frameworks.most_common()),
            "ontologies": dict(ontologies.most_common()),
            "roles": dict(roles.most_common()),
            "relevance": dict(relevance.most_common()),
        },
        "rows": rows,
    }
    return _render("dataset_report_template.html", report_data, output_path)
```

- [ ] **Step 4: Run tests to verify they fail (templates missing)**

Run: `cd refiner && uv run pytest tests/test_artifact_reports.py -v`
Expected: FAIL with `FileNotFoundError` (templates don't exist yet)

- [ ] **Step 5: Commit builder module and tests**

```bash
git add refiner/src/refiner/artifact_reports.py refiner/tests/test_artifact_reports.py
git commit -m "feat: add artifact_reports.py with 5 builder functions + tests"
```

---

### Task 2: Risk Landscape HTML template

**Files:**
- Create: `refiner/src/refiner/risk_landscape_report_template.html`

This report shows the RiskLandscape artifact contents: header metadata, risk registry with framework labels and cross-mappings, policy mappings with distances, framework coverage summary, and weak matches.

**Sections:**
1. **Header** — model, timestamp, run_slug, policy_source (org, domain, count)
2. **Overview cards** — total risks, domains selected, framework count
3. **Framework Coverage** — bar-style counts per framework
4. **Risk Registry** — collapsible list of all risks with framework badge, description, cross-mappings, related actions
5. **Policy Mappings** — per-policy table showing matched risks with relevance, justification, distance
6. **Weak Matches** — amber-highlighted list of high-distance matches

- [ ] **Step 1: Create the template**

Create `refiner/src/refiner/risk_landscape_report_template.html` — full self-contained Alpine.js + Tailwind HTML template that reads from `__REPORT_DATA__` and renders all 6 sections above. Follow the style conventions of `evaluation_report_template.html` (dark header, white cards with rounded-xl, gray-200 borders, indigo/green/amber/red accent colors, tip tooltips).

The data shape matches the RiskLandscape Pydantic model serialized to dict:
```json
{
  "version": "0.1",
  "model": "gemma-4-26b-a4b-it",
  "timestamp": "2026-04-14T...",
  "run_slug": "swb",
  "selected_domains": ["CCO", "Commons", "FIBO"],
  "policy_source": {"organization": "South West Bank", "domain": "banking", "policy_count": 6},
  "risks": [
    {"risk_id": "atlas-r1", "risk_name": "Risk One", "risk_description": "...", "risk_concern": "...",
     "risk_framework": "IBM Risk Atlas",
     "cross_mappings": [{"id": "nist-r1", "mapping_type": "broad"}],
     "related_actions": ["action1"]}
  ],
  "policy_mappings": [
    {"policy_concept": "Fraud", "matched_risks": [
      {"risk_id": "atlas-r1", "risk_name": "Risk One", "relevance": "primary",
       "justification": "Direct fraud risk", "match_distance": 0.234}
    ]}
  ],
  "framework_coverage": {"IBM Risk Atlas": 5, "NIST AI RMF": 3},
  "weak_matches": [{"risk_id": "atlas-r2", "policy_concept": "Safety", "distance": 0.72}]
}
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd refiner && uv run pytest tests/test_artifact_reports.py::test_build_risk_landscape_report -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add refiner/src/refiner/risk_landscape_report_template.html
git commit -m "feat: add risk landscape HTML report template"
```

---

### Task 3: Domain Context Document HTML template

**Files:**
- Create: `refiner/src/refiner/domain_context_report_template.html`

This report shows the DomainContextDocument: the grounded ontology axes and enumerations for each policy-risk combination.

**Sections:**
1. **Header** — model, timestamp, run_slug, policy_source
2. **Overview cards** — total risks, total policies, total axes, total enumerations, domains
3. **Risks Summary** — table of risk_id, risk_name, framework badge, cross-mapping count
4. **Policy Contexts** — collapsible per-policy sections, each containing:
   - Per-risk groundings with axes
   - Per-axis: class label, BFO category badge, roles badges, vocabulary context
   - Enumerations table: label, source ontology, relevance badge, provenance badge
   - Derivation info: source, seed URI, path, confidence, domain

The data shape matches `DomainContextDocument.model_dump()`:
```json
{
  "version": "0.1",
  "model": "...",
  "timestamp": "...",
  "run_slug": "swb",
  "selected_domains": ["CCO", "FIBO"],
  "policy_source": {...},
  "risks": [{"risk_id": "...", "risk_name": "...", "risk_framework": "...", "cross_mappings": [...]}],
  "policy_contexts": [
    {"policy_concept": "Fraud", "risk_groundings": [
      {"risk_id": "atlas-r1", "axes": [
        {"cco_class_label": "Person", "cco_class_uri": "http://...",
         "bfo_category": "Object", "roles": ["agent"],
         "vocabulary_concept": "eu-aiact:AISubject",
         "vocabulary_label": "AI Subject",
         "vocabulary_context": {"stakeholders": [...]},
         "derivation": {"source": "structural", "seed_uri": "...", "path": [...], "effective_confidence": 0.9, "domain": "CCO"},
         "enumerations": [
           {"class_label": "Employee", "class_uri": "http://...", "source_ontology": "CCO", "relevance": "high", "provenance": "subclass"}
         ]}
      ]}
    ]}
  ]
}
```

- [ ] **Step 1: Create the template**

Create `refiner/src/refiner/domain_context_report_template.html` with all sections described above.

- [ ] **Step 2: Run tests**

Run: `cd refiner && uv run pytest tests/test_artifact_reports.py::test_build_domain_context_report -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add refiner/src/refiner/domain_context_report_template.html
git commit -m "feat: add domain context document HTML report template"
```

---

### Task 4: Taxonomy HTML template

**Files:**
- Create: `refiner/src/refiner/taxonomy_report_template.html`

This report shows the LinkML-conformant taxonomy: CURIE map, taxonomy definitions, risk groups, and risk entries with cross-mappings and domain context summaries.

**Sections:**
1. **Header** — taxonomy name, entry count
2. **Overview cards** — taxonomies count, groups count, entries count, CURIE prefixes count
3. **CURIE Map** — collapsible table of prefix → URI
4. **Groups** — collapsible list grouped by taxonomy, showing group name and type
5. **Entries** — collapsible list of risk entries, each showing:
   - Name, type, tag
   - Defined by taxonomy (badge)
   - Cross-mappings: broad, related, exact, narrow (badges with mapping type)
   - Domain context summary: axis_count, enumeration_count, source_ontologies, per-axis details

The data shape matches `taxonomy.yaml` loaded as dict:
```json
{
  "curie_map": {"airo": "https://w3id.org/airo#", ...},
  "taxonomies": [{"id": "client-swb", "name": "Client SWB Policy Taxonomy", "type": "RiskTaxonomy"}],
  "groups": [{"id": "g1", "name": "Fraud", "type": "RiskGroup", "isDefinedByTaxonomy": "client-swb"}],
  "entries": [
    {"id": "e1", "name": "Risk One", "type": "Risk", "tag": "risk-one",
     "isDefinedByTaxonomy": "client-swb",
     "broad_mappings": ["nist-r1"], "related_mappings": ["owasp-r2"],
     "domain_context_summary": {
       "axis_count": 2, "enumeration_count": 7,
       "source_ontologies": ["CCO", "FIBO"],
       "axes": [{"class": "Person", "uri": "http://...", "roles": ["agent"], "enumeration_count": 4}]
     }}
  ]
}
```

- [ ] **Step 1: Create the template**

Create `refiner/src/refiner/taxonomy_report_template.html` with all sections.

- [ ] **Step 2: Run tests**

Run: `cd refiner && uv run pytest tests/test_artifact_reports.py::test_build_taxonomy_report -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add refiner/src/refiner/taxonomy_report_template.html
git commit -m "feat: add taxonomy HTML report template"
```

---

### Task 5: Run Report HTML template

**Files:**
- Create: `refiner/src/refiner/run_report_template.html`

This report visualizes the pipeline execution events from `run-report.yaml`.

**Sections:**
1. **Header** — model, policy_set, timestamp
2. **Overview** — model, policy set, stages completed (as pipeline flow badges), token usage summary
3. **Token Usage** — prompt/completion/total tokens, call count (if present)
4. **Pipeline Events** — grouped by stage, each stage collapsible:
   - `identify_domains`: selected_domains list
   - `map_risks`: match_count per policy, weak_match list, invalid indices
   - `anchor`: candidate_tiers per risk (seeds/structural/search/merged counts), domain_filtered, role_derivation, cache_hits
   - `contextualize`: sibling_fallbacks, empty_enumerations, self_references_filtered, disjoint_filtered
   - `structure`: cross_mappings_filtered

The data shape matches `run-report.yaml`:
```json
{
  "model": "gemma-4-26b-a4b-it",
  "policy_set": "swb-policy-document.json",
  "timestamp": "2026-04-14T...",
  "stages_completed": ["identify_domains", "map_risks", "anchor", "contextualize", "structure"],
  "events": [
    {"stage": "identify_domains", "event": "selected_domains", "domains": ["CCO", "FIBO"]},
    {"stage": "map_risks", "event": "match_count", "policy_concept": "Fraud", "count": 3},
    {"stage": "map_risks", "event": "weak_match", "risk_id": "atlas-r1", "distance": 0.72},
    {"stage": "anchor", "event": "candidate_tiers", "risk_id": "atlas-r1", "seeds": 5, "structural": 40, "search_connected": 6, "search_only": 12, "merged": 10}
  ],
  "token_usage": {"prompt_tokens": 5000, "completion_tokens": 2000, "total_tokens": 7000, "calls": 25}
}
```

- [ ] **Step 1: Create the template**

Create `refiner/src/refiner/run_report_template.html` with all sections.

- [ ] **Step 2: Run tests**

Run: `cd refiner && uv run pytest tests/test_artifact_reports.py::test_build_run_report_html -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add refiner/src/refiner/run_report_template.html
git commit -m "feat: add run report HTML template"
```

---

### Task 6: Dataset HTML template

**Files:**
- Create: `refiner/src/refiner/dataset_report_template.html`

This report visualizes the emit dataset: distribution summaries and a browsable prompt table.

**Sections:**
1. **Header** — total rows
2. **Overview cards** — total rows, unique policies, unique risks, unique techniques
3. **Distribution cards**:
   - Policies: count per policy_concept
   - Techniques: count per adversarial technique
   - Risks: count per risk_id
   - Frameworks: count per risk_framework
   - Ontologies: count per source_ontology from sampled_axes
   - Roles: count per role from sampled_axes
   - Relevance: count per relevance from sampled_axes
4. **Prompt Browser** — filterable, paginated table of rows showing: policy, risk, technique, sampled axes labels, generation_prompt preview (expandable)

The data shape is built by `build_dataset_report()`:
```json
{
  "summary": {
    "total_rows": 90,
    "policies": {"Fraud": 15, "Safety": 15, ...},
    "techniques": {"pretexting": 20, "analytical_reframing": 25, ...},
    "risks": {"atlas-r1": 15, ...},
    "frameworks": {"IBM Risk Atlas": 30, ...},
    "ontologies": {"CCO": 50, "FIBO": 20, ...},
    "roles": {"agent": 40, "object": 30, ...},
    "relevance": {"high": 60, "medium": 20, "low": 10}
  },
  "rows": [
    {"policy_concept": "Fraud", "risk_id": "atlas-r1", "technique": "pretexting",
     "risk_framework": "IBM Risk Atlas",
     "generation_prompt": [...],
     "sampled_axes": [...]}
  ]
}
```

- [ ] **Step 1: Create the template**

Create `refiner/src/refiner/dataset_report_template.html` with all sections. Include Alpine.js client-side filtering by policy, risk, and technique. Paginate the prompt browser at 25 rows per page.

- [ ] **Step 2: Run tests**

Run: `cd refiner && uv run pytest tests/test_artifact_reports.py::test_build_dataset_report -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add refiner/src/refiner/dataset_report_template.html
git commit -m "feat: add dataset HTML report template"
```

---

### Task 7: Wire builders into CLI

**Files:**
- Modify: `refiner/src/refiner/cli.py`
- Modify: `refiner/tests/test_cli.py`

Add HTML generation calls after each artifact write in the CLI. The CLI already writes the YAML/JSON artifacts; we add one line after each to generate the corresponding HTML.

- [ ] **Step 1: Add test for HTML report generation in full pipeline**

In `refiner/tests/test_cli.py`, update `test_cli_run_enriched_format` to verify HTML reports are generated alongside YAML:

```python
# Add at end of test_cli_run_enriched_format:
    # Verify HTML reports generated
    assert (tmp_path / "enriched-risk-landscape.html").exists()
    assert (tmp_path / "enriched-domain-context.html").exists()
    assert (tmp_path / "enriched-taxonomy.html").exists()
    assert (tmp_path / "enriched-run-report.html").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd refiner && uv run pytest tests/test_cli.py::test_cli_run_enriched_format -v`
Expected: FAIL (HTML files don't exist)

- [ ] **Step 3: Wire builders into cli.py `run` command**

In `refiner/src/refiner/cli.py`, after each artifact write, add the HTML builder call. The changes go in the `run` command's output section (around lines 300-370):

After writing risk landscape YAML (~line 328-330):
```python
                from refiner.artifact_reports import build_risk_landscape_report
                build_risk_landscape_report(
                    state.risk_landscape.model_dump(),
                    out / f"{client_slug}-risk-landscape.html",
                )
```

After writing taxonomy YAML (~line 333-334):
```python
                from refiner.artifact_reports import build_taxonomy_report
                build_taxonomy_report(taxonomy, out / f"{client_slug}-taxonomy.html")
```

After writing domain context YAML (~line 337-339):
```python
                from refiner.artifact_reports import build_domain_context_report
                build_domain_context_report(
                    doc.model_dump(),
                    out / f"{client_slug}-domain-context.html",
                )
```

After writing run report YAML (~line 342-343):
```python
                from refiner.artifact_reports import build_run_report_html
                build_run_report_html(report.to_dict(), out / f"{client_slug}-run-report.html")
```

- [ ] **Step 4: Wire builders into cli.py `map-risks` command**

After the risk landscape YAML write (~line 473-477):
```python
    from refiner.artifact_reports import build_risk_landscape_report
    build_risk_landscape_report(landscape.model_dump(), out / f"{client_slug}-risk-landscape.html")
```

After the run report YAML write (~line 480-482):
```python
    from refiner.artifact_reports import build_run_report_html
    build_run_report_html(report.to_dict(), out / f"{client_slug}-run-report.html")
```

- [ ] **Step 5: Wire builders into cli.py `ground` command**

After the DCD YAML write (~line 599-603):
```python
    from refiner.artifact_reports import build_domain_context_report
    build_domain_context_report(dcd.model_dump(), out / f"{client_slug}-domain-context.html")
```

After the taxonomy YAML write (~line 613-614):
```python
    from refiner.artifact_reports import build_taxonomy_report
    build_taxonomy_report(taxonomy, out / f"{client_slug}-taxonomy.html")
```

After the run report YAML write (~line 617-618):
```python
    from refiner.artifact_reports import build_run_report_html
    build_run_report_html(report.to_dict(), out / f"{client_slug}-run-report.html")
```

- [ ] **Step 6: Wire dataset report into cli.py `emit` command**

After the emit call (~line 665-667):
```python
    # Build dataset HTML report
    rows = [json.loads(line) for line in out_path.read_text().strip().split("\n") if line]
    from refiner.artifact_reports import build_dataset_report
    build_dataset_report(rows, out_path.with_suffix(".html"))
    typer.echo(f"Dataset report written to {out_path.with_suffix('.html')}")
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd refiner && uv run pytest tests/test_cli.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add refiner/src/refiner/cli.py refiner/tests/test_cli.py
git commit -m "feat: wire HTML report generation into CLI commands"
```

---

### Task 8: Update tracking patterns

**Files:**
- Modify: `refiner/src/refiner/tracking.py`
- Modify: `refiner/tests/test_tracking.py`

Add the 5 new HTML report patterns to `_ARTIFACT_PATTERNS` so MLflow picks them up.

- [ ] **Step 1: Update test to expect new patterns**

In `refiner/tests/test_tracking.py`, add the new HTML files to the test fixture that checks artifact collection:

```python
# In the test that creates artifact files, add:
    (tmp_path / "test-risk-landscape.html").write_text("<html></html>")
    (tmp_path / "test-domain-context.html").write_text("<html></html>")
    (tmp_path / "test-taxonomy.html").write_text("<html></html>")
    (tmp_path / "test-run-report.html").write_text("<html></html>")
    (tmp_path / "test-dataset.html").write_text("<html></html>")
```

And update the assertion count accordingly.

- [ ] **Step 2: Add patterns to tracking.py**

In `refiner/src/refiner/tracking.py`, add to `_ARTIFACT_PATTERNS`:
```python
    "*-risk-landscape.html",
    "*-domain-context.html",
    "*-taxonomy.html",
    "*-run-report.html",
    "*-dataset.html",
```

- [ ] **Step 3: Run tests**

Run: `cd refiner && uv run pytest tests/test_tracking.py -v`
Expected: PASS

- [ ] **Step 4: Run full test suite**

Run: `cd refiner && uv run pytest -x -q`
Expected: All ~395+ tests pass

- [ ] **Step 5: Commit**

```bash
git add refiner/src/refiner/tracking.py refiner/tests/test_tracking.py
git commit -m "feat: add HTML report patterns to MLflow artifact tracking"
```
