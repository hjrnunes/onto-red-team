import pytest
from dataclasses import dataclass, field


@dataclass
class MockRisk:
    id: str
    name: str
    description: str = ""
    concern: str = ""
    tag: str = ""
    risk_type: str = "output"
    descriptor: list = field(default_factory=list)
    isDefinedByTaxonomy: str = ""
    isPartOf: str = ""
    exact_mappings: list = field(default_factory=list)
    close_mappings: list = field(default_factory=list)
    broad_mappings: list = field(default_factory=list)
    narrow_mappings: list = field(default_factory=list)
    related_mappings: list = field(default_factory=list)
    hasRelatedAction: list = field(default_factory=list)
    type: str = "Risk"


@dataclass
class MockAction:
    id: str
    name: str
    description: str = ""
    type: str = "Action"


@dataclass
class MockTaxonomy:
    id: str
    name: str
    description: str = ""
    type: str = "RiskTaxonomy"


@dataclass
class MockGroup:
    id: str
    name: str
    isDefinedByTaxonomy: str = ""
    type: str = "RiskGroup"


MOCK_RISKS = [
    MockRisk(
        id="atlas-prompt-injection",
        name="Prompt injection",
        description="An attacker crafts input to manipulate an LLM.",
        concern="Attackers can override system instructions.",
        tag="prompt-injection",
        isDefinedByTaxonomy="ibm-risk-atlas",
        isPartOf="ibm-risk-atlas-robustness",
        exact_mappings=["llm01-prompt-injection"],
        related_mappings=["atlas-jailbreaking"],
    ),
    MockRisk(
        id="atlas-confidential-data-in-prompt",
        name="Confidential data in prompt",
        description="Users may inadvertently or intentionally include confidential information in prompts.",
        concern="Sensitive data may be exposed or logged.",
        tag="confidential-data-in-prompt",
        isDefinedByTaxonomy="ibm-risk-atlas",
        isPartOf="ibm-risk-atlas-privacy",
        close_mappings=["llm022025-sensitive-information-disclosure"],
    ),
    MockRisk(
        id="llm01-prompt-injection",
        name="LLM01: Prompt Injection",
        description="Prompt injection involves crafting inputs that alter the LLM's behavior.",
        concern="May lead to unauthorized actions or data exposure.",
        tag="llm01",
        isDefinedByTaxonomy="owasp-llm-top-10",
        isPartOf="owasp-llm-top-10-group",
    ),
    MockRisk(
        id="llm022025-sensitive-information-disclosure",
        name="LLM02: Sensitive Information Disclosure",
        description="LLMs may reveal sensitive information in responses.",
        concern="Confidential data leakage through model outputs.",
        tag="llm02",
        isDefinedByTaxonomy="owasp-llm-top-10",
        isPartOf="owasp-llm-top-10-group",
    ),
    MockRisk(
        id="atlas-social-hacking-attack",
        name="Social hacking attack",
        description="An attacker uses social engineering to manipulate users via AI.",
        concern="Users may be tricked into unsafe actions.",
        tag="social-hacking-attack",
        isDefinedByTaxonomy="ibm-risk-atlas",
        isPartOf="ibm-risk-atlas-misuse",
    ),
]

MOCK_ACTIONS = [
    MockAction(
        id="action-input-validation",
        name="Input validation",
        description="Validate and sanitize all inputs before processing.",
    ),
    MockAction(
        id="action-output-filtering",
        name="Output filtering",
        description="Filter model outputs to remove sensitive information.",
    ),
]

MOCK_TAXONOMIES = [
    MockTaxonomy(id="ibm-risk-atlas", name="IBM AI Risk Atlas", description="Comprehensive AI risk taxonomy"),
    MockTaxonomy(id="owasp-llm-top-10", name="OWASP Top 10 for LLMs", description="Top 10 LLM vulnerabilities"),
]

MOCK_GROUPS = [
    MockGroup(id="ibm-risk-atlas-robustness", name="Robustness", isDefinedByTaxonomy="ibm-risk-atlas"),
    MockGroup(id="ibm-risk-atlas-privacy", name="Privacy", isDefinedByTaxonomy="ibm-risk-atlas"),
    MockGroup(id="ibm-risk-atlas-misuse", name="Misuse", isDefinedByTaxonomy="ibm-risk-atlas"),
    MockGroup(id="owasp-llm-top-10-group", name="OWASP LLM Top 10", isDefinedByTaxonomy="owasp-llm-top-10"),
]

# Link actions to risks
MOCK_RISKS[0].hasRelatedAction = ["action-input-validation"]
MOCK_RISKS[1].hasRelatedAction = ["action-output-filtering"]


@pytest.fixture
def chroma_dir(tmp_path):
    d = tmp_path / "chroma"
    d.mkdir()
    return d


@pytest.fixture
def mock_risks():
    return MOCK_RISKS


@pytest.fixture
def mock_actions():
    return MOCK_ACTIONS


@pytest.fixture
def mock_taxonomies():
    return MOCK_TAXONOMIES


@pytest.fixture
def mock_groups():
    return MOCK_GROUPS
