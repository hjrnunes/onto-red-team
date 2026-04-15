#!/usr/bin/env python3
"""Mock ORT-enriched garak data generator.

Takes an existing garak report/hitlog and an ORT Refiner run, then produces
re-keyed outputs where generic safety intents (S00Xfraud, etc.) are replaced
with Nexus risk-backed intents and linked to adversarial prompt stubs.

Output files (in prototypes/garak/mock_runs/):
  - ort-rdash.report.jsonl   — re-keyed garak report
  - ort-rdash.hitlog.jsonl    — re-keyed garak hitlog
  - ort_intent_mapping.json   — intent mapping with cross-framework data
  - ort_stubs.jsonl           — adversarial prompt stubs with stub IDs
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

GARAK_REPORT = (
    REPO_ROOT
    / "prototypes/garak/garak_runs"
    / "garak.0e04280f-b86a-45d3-b741-f763219cc2c3.report.jsonl"
)
GARAK_HITLOG = (
    REPO_ROOT
    / "prototypes/garak/garak_runs"
    / "garak.0e04280f-b86a-45d3-b741-f763219cc2c3.hitlog.jsonl"
)
ORT_RUN_DIR = REPO_ROOT / "runs/rdash-nhs-gemma-4-26b-a4b-it-g12"
OUTPUT_DIR = REPO_ROOT / "prototypes/garak/mock_runs"

# ---------------------------------------------------------------------------
# Intent re-keying: old generic intents -> new Nexus-backed intents
# ---------------------------------------------------------------------------

INTENT_REKEY: dict[str, str] = {
    "S001fraud": "S001regulatorycompliance",
    "S002hatespeech": "S002dataprivacy",
    "S003illegalactivity": "S003nondisclosure",
    "S004misinformation": "S004personalinformation",
    "S005securitymalware": "S005sensitiveinfo",
    "S006selfharm": "S006accountability",
    "S007sexuallyexplicit": "S007privacycompromise",
    "S008violence": "S008governancefailure",
}

# ---------------------------------------------------------------------------
# Nexus risk info per new intent
# ---------------------------------------------------------------------------

INTENT_TO_RISK: dict[str, dict[str, str]] = {
    "S001regulatorycompliance": {
        "risk_id": "credo-risk-023",
        "risk_name": "Regulatory compliance",
        "risk_framework": "Credo AI",
    },
    "S002dataprivacy": {
        "risk_id": "nist-data-privacy",
        "risk_name": "Data Privacy",
        "risk_framework": "NIST AI RMF",
    },
    "S003nondisclosure": {
        "risk_id": "atlas-non-disclosure",
        "risk_name": "Non-disclosure",
        "risk_framework": "IBM Risk Atlas",
    },
    "S004personalinformation": {
        "risk_id": "atlas-personal-information-in-data",
        "risk_name": "Personal information in data",
        "risk_framework": "IBM Risk Atlas",
    },
    "S005sensitiveinfo": {
        "risk_id": "credo-risk-037",
        "risk_name": "Compromised sensitive information",
        "risk_framework": "Credo AI",
    },
    "S006accountability": {
        "risk_id": "atlas-accountability-agentic",
        "risk_name": "Accountability of AI agent actions",
        "risk_framework": "IBM Risk Atlas",
    },
    "S007privacycompromise": {
        "risk_id": "mit-ai-risk-subdomain-2.1",
        "risk_name": "Compromise of privacy",
        "risk_framework": "MIT AI Risk Repository",
    },
    "S008governancefailure": {
        "risk_id": "mit-ai-risk-subdomain-6.5",
        "risk_name": "Governance failure",
        "risk_framework": "MIT AI Risk Repository",
    },
}

# ---------------------------------------------------------------------------
# Taxonomy risk groups
# ---------------------------------------------------------------------------

RISK_GROUPS: dict[str, list[str]] = {
    "Clinical Decision-Making & Care Planning": [
        "atlas-accountability-agentic",
        "credo-risk-023",
    ],
    "Protected Health Information & Data Privacy": [
        "nist-data-privacy",
        "atlas-personal-information-in-data",
        "credo-risk-037",
    ],
    "Research & Clinical Governance": [
        "mit-ai-risk-subdomain-6.5",
    ],
    "Patient Consent": [
        "mit-ai-risk-subdomain-2.1",
        "atlas-non-disclosure",
    ],
}

# Reverse lookup: risk_id -> group name
RISK_TO_GROUP: dict[str, str] = {
    risk_id: group
    for group, risk_ids in RISK_GROUPS.items()
    for risk_id in risk_ids
}


# ---------------------------------------------------------------------------
# Stub ID generation
# ---------------------------------------------------------------------------


def generate_stub_id(risk_id: str, technique: str, index: int) -> str:
    """Generate a deterministic stub ID from risk, technique, and index.

    Format: ``{risk_id}:{technique_slug}:{index}``
    where technique_slug has underscores replaced with hyphens.
    """
    technique_slug = technique.replace("_", "-")
    return f"{risk_id}:{technique_slug}:{index}"


# ---------------------------------------------------------------------------
# Load adversarial prompts and assign stub IDs
# ---------------------------------------------------------------------------


def load_adversarial_prompts(path: Path) -> list[dict]:
    """Load adversarial prompts JSONL and assign stub IDs.

    Stubs are grouped by (risk_id, technique) and indexed within each group.
    """
    entries: list[dict] = []
    with open(path) as f:
        for line in f:
            entries.append(json.loads(line))

    # Group by (risk_id, technique) to assign sequential indices
    group_counters: dict[tuple[str, str], int] = defaultdict(int)
    for entry in entries:
        key = (entry["risk_id"], entry["technique"])
        idx = group_counters[key]
        entry["stub_id"] = generate_stub_id(entry["risk_id"], entry["technique"], idx)
        group_counters[key] += 1

    return entries
