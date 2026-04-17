import json
import random

import yaml

from refiner.models import (
    AxisEnumeration, DomainContext, DomainContextAxis, PolicyDomainContext,
    RiskGrounding, RiskSummary, SampledAxis, Stakeholder,
)
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


def _make_axes():
    """Build test axes used by _make_doc and standalone tests."""
    return [
        DomainContextAxis(
            cco_class_uri="http://example.org/Person",
            cco_class_label="Person",
            enumerations=[
                _enum("high"),
                AxisEnumeration(class_uri="http://example.org/Manager", class_label="Manager", source_ontology="FIBO", relevance="medium"),
            ],
        ),
        DomainContextAxis(
            cco_class_uri="http://example.org/Instrument",
            cco_class_label="Instrument",
            enumerations=[
                AxisEnumeration(class_uri="http://example.org/Bond", class_label="Bond", source_ontology="FIBO", relevance="high"),
            ],
        ),
    ]


def _make_doc():
    """Build a minimal DomainContext for tests."""
    axes = _make_axes()
    return DomainContext(
        risks=[RiskSummary(risk_id="r1", risk_name="Risk One")],
        policy_contexts=[
            PolicyDomainContext(
                policy_concept="Fraud",
                risk_groundings=[RiskGrounding(risk_id="r1", axes=axes)],
            ),
        ],
    )


def test_sample_axes_returns_sampled_axes():
    import random
    random.seed(42)
    axes = _make_axes()
    samples = sample_axes(axes, n=5)
    assert len(samples) > 0
    for sample in samples:
        assert len(sample) == 2  # two axes
        for sa in sample:
            assert isinstance(sa, SampledAxis)


def test_sample_axes_deduplicates():
    # One enumeration per axis → only 1 unique combination possible
    axes = [
        DomainContextAxis(
            cco_class_uri="http://example.org/A",
            cco_class_label="A",
            enumerations=[_enum("high")],
        ),
    ]
    samples = sample_axes(axes, n=10)
    assert len(samples) == 1


def test_sample_axes_skips_empty_axes():
    axes = [
        DomainContextAxis(
            cco_class_uri="http://example.org/A",
            cco_class_label="A",
            enumerations=[_enum("high")],
        ),
        DomainContextAxis(
            cco_class_uri="http://example.org/B",
            cco_class_label="B",
            enumerations=[],  # empty — should be skipped
        ),
    ]
    samples = sample_axes(axes, n=5)
    for sample in samples:
        assert len(sample) == 1  # only the non-empty axis


def test_sample_axes_reproducible_with_seed():
    import random
    axes = _make_axes()
    random.seed(99)
    samples_a = sample_axes(axes, n=5)
    random.seed(99)
    samples_b = sample_axes(axes, n=5)
    assert samples_a == samples_b


def test_build_prompt_returns_messages():
    axes = [
        SampledAxis(
            cco_class_uri="http://example.org/Person",
            cco_class_label="Person",
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
            sampled_uri="http://example.org/Manager",
            sampled_label="Manager",
            source_ontology="FIBO",
            relevance="high",
        ),
        SampledAxis(
            cco_class_uri="http://example.org/Instrument",
            cco_class_label="Instrument",
            sampled_uri="http://example.org/Bond",
            sampled_label="Bond",
            source_ontology="FIBO",
            relevance="high",
        ),
    ]
    messages = build_prompt("X", "Y", "Z", axes)
    user = messages[1]["content"]
    assert "Manager" in user
    assert "Person" in user
    assert "Bond" in user


def test_load_domain_context(tmp_path):
    doc_data = {
        "version": "0.1",
        "risks": [
            {"risk_id": "r1", "risk_name": "Test Risk"},
        ],
        "policy_contexts": [
            {
                "policy_concept": "Fraud",
                "risk_groundings": [
                    {
                        "risk_id": "r1",
                        "axes": [
                            {
                                "cco_class_uri": "http://example.org/Person",
                                "cco_class_label": "Person",
                                "enumerations": [
                                    {"class_uri": "http://example.org/Manager", "class_label": "Manager", "source_ontology": "FIBO", "relevance": "high"},
                                ],
                            },
                        ],
                    },
                ],
            },
        ],
    }
    p = tmp_path / "test-domain-context.yaml"
    p.write_text(yaml.dump(doc_data))
    result = load_domain_context(p)
    assert isinstance(result, DomainContext)
    assert len(result.risks) == 1
    assert result.risks[0].risk_id == "r1"
    assert len(result.policy_contexts) == 1
    assert result.policy_contexts[0].risk_groundings[0].axes[0].enumerations[0].class_label == "Manager"


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

    policies, policy_profile = load_policies(p)
    assert "PHI" in policies
    assert policy_profile is not None
    assert policy_profile.organization.name == "Test Org"
    assert len(policies["PHI"].boundary_examples) == 1


def test_build_prompt_with_boundary_examples():
    from refiner.models import Policy, BoundaryExample, PolicyProfile

    policy = Policy(
        policy_concept="Clinical",
        concept_definition="No clinical decisions",
        boundary_examples=[
            BoundaryExample(prohibited="care plan for John", acceptable="summarise guidelines")
        ],
        acceptable_uses=["General health concepts"],
    )
    doc_ctx = PolicyProfile(
        organization="NHS Trust",
        domain="healthcare",
        stakeholders=[Stakeholder(name="patients", roles=["airo:AISubject"])],
    )

    messages = build_prompt("Clinical", "No clinical decisions", "Misdiagnosis", [], policy=policy, policy_profile=doc_ctx)
    user_msg = messages[1]["content"]
    assert "PROHIBITED: care plan for John" in user_msg
    assert "ACCEPTABLE: summarise guidelines" in user_msg
    assert "General health concepts" in user_msg
    assert "NHS Trust" in user_msg
    assert "patients" in user_msg


def test_build_prompt_with_decomposition():
    from refiner.models import Policy, PolicyDecomposition

    policy = Policy(
        policy_concept="Clinical Diagnosis",
        concept_definition="No clinical decisions by AI",
        decomposition=PolicyDecomposition(
            agent="AI assistant",
            activity="diagnose",
            entity="patient conditions",
        ),
    )
    messages = build_prompt("Clinical Diagnosis", "No clinical decisions by AI", "Misdiagnosis", [], policy=policy)
    user_msg = messages[1]["content"]
    assert "Agent: AI assistant" in user_msg
    assert "Activity: diagnose" in user_msg
    assert "Entity: patient conditions" in user_msg
    assert "The policy governs this configuration" in user_msg


def test_build_prompt_without_enrichments():
    messages = build_prompt("Fraud", "About fraud", "Financial Fraud", [])
    user_msg = messages[1]["content"]
    assert "PROHIBITED:" not in user_msg
    assert "About fraud" in user_msg


from refiner.emit import emit


def _write_test_files(tmp_path):
    """Write domain context YAML and policy JSON for testing."""
    doc_data = {
        "version": "0.1",
        "risks": [
            {"risk_id": "r1", "risk_name": "Risk One"},
        ],
        "policy_contexts": [
            {
                "policy_concept": "Fraud",
                "risk_groundings": [
                    {
                        "risk_id": "r1",
                        "axes": [
                            {
                                "cco_class_uri": "http://example.org/Person",
                                "cco_class_label": "Person",
                                "enumerations": [
                                    {"class_uri": "http://example.org/Manager", "class_label": "Manager", "source_ontology": "FIBO", "relevance": "high"},
                                    {"class_uri": "http://example.org/Employee", "class_label": "Employee", "source_ontology": "CCO", "relevance": "medium"},
                                ],
                            },
                        ],
                    },
                ],
            },
        ],
    }
    dc_path = tmp_path / "test-domain-context.yaml"
    dc_path.write_text(yaml.dump(doc_data))

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
    (tmp_path / "a-domain-context.yaml").write_text("version: '0.1'\nrisks: []\npolicy_contexts: []")
    (tmp_path / "b-domain-context.yaml").write_text("version: '0.1'\nrisks: []\npolicy_contexts: []")
    pol_path = tmp_path / "policies.json"
    pol_path.write_text('[{"policy_concept": "X", "concept_definition": "Y"}]')
    out_path = tmp_path / "dataset.jsonl"
    import pytest
    with pytest.raises(SystemExit):
        emit(tmp_path, pol_path, samples_per_risk=1, output_path=out_path)


def test_emit_skips_risk_with_no_axes(tmp_path):
    doc_data = {
        "version": "0.1",
        "risks": [{"risk_id": "r1", "risk_name": "Risk One"}],
        "policy_contexts": [
            {
                "policy_concept": "Fraud",
                "risk_groundings": [
                    {"risk_id": "r1", "axes": []},  # no axes
                ],
            },
        ],
    }
    dc_path = tmp_path / "test-domain-context.yaml"
    dc_path.write_text(yaml.dump(doc_data))
    pol_path = tmp_path / "policies.json"
    pol_path.write_text('[{"policy_concept": "Fraud", "concept_definition": "About fraud"}]')
    out_path = tmp_path / "dataset.jsonl"
    emit(tmp_path, pol_path, samples_per_risk=5, output_path=out_path, seed=1)
    content = out_path.read_text().strip()
    assert content == ""


def test_emit_empty_profiles(tmp_path):
    dc_path = tmp_path / "test-domain-context.yaml"
    dc_path.write_text(yaml.dump({"version": "0.1", "risks": [], "policy_contexts": []}))
    pol_path = tmp_path / "policies.json"
    pol_path.write_text('[{"policy_concept": "X", "concept_definition": "Y"}]')
    out_path = tmp_path / "dataset.jsonl"
    emit(tmp_path, pol_path, samples_per_risk=5, output_path=out_path, seed=1)
    assert out_path.read_text().strip() == ""


def test_emit_skips_missing_policy_concept(tmp_path):
    doc_data = {
        "version": "0.1",
        "risks": [{"risk_id": "r1", "risk_name": "Risk One"}],
        "policy_contexts": [
            {
                "policy_concept": "Unknown",
                "risk_groundings": [
                    {
                        "risk_id": "r1",
                        "axes": [
                            {
                                "cco_class_uri": "http://example.org/A",
                                "cco_class_label": "A",
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
            },
        ],
    }
    dc_path = tmp_path / "test-domain-context.yaml"
    dc_path.write_text(yaml.dump(doc_data))
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
    default_out = tmp_path / "test-dataset.jsonl"
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


def test_strip_obo_ae_suffix():
    assert _strip_framework_suffix("Phobia AE") == "Phobia"


def test_strip_obo_ae_suffix_multi_word():
    assert _strip_framework_suffix("Somnambulism AE") == "Somnambulism"


def test_strip_obo_hp_suffix():
    assert _strip_framework_suffix("Seizure HP") == "Seizure"


def test_strip_obo_go_suffix():
    assert _strip_framework_suffix("Apoptosis GO") == "Apoptosis"


def test_strip_obo_suffix_in_prompt():
    axes = [
        SampledAxis(
            cco_class_uri="http://purl.obolibrary.org/obo/DOID_0001",
            cco_class_label="Adverse Event",
            sampled_uri="http://purl.obolibrary.org/obo/DOID_0002",
            sampled_label="Somnambulism AE",
            source_ontology="OBO",
            relevance="high",
        ),
    ]
    messages = build_prompt("PHI", "About PHI", "PHI Disclosure", axes)
    user = messages[1]["content"]
    assert "Somnambulism" in user
    assert "Somnambulism AE" not in user


def test_strip_framework_suffix_in_prompt():
    axes = [
        SampledAxis(
            cco_class_uri="http://d3fend.mitre.org/ontologies/d3fend.owl#T1234",
            cco_class_label="Offensive Technique - ATLAS",
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


def test_sample_axes_propagates_bfo_category():
    """bfo_category from DomainContextAxis should flow to SampledAxis."""
    import random
    random.seed(42)
    axes = [
        DomainContextAxis(
            cco_class_uri="http://example.org/A",
            cco_class_label="A",
            bfo_category="Role",
            enumerations=[_enum("high")],
        ),
    ]
    samples = sample_axes(axes, n=1)
    assert len(samples) == 1
    assert samples[0][0].bfo_category == "Role"


def test_sample_axes_propagates_empty_bfo_category():
    """Empty bfo_category should also propagate cleanly."""
    import random
    random.seed(42)
    axes = [
        DomainContextAxis(
            cco_class_uri="http://example.org/A",
            cco_class_label="A",
            enumerations=[_enum("high")],
        ),
    ]
    samples = sample_axes(axes, n=1)
    assert samples[0][0].bfo_category == ""


def test_build_prompt_with_frame():
    from refiner.frames import FRAMES
    frame = FRAMES["pretexting"]
    axes = [
        SampledAxis(
            cco_class_uri="http://example.org/Person",
            cco_class_label="Person",
            bfo_category="Role",
            sampled_uri="http://example.org/Manager",
            sampled_label="Manager",
            source_ontology="FIBO",
            relevance="high",
        ),
    ]
    messages = build_prompt("Fraud", "About fraud", "Financial Fraud", axes, frame=frame)
    user = messages[1]["content"]
    assert "professional role: Manager" in user
    assert "Adversarial technique:" in user


def test_build_prompt_with_frame_uses_slot_labels():
    from refiner.frames import FRAMES
    frame = FRAMES["delegated_authority"]
    axes = [
        SampledAxis(
            cco_class_uri="http://example.org/Agent",
            cco_class_label="Agent",
            bfo_category="Agent",
            sampled_uri="http://example.org/CMO",
            sampled_label="Chief Medical Officer",
            source_ontology="CCO",
            relevance="high",
        ),
    ]
    messages = build_prompt("PHI", "About PHI", "Data Leak", axes, frame=frame)
    user = messages[1]["content"]
    assert "authority figure: Chief Medical Officer" in user


def test_build_prompt_with_frame_empty_bfo_falls_back():
    from refiner.frames import FRAMES
    frame = FRAMES["pretexting"]
    axes = [
        SampledAxis(
            cco_class_uri="http://example.org/X",
            cco_class_label="X",
            bfo_category="",
            sampled_uri="http://example.org/Y",
            sampled_label="Y Label",
            source_ontology="CCO",
            relevance="high",
        ),
    ]
    messages = build_prompt("P", "D", "R", axes, frame=frame)
    user = messages[1]["content"]
    # No slot label, should fall back to plain format
    assert "Y Label (a type of X)" in user
    # But technique block should still appear
    assert "Adversarial technique:" in user


def test_build_prompt_with_frame_includes_examples():
    from refiner.frames import FRAMES
    frame = FRAMES["analytical_reframing"]
    messages = build_prompt("P", "D", "R", [], frame=frame)
    user = messages[1]["content"]
    assert "Examples of effective prompts" in user


def test_build_prompt_without_frame_backward_compat():
    axes = [
        SampledAxis(
            cco_class_uri="http://example.org/Person",
            cco_class_label="Person",
            sampled_uri="http://example.org/Manager",
            sampled_label="Manager",
            source_ontology="FIBO",
            relevance="high",
        ),
    ]
    messages = build_prompt("Fraud", "About fraud", "Financial Fraud", axes, frame=None)
    user = messages[1]["content"]
    assert "Manager" in user
    assert "Adversarial technique:" not in user


def test_emit_writes_technique_metadata(tmp_path):
    _write_test_files(tmp_path)
    pol_path = tmp_path / "policies.json"
    out_path = tmp_path / "dataset.jsonl"
    emit(tmp_path, pol_path, samples_per_risk=3, output_path=out_path, seed=42)
    lines = out_path.read_text().strip().split("\n")
    for line in lines:
        row = json.loads(line)
        assert "technique" in row
        assert "technique_description" in row
        assert row["technique"] in {
            "pretexting", "narrative_framing", "analytical_reframing",
            "delegated_authority", "comparative_benchmark",
        }
        assert len(row["technique_description"]) > 50


def test_emit_with_custom_technique_weights(tmp_path):
    _write_test_files(tmp_path)
    pol_path = tmp_path / "policies.json"
    out_path = tmp_path / "dataset.jsonl"
    weights = {"pretexting": 0.0, "narrative_framing": 0.0,
               "analytical_reframing": 0.0, "delegated_authority": 0.0,
               "comparative_benchmark": 1.0}
    emit(tmp_path, pol_path, samples_per_risk=5, output_path=out_path, seed=42,
         technique_weights=weights)
    lines = out_path.read_text().strip().split("\n")
    for line in lines:
        row = json.loads(line)
        assert row["technique"] == "comparative_benchmark"


def test_sample_axes_caps_at_combinatorial_space():
    """When space is smaller than n, return at most space samples."""
    axes = [
        DomainContextAxis(
            cco_class_uri="http://example.org/A",
            cco_class_label="A",
            enumerations=[_enum("high"), _enum("medium")],
        ),
        DomainContextAxis(
            cco_class_uri="http://example.org/B",
            cco_class_label="B",
            enumerations=[_enum("high")],
        ),
    ]
    # Space is 2 * 1 = 2, requesting 100 should return at most 2
    import random
    random.seed(42)
    samples = sample_axes(axes, n=100)
    assert len(samples) <= 2


class TestAxisGroupSampling:
    def _make_axis(self, uri, label, enumerations):
        return DomainContextAxis(
            cco_class_uri=uri,
            cco_class_label=label,
            bfo_category="Role",
            enumerations=[
                AxisEnumeration(
                    class_uri=f"{uri}/enum/{i}",
                    class_label=e,
                    source_ontology="test",
                    relevance="high",
                    provenance="subclass",
                )
                for i, e in enumerate(enumerations)
            ],
        )

    def test_samples_axes_from_groups(self):
        axes = [
            self._make_axis("http://ex/A", "A", ["a1", "a2"]),
            self._make_axis("http://ex/B", "B", ["b1", "b2"]),
            self._make_axis("http://ex/C", "C", ["c1", "c2"]),
            self._make_axis("http://ex/D", "D", ["d1", "d2"]),
        ]
        groups = [["http://ex/A", "http://ex/B"], ["http://ex/C", "http://ex/D"]]
        random.seed(42)
        results = sample_axes(axes, n=10, axis_groups=groups, axes_per_prompt=2)
        for sample in results:
            uris = {sa.cco_class_uri for sa in sample}
            assert uris <= {"http://ex/A", "http://ex/B"} or uris <= {"http://ex/C", "http://ex/D"}

    def test_axes_per_prompt_limits_selection(self):
        axes = [
            self._make_axis("http://ex/A", "A", ["a1"]),
            self._make_axis("http://ex/B", "B", ["b1"]),
            self._make_axis("http://ex/C", "C", ["c1"]),
        ]
        groups = [["http://ex/A", "http://ex/B", "http://ex/C"]]
        random.seed(42)
        results = sample_axes(axes, n=5, axis_groups=groups, axes_per_prompt=2)
        for sample in results:
            assert len(sample) == 2

    def test_no_groups_falls_back_to_full_pool(self):
        axes = [
            self._make_axis("http://ex/A", "A", ["a1", "a2"]),
            self._make_axis("http://ex/B", "B", ["b1", "b2"]),
            self._make_axis("http://ex/C", "C", ["c1", "c2"]),
        ]
        random.seed(42)
        results = sample_axes(axes, n=5, axis_groups=None, axes_per_prompt=2)
        for sample in results:
            assert len(sample) == 2

    def test_backward_compat_no_new_params(self):
        axes = [
            self._make_axis("http://ex/A", "A", ["a1", "a2"]),
            self._make_axis("http://ex/B", "B", ["b1", "b2"]),
        ]
        random.seed(42)
        results = sample_axes(axes, n=3)
        for sample in results:
            assert len(sample) == 2

    def test_dedup_includes_axis_identity(self):
        axes = [
            self._make_axis("http://ex/A", "A", ["shared"]),
            self._make_axis("http://ex/B", "B", ["shared"]),
            self._make_axis("http://ex/C", "C", ["shared"]),
        ]
        groups = [["http://ex/A", "http://ex/B"], ["http://ex/A", "http://ex/C"]]
        results = sample_axes(axes, n=5, axis_groups=groups, axes_per_prompt=2)
        assert len(results) == 2


from refiner.emit import build_utility_prompt, UTILITY_SYSTEM_MESSAGE
from refiner.benign_frames import BENIGN_FRAMES


def test_build_utility_prompt_returns_messages():
    axes = [
        SampledAxis(
            cco_class_uri="http://example.org/Person",
            cco_class_label="Person",
            sampled_uri="http://example.org/Manager",
            sampled_label="Manager",
            source_ontology="FIBO",
            relevance="high",
        ),
    ]
    messages = build_utility_prompt("Fraud", "About fraud", "Financial Fraud", axes)
    assert isinstance(messages, list)
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"


def test_build_utility_prompt_system_message_content():
    messages = build_utility_prompt("X", "Y", "Z", [])
    system = messages[0]["content"]
    assert "utility-testing scenario writer" in system
    assert "authenticity" in system.lower()
    assert "red-team" not in system.lower()


def test_build_utility_prompt_user_message_has_policy():
    axes = [
        SampledAxis(
            cco_class_uri="http://example.org/Person",
            cco_class_label="Person",
            sampled_uri="http://example.org/Manager",
            sampled_label="Manager",
            source_ontology="FIBO",
            relevance="high",
        ),
    ]
    messages = build_utility_prompt("Fraud", "About fraud", "Financial Fraud", axes)
    user = messages[1]["content"]
    assert "Fraud" in user
    assert "About fraud" in user
    assert "Financial Fraud" in user


def test_build_utility_prompt_user_message_has_axes():
    axes = [
        SampledAxis(
            cco_class_uri="http://example.org/Person",
            cco_class_label="Person",
            sampled_uri="http://example.org/Manager",
            sampled_label="Manager",
            source_ontology="FIBO",
            relevance="high",
        ),
        SampledAxis(
            cco_class_uri="http://example.org/Instrument",
            cco_class_label="Instrument",
            sampled_uri="http://example.org/Bond",
            sampled_label="Bond",
            source_ontology="FIBO",
            relevance="high",
        ),
    ]
    messages = build_utility_prompt("X", "Y", "Z", axes)
    user = messages[1]["content"]
    assert "Manager" in user
    assert "Bond" in user


def test_build_utility_prompt_inverted_instructions():
    messages = build_utility_prompt("Fraud", "About fraud", "Financial Fraud", [])
    user = messages[1]["content"]
    assert "AI SHOULD comply" in user
    assert "Be clearly within acceptable use" in user


def test_build_utility_prompt_with_benign_frame():
    frame = BENIGN_FRAMES["routine_practice"]
    axes = [
        SampledAxis(
            cco_class_uri="http://example.org/Person",
            cco_class_label="Person",
            bfo_category="Role",
            sampled_uri="http://example.org/Manager",
            sampled_label="Manager",
            source_ontology="FIBO",
            relevance="high",
        ),
    ]
    messages = build_utility_prompt("Fraud", "About fraud", "Financial Fraud", axes, frame=frame)
    user = messages[1]["content"]
    assert "practitioner: Manager" in user
    assert "Legitimate use-case pattern:" in user


def test_build_utility_prompt_with_boundary_examples():
    from refiner.models import Policy, BoundaryExample, PolicyProfile

    policy = Policy(
        policy_concept="Clinical",
        concept_definition="No clinical decisions",
        boundary_examples=[
            BoundaryExample(prohibited="care plan for John", acceptable="summarise guidelines")
        ],
        acceptable_uses=["General health concepts"],
    )
    doc_ctx = PolicyProfile(
        organization="NHS Trust",
        domain="healthcare",
        stakeholders=[Stakeholder(name="patients", roles=["airo:AISubject"])],
    )

    messages = build_utility_prompt(
        "Clinical", "No clinical decisions", "Misdiagnosis", [],
        policy=policy, policy_profile=doc_ctx,
    )
    user = messages[1]["content"]
    assert "PROHIBITED: care plan for John" in user
    assert "ACCEPTABLE: summarise guidelines" in user
    assert "General health concepts" in user
    assert "NHS Trust" in user


def test_build_utility_prompt_without_frame_no_technique_block():
    messages = build_utility_prompt("Fraud", "About fraud", "Financial Fraud", [], frame=None)
    user = messages[1]["content"]
    assert "Legitimate use-case pattern:" not in user
    assert "Adversarial technique:" not in user
