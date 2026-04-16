# UGA–ORT Semantic Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adopt nexus terms for ORT's input envelope, implement Risk → Policy projection from nexus AiSystem payloads, and create the SSSOM output alignment artifact.

**Architecture:** Rename `GovernedSystem` → `AiSystem` in ORT models with backward-compatible deserialization. Add a nexus adapter module that converts nexus-format AiSystem + Risk payloads into `PolicyProfile` inputs. The adapter handles the genuine semantic gap: projecting `Risk.concern` into `Policy.concept_definition`. Output alignment is a static SSSOM TSV file.

**Tech Stack:** Pydantic (models, validators), Python (adapter), SSSOM TSV (mappings)

**Spec:** `docs/superpowers/specs/2026-04-16-uga-ort-bridge-design.md`

---

### Task 1: Rename GovernedSystem → AiSystem in models.py

**Files:**
- Modify: `refiner/src/refiner/models.py:26-30` (class definition)
- Modify: `refiner/src/refiner/models.py:58-66` (PolicyProfile field)
- Test: `refiner/tests/test_models.py`

- [ ] **Step 1: Write failing test for AiSystem class**

In `refiner/tests/test_models.py`, add:

```python
def test_ai_system_creation():
    from refiner.models import AiSystem
    system = AiSystem(name="Medical Triage Chatbot", description="Patient triage", purpose=["symptom assessment"], risk_level="high")
    assert system.name == "Medical Triage Chatbot"
    assert system.purpose == ["symptom assessment"]
    assert system.risk_level == "high"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd refiner && uv run pytest tests/test_models.py::test_ai_system_creation -v`
Expected: FAIL with `ImportError: cannot import name 'AiSystem'`

- [ ] **Step 3: Rename GovernedSystem → AiSystem in models.py**

In `refiner/src/refiner/models.py`, rename the class:

```python
class AiSystem(BaseModel):
    name: str
    description: str | None = None
    purpose: list[str] = []
    risk_level: Literal["high", "limited", "minimal", "unclassified"] | None = None
```

Update `PolicyProfile` to use `ai_systems` as the primary field name with `governed_systems` backward compat:

```python
class PolicyProfile(BaseModel):
    airo_version: str = "0.2"
    organization: Stakeholder | None = None
    domain: str | None = None
    purpose: list[str] = []
    ai_systems: list[AiSystem] = []
    stakeholders: list[Stakeholder] = []
    regulations: list[RegulatoryReference] = []
    policies: list[Policy] = []

    @field_validator("organization", mode="before")
    @classmethod
    def _coerce_organization(cls, v):
        if isinstance(v, str):
            return Stakeholder(name=v) if v else None
        return v

    @model_validator(mode="before")
    @classmethod
    def _migrate_governed_systems(cls, data):
        if isinstance(data, dict) and "governed_systems" in data and "ai_systems" not in data:
            data["ai_systems"] = data.pop("governed_systems")
        return data
```

Add `model_validator` to the imports at top of `models.py`:

```python
from pydantic import BaseModel, field_validator, model_validator
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd refiner && uv run pytest tests/test_models.py::test_ai_system_creation -v`
Expected: PASS

- [ ] **Step 5: Write test for backward compatibility with governed_systems**

In `refiner/tests/test_models.py`, add:

```python
def test_policy_profile_governed_systems_backward_compat():
    from refiner.models import PolicyProfile
    data = {
        "governed_systems": [{"name": "Legacy System"}],
        "policies": [],
    }
    profile = PolicyProfile(**data)
    assert len(profile.ai_systems) == 1
    assert profile.ai_systems[0].name == "Legacy System"


def test_policy_profile_ai_systems_field():
    from refiner.models import AiSystem, PolicyProfile
    profile = PolicyProfile(
        ai_systems=[AiSystem(name="New System")],
        policies=[],
    )
    assert len(profile.ai_systems) == 1
    assert profile.ai_systems[0].name == "New System"
```

- [ ] **Step 6: Run backward compat tests**

Run: `cd refiner && uv run pytest tests/test_models.py::test_policy_profile_governed_systems_backward_compat tests/test_models.py::test_policy_profile_ai_systems_field -v`
Expected: PASS

- [ ] **Step 7: Update all GovernedSystem references across codebase**

Update imports and references in these files:

`refiner/src/refiner/stages/ingest.py:11` — change `GovernedSystem` to `AiSystem` in the import and in `_build_document()` at line 401:
```python
governed_systems=[AiSystem(name=s) for s in context.ai_systems],
```
becomes:
```python
ai_systems=[AiSystem(name=s) for s in context.ai_systems],
```

`refiner/src/refiner/cli.py` — if `GovernedSystem` is imported or referenced, update to `AiSystem`.

Grep for any other `GovernedSystem` references and update them.

- [ ] **Step 8: Run full test suite**

Run: `cd refiner && uv run pytest tests/ -v`
Expected: All tests pass. Some tests may reference `GovernedSystem` — fix any failures.

- [ ] **Step 9: Commit**

```bash
git add refiner/src/refiner/models.py refiner/src/refiner/stages/ingest.py refiner/src/refiner/cli.py refiner/tests/test_models.py
git commit -m "refactor(models): rename GovernedSystem → AiSystem, adopt nexus terms

Aligns ORT input envelope with nexus LinkML schema terminology.
Adds model_validator for backward compat with governed_systems field."
```

---

### Task 2: Create nexus adapter — Risk → Policy projection

**Files:**
- Create: `refiner/src/refiner/nexus_adapter.py`
- Test: `refiner/tests/test_nexus_adapter.py`

This is the core semantic bridge: converting a nexus-format payload (AiSystem + Risk entities) into an ORT `PolicyProfile`.

- [ ] **Step 1: Write failing test for Risk → Policy projection**

Create `refiner/tests/test_nexus_adapter.py`:

```python
from refiner.nexus_adapter import project_risk_to_policy


def test_project_risk_to_policy_uses_concern():
    risk = {
        "id": "atlas-social-engineering",
        "name": "Social Engineering",
        "description": "An AI model may be used to generate social engineering attacks.",
        "concern": "An AI model may generate content that could be used to manipulate individuals into revealing sensitive information.",
        "tag": "social-engineering",
        "risk_type": "output",
        "isDefinedByTaxonomy": "ibm-risk-atlas",
    }
    policy = project_risk_to_policy(risk)
    assert policy.policy_concept == "Social Engineering"
    assert policy.concept_definition == risk["concern"]


def test_project_risk_to_policy_falls_back_to_description():
    risk = {
        "id": "atlas-test",
        "name": "Test Risk",
        "description": "A test risk description.",
        "concern": "",
    }
    policy = project_risk_to_policy(risk)
    assert policy.concept_definition == "A test risk description."


def test_project_risk_to_policy_no_concern_no_description():
    risk = {
        "id": "atlas-minimal",
        "name": "Minimal Risk",
    }
    policy = project_risk_to_policy(risk)
    assert policy.policy_concept == "Minimal Risk"
    assert policy.concept_definition == "Minimal Risk"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd refiner && uv run pytest tests/test_nexus_adapter.py::test_project_risk_to_policy_uses_concern -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'refiner.nexus_adapter'`

- [ ] **Step 3: Implement project_risk_to_policy**

Create `refiner/src/refiner/nexus_adapter.py`:

```python
"""Nexus adapter — converts AI Atlas Nexus payloads to ORT pipeline inputs.

Implements the UGA–ORT semantic bridge (Layer A: input projection).
See docs/superpowers/specs/2026-04-16-uga-ort-bridge-design.md
"""
from refiner.models import (
    AiSystem,
    Policy,
    PolicyProfile,
    RegulatoryReference,
    Stakeholder,
)


def project_risk_to_policy(risk: dict) -> Policy:
    """Project a nexus Risk entity into an ORT Policy.

    Uses Risk.concern as the policy definition (default), falling back
    to Risk.description, then Risk.name.
    """
    name = risk.get("name", "")
    concern = risk.get("concern", "")
    description = risk.get("description", "")
    definition = concern if concern else (description if description else name)
    return Policy(policy_concept=name, concept_definition=definition)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd refiner && uv run pytest tests/test_nexus_adapter.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Write failing test for full nexus payload → PolicyProfile conversion**

Add to `refiner/tests/test_nexus_adapter.py`:

```python
from refiner.nexus_adapter import nexus_to_policy_profile


def test_nexus_to_policy_profile_basic():
    payload = {
        "ai_system": {
            "name": "Medical Triage Bot",
            "description": "AI-assisted patient triage",
            "hasPurpose": ["symptom assessment", "triage prioritization"],
            "isAppliedWithinDomain": "healthcare",
            "isDevelopedBy": {"name": "HealthCo"},
            "isDeployedBy": {"name": "City Hospital"},
            "hasAIUser": [{"name": "Nurse"}],
            "hasAISubject": [{"name": "Patient"}],
            "hasEuRiskCategory": "high",
        },
        "risks": [
            {
                "id": "atlas-generating-inaccurate-output",
                "name": "Generating Inaccurate Output",
                "concern": "An AI model may produce medically inaccurate triage recommendations.",
            },
            {
                "id": "atlas-personal-information-in-prompt",
                "name": "Personal Information in Prompt",
                "concern": "Patient health data may be included in prompts sent to the AI model.",
            },
        ],
    }
    profile = nexus_to_policy_profile(payload)
    assert profile.domain == "healthcare"
    assert profile.organization.name == "HealthCo"
    assert profile.organization.roles == ["airo:AIProvider"]
    assert len(profile.ai_systems) == 1
    assert profile.ai_systems[0].name == "Medical Triage Bot"
    assert profile.ai_systems[0].risk_level == "high"
    assert len(profile.policies) == 2
    assert profile.policies[0].policy_concept == "Generating Inaccurate Output"
    assert profile.policies[1].concept_definition == "Patient health data may be included in prompts sent to the AI model."
    # Stakeholders
    deployer_names = [s.name for s in profile.stakeholders if "airo:AIDeployer" in s.roles]
    assert "City Hospital" in deployer_names
    user_names = [s.name for s in profile.stakeholders if "airo:AIUser" in s.roles]
    assert "Nurse" in user_names
    subject_names = [s.name for s in profile.stakeholders if "airo:AISubject" in s.roles]
    assert "Patient" in subject_names


def test_nexus_to_policy_profile_minimal():
    payload = {
        "risks": [
            {"id": "r1", "name": "Test Risk", "concern": "Test concern."},
        ],
    }
    profile = nexus_to_policy_profile(payload)
    assert profile.organization is None
    assert profile.ai_systems == []
    assert len(profile.policies) == 1


def test_nexus_to_policy_profile_risk_controls():
    payload = {
        "risks": [
            {"id": "r1", "name": "Bias", "concern": "Model may exhibit bias."},
        ],
        "risk_controls": [
            {"name": "Fairness testing", "description": "Run fairness benchmarks before deployment."},
        ],
    }
    profile = nexus_to_policy_profile(payload)
    assert profile.policies[0].risk_controls == ["Run fairness benchmarks before deployment."]
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd refiner && uv run pytest tests/test_nexus_adapter.py::test_nexus_to_policy_profile_basic -v`
Expected: FAIL with `ImportError: cannot import name 'nexus_to_policy_profile'`

- [ ] **Step 7: Implement nexus_to_policy_profile**

Add to `refiner/src/refiner/nexus_adapter.py`:

```python
def nexus_to_policy_profile(payload: dict) -> PolicyProfile:
    """Convert a nexus-format payload to an ORT PolicyProfile.

    Expected payload structure:
        ai_system: dict (nexus AiSystem fields)
        risks: list[dict] (nexus Risk entities, each with id/name/concern)
        risk_controls: list[dict] (optional, nexus RiskControl entities)
    """
    ai_system_data = payload.get("ai_system", {})
    risks = payload.get("risks", [])
    risk_controls = payload.get("risk_controls", [])

    # Extract control descriptions for attachment to policies
    control_descriptions = [
        rc.get("description", rc.get("name", ""))
        for rc in risk_controls
        if rc.get("description") or rc.get("name")
    ]

    # Build organization from isDevelopedBy
    organization = None
    dev = ai_system_data.get("isDevelopedBy")
    if dev:
        org_name = dev if isinstance(dev, str) else dev.get("name", "")
        if org_name:
            organization = Stakeholder(name=org_name, roles=["airo:AIProvider"])

    # Build AI system
    ai_systems = []
    if ai_system_data:
        purpose_raw = ai_system_data.get("hasPurpose", [])
        if isinstance(purpose_raw, str):
            purpose_raw = [purpose_raw]
        ai_systems.append(AiSystem(
            name=ai_system_data.get("name", ""),
            description=ai_system_data.get("description"),
            purpose=purpose_raw,
            risk_level=ai_system_data.get("hasEuRiskCategory"),
        ))

    # Build domain
    domain_raw = ai_system_data.get("isAppliedWithinDomain")
    domain = domain_raw if isinstance(domain_raw, str) else (
        domain_raw.get("name", "") if isinstance(domain_raw, dict) else None
    )

    # Build stakeholders
    stakeholders = []
    deployer = ai_system_data.get("isDeployedBy")
    if deployer:
        dep_name = deployer if isinstance(deployer, str) else deployer.get("name", "")
        if dep_name:
            stakeholders.append(Stakeholder(name=dep_name, roles=["airo:AIDeployer"]))

    for user in ai_system_data.get("hasAIUser", []):
        u_name = user if isinstance(user, str) else user.get("name", "")
        if u_name:
            stakeholders.append(Stakeholder(name=u_name, roles=["airo:AIUser"]))

    for subject in ai_system_data.get("hasAISubject", []):
        s_name = subject if isinstance(subject, str) else subject.get("name", "")
        if s_name:
            stakeholders.append(Stakeholder(name=s_name, roles=["airo:AISubject"]))

    # Project risks to policies
    policies = [project_risk_to_policy(r) for r in risks]

    # Attach risk controls to all policies
    if control_descriptions:
        policies = [
            Policy(
                policy_concept=p.policy_concept,
                concept_definition=p.concept_definition,
                risk_controls=control_descriptions,
            )
            for p in policies
        ]

    # Build purpose from ai_system or top-level
    purpose = ai_system_data.get("hasPurpose", [])
    if isinstance(purpose, str):
        purpose = [purpose]

    return PolicyProfile(
        organization=organization,
        domain=domain,
        purpose=purpose,
        ai_systems=ai_systems,
        stakeholders=stakeholders,
        policies=policies,
    )
```

- [ ] **Step 8: Run all nexus adapter tests**

Run: `cd refiner && uv run pytest tests/test_nexus_adapter.py -v`
Expected: All 6 tests PASS

- [ ] **Step 9: Commit**

```bash
git add refiner/src/refiner/nexus_adapter.py refiner/tests/test_nexus_adapter.py
git commit -m "feat(nexus_adapter): Risk → Policy projection and AiSystem → PolicyProfile conversion

Implements Layer A of the UGA–ORT semantic bridge. Nexus AiSystem
payloads with Risk entities are projected into PolicyProfile inputs
using Risk.concern as the policy definition."
```

---

### Task 3: Add nexus input format to CLI

**Files:**
- Modify: `refiner/src/refiner/cli.py:181-189` (input format detection)
- Test: `refiner/tests/test_nexus_adapter.py` (add CLI-level roundtrip test)

- [ ] **Step 1: Write failing test for nexus format detection**

Add to `refiner/tests/test_nexus_adapter.py`:

```python
import json
from pathlib import Path


def test_detect_nexus_format(tmp_path):
    from refiner.nexus_adapter import detect_nexus_format
    nexus_payload = {
        "ai_system": {"name": "Test"},
        "risks": [{"id": "r1", "name": "Risk", "concern": "Concern."}],
    }
    path = tmp_path / "use-case.json"
    path.write_text(json.dumps(nexus_payload))
    raw = json.loads(path.read_text())
    assert detect_nexus_format(raw) is True

    flat_array = [{"policy_concept": "Fraud", "concept_definition": "..."}]
    assert detect_nexus_format(flat_array) is False

    profile = {"airo_version": "0.2", "policies": []}
    assert detect_nexus_format(profile) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd refiner && uv run pytest tests/test_nexus_adapter.py::test_detect_nexus_format -v`
Expected: FAIL with `ImportError: cannot import name 'detect_nexus_format'`

- [ ] **Step 3: Implement detect_nexus_format**

Add to `refiner/src/refiner/nexus_adapter.py`:

```python
def detect_nexus_format(raw: dict | list) -> bool:
    """Detect whether a parsed JSON payload is in nexus format.

    Nexus format is a dict with 'risks' key (list of Risk entities)
    and optionally 'ai_system'. Distinguished from PolicyProfile
    (which has 'policies') and flat arrays.
    """
    if isinstance(raw, list):
        return False
    if not isinstance(raw, dict):
        return False
    if "policies" in raw:
        return False
    return "risks" in raw
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd refiner && uv run pytest tests/test_nexus_adapter.py::test_detect_nexus_format -v`
Expected: PASS

- [ ] **Step 5: Update CLI input detection in cli.py**

In `refiner/src/refiner/cli.py`, update the input detection block (around line 181-189). Add the nexus adapter import at the top of the file:

```python
from refiner.nexus_adapter import detect_nexus_format, nexus_to_policy_profile
```

Update the format detection in the `run` command:

```python
    # Load policies — detect flat array vs enriched PolicyProfile vs nexus format
    raw = json.loads(policy_json.read_text())
    if isinstance(raw, list):
        policies = [Policy(**p) for p in raw]
        policy_profile = None
    elif detect_nexus_format(raw):
        doc = nexus_to_policy_profile(raw)
        policies = doc.policies
        policy_profile = doc
        typer.echo(f"Detected nexus format: {len(policies)} risks projected to policies")
    else:
        doc = PolicyProfile(**raw)
        policies = doc.policies
        policy_profile = doc
```

- [ ] **Step 6: Write integration test with a nexus input file**

Create a test fixture and test in `refiner/tests/test_nexus_adapter.py`:

```python
def test_nexus_payload_roundtrip_to_profile():
    payload = {
        "ai_system": {
            "name": "Fraud Detection System",
            "isAppliedWithinDomain": "finance",
            "isDevelopedBy": {"name": "FinTech Corp"},
            "hasAISubject": [{"name": "Bank Customer"}],
            "hasEuRiskCategory": "high",
        },
        "risks": [
            {
                "id": "atlas-social-engineering",
                "name": "Social Engineering",
                "concern": "An AI model may generate content used to manipulate individuals.",
            },
        ],
        "risk_controls": [
            {"name": "Content filtering", "description": "Apply output content filters."},
        ],
    }
    profile = nexus_to_policy_profile(payload)

    # Verify full roundtrip to dict and back
    d = profile.model_dump()
    restored = PolicyProfile(**d)
    assert restored.domain == "finance"
    assert restored.ai_systems[0].name == "Fraud Detection System"
    assert restored.policies[0].policy_concept == "Social Engineering"
    assert restored.policies[0].risk_controls == ["Apply output content filters."]
```

- [ ] **Step 7: Run all tests**

Run: `cd refiner && uv run pytest tests/test_nexus_adapter.py -v`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
git add refiner/src/refiner/nexus_adapter.py refiner/src/refiner/cli.py refiner/tests/test_nexus_adapter.py
git commit -m "feat(cli): accept nexus-format input (AiSystem + risks)

Adds detect_nexus_format() to auto-detect nexus payloads alongside
existing flat-array and PolicyProfile formats. Nexus risks are
projected to policies via Risk.concern."
```

---

### Task 4: Create ort-to-uga.sssom.tsv output alignment

**Files:**
- Create: `refiner/data/ort-to-uga.sssom.tsv`

- [ ] **Step 1: Create the SSSOM file**

Create `refiner/data/ort-to-uga.sssom.tsv`:

```tsv
# curie_map:
#   ort: https://taxonomy-refiner.io/schema/
#   nexus: https://ibm.github.io/ai-atlas-nexus/
#   airo: https://w3id.org/airo#
#   skos: http://www.w3.org/2004/02/skos/core#
#   semapv: https://w3id.org/semapv/vocab/
#
# mapping_set_id: ort-to-uga-output-alignment
# mapping_set_description: Maps ORT pipeline outputs to AI Atlas Nexus LinkML schema classes for UGA consumption
# mapping_set_version: 0.1
# mapping_date: 2026-04-16
# mapping_tool: manual
# license: https://creativecommons.org/licenses/by/4.0/
subject_id	subject_label	predicate_id	object_id	object_label	mapping_justification	confidence
ort:RiskDetail.risk_id	Risk Detail ID	skos:exactMatch	nexus:Risk.id	Risk ID	semapv:ManualMappingCuration	0.95
ort:RiskDetail.risk_name	Risk Detail Name	skos:exactMatch	nexus:Risk.name	Risk Name	semapv:ManualMappingCuration	0.95
ort:RiskDetail.cross_mappings	Risk Cross Mappings	skos:exactMatch	nexus:Risk.related_mappings	Risk Related Mappings	semapv:ManualMappingCuration	0.95
ort:RiskDetail.related_actions	Risk Related Actions	skos:exactMatch	nexus:Risk.hasRelatedAction	Risk Has Related Action	semapv:ManualMappingCuration	0.95
ort:PolicyRiskMapping.distance	Match Distance	skos:relatedMatch	nexus:AiEvalResult.value	Evaluation Result Value	semapv:ManualMappingCuration	0.70
ort:JudgeScore.subtlety	Judge Subtlety Score	skos:closeMatch	nexus:AiEvalResult	AI Evaluation Result	semapv:ManualMappingCuration	0.80
ort:JudgeScore.plausibility	Judge Plausibility Score	skos:closeMatch	nexus:AiEvalResult	AI Evaluation Result	semapv:ManualMappingCuration	0.80
ort:JudgeScore.domain_grounding	Judge Domain Grounding Score	skos:closeMatch	nexus:AiEvalResult	AI Evaluation Result	semapv:ManualMappingCuration	0.80
ort:JudgeScore.policy_relevance	Judge Policy Relevance Score	skos:closeMatch	nexus:AiEvalResult	AI Evaluation Result	semapv:ManualMappingCuration	0.80
ort:EmittedPrompt	Emitted Adversarial Prompt	skos:broadMatch	nexus:Fact.value	Fact Value	semapv:ManualMappingCuration	0.60
ort:EmittedPrompt.risk_id	Emitted Prompt Risk ID	skos:exactMatch	nexus:Risk.id	Risk ID	semapv:ManualMappingCuration	0.95
ort:Coverage.risks_matched	Risks Matched Count	skos:relatedMatch	nexus:AiEvalResult	AI Evaluation Result	semapv:ManualMappingCuration	0.65
ort:PromptMetrics.semantic_diversity	Semantic Diversity Score	skos:relatedMatch	nexus:AiEvalResult	AI Evaluation Result	semapv:ManualMappingCuration	0.60
ort:RiskLandscape.framework_coverage	Framework Coverage	skos:relatedMatch	nexus:Risk.isDefinedByTaxonomy	Risk Taxonomy Source	semapv:ManualMappingCuration	0.65
```

- [ ] **Step 2: Verify the file parses correctly**

Run: `cd refiner && python -c "import csv; rows = list(csv.DictReader(open('data/ort-to-uga.sssom.tsv'), delimiter='\t')); print(f'{len(rows)} mappings loaded'); assert len(rows) == 14"`
Expected: `14 mappings loaded`

- [ ] **Step 3: Commit**

```bash
git add refiner/data/ort-to-uga.sssom.tsv
git commit -m "data: add ort-to-uga.sssom.tsv output alignment mappings

Layer B of the UGA–ORT semantic bridge. Maps ORT pipeline outputs
(RiskDetail, judge scores, emitted prompts, coverage metrics) to
nexus schema classes where semantic correspondence exists."
```

---

### Task 5: Create nexus format example policy file

**Files:**
- Create: `policy_examples/nexus-healthcare.json`

- [ ] **Step 1: Create the example file**

Create `policy_examples/nexus-healthcare.json`:

```json
{
  "ai_system": {
    "name": "Medical Triage Chatbot",
    "description": "An AI-assisted system for initial patient symptom assessment and triage prioritization in emergency departments.",
    "hasPurpose": ["symptom assessment", "triage prioritization", "patient routing"],
    "isAppliedWithinDomain": "healthcare",
    "isDevelopedBy": {"name": "HealthTech Solutions"},
    "isDeployedBy": {"name": "City General Hospital"},
    "hasAIUser": [
      {"name": "Emergency nurse"},
      {"name": "Triage coordinator"}
    ],
    "hasAISubject": [
      {"name": "Emergency patient"},
      {"name": "Patient family member"}
    ],
    "hasEuRiskCategory": "high"
  },
  "risks": [
    {
      "id": "atlas-generating-inaccurate-output",
      "name": "Generating Inaccurate Output",
      "concern": "An AI model may produce medically inaccurate triage recommendations, potentially leading to incorrect prioritization of patient severity and delayed treatment for critical cases."
    },
    {
      "id": "atlas-personal-information-in-prompt",
      "name": "Personal Information in Prompt",
      "concern": "Protected health information (PHI) including patient symptoms, medical history, and identifying details may be included in prompts sent to the AI model, risking HIPAA violations."
    },
    {
      "id": "atlas-societal-bias",
      "name": "Societal Bias",
      "concern": "The triage system may exhibit bias based on patient demographics such as race, gender, or socioeconomic status, leading to inequitable care prioritization."
    }
  ],
  "risk_controls": [
    {"name": "Clinical validation", "description": "All AI triage recommendations must be reviewed by a qualified healthcare professional before acting on them."},
    {"name": "PHI minimization", "description": "Minimize protected health information in prompts through de-identification and data masking techniques."}
  ]
}
```

- [ ] **Step 2: Verify it parses via the adapter**

Run: `cd refiner && python -c "
import json
from refiner.nexus_adapter import detect_nexus_format, nexus_to_policy_profile
raw = json.loads(open('../policy_examples/nexus-healthcare.json').read())
assert detect_nexus_format(raw)
profile = nexus_to_policy_profile(raw)
print(f'Domain: {profile.domain}')
print(f'Org: {profile.organization.name}')
print(f'Systems: {len(profile.ai_systems)}')
print(f'Policies: {len(profile.policies)}')
print(f'Stakeholders: {len(profile.stakeholders)}')
for p in profile.policies:
    print(f'  - {p.policy_concept}: {p.concept_definition[:60]}...')
"`

Expected output:
```
Domain: healthcare
Org: HealthTech Solutions
Systems: 1
Policies: 3
Stakeholders: 4
  - Generating Inaccurate Output: An AI model may produce medically inaccurate triage recomme...
  - Personal Information in Prompt: Protected health information (PHI) including patient symptom...
  - Societal Bias: The triage system may exhibit bias based on patient demograp...
```

- [ ] **Step 3: Commit**

```bash
git add policy_examples/nexus-healthcare.json
git commit -m "docs: add nexus-format healthcare example policy

Demonstrates the UGA–ORT input projection: a nexus AiSystem payload
with risks and risk_controls, consumable directly by the ORT pipeline."
```

---

### Task 6: Run full test suite and fix any regressions

**Files:**
- Modify: any files with test failures

- [ ] **Step 1: Run the full refiner test suite**

Run: `cd refiner && uv run pytest tests/ -v`
Expected: All tests pass. If any fail due to `GovernedSystem` rename, fix them.

- [ ] **Step 2: Grep for any remaining GovernedSystem references**

Run: `cd refiner && grep -rn "GovernedSystem" src/ tests/`
Expected: No results. If any remain, update them to `AiSystem`.

- [ ] **Step 3: Verify existing policy files still load correctly**

Run: `cd refiner && python -c "
import json
from refiner.models import Policy, PolicyProfile
# Flat array format
raw = json.loads(open('../policy_examples/swb.json').read())
assert isinstance(raw, list)
policies = [Policy(**p) for p in raw]
print(f'swb.json: {len(policies)} policies')
# Generic format
raw2 = json.loads(open('../policy_examples/generic.json').read())
policies2 = [Policy(**p) for p in raw2]
print(f'generic.json: {len(policies2)} policies')
print('All existing formats load correctly')
"`

Expected:
```
swb.json: 6 policies
generic.json: 8 policies
All existing formats load correctly
```

- [ ] **Step 4: Commit any regression fixes**

If any fixes were needed:
```bash
git add -u
git commit -m "fix: address regressions from GovernedSystem → AiSystem rename"
```
