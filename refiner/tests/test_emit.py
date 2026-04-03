import json

import yaml

from refiner.models import AxisEnumeration, DomainContextProfile, DomainContextAxis, SampledAxis
from refiner.emit import relevance_weights, sample_axes, build_prompt, load_domain_context, load_policies


def _enum(relevance):
    return AxisEnumeration(
        class_uri="http://example.org/X",
        class_label="X",
        source_ontology="CCO",
        relevance=relevance,
    )


def test_relevance_weights_high_medium_low():
    enums = [_enum("high"), _enum("medium"), _enum("low")]
    weights = relevance_weights(enums)
    assert len(weights) == 3
    assert abs(sum(weights) - 1.0) < 1e-9
    # high=3, medium=2, low=1 → total=6
    assert abs(weights[0] - 0.5) < 1e-9
    assert abs(weights[1] - 1/3) < 1e-9
    assert abs(weights[2] - 1/6) < 1e-9


def test_relevance_weights_all_same():
    enums = [_enum("high"), _enum("high"), _enum("high")]
    weights = relevance_weights(enums)
    for w in weights:
        assert abs(w - 1/3) < 1e-9


def test_relevance_weights_single():
    enums = [_enum("low")]
    weights = relevance_weights(enums)
    assert weights == [1.0]


def _make_profile():
    return DomainContextProfile(
        risk_id="r1",
        risk_name="Risk One",
        policy_concept="Fraud",
        axes=[
            DomainContextAxis(
                cco_class_uri="http://example.org/Person",
                cco_class_label="Person",
                roles=["agent"],
                enumerations=[
                    _enum("high"),
                    AxisEnumeration(class_uri="http://example.org/Manager", class_label="Manager", source_ontology="FIBO", relevance="medium"),
                ],
            ),
            DomainContextAxis(
                cco_class_uri="http://example.org/Instrument",
                cco_class_label="Instrument",
                roles=["instrument"],
                enumerations=[
                    AxisEnumeration(class_uri="http://example.org/Bond", class_label="Bond", source_ontology="FIBO", relevance="high"),
                ],
            ),
        ],
    )


def test_sample_axes_returns_sampled_axes():
    import random
    random.seed(42)
    profile = _make_profile()
    samples = sample_axes(profile, n=5)
    assert len(samples) > 0
    for sample in samples:
        assert len(sample) == 2  # two axes
        for sa in sample:
            assert isinstance(sa, SampledAxis)
            assert sa.roles in (["agent"], ["instrument"])


def test_sample_axes_deduplicates():
    # One enumeration per axis → only 1 unique combination possible
    profile = DomainContextProfile(
        risk_id="r1", risk_name="R", policy_concept="P",
        axes=[
            DomainContextAxis(
                cco_class_uri="http://example.org/A",
                cco_class_label="A",
                roles=["agent"],
                enumerations=[_enum("high")],
            ),
        ],
    )
    samples = sample_axes(profile, n=10)
    assert len(samples) == 1


def test_sample_axes_skips_empty_axes():
    profile = DomainContextProfile(
        risk_id="r1", risk_name="R", policy_concept="P",
        axes=[
            DomainContextAxis(
                cco_class_uri="http://example.org/A",
                cco_class_label="A",
                roles=["agent"],
                enumerations=[_enum("high")],
            ),
            DomainContextAxis(
                cco_class_uri="http://example.org/B",
                cco_class_label="B",
                roles=["object"],
                enumerations=[],  # empty — should be skipped
            ),
        ],
    )
    samples = sample_axes(profile, n=5)
    for sample in samples:
        assert len(sample) == 1  # only the non-empty axis
        assert sample[0].roles == ["agent"]


def test_sample_axes_reproducible_with_seed():
    import random
    profile = _make_profile()
    random.seed(99)
    samples_a = sample_axes(profile, n=5)
    random.seed(99)
    samples_b = sample_axes(profile, n=5)
    assert samples_a == samples_b


def test_build_prompt_returns_messages():
    axes = [
        SampledAxis(
            cco_class_uri="http://example.org/Person",
            cco_class_label="Person",
            roles=["agent"],
            sampled_uri="http://example.org/Manager",
            sampled_label="Manager",
            source_ontology="FIBO",
            relevance="high",
        ),
    ]
    messages = build_prompt("Fraud", "About fraud", "Financial Fraud", axes)
    assert isinstance(messages, list)
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"


def test_build_prompt_system_message_content():
    messages = build_prompt("X", "Y", "Z", [])
    system = messages[0]["content"]
    assert "red-team scenario writer" in system
    assert "subtlety" in system.lower()


def test_build_prompt_user_message_has_policy():
    axes = [
        SampledAxis(
            cco_class_uri="http://example.org/Person",
            cco_class_label="Person",
            roles=["agent"],
            sampled_uri="http://example.org/Manager",
            sampled_label="Manager",
            source_ontology="FIBO",
            relevance="high",
        ),
    ]
    messages = build_prompt("Fraud", "About fraud", "Financial Fraud", axes)
    user = messages[1]["content"]
    assert "Fraud" in user
    assert "About fraud" in user
    assert "Financial Fraud" in user


def test_build_prompt_user_message_has_axes():
    axes = [
        SampledAxis(
            cco_class_uri="http://example.org/Person",
            cco_class_label="Person",
            roles=["agent"],
            sampled_uri="http://example.org/Manager",
            sampled_label="Manager",
            source_ontology="FIBO",
            relevance="high",
        ),
        SampledAxis(
            cco_class_uri="http://example.org/Instrument",
            cco_class_label="Instrument",
            roles=["instrument"],
            sampled_uri="http://example.org/Bond",
            sampled_label="Bond",
            source_ontology="FIBO",
            relevance="high",
        ),
    ]
    messages = build_prompt("X", "Y", "Z", axes)
    user = messages[1]["content"]
    assert "agent" in user
    assert "Manager" in user
    assert "Person" in user
    assert "instrument" in user
    assert "Bond" in user


def test_load_domain_context(tmp_path):
    profiles_data = {
        "profiles": [
            {
                "risk_id": "r1",
                "risk_name": "Risk One",
                "policy_concept": "Fraud",
                "axes": [
                    {
                        "cco_class_uri": "http://example.org/Person",
                        "cco_class_label": "Person",
                        "roles": ["agent"],
                        "enumerations": [
                            {"class_uri": "http://example.org/Manager", "class_label": "Manager", "source_ontology": "FIBO", "relevance": "high"},
                        ],
                    },
                ],
            },
        ],
    }
    p = tmp_path / "test-domain-context.yaml"
    p.write_text(yaml.dump(profiles_data))
    result = load_domain_context(p)
    assert len(result) == 1
    assert result[0].risk_id == "r1"
    assert result[0].axes[0].enumerations[0].class_label == "Manager"


def test_load_policies(tmp_path):
    policies = [
        {"policy_concept": "Fraud", "concept_definition": "About fraud"},
        {"policy_concept": "Violence", "concept_definition": "About violence"},
    ]
    p = tmp_path / "policies.json"
    p.write_text(json.dumps(policies))
    result, doc_ctx = load_policies(p)
    assert doc_ctx is None
    assert "Fraud" in result
    assert result["Fraud"].concept_definition == "About fraud"
    assert "Violence" in result


def test_load_policies_enriched_format(tmp_path):
    doc = {
        "airo_version": "0.2",
        "organization": "Test Org",
        "domain": "healthcare",
        "policies": [
            {
                "policy_concept": "PHI",
                "concept_definition": "No PII",
                "boundary_examples": [
                    {"prohibited": "enter patient data", "acceptable": "draft template"}
                ],
                "acceptable_uses": ["non-clinical drafting"],
            },
        ],
    }
    p = tmp_path / "enriched.json"
    p.write_text(json.dumps(doc))

    policies, doc_context = load_policies(p)
    assert "PHI" in policies
    assert doc_context is not None
    assert doc_context.organization == "Test Org"
    assert len(policies["PHI"].boundary_examples) == 1


def test_build_prompt_with_boundary_examples():
    from refiner.models import Policy, BoundaryExample, PolicyDocument

    policy = Policy(
        policy_concept="Clinical",
        concept_definition="No clinical decisions",
        boundary_examples=[
            BoundaryExample(prohibited="care plan for John", acceptable="summarise guidelines")
        ],
        acceptable_uses=["General health concepts"],
    )
    doc_ctx = PolicyDocument(
        organization="NHS Trust",
        domain="healthcare",
        ai_subjects=["patients"],
    )

    messages = build_prompt("Clinical", "No clinical decisions", "Misdiagnosis", [], policy=policy, doc_context=doc_ctx)
    user_msg = messages[1]["content"]
    assert "PROHIBITED: care plan for John" in user_msg
    assert "ACCEPTABLE: summarise guidelines" in user_msg
    assert "General health concepts" in user_msg
    assert "NHS Trust" in user_msg
    assert "patients" in user_msg


def test_build_prompt_without_enrichments():
    messages = build_prompt("Fraud", "About fraud", "Financial Fraud", [])
    user_msg = messages[1]["content"]
    assert "PROHIBITED:" not in user_msg
    assert "About fraud" in user_msg


from refiner.emit import emit


def _write_test_files(tmp_path):
    """Write domain context YAML and policy JSON for testing."""
    profiles_data = {
        "profiles": [
            {
                "risk_id": "r1",
                "risk_name": "Risk One",
                "policy_concept": "Fraud",
                "axes": [
                    {
                        "cco_class_uri": "http://example.org/Person",
                        "cco_class_label": "Person",
                        "roles": ["agent"],
                        "enumerations": [
                            {"class_uri": "http://example.org/Manager", "class_label": "Manager", "source_ontology": "FIBO", "relevance": "high"},
                            {"class_uri": "http://example.org/Employee", "class_label": "Employee", "source_ontology": "CCO", "relevance": "medium"},
                        ],
                    },
                ],
            },
        ],
    }
    dc_path = tmp_path / "test-domain-context.yaml"
    dc_path.write_text(yaml.dump(profiles_data))

    policies = [{"policy_concept": "Fraud", "concept_definition": "About fraud"}]
    pol_path = tmp_path / "policies.json"
    pol_path.write_text(json.dumps(policies))
    return dc_path, pol_path


def test_emit_writes_jsonl(tmp_path):
    _write_test_files(tmp_path)
    pol_path = tmp_path / "policies.json"
    out_path = tmp_path / "dataset.jsonl"
    emit(tmp_path, pol_path, samples_per_risk=3, output_path=out_path, seed=42)
    assert out_path.exists()
    lines = out_path.read_text().strip().split("\n")
    assert len(lines) > 0
    row = json.loads(lines[0])
    assert "generation_prompt" in row
    assert "policy_concept" in row
    assert "risk_id" in row
    assert "risk_name" in row
    assert "sampled_axes" in row
    assert "domain_context_axes" in row
    assert row["policy_concept"] == "Fraud"
    assert row["risk_id"] == "r1"
    # domain_context_axes should contain the full axis definitions
    dc_axes = row["domain_context_axes"]
    assert isinstance(dc_axes, list)
    assert len(dc_axes) == 1  # one axis in test fixture
    assert dc_axes[0]["cco_class_label"] == "Person"
    assert len(dc_axes[0]["enumerations"]) == 2  # Manager + Employee


def test_emit_generation_prompt_is_messages(tmp_path):
    _write_test_files(tmp_path)
    pol_path = tmp_path / "policies.json"
    out_path = tmp_path / "dataset.jsonl"
    emit(tmp_path, pol_path, samples_per_risk=1, output_path=out_path, seed=42)
    row = json.loads(out_path.read_text().strip().split("\n")[0])
    messages = row["generation_prompt"]
    assert isinstance(messages, list)
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"


def test_emit_discovers_domain_context_file(tmp_path):
    _write_test_files(tmp_path)
    pol_path = tmp_path / "policies.json"
    out_path = tmp_path / "dataset.jsonl"
    emit(tmp_path, pol_path, samples_per_risk=1, output_path=out_path, seed=1)
    assert out_path.exists()


def test_emit_fails_no_domain_context(tmp_path):
    pol_path = tmp_path / "policies.json"
    pol_path.write_text('[{"policy_concept": "X", "concept_definition": "Y"}]')
    out_path = tmp_path / "dataset.jsonl"
    import pytest
    with pytest.raises(SystemExit):
        emit(tmp_path, pol_path, samples_per_risk=1, output_path=out_path)


def test_emit_fails_multiple_domain_context(tmp_path):
    (tmp_path / "a-domain-context.yaml").write_text("profiles: []")
    (tmp_path / "b-domain-context.yaml").write_text("profiles: []")
    pol_path = tmp_path / "policies.json"
    pol_path.write_text('[{"policy_concept": "X", "concept_definition": "Y"}]')
    out_path = tmp_path / "dataset.jsonl"
    import pytest
    with pytest.raises(SystemExit):
        emit(tmp_path, pol_path, samples_per_risk=1, output_path=out_path)


def test_emit_skips_risk_with_no_axes(tmp_path):
    profiles_data = {
        "profiles": [
            {
                "risk_id": "r1",
                "risk_name": "Risk One",
                "policy_concept": "Fraud",
                "axes": [],  # no axes
            },
        ],
    }
    dc_path = tmp_path / "test-domain-context.yaml"
    dc_path.write_text(yaml.dump(profiles_data))
    pol_path = tmp_path / "policies.json"
    pol_path.write_text('[{"policy_concept": "Fraud", "concept_definition": "About fraud"}]')
    out_path = tmp_path / "dataset.jsonl"
    emit(tmp_path, pol_path, samples_per_risk=5, output_path=out_path, seed=1)
    content = out_path.read_text().strip()
    assert content == ""


def test_emit_empty_profiles(tmp_path):
    dc_path = tmp_path / "test-domain-context.yaml"
    dc_path.write_text(yaml.dump({"profiles": []}))
    pol_path = tmp_path / "policies.json"
    pol_path.write_text('[{"policy_concept": "X", "concept_definition": "Y"}]')
    out_path = tmp_path / "dataset.jsonl"
    emit(tmp_path, pol_path, samples_per_risk=5, output_path=out_path, seed=1)
    assert out_path.read_text().strip() == ""


def test_emit_skips_missing_policy_concept(tmp_path):
    profiles_data = {
        "profiles": [
            {
                "risk_id": "r1",
                "risk_name": "Risk One",
                "policy_concept": "Unknown",
                "axes": [
                    {
                        "cco_class_uri": "http://example.org/A",
                        "cco_class_label": "A",
                        "roles": ["agent"],
                        "enumerations": [
                            {
                                "class_uri": "http://example.org/E1",
                                "class_label": "E1",
                                "source_ontology": "X",
                                "relevance": "high",
                            },
                        ],
                    },
                ],
            },
        ],
    }
    dc_path = tmp_path / "test-domain-context.yaml"
    dc_path.write_text(yaml.dump(profiles_data))
    pol_path = tmp_path / "policies.json"
    pol_path.write_text('[{"policy_concept": "Fraud", "concept_definition": "About fraud"}]')
    out_path = tmp_path / "dataset.jsonl"
    emit(tmp_path, pol_path, samples_per_risk=5, output_path=out_path, seed=1)
    assert out_path.read_text().strip() == ""


from typer.testing import CliRunner
from refiner.cli import app

runner = CliRunner()


def test_emit_cli_command(tmp_path):
    _write_test_files(tmp_path)
    pol_path = tmp_path / "policies.json"
    out_path = tmp_path / "dataset.jsonl"
    result = runner.invoke(app, [
        "emit", str(tmp_path),
        "--policies", str(pol_path),
        "--samples-per-risk", "2",
        "--seed", "42",
        "--output", str(out_path),
    ])
    assert result.exit_code == 0, result.output
    assert out_path.exists()
    lines = out_path.read_text().strip().split("\n")
    assert len(lines) > 0


def test_emit_cli_default_output(tmp_path):
    _write_test_files(tmp_path)
    pol_path = tmp_path / "policies.json"
    result = runner.invoke(app, [
        "emit", str(tmp_path),
        "--policies", str(pol_path),
        "--samples-per-risk", "1",
        "--seed", "1",
    ])
    assert result.exit_code == 0, result.output
    default_out = tmp_path / "dataset.jsonl"
    assert default_out.exists()


def test_emit_cli_missing_policies(tmp_path):
    result = runner.invoke(app, [
        "emit", str(tmp_path),
        "--policies", str(tmp_path / "nonexistent.json"),
    ])
    assert result.exit_code != 0


# --- Quick-win fixes (gen3 assessment) ---

from refiner.emit import _strip_framework_suffix, _fuzzy_match_policy
from refiner.models import Policy


def test_strip_framework_suffix_atlas():
    assert _strip_framework_suffix("Spamming AI System with Chaff Data - ATLAS") == "Spamming AI System with Chaff Data"


def test_strip_framework_suffix_attack_ics():
    assert _strip_framework_suffix("Rootkit - ATTACK ICS") == "Rootkit"


def test_strip_framework_suffix_attack_mobile():
    assert _strip_framework_suffix("Masquerading - ATTACK Mobile") == "Masquerading"


def test_strip_framework_suffix_attack():
    assert _strip_framework_suffix("Spearphishing Attachment - ATTACK") == "Spearphishing Attachment"


def test_strip_framework_suffix_sparta():
    assert _strip_framework_suffix("Jamming - SPARTA") == "Jamming"


def test_strip_framework_suffix_no_suffix():
    assert _strip_framework_suffix("Credit Card Fraud") == "Credit Card Fraud"


def test_strip_framework_suffix_in_prompt():
    axes = [
        SampledAxis(
            cco_class_uri="http://d3fend.mitre.org/ontologies/d3fend.owl#T1234",
            cco_class_label="Offensive Technique - ATLAS",
            roles=["instrument"],
            sampled_uri="http://d3fend.mitre.org/ontologies/d3fend.owl#T5678",
            sampled_label="Extract AI Model - ATLAS",
            source_ontology="D3FEND",
            relevance="high",
        ),
    ]
    messages = build_prompt("X", "Y", "Z", axes)
    user = messages[1]["content"]
    assert "Extract AI Model" in user
    assert " - ATLAS" not in user


def test_fuzzy_match_policy_suffix_added():
    policy_map = {
        "Clinical Diagnosis & Treatment": Policy(
            policy_concept="Clinical Diagnosis & Treatment",
            concept_definition="About clinical decisions",
        ),
    }
    result = _fuzzy_match_policy("Clinical Diagnosis & Treatment Restriction", policy_map)
    assert result is not None
    assert result.policy_concept == "Clinical Diagnosis & Treatment"


def test_fuzzy_match_policy_suffix_handling():
    policy_map = {
        "Protected Health Information": Policy(
            policy_concept="Protected Health Information",
            concept_definition="About PHI",
        ),
    }
    result = _fuzzy_match_policy("Protected Health Information Handling", policy_map)
    assert result is not None
    assert result.policy_concept == "Protected Health Information"


def test_fuzzy_match_policy_no_match():
    policy_map = {
        "Fraud": Policy(policy_concept="Fraud", concept_definition="About fraud"),
    }
    result = _fuzzy_match_policy("Clinical Diagnosis", policy_map)
    assert result is None


def test_fuzzy_match_policy_case_insensitive():
    policy_map = {
        "Protected Health Information": Policy(
            policy_concept="Protected Health Information",
            concept_definition="About PHI",
        ),
    }
    result = _fuzzy_match_policy("protected health information handling", policy_map)
    assert result is not None


def test_sample_axes_caps_at_combinatorial_space():
    """When space is smaller than n, return at most space samples."""
    profile = DomainContextProfile(
        risk_id="r1", risk_name="R", policy_concept="P",
        axes=[
            DomainContextAxis(
                cco_class_uri="http://example.org/A",
                cco_class_label="A",
                roles=["agent"],
                enumerations=[_enum("high"), _enum("medium")],
            ),
            DomainContextAxis(
                cco_class_uri="http://example.org/B",
                cco_class_label="B",
                roles=["object"],
                enumerations=[_enum("high")],
            ),
        ],
    )
    # Space is 2 * 1 = 2, requesting 100 should return at most 2
    import random
    random.seed(42)
    samples = sample_axes(profile, n=100)
    assert len(samples) <= 2
