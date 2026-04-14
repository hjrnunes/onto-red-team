import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from typer.testing import CliRunner
from refiner.cli import app
from refiner.models import (
    Policy,
    PolicyRiskMapping,
    DomainContextDocument,
    RiskSummary,
)
from refiner.pipeline import PipelineState

runner = CliRunner()


def _make_policy_file(tmp_path: Path) -> Path:
    policies = [
        {"policy_concept": "Fraud", "concept_definition": "About fraud"},
    ]
    p = tmp_path / "test.json"
    p.write_text(json.dumps(policies))
    return p


def _make_completed_state():
    state = PipelineState(
        policies=[Policy(policy_concept="Fraud", concept_definition="About fraud")],
        risk_mappings=[
            PolicyRiskMapping(
                policy_concept="Fraud",
                matched_risks=[],
            ),
        ],
        risk_details={},
        variation_axes=[],
        domain_context=DomainContextDocument(
            model="test-model",
            risks=[
                RiskSummary(risk_id="ibm-risk-atlas-r1", risk_name="R1"),
            ],
            policy_contexts=[],
        ),
    )
    return state


@patch("refiner.cli.export_taxonomy")
@patch("refiner.cli._create_risk_handlers")
@patch("refiner.cli._create_onto_handlers")
@patch("refiner.cli.create_client")
@patch("refiner.cli.run_pipeline")
def test_cli_run_full_pipeline(mock_run, mock_create_client, mock_onto, mock_risk, mock_export, tmp_path, monkeypatch):
    monkeypatch.setenv("REFINER_BASE_URL", "http://localhost:8000/v1")
    monkeypatch.setenv("REFINER_MODEL", "test-model")
    monkeypatch.setenv("NEXUS_BASE_DIR", "/tmp/nexus")

    policy_file = _make_policy_file(tmp_path)
    mock_run.return_value = _make_completed_state()
    mock_create_client.return_value = MagicMock()
    mock_risk.return_value = {}
    mock_onto.return_value = {}
    mock_export.return_value = ({"name": "test"}, [])

    result = runner.invoke(app, ["run", str(policy_file)])
    assert result.exit_code == 0, result.output
    mock_run.assert_called_once()
    # Verify run_slug is passed
    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs.get("run_slug") == "test"


@patch("refiner.cli._create_risk_handlers")
@patch("refiner.cli._create_onto_handlers")
@patch("refiner.cli.create_client")
@patch("refiner.cli.run_pipeline")
def test_cli_run_with_until(mock_run, mock_create_client, mock_onto, mock_risk, tmp_path, monkeypatch):
    monkeypatch.setenv("REFINER_BASE_URL", "http://localhost:8000/v1")
    monkeypatch.setenv("REFINER_MODEL", "test-model")

    policy_file = _make_policy_file(tmp_path)
    state = _make_completed_state()
    state.risk_mappings = None
    mock_run.return_value = state
    mock_create_client.return_value = MagicMock()
    mock_risk.return_value = {}
    mock_onto.return_value = {}

    result = runner.invoke(app, ["run", "--until", "identify_domains", str(policy_file)])
    assert result.exit_code == 0, result.output
    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs.get("until") == "identify_domains"


@patch("refiner.cli.create_client")
def test_cli_ingest_markdown(mock_create_client, tmp_path, monkeypatch):
    from refiner.stages.ingest import _SlimContext, _SlimPolicyList, _SlimPolicy, _SlimEnrichmentList, _SlimEnrichment, _SlimBoundaryExample

    monkeypatch.setenv("REFINER_BASE_URL", "http://localhost:8000/v1")
    monkeypatch.setenv("REFINER_MODEL", "test-model")

    doc = tmp_path / "policy.md"
    doc.write_text("# Test Policy\nAI must not do bad things.")

    mock_client = MagicMock()
    mock_create_client.return_value = mock_client
    mock_client.chat.completions.create.side_effect = [
        _SlimContext(
            organization="Test", domain="general", purpose=[], ai_systems=[],
            ai_users=[], ai_subjects=[], governing_regulations=[], named_entities=[],
        ),
        _SlimPolicyList(policies=[
            _SlimPolicy(policy_concept="Safety", concept_definition="No harm"),
        ]),
        _SlimEnrichmentList(enrichments=[
            _SlimEnrichment(
                policy_concept="Safety",
                boundary_examples=[
                    _SlimBoundaryExample(prohibited="cause harm", acceptable="discuss safety")
                ],
                acceptable_uses=[], risk_controls=[], human_involvement="",
            ),
        ]),
    ]

    out = tmp_path / "output.json"
    result = runner.invoke(app, [
        "ingest", str(doc), "-o", str(out),
    ])
    assert result.exit_code == 0, result.output
    assert out.exists()

    data = json.loads(out.read_text())
    assert data["organization"]["name"] == "Test"
    assert len(data["policies"]) == 1


@patch("refiner.cli.create_client")
def test_cli_ingest_json(mock_create_client, tmp_path, monkeypatch):
    from refiner.stages.ingest import _SlimContext, _SlimEnrichmentList

    monkeypatch.setenv("REFINER_BASE_URL", "http://localhost:8000/v1")
    monkeypatch.setenv("REFINER_MODEL", "test-model")

    policy_file = tmp_path / "policies.json"
    policy_file.write_text(json.dumps([
        {"policy_concept": "Fraud", "concept_definition": "About fraud"},
    ]))

    mock_client = MagicMock()
    mock_create_client.return_value = mock_client
    mock_client.chat.completions.create.side_effect = [
        _SlimContext(
            organization="Bank", domain="finance", purpose=[], ai_systems=[],
            ai_users=[], ai_subjects=[], governing_regulations=[], named_entities=[],
        ),
        _SlimEnrichmentList(enrichments=[]),
    ]

    out = tmp_path / "enriched.json"
    result = runner.invoke(app, [
        "ingest", str(policy_file), "-o", str(out),
    ])
    assert result.exit_code == 0, result.output

    data = json.loads(out.read_text())
    assert data["domain"] == "finance"
    assert data["policies"][0]["policy_concept"] == "Fraud"


def test_cli_ingest_already_enriched(tmp_path, monkeypatch):
    monkeypatch.setenv("REFINER_BASE_URL", "http://localhost:8000/v1")
    monkeypatch.setenv("REFINER_MODEL", "test-model")

    enriched = tmp_path / "enriched.json"
    enriched.write_text(json.dumps({
        "airo_version": "0.2",
        "organization": "Test",
        "domain": "general",
        "policies": [{"policy_concept": "X", "concept_definition": "Y"}],
    }))

    result = runner.invoke(app, ["ingest", str(enriched)])
    assert result.exit_code == 1
    assert "Already an enriched PolicyDocument" in result.output


def _make_enriched_policy_file(tmp_path: Path) -> Path:
    doc = {
        "airo_version": "0.2",
        "organization": {"name": "Test Org", "roles": [], "description": None},
        "domain": "healthcare",
        "purpose": [],
        "governed_systems": [],
        "stakeholders": [],
        "regulations": [],
        "policies": [
            {"policy_concept": "Fraud", "concept_definition": "About fraud"},
        ],
    }
    p = tmp_path / "enriched.json"
    p.write_text(json.dumps(doc))
    return p


@patch("refiner.cli.export_taxonomy")
@patch("refiner.cli._create_risk_handlers")
@patch("refiner.cli._create_onto_handlers")
@patch("refiner.cli.create_client")
@patch("refiner.cli.run_pipeline")
def test_cli_run_enriched_format(mock_run, mock_create_client, mock_onto, mock_risk, mock_export, tmp_path, monkeypatch):
    monkeypatch.setenv("REFINER_BASE_URL", "http://localhost:8000/v1")
    monkeypatch.setenv("REFINER_MODEL", "test-model")
    monkeypatch.setenv("NEXUS_BASE_DIR", "/tmp/nexus")

    policy_file = _make_enriched_policy_file(tmp_path)
    mock_run.return_value = _make_completed_state()
    mock_create_client.return_value = MagicMock()
    mock_risk.return_value = {}
    mock_onto.return_value = {}
    mock_export.return_value = ({"entries": []}, {"profiles": []})

    result = runner.invoke(app, [
        "run", str(policy_file), "-o", str(tmp_path),
    ])
    assert result.exit_code == 0, result.output
    call_args = mock_run.call_args
    policies = call_args[0][0]
    assert len(policies) == 1
    assert policies[0].policy_concept == "Fraud"

    # Verify domain context YAML uses document envelope
    import yaml
    prof_path = tmp_path / "enriched-domain-context.yaml"
    assert prof_path.exists(), f"Expected {prof_path} to exist"
    written = yaml.safe_load(prof_path.read_text())
    assert "version" in written
    assert "risks" in written
    assert "policy_contexts" in written


@patch("refiner.cli.export_taxonomy")
@patch("refiner.cli._create_risk_handlers")
@patch("refiner.cli._create_onto_handlers")
@patch("refiner.cli.create_client")
@patch("refiner.cli.run_pipeline")
def test_cli_run_framework_labels_and_cross_mappings(mock_run, mock_create_client, mock_onto, mock_risk, mock_export, tmp_path, monkeypatch):
    """Framework labels are set on RiskSummary and cross-mappings are populated."""
    monkeypatch.setenv("REFINER_BASE_URL", "http://localhost:8000/v1")
    monkeypatch.setenv("REFINER_MODEL", "test-model")
    monkeypatch.setenv("NEXUS_BASE_DIR", "/tmp/nexus")

    policy_file = _make_policy_file(tmp_path)
    state = _make_completed_state()
    # Framework and cross-mappings now come from the pipeline (contextualize pulls from RiskLandscape)
    state.domain_context.risks[0].risk_framework = "IBM Risk Atlas"
    state.domain_context.risks[0].cross_mappings = [{"id": "owasp-llm-x", "mapping_type": "close"}]
    mock_run.return_value = state
    mock_create_client.return_value = MagicMock()
    mock_risk.return_value = {}
    mock_onto.return_value = {}
    mock_export.return_value = ({"name": "test"}, [])

    result = runner.invoke(app, ["run", str(policy_file), "-o", str(tmp_path)])
    assert result.exit_code == 0, result.output

    import yaml
    prof_path = tmp_path / "test-domain-context.yaml"
    written = yaml.safe_load(prof_path.read_text())
    risk = written["risks"][0]
    assert risk["risk_framework"] == "IBM Risk Atlas"
    assert risk["cross_mappings"] == [{"id": "owasp-llm-x", "mapping_type": "close"}]


@patch("refiner.cli.export_taxonomy")
@patch("refiner.cli._create_risk_handlers")
@patch("refiner.cli._create_onto_handlers")
@patch("refiner.cli.create_client")
@patch("refiner.cli.run_pipeline")
def test_cli_run_policy_source_from_enriched(mock_run, mock_create_client, mock_onto, mock_risk, mock_export, tmp_path, monkeypatch):
    """PolicySourceRef is populated from enriched PolicyDocument."""
    monkeypatch.setenv("REFINER_BASE_URL", "http://localhost:8000/v1")
    monkeypatch.setenv("REFINER_MODEL", "test-model")
    monkeypatch.setenv("NEXUS_BASE_DIR", "/tmp/nexus")

    policy_file = _make_enriched_policy_file(tmp_path)
    mock_run.return_value = _make_completed_state()
    mock_create_client.return_value = MagicMock()
    mock_risk.return_value = {}
    mock_onto.return_value = {}
    mock_export.return_value = ({"entries": []}, [])

    result = runner.invoke(app, ["run", str(policy_file), "-o", str(tmp_path)])
    assert result.exit_code == 0, result.output

    import yaml
    prof_path = tmp_path / "enriched-domain-context.yaml"
    written = yaml.safe_load(prof_path.read_text())
    assert written["policy_source"]["organization"] == "Test Org"
    assert written["policy_source"]["domain"] == "healthcare"
    assert written["policy_source"]["policy_count"] == 1


@patch("refiner.cli.create_client")
def test_ingest_then_run_integration(mock_create_client, tmp_path, monkeypatch):
    """Full workflow: ingest flat JSON → enriched JSON → refiner run accepts it."""
    from refiner.stages.ingest import _SlimContext, _SlimEnrichmentList, _SlimEnrichment, _SlimBoundaryExample
    from refiner.models import PolicyDocument

    monkeypatch.setenv("REFINER_BASE_URL", "http://localhost:8000/v1")
    monkeypatch.setenv("REFINER_MODEL", "test-model")

    # Create flat JSON
    flat_json = tmp_path / "policies.json"
    flat_json.write_text(json.dumps([
        {"policy_concept": "Fraud", "concept_definition": "About fraud"},
    ]))

    # Mock client for ingest
    mock_client = MagicMock()
    mock_create_client.return_value = mock_client
    mock_client.chat.completions.create.side_effect = [
        _SlimContext(
            organization="Bank", domain="finance", purpose=["services"],
            ai_systems=["ChatBot"], ai_users=["staff"], ai_subjects=["customers"],
            governing_regulations=[], named_entities=[],
        ),
        _SlimEnrichmentList(enrichments=[
            _SlimEnrichment(
                policy_concept="Fraud",
                boundary_examples=[
                    _SlimBoundaryExample(prohibited="commit fraud", acceptable="report fraud")
                ],
                acceptable_uses=["fraud reporting"],
                risk_controls=[], human_involvement="",
            ),
        ]),
    ]

    enriched = tmp_path / "enriched.json"
    result = runner.invoke(app, ["ingest", str(flat_json), "-o", str(enriched)])
    assert result.exit_code == 0, result.output
    assert enriched.exists()

    # Verify enriched file is valid PolicyDocument
    data = json.loads(enriched.read_text())
    assert data["organization"]["name"] == "Bank"
    assert data["policies"][0]["boundary_examples"][0]["prohibited"] == "commit fraud"

    # Verify refiner run would accept this file
    doc = PolicyDocument(**data)
    assert len(doc.policies) == 1
    assert doc.policies[0].policy_concept == "Fraud"
