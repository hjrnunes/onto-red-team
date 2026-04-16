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
