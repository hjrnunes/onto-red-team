# Ingest Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a stakeholder-facing HTML report generated alongside the enriched PolicyProfile JSON during `refiner ingest`.

**Architecture:** A new `ingest_report.py` module computes confidence signals from the PolicyProfile and RunReport events, then injects the data into a self-contained HTML template (Tailwind + Alpine.js). The CLI calls this after writing the JSON. No new dependencies.

**Tech Stack:** Python (Pydantic, Typer), HTML/JS (Tailwind CDN, Alpine.js)

**Spec:** `docs/superpowers/specs/2026-04-14-ingest-report-design.md`

---

### Task 1: Confidence computation — `build_report_data()`

**Files:**
- Create: `refiner/src/refiner/ingest_report.py`
- Test: `refiner/tests/test_ingest_report.py`

- [ ] **Step 1: Write test for context confidence — all green**

Create `refiner/tests/test_ingest_report.py`:

```python
"""Tests for ingest report data builder and confidence signals."""

import json

from refiner.ingest_report import build_report_data
from refiner.models import (
    BoundaryExample,
    GovernedSystem,
    Policy,
    PolicyDecomposition,
    PolicyProfile,
    RegulatoryReference,
    RunReport,
    Stakeholder,
)


def _make_meta(**overrides):
    base = {
        "model": "test-model",
        "source_document": "test.md",
        "timestamp": "2026-01-01T00:00:00Z",
        "input_format": "markdown",
        "passes_completed": ["context", "policies", "enrichment"],
    }
    base.update(overrides)
    return base


def _make_report(**overrides):
    base = {"model": "test-model", "policy_set": "test", "timestamp": "2026-01-01T00:00:00Z"}
    base.update(overrides)
    return RunReport(**base)


def _full_doc():
    """PolicyProfile with all fields populated — expect all green."""
    return PolicyProfile(
        organization=Stakeholder(name="Acme Corp"),
        domain="finance",
        purpose=["chatbot"],
        governed_systems=[GovernedSystem(name="ChatGPT")],
        stakeholders=[
            Stakeholder(name="staff", roles=["airo:AIUser"]),
            Stakeholder(name="customers", roles=["airo:AISubject"]),
            Stakeholder(name="DPO", roles=["data protection"]),
        ],
        regulations=[
            RegulatoryReference(name="GDPR", jurisdiction="EU", reference="https://gdpr.eu")
        ],
        policies=[
            Policy(
                policy_concept="Data Privacy",
                concept_definition="No PII disclosure",
                boundary_examples=[
                    BoundaryExample(prohibited="Share SSN", acceptable="Confirm last 4")
                ],
                acceptable_uses=["General info"],
                risk_controls=["PII filter"],
                human_involvement="Required",
                decomposition=PolicyDecomposition(
                    agent="staff", activity="disclose", entity="PII"
                ),
            )
        ],
    )


def test_context_confidence_all_green():
    doc = _full_doc()
    data = build_report_data(doc, _make_report(), _make_meta())
    ctx = data["confidence"]["context"]
    assert ctx["organization"] == "green"
    assert ctx["domain"] == "green"
    assert ctx["purpose"] == "green"
    assert ctx["governed_systems"] == "green"
    assert ctx["stakeholders"] == "green"
    assert ctx["regulations"] == "green"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd refiner && uv run pytest tests/test_ingest_report.py::test_context_confidence_all_green -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'refiner.ingest_report'`

- [ ] **Step 3: Write test for context confidence — missing and amber fields**

Append to `refiner/tests/test_ingest_report.py`:

```python
def test_context_confidence_missing_fields():
    doc = PolicyProfile()
    data = build_report_data(doc, _make_report(), _make_meta())
    ctx = data["confidence"]["context"]
    assert ctx["organization"] == "red"
    assert ctx["domain"] == "red"
    assert ctx["purpose"] == "red"
    assert ctx["governed_systems"] == "red"
    assert ctx["stakeholders"] == "red"
    assert ctx["regulations"] == "red"


def test_context_confidence_regulations_amber():
    """Regulations present but missing jurisdiction/reference → amber."""
    doc = PolicyProfile(
        organization=Stakeholder(name="Acme"),
        domain="finance",
        purpose=["chatbot"],
        governed_systems=[GovernedSystem(name="ChatGPT")],
        stakeholders=[Stakeholder(name="staff", roles=["airo:AIUser"])],
        regulations=[RegulatoryReference(name="GDPR")],  # no jurisdiction or reference
    )
    data = build_report_data(doc, _make_report(), _make_meta())
    assert data["confidence"]["context"]["regulations"] == "amber"


def test_context_confidence_stakeholders_amber():
    """Stakeholders present but none with governance roles → amber."""
    doc = PolicyProfile(
        organization=Stakeholder(name="Acme"),
        domain="finance",
        purpose=["chatbot"],
        governed_systems=[GovernedSystem(name="ChatGPT")],
        stakeholders=[
            Stakeholder(name="staff", roles=["airo:AIUser"]),
            Stakeholder(name="patients", roles=["airo:AISubject"]),
        ],
        regulations=[
            RegulatoryReference(name="GDPR", jurisdiction="EU", reference="https://gdpr.eu")
        ],
    )
    data = build_report_data(doc, _make_report(), _make_meta())
    assert data["confidence"]["context"]["stakeholders"] == "amber"
```

- [ ] **Step 4: Write test for per-policy confidence**

Append to `refiner/tests/test_ingest_report.py`:

```python
def test_policy_confidence_all_green():
    doc = _full_doc()
    data = build_report_data(doc, _make_report(), _make_meta())
    pc = data["confidence"]["policies"][0]
    assert pc["policy_concept"] == "Data Privacy"
    assert pc["boundary_examples"] == "green"
    assert pc["acceptable_uses"] == "green"
    assert pc["risk_controls"] == "green"
    assert pc["human_involvement"] == "green"
    assert pc["decomposition"] == "green"


def test_policy_confidence_minimal():
    """Policy with only concept + definition — everything red/amber."""
    doc = PolicyProfile(
        policies=[
            Policy(policy_concept="Fraud", concept_definition="About fraud")
        ]
    )
    data = build_report_data(doc, _make_report(), _make_meta())
    pc = data["confidence"]["policies"][0]
    assert pc["boundary_examples"] == "red"
    assert pc["acceptable_uses"] == "amber"
    assert pc["risk_controls"] == "amber"
    assert pc["human_involvement"] == "amber"
    assert pc["decomposition"] == "red"


def test_policy_confidence_partial_decomposition():
    """Decomposition with only 1 of 3 fields → amber."""
    doc = PolicyProfile(
        policies=[
            Policy(
                policy_concept="Test",
                concept_definition="Test",
                decomposition=PolicyDecomposition(agent="clinician"),
            )
        ]
    )
    data = build_report_data(doc, _make_report(), _make_meta())
    assert data["confidence"]["policies"][0]["decomposition"] == "amber"
```

- [ ] **Step 5: Write test for summary and meta**

Append to `refiner/tests/test_ingest_report.py`:

```python
def test_summary_counts():
    doc = PolicyProfile(
        policies=[
            Policy(
                policy_concept="P1",
                concept_definition="D1",
                boundary_examples=[
                    BoundaryExample(prohibited="x", acceptable="y"),
                    BoundaryExample(prohibited="a", acceptable="b"),
                ],
            ),
            Policy(policy_concept="P2", concept_definition="D2"),
        ]
    )
    data = build_report_data(doc, _make_report(), _make_meta())
    summary = data["confidence"]["summary"]
    assert summary["policies_total"] == 2
    assert summary["policies_enriched"] == 1
    assert summary["boundary_pairs_total"] == 2
    assert summary["policies_with_zero_pairs"] == 1


def test_summary_weak_inferences():
    report = _make_report()
    report.events.append({
        "stage": "ingest",
        "event": "context_weak_inference",
        "missing_fields": ["organization", "domain"],
    })
    doc = PolicyProfile()
    data = build_report_data(doc, report, _make_meta())
    assert data["confidence"]["summary"]["weak_inferences"] == ["organization", "domain"]


def test_meta_passthrough():
    meta = _make_meta(model="gemma-4", source_document="rdash.md")
    doc = PolicyProfile()
    data = build_report_data(doc, _make_report(), meta)
    assert data["meta"]["model"] == "gemma-4"
    assert data["meta"]["source_document"] == "rdash.md"


def test_document_included():
    doc = _full_doc()
    data = build_report_data(doc, _make_report(), _make_meta())
    assert data["document"]["domain"] == "finance"
    assert len(data["document"]["policies"]) == 1
```

- [ ] **Step 6: Implement `build_report_data()`**

Create `refiner/src/refiner/ingest_report.py`:

```python
"""Ingest report: confidence computation and HTML generation."""

import json
from pathlib import Path

from refiner.models import PolicyProfile, RunReport


_AIRO_ROLES = {"airo:AIUser", "airo:AISubject", "airo:AIProvider", "airo:AIDeployer"}


def _context_confidence(doc: PolicyProfile) -> dict:
    """Compute green/amber/red for each context-level field."""
    ctx = {}

    # Organization
    ctx["organization"] = "green" if doc.organization and doc.organization.name else "red"

    # Domain
    ctx["domain"] = "green" if doc.domain else "red"

    # Purpose
    ctx["purpose"] = "green" if doc.purpose else "red"

    # Governed systems
    ctx["governed_systems"] = "green" if doc.governed_systems else "red"

    # Stakeholders: green if any governance role, amber if only airo roles, red if empty
    if not doc.stakeholders:
        ctx["stakeholders"] = "red"
    else:
        has_governance = any(
            role not in _AIRO_ROLES
            for s in doc.stakeholders
            for role in s.roles
        )
        ctx["stakeholders"] = "green" if has_governance else "amber"

    # Regulations: green if all have jurisdiction or reference, amber if present but incomplete, red if empty
    if not doc.regulations:
        ctx["regulations"] = "red"
    else:
        all_complete = all(
            r.jurisdiction or r.reference for r in doc.regulations
        )
        ctx["regulations"] = "green" if all_complete else "amber"

    return ctx


def _policy_confidence(doc: PolicyProfile) -> list[dict]:
    """Compute green/amber/red for each per-policy field."""
    results = []
    for p in doc.policies:
        pc = {"policy_concept": p.policy_concept}

        # Boundary examples: green >= 1, red = 0
        pc["boundary_examples"] = "green" if p.boundary_examples else "red"

        # Acceptable uses: green >= 1, amber = 0
        pc["acceptable_uses"] = "green" if p.acceptable_uses else "amber"

        # Risk controls: green >= 1, amber = 0
        pc["risk_controls"] = "green" if p.risk_controls else "amber"

        # Human involvement: green if non-empty, amber if empty/None
        pc["human_involvement"] = "green" if p.human_involvement else "amber"

        # Decomposition: green if all 3, amber if 1-2, red if missing
        if p.decomposition is None:
            pc["decomposition"] = "red"
        else:
            filled = sum(1 for f in [p.decomposition.agent, p.decomposition.activity, p.decomposition.entity] if f)
            if filled == 3:
                pc["decomposition"] = "green"
            elif filled >= 1:
                pc["decomposition"] = "amber"
            else:
                pc["decomposition"] = "red"

        results.append(pc)
    return results


def _summary(doc: PolicyProfile, report: RunReport) -> dict:
    """Compute aggregate summary stats."""
    policies_enriched = sum(
        1 for p in doc.policies if p.boundary_examples or p.acceptable_uses or p.risk_controls
    )
    boundary_pairs_total = sum(len(p.boundary_examples) for p in doc.policies)
    policies_with_zero_pairs = sum(1 for p in doc.policies if not p.boundary_examples)

    # Extract weak inferences from report events
    weak_inferences = []
    for ev in report.events:
        if ev.get("event") == "context_weak_inference":
            weak_inferences.extend(ev.get("missing_fields", []))

    return {
        "policies_total": len(doc.policies),
        "policies_enriched": policies_enriched,
        "boundary_pairs_total": boundary_pairs_total,
        "policies_with_zero_pairs": policies_with_zero_pairs,
        "weak_inferences": weak_inferences,
    }


def build_report_data(
    doc: PolicyProfile,
    report: RunReport,
    meta: dict,
) -> dict:
    """Combine PolicyProfile + RunReport events into report payload."""
    return {
        "meta": meta,
        "document": doc.model_dump(),
        "confidence": {
            "context": _context_confidence(doc),
            "policies": _policy_confidence(doc),
            "summary": _summary(doc, report),
        },
    }
```

- [ ] **Step 7: Run all tests to verify they pass**

Run: `cd refiner && uv run pytest tests/test_ingest_report.py -v`
Expected: all 10 tests PASS

- [ ] **Step 8: Commit**

```bash
cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner
git add refiner/src/refiner/ingest_report.py refiner/tests/test_ingest_report.py
git commit -m "feat: add ingest report confidence computation (build_report_data)"
```

---

### Task 2: Stakeholder grouping logic

**Files:**
- Modify: `refiner/src/refiner/ingest_report.py`
- Modify: `refiner/tests/test_ingest_report.py`

- [ ] **Step 1: Write test for stakeholder grouping**

Append to `refiner/tests/test_ingest_report.py`:

```python
from refiner.ingest_report import group_stakeholders


def test_group_stakeholders_full():
    """Stakeholders are grouped by Lewis et al. categories."""
    doc = PolicyProfile(
        organization=Stakeholder(name="RDaSH"),
        stakeholders=[
            Stakeholder(name="staff", roles=["airo:AIUser"]),
            Stakeholder(name="volunteers", roles=["airo:AIUser"]),
            Stakeholder(name="patients", roles=["airo:AISubject"]),
            Stakeholder(name="DPO", roles=["data protection"]),
            Stakeholder(name="Caldicott Guardian", roles=["patient info oversight"]),
        ],
    )
    groups = group_stakeholders(doc)
    assert groups["organisation"] == {"name": "RDaSH"}
    assert len(groups["users"]) == 2
    assert groups["users"][0]["name"] == "staff"
    assert len(groups["subjects"]) == 1
    assert groups["subjects"][0]["name"] == "patients"
    assert len(groups["governance"]) == 2
    assert groups["governance"][0]["name"] == "DPO"


def test_group_stakeholders_empty():
    doc = PolicyProfile()
    groups = group_stakeholders(doc)
    assert groups["organisation"] is None
    assert groups["users"] == []
    assert groups["subjects"] == []
    assert groups["governance"] == []


def test_group_stakeholders_mixed_roles():
    """Stakeholder with both airo:AIUser and governance role goes to governance."""
    doc = PolicyProfile(
        stakeholders=[
            Stakeholder(name="Admin", roles=["airo:AIUser", "system admin"]),
        ],
    )
    groups = group_stakeholders(doc)
    assert len(groups["governance"]) == 1
    assert groups["users"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd refiner && uv run pytest tests/test_ingest_report.py::test_group_stakeholders_full -v`
Expected: FAIL with `ImportError: cannot import name 'group_stakeholders'`

- [ ] **Step 3: Implement `group_stakeholders()`**

Add to `refiner/src/refiner/ingest_report.py`, before `build_report_data()`:

```python
def group_stakeholders(doc: PolicyProfile) -> dict:
    """Group stakeholders into Lewis et al. 2021 categories.

    Returns dict with keys: organisation, governance, users, subjects.
    """
    result = {
        "organisation": {"name": doc.organization.name} if doc.organization and doc.organization.name else None,
        "governance": [],
        "users": [],
        "subjects": [],
    }

    for s in doc.stakeholders:
        roles_set = set(s.roles)
        # If any role is outside the standard AIRO set, it's governance
        non_airo = roles_set - _AIRO_ROLES
        if non_airo:
            result["governance"].append({"name": s.name, "roles": s.roles})
        elif "airo:AISubject" in roles_set:
            result["subjects"].append({"name": s.name, "roles": s.roles})
        elif "airo:AIUser" in roles_set:
            result["users"].append({"name": s.name, "roles": s.roles})

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd refiner && uv run pytest tests/test_ingest_report.py -v`
Expected: all 13 tests PASS

- [ ] **Step 5: Add stakeholder groups to report data**

In `build_report_data()`, add `"stakeholder_groups"` to the returned dict:

```python
def build_report_data(
    doc: PolicyProfile,
    report: RunReport,
    meta: dict,
) -> dict:
    """Combine PolicyProfile + RunReport events into report payload."""
    return {
        "meta": meta,
        "document": doc.model_dump(),
        "stakeholder_groups": group_stakeholders(doc),
        "confidence": {
            "context": _context_confidence(doc),
            "policies": _policy_confidence(doc),
            "summary": _summary(doc, report),
        },
    }
```

- [ ] **Step 6: Write test for stakeholder groups in report data**

Append to `refiner/tests/test_ingest_report.py`:

```python
def test_report_data_includes_stakeholder_groups():
    doc = _full_doc()
    data = build_report_data(doc, _make_report(), _make_meta())
    groups = data["stakeholder_groups"]
    assert groups["organisation"]["name"] == "Acme Corp"
    assert len(groups["users"]) == 1
    assert len(groups["subjects"]) == 1
    assert len(groups["governance"]) == 1
```

- [ ] **Step 7: Run tests to verify all pass**

Run: `cd refiner && uv run pytest tests/test_ingest_report.py -v`
Expected: all 14 tests PASS

- [ ] **Step 8: Commit**

```bash
cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner
git add refiner/src/refiner/ingest_report.py refiner/tests/test_ingest_report.py
git commit -m "feat: add Lewis et al. stakeholder grouping for ingest report"
```

---

### Task 3: HTML template

**Files:**
- Create: `refiner/src/refiner/ingest_report_template.html`

- [ ] **Step 1: Create the HTML template**

Create `refiner/src/refiner/ingest_report_template.html`. This is a self-contained HTML file using Tailwind CDN + Alpine.js, with `__REPORT_DATA__` as the data injection point. The template has 5 sections:

1. **Header** — dark bar with org, domain, model, timestamp
2. **Context Summary** — grid of cards with confidence dots
3. **Stakeholders** — grouped into Organisation / Governance / Users / Subjects
4. **Policies** — expandable cards with boundary examples table, lists, decomposition flow
5. **Coverage Summary** — aggregate stats

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Policy Ingest Report</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script defer src="https://unpkg.com/alpinejs@3.x.x/dist/cdn.min.js"></script>
  <style>
    [x-cloak] { display: none !important; }
    .dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; }
    .dot-green { background: #22c55e; }
    .dot-amber { background: #f59e0b; }
    .dot-red { background: #ef4444; }
    .flow-arrow { color: #9ca3af; font-size: 1.25rem; line-height: 1; }
  </style>
</head>
<body class="bg-gray-100 min-h-screen" x-data="reportApp()" x-cloak>

  <!-- 1. Header -->
  <header class="bg-gray-900 text-white px-6 py-4 shadow-lg">
    <div class="max-w-screen-xl mx-auto">
      <h1 class="text-2xl font-bold tracking-tight">Policy Ingest Report</h1>
      <p class="text-gray-400 text-sm mt-0.5">
        <span x-text="data.document?.organization?.name || 'Unknown Organisation'"></span>
        &mdash; <span x-text="data.document?.domain || '?'"></span>
        &mdash; <span x-text="data.meta?.model || '?'"></span>
        &mdash; <span x-text="data.meta?.timestamp || '?'"></span>
      </p>
    </div>
  </header>

  <div class="max-w-screen-xl mx-auto p-6 space-y-6">

    <!-- 2. Context Summary -->
    <section class="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
      <h2 class="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">Context Summary</h2>
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">

        <!-- Organisation & Domain -->
        <div class="border border-gray-200 rounded-lg p-4">
          <div class="flex items-center gap-2 mb-2">
            <span class="dot" :class="'dot-' + data.confidence?.context?.organization"></span>
            <h3 class="text-sm font-semibold text-gray-700">Organisation</h3>
          </div>
          <p class="text-gray-800 font-medium" x-text="data.document?.organization?.name || 'Not identified'"></p>
          <div class="flex items-center gap-2 mt-3">
            <span class="dot" :class="'dot-' + data.confidence?.context?.domain"></span>
            <span class="text-xs text-gray-400 uppercase">Domain</span>
          </div>
          <p class="text-gray-700 text-sm" x-text="data.document?.domain || 'Not identified'"></p>
        </div>

        <!-- Purpose -->
        <div class="border border-gray-200 rounded-lg p-4">
          <div class="flex items-center gap-2 mb-2">
            <span class="dot" :class="'dot-' + data.confidence?.context?.purpose"></span>
            <h3 class="text-sm font-semibold text-gray-700">Purpose</h3>
          </div>
          <ul class="text-sm text-gray-700 space-y-1">
            <template x-for="p in data.document?.purpose || []" :key="p">
              <li class="flex items-start gap-1.5">
                <span class="text-gray-400 mt-0.5">&#8226;</span>
                <span x-text="p"></span>
              </li>
            </template>
          </ul>
          <p x-show="!(data.document?.purpose?.length)" class="text-sm text-gray-400 italic">None identified</p>
        </div>

        <!-- Governed Systems -->
        <div class="border border-gray-200 rounded-lg p-4">
          <div class="flex items-center gap-2 mb-2">
            <span class="dot" :class="'dot-' + data.confidence?.context?.governed_systems"></span>
            <h3 class="text-sm font-semibold text-gray-700">Governed AI Systems</h3>
          </div>
          <div class="flex flex-wrap gap-2">
            <template x-for="gs in data.document?.governed_systems || []" :key="gs.name">
              <span class="px-2 py-0.5 rounded text-xs bg-blue-100 text-blue-800" x-text="gs.name"></span>
            </template>
          </div>
          <p x-show="!(data.document?.governed_systems?.length)" class="text-sm text-gray-400 italic">None identified</p>
        </div>

        <!-- Regulations -->
        <div class="border border-gray-200 rounded-lg p-4">
          <div class="flex items-center gap-2 mb-2">
            <span class="dot" :class="'dot-' + data.confidence?.context?.regulations"></span>
            <h3 class="text-sm font-semibold text-gray-700">Regulations</h3>
          </div>
          <div class="space-y-1">
            <template x-for="r in data.document?.regulations || []" :key="r.name">
              <div class="text-sm">
                <span class="font-medium text-gray-700" x-text="r.name"></span>
                <span x-show="r.jurisdiction" class="text-gray-400 text-xs ml-1" x-text="'(' + r.jurisdiction + ')'"></span>
                <template x-if="!r.jurisdiction && !r.reference">
                  <span class="text-amber-500 text-xs ml-1">(incomplete)</span>
                </template>
              </div>
            </template>
          </div>
          <p x-show="!(data.document?.regulations?.length)" class="text-sm text-gray-400 italic">None identified</p>
        </div>

      </div>
    </section>

    <!-- 3. Stakeholders (Lewis et al. framing) -->
    <section class="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
      <div class="flex items-center gap-2 mb-3">
        <span class="dot" :class="'dot-' + data.confidence?.context?.stakeholders"></span>
        <h2 class="text-sm font-semibold text-gray-500 uppercase tracking-wide">Stakeholders</h2>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">

        <!-- Organisation -->
        <div class="border border-gray-200 rounded-lg p-4">
          <h3 class="text-xs text-gray-400 uppercase tracking-wide mb-2">Organisation</h3>
          <p class="font-medium text-gray-800" x-text="data.stakeholder_groups?.organisation?.name || 'Not identified'"></p>
        </div>

        <!-- Governance -->
        <div class="border border-gray-200 rounded-lg p-4">
          <h3 class="text-xs text-gray-400 uppercase tracking-wide mb-2">Governance</h3>
          <div class="space-y-2">
            <template x-for="s in data.stakeholder_groups?.governance || []" :key="s.name">
              <div>
                <span class="text-sm font-medium text-gray-800" x-text="s.name"></span>
                <div class="flex flex-wrap gap-1 mt-0.5">
                  <template x-for="r in s.roles" :key="r">
                    <span class="px-1.5 py-0.5 rounded text-[10px] bg-purple-100 text-purple-800" x-text="r"></span>
                  </template>
                </div>
              </div>
            </template>
          </div>
          <p x-show="!(data.stakeholder_groups?.governance?.length)" class="text-sm text-gray-400 italic">None identified</p>
        </div>

        <!-- Users -->
        <div class="border border-gray-200 rounded-lg p-4">
          <h3 class="text-xs text-gray-400 uppercase tracking-wide mb-2">Users</h3>
          <div class="flex flex-wrap gap-1.5">
            <template x-for="s in data.stakeholder_groups?.users || []" :key="s.name">
              <span class="px-2 py-0.5 rounded text-xs bg-teal-100 text-teal-800" x-text="s.name"></span>
            </template>
          </div>
          <p x-show="!(data.stakeholder_groups?.users?.length)" class="text-sm text-gray-400 italic">None identified</p>
        </div>

        <!-- Subjects -->
        <div class="border border-gray-200 rounded-lg p-4">
          <h3 class="text-xs text-gray-400 uppercase tracking-wide mb-2">Subjects</h3>
          <div class="flex flex-wrap gap-1.5">
            <template x-for="s in data.stakeholder_groups?.subjects || []" :key="s.name">
              <span class="px-2 py-0.5 rounded text-xs bg-amber-100 text-amber-800" x-text="s.name"></span>
            </template>
          </div>
          <p x-show="!(data.stakeholder_groups?.subjects?.length)" class="text-sm text-gray-400 italic">None identified</p>
        </div>

      </div>
    </section>

    <!-- 4. Policies -->
    <section class="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
      <h2 class="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
        Policies
        <span class="text-gray-400 font-normal" x-text="'(' + (data.document?.policies?.length || 0) + ')'"></span>
      </h2>
      <div class="space-y-4">
        <template x-for="(policy, idx) in data.document?.policies || []" :key="policy.policy_concept">
          <div class="border border-gray-200 rounded-lg" x-data="{ open: true }">

            <!-- Policy header -->
            <button @click="open = !open"
              class="w-full flex items-center justify-between p-4 text-left hover:bg-gray-50 rounded-t-lg">
              <div class="flex items-center gap-3">
                <span class="font-semibold text-gray-800" x-text="policy.policy_concept"></span>
                <!-- Confidence dots -->
                <div class="flex gap-1">
                  <span class="dot" :class="'dot-' + (data.confidence?.policies?.[idx]?.boundary_examples || 'red')"
                    title="Boundary examples"></span>
                  <span class="dot" :class="'dot-' + (data.confidence?.policies?.[idx]?.acceptable_uses || 'red')"
                    title="Acceptable uses"></span>
                  <span class="dot" :class="'dot-' + (data.confidence?.policies?.[idx]?.risk_controls || 'red')"
                    title="Risk controls"></span>
                  <span class="dot" :class="'dot-' + (data.confidence?.policies?.[idx]?.human_involvement || 'red')"
                    title="Human involvement"></span>
                  <span class="dot" :class="'dot-' + (data.confidence?.policies?.[idx]?.decomposition || 'red')"
                    title="Decomposition"></span>
                </div>
              </div>
              <svg class="w-5 h-5 text-gray-400 transition-transform" :class="open ? 'rotate-180' : ''"
                fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
              </svg>
            </button>

            <!-- Policy body -->
            <div x-show="open" class="p-4 pt-0 space-y-4">

              <!-- Definition -->
              <div>
                <h4 class="text-xs text-gray-400 uppercase tracking-wide mb-1">Definition</h4>
                <p class="text-sm text-gray-700 leading-relaxed" x-text="policy.concept_definition"></p>
              </div>

              <!-- Boundary Examples -->
              <div x-show="policy.boundary_examples?.length">
                <h4 class="text-xs text-gray-400 uppercase tracking-wide mb-1">Boundary Examples</h4>
                <table class="w-full text-sm">
                  <thead>
                    <tr class="text-left text-xs text-gray-400 uppercase border-b border-gray-200">
                      <th class="pb-2 pr-3 w-1/2">Prohibited</th>
                      <th class="pb-2 w-1/2">Acceptable</th>
                    </tr>
                  </thead>
                  <tbody>
                    <template x-for="be in policy.boundary_examples" :key="be.prohibited">
                      <tr class="border-b border-gray-100">
                        <td class="py-2 pr-3 text-red-700 bg-red-50/50" x-text="be.prohibited"></td>
                        <td class="py-2 text-green-700 bg-green-50/50" x-text="be.acceptable"></td>
                      </tr>
                    </template>
                  </tbody>
                </table>
              </div>

              <!-- Acceptable Uses -->
              <div x-show="policy.acceptable_uses?.length">
                <h4 class="text-xs text-gray-400 uppercase tracking-wide mb-1">Acceptable Uses</h4>
                <ul class="text-sm text-gray-700 space-y-1">
                  <template x-for="au in policy.acceptable_uses" :key="au">
                    <li class="flex items-start gap-1.5">
                      <span class="text-green-500 mt-0.5">&#10003;</span>
                      <span x-text="au"></span>
                    </li>
                  </template>
                </ul>
              </div>

              <!-- Risk Controls -->
              <div x-show="policy.risk_controls?.length">
                <h4 class="text-xs text-gray-400 uppercase tracking-wide mb-1">Risk Controls</h4>
                <ul class="text-sm text-gray-700 space-y-1">
                  <template x-for="rc in policy.risk_controls" :key="rc">
                    <li class="flex items-start gap-1.5">
                      <span class="text-blue-500 mt-0.5">&#9632;</span>
                      <span x-text="rc"></span>
                    </li>
                  </template>
                </ul>
              </div>

              <!-- Human Involvement -->
              <div x-show="policy.human_involvement">
                <h4 class="text-xs text-gray-400 uppercase tracking-wide mb-1">Human Involvement</h4>
                <div class="bg-indigo-50 border border-indigo-200 rounded-lg p-3">
                  <p class="text-sm text-indigo-800" x-text="policy.human_involvement"></p>
                </div>
              </div>

              <!-- Decomposition: Agent -> Activity -> Entity -->
              <div x-show="policy.decomposition">
                <h4 class="text-xs text-gray-400 uppercase tracking-wide mb-1">Decomposition</h4>
                <div class="flex items-center gap-2 text-sm">
                  <span x-show="policy.decomposition?.agent"
                    class="px-2 py-1 rounded bg-teal-100 text-teal-800 font-medium" x-text="policy.decomposition?.agent"></span>
                  <span x-show="policy.decomposition?.agent" class="flow-arrow">&rarr;</span>
                  <span x-show="policy.decomposition?.activity"
                    class="px-2 py-1 rounded bg-blue-100 text-blue-800 font-medium" x-text="policy.decomposition?.activity"></span>
                  <span x-show="policy.decomposition?.activity" class="flow-arrow">&rarr;</span>
                  <span x-show="policy.decomposition?.entity"
                    class="px-2 py-1 rounded bg-amber-100 text-amber-800 font-medium" x-text="policy.decomposition?.entity"></span>
                </div>
                <div class="flex gap-4 mt-1 text-[10px] text-gray-400 uppercase">
                  <span x-show="policy.decomposition?.agent">Agent</span>
                  <span x-show="policy.decomposition?.agent">&nbsp;</span>
                  <span x-show="policy.decomposition?.activity">Activity</span>
                  <span x-show="policy.decomposition?.activity">&nbsp;</span>
                  <span x-show="policy.decomposition?.entity">Entity</span>
                </div>
              </div>

            </div>
          </div>
        </template>
      </div>
    </section>

    <!-- 5. Coverage Summary -->
    <section class="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
      <h2 class="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">Coverage Summary</h2>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4">

        <div class="text-center p-3 bg-gray-50 rounded-lg">
          <p class="text-2xl font-bold text-indigo-600" x-text="data.confidence?.summary?.policies_total || 0"></p>
          <p class="text-xs text-gray-400">Policies Extracted</p>
        </div>
        <div class="text-center p-3 bg-gray-50 rounded-lg">
          <p class="text-2xl font-bold text-green-600" x-text="data.confidence?.summary?.policies_enriched || 0"></p>
          <p class="text-xs text-gray-400">Policies Enriched</p>
        </div>
        <div class="text-center p-3 bg-gray-50 rounded-lg">
          <p class="text-2xl font-bold text-teal-600" x-text="data.confidence?.summary?.boundary_pairs_total || 0"></p>
          <p class="text-xs text-gray-400">Boundary Pairs</p>
        </div>
        <div class="text-center p-3 bg-gray-50 rounded-lg">
          <p class="text-2xl font-bold"
            :class="(data.confidence?.summary?.policies_with_zero_pairs || 0) > 0 ? 'text-red-600' : 'text-green-600'"
            x-text="data.confidence?.summary?.policies_with_zero_pairs || 0"></p>
          <p class="text-xs text-gray-400">Zero-Pair Policies</p>
        </div>

      </div>

      <!-- Weak Inferences -->
      <div x-show="data.confidence?.summary?.weak_inferences?.length" class="mt-4">
        <h3 class="text-xs text-gray-400 uppercase tracking-wide mb-2">Weak Inferences</h3>
        <div class="flex flex-wrap gap-2">
          <template x-for="wi in data.confidence?.summary?.weak_inferences || []" :key="wi">
            <span class="px-2 py-0.5 rounded text-xs bg-amber-100 text-amber-800" x-text="wi"></span>
          </template>
        </div>
      </div>

      <!-- Passes Completed -->
      <div class="mt-4">
        <h3 class="text-xs text-gray-400 uppercase tracking-wide mb-2">Passes Completed</h3>
        <div class="flex gap-2">
          <template x-for="pass_name in data.meta?.passes_completed || []" :key="pass_name">
            <span class="px-2 py-0.5 rounded text-xs bg-green-100 text-green-800" x-text="pass_name"></span>
          </template>
        </div>
      </div>

      <!-- Source Info -->
      <div class="mt-4 text-xs text-gray-400">
        Source: <span x-text="data.meta?.source_document || '?'"></span>
        &middot; Format: <span x-text="data.meta?.input_format || '?'"></span>
        &middot; Model: <span x-text="data.meta?.model || '?'"></span>
      </div>
    </section>

  </div>

<script>
const DATA = __REPORT_DATA__;

function reportApp() {
  return {
    data: DATA,
  };
}
</script>
</body>
</html>
```

- [ ] **Step 2: Commit**

```bash
cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner
git add refiner/src/refiner/ingest_report_template.html
git commit -m "feat: add ingest report HTML template (Tailwind + Alpine.js)"
```

---

### Task 4: HTML generation and CLI integration

**Files:**
- Modify: `refiner/src/refiner/ingest_report.py`
- Modify: `refiner/src/refiner/cli.py`
- Modify: `refiner/tests/test_ingest_report.py`

- [ ] **Step 1: Write test for `build_ingest_report()`**

Append to `refiner/tests/test_ingest_report.py`:

```python
from refiner.ingest_report import build_ingest_report


def test_build_ingest_report_writes_html(tmp_path):
    doc = _full_doc()
    report = _make_report()
    meta = _make_meta()
    out = tmp_path / "test-report.html"

    result_path = build_ingest_report(doc, report, out, meta)

    assert result_path == out
    assert out.exists()
    html = out.read_text()
    assert "<!DOCTYPE html>" in html
    assert "__REPORT_DATA__" not in html
    assert "Acme Corp" in html
    assert "Data Privacy" in html


def test_build_ingest_report_valid_json_in_html(tmp_path):
    """The injected JSON must be parseable."""
    import re

    doc = _full_doc()
    out = tmp_path / "test-report.html"
    build_ingest_report(doc, _make_report(), out, _make_meta())

    html = out.read_text()
    match = re.search(r"const DATA = (.+?);", html, re.DOTALL)
    assert match is not None
    parsed = json.loads(match.group(1))
    assert parsed["document"]["domain"] == "finance"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd refiner && uv run pytest tests/test_ingest_report.py::test_build_ingest_report_writes_html -v`
Expected: FAIL with `ImportError: cannot import name 'build_ingest_report'`

- [ ] **Step 3: Implement `build_ingest_report()`**

Add to `refiner/src/refiner/ingest_report.py`:

```python
def build_ingest_report(
    doc: PolicyProfile,
    report: RunReport,
    output_path: Path,
    meta: dict,
) -> Path:
    """Build self-contained HTML report. Returns path to written file."""
    data = build_report_data(doc, report, meta)
    template_path = Path(__file__).parent / "ingest_report_template.html"
    template = template_path.read_text()
    html = template.replace("__REPORT_DATA__", json.dumps(data, default=str))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html)
    return output_path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd refiner && uv run pytest tests/test_ingest_report.py -v`
Expected: all 16 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner
git add refiner/src/refiner/ingest_report.py refiner/tests/test_ingest_report.py
git commit -m "feat: add build_ingest_report() HTML generation"
```

- [ ] **Step 6: Integrate into CLI**

In `refiner/src/refiner/cli.py`, after line 103 (`typer.echo(f"Debug markdown written to {md_path}")`), add:

```python
    # Generate ingest report HTML
    from refiner.ingest_report import build_ingest_report
    passes = ["context"]
    if not until or until != "context":
        passes.append("policies")
    if not until and not skip_enrichment:
        passes.append("enrichment")
    meta = {
        "model": config.model,
        "source_document": document.name,
        "timestamp": report.timestamp,
        "input_format": input_format,
        "passes_completed": passes,
    }
    report_path = build_ingest_report(result, report, out_path.with_suffix(".html"), meta)
    typer.echo(f"Ingest report written to {report_path}")
```

- [ ] **Step 7: Write CLI integration test**

Append to `refiner/tests/test_ingest_report.py`:

```python
from unittest.mock import patch, MagicMock
from typer.testing import CliRunner
from refiner.cli import app


def test_cli_ingest_generates_html_report(tmp_path):
    """The ingest CLI command should write an HTML report alongside the JSON."""
    from refiner.stages.ingest import _SlimContext, _SlimPolicyList, _SlimPolicy

    # Create a minimal markdown policy file
    policy_file = tmp_path / "test-policy.md"
    policy_file.write_text("# Test Policy\n\nDo not share PII.")

    mock_context = _SlimContext(
        organization="TestOrg",
        domain="testing",
        purpose=["test"],
        ai_systems=[],
        ai_users=["testers"],
        ai_subjects=[],
        governing_regulations=[],
        named_entities=[],
    )
    mock_policies = _SlimPolicyList(
        policies=[_SlimPolicy(policy_concept="PII", concept_definition="No PII")]
    )

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [mock_context, mock_policies]

    with patch("refiner.cli.create_client", return_value=mock_client):
        runner = CliRunner()
        result = runner.invoke(app, [
            "ingest", str(policy_file),
            "--base-url", "http://localhost:8000/v1",
            "--model", "test-model",
            "--skip-enrichment",
            "--output", str(tmp_path / "out.json"),
        ])

    assert result.exit_code == 0
    assert (tmp_path / "out.html").exists()
    html = (tmp_path / "out.html").read_text()
    assert "TestOrg" in html
    assert "Policy Ingest Report" in html
```

- [ ] **Step 8: Run all tests**

Run: `cd refiner && uv run pytest tests/test_ingest_report.py -v`
Expected: all 17 tests PASS

- [ ] **Step 9: Run full test suite to check for regressions**

Run: `cd refiner && uv run pytest -x -q`
Expected: all tests PASS

- [ ] **Step 10: Commit**

```bash
cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner
git add refiner/src/refiner/cli.py refiner/tests/test_ingest_report.py
git commit -m "feat: integrate ingest report into CLI (always generated)"
```

---

### Task 5: Validate with real data

**Files:** none modified

- [ ] **Step 1: Generate report from existing enriched JSON**

Write a quick validation script that loads the RDaSH enriched JSON and generates a report from it:

```bash
cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner
uv run python -c "
import json
from pathlib import Path
from refiner.ingest_report import build_ingest_report
from refiner.models import PolicyProfile, RunReport

doc = PolicyProfile(**json.loads(Path('runs/rdash-nhs-gemma-4-26b-a4b-it-g10.1/rdash-nhs-enriched.json').read_text()))
report = RunReport(model='gemma-4-26b-a4b-it', policy_set='rdash-nhs', timestamp='2026-04-14T16:52:00Z')
meta = {'model': 'gemma-4-26b-a4b-it', 'source_document': 'rdash-nhs.md', 'timestamp': '2026-04-14T16:52:00Z', 'input_format': 'markdown', 'passes_completed': ['context', 'policies', 'enrichment']}
out = Path('/tmp/rdash-nhs-ingest-report.html')
build_ingest_report(doc, report, out, meta)
print(f'Report written to {out}')
"
```

- [ ] **Step 2: Open the report in a browser and verify**

```bash
open /tmp/rdash-nhs-ingest-report.html
```

Check:
- Header shows "Rotherham Doncaster and South Humber NHS Foundation Trust (RDaSH)"
- Domain is "healthcare"
- Governed Systems shows ChatGPT, Copilot, M365 Copilot, Publicly Available AI
- Stakeholders grouped: Organisation (RDaSH), Governance (Chief Executive, DPO, Caldicott Guardian, SIRO, Clinical Safety Officer), Users (staff, volunteers, students, etc.), Subjects (patients)
- All 5 policies render with expandable cards
- Boundary examples show in prohibited/acceptable table
- Decomposition shows Agent → Activity → Entity flow
- Confidence dots are appropriate colours
- Regulations show "(incomplete)" for entries without jurisdiction

- [ ] **Step 3: Fix any visual issues found during review**

Iterate on the template if layout or styling needs adjustment. Commit any fixes.

- [ ] **Step 4: Commit any final adjustments**

```bash
cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner
git add -A
git commit -m "fix: polish ingest report template after visual review"
```
