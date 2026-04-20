import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from typer.testing import CliRunner
import yaml
from refiner.cli import app
from refiner.models import (
    Policy,
    PolicyRiskMapping,
    DomainContext,
    RiskLandscape,
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


def _make_landscape_file(tmp_path: Path) -> Path:
    landscape = RiskLandscape(model="test-model", risks=[], policy_mappings=[])
    p = tmp_path / "risk-landscape.yaml"
    p.write_text(yaml.dump(landscape.model_dump(), default_flow_style=False))
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
        risk_landscape=RiskLandscape(
            model="test-model",
            risks=[],
            policy_mappings=[],
        ),
        domain_context=DomainContext(
            model="test-model",
            risks=[
                RiskSummary(risk_id="ibm-risk-atlas-r1", risk_name="R1"),
            ],
            policy_contexts=[],
        ),
    )
    return state


@patch("refiner.cli.export_taxonomy")
@patch("refiner.cli._create_onto_handlers")
@patch("refiner.cli.create_client")
@patch("refiner.cli.run_pipeline")
def test_cli_run_full_pipeline(mock_run, mock_create_client, mock_onto, mock_export, tmp_path, monkeypatch):
    monkeypatch.setenv("REFINER_BASE_URL", "http://localhost:8000/v1")
    monkeypatch.setenv("REFINER_MODEL", "test-model")

    policy_file = _make_policy_file(tmp_path)
    landscape_file = _make_landscape_file(tmp_path)
    mock_run.return_value = _make_completed_state()
    mock_create_client.return_value = MagicMock()
    mock_onto.return_value = {}
    mock_export.return_value = ({"name": "test"}, [])

    result = runner.invoke(app, ["run", "--landscape", str(landscape_file), str(policy_file)])
    assert result.exit_code == 0, result.output
    mock_run.assert_called_once()
    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs.get("run_slug") == "test"
    assert call_kwargs.get("landscape") is not None


@patch("refiner.cli._create_onto_handlers")
@patch("refiner.cli.create_client")
@patch("refiner.cli.run_pipeline")
def test_cli_run_with_until(mock_run, mock_create_client, mock_onto, tmp_path, monkeypatch):
    monkeypatch.setenv("REFINER_BASE_URL", "http://localhost:8000/v1")
    monkeypatch.setenv("REFINER_MODEL", "test-model")

    policy_file = _make_policy_file(tmp_path)
    landscape_file = _make_landscape_file(tmp_path)
    state = _make_completed_state()
    state.risk_mappings = None
    mock_run.return_value = state
    mock_create_client.return_value = MagicMock()
    mock_onto.return_value = {}

    result = runner.invoke(app, ["run", "--landscape", str(landscape_file), "--until", "anchor", str(policy_file)])
    assert result.exit_code == 0, result.output
    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs.get("until") == "anchor"


def _make_enriched_policy_file(tmp_path: Path) -> Path:
    doc = {
        "airo_version": "0.2",
        "organization": {"name": "Test Org", "roles": [], "description": None},
        "domain": "healthcare",
        "purpose": [],
        "ai_systems": [],
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
@patch("refiner.cli._create_onto_handlers")
@patch("refiner.cli.create_client")
@patch("refiner.cli.run_pipeline")
def test_cli_run_enriched_format(mock_run, mock_create_client, mock_onto, mock_export, tmp_path, monkeypatch):
    monkeypatch.setenv("REFINER_BASE_URL", "http://localhost:8000/v1")
    monkeypatch.setenv("REFINER_MODEL", "test-model")

    policy_file = _make_enriched_policy_file(tmp_path)
    landscape_file = _make_landscape_file(tmp_path)
    mock_run.return_value = _make_completed_state()
    mock_create_client.return_value = MagicMock()
    mock_onto.return_value = {}
    mock_export.return_value = ({"entries": []}, {"profiles": []})

    result = runner.invoke(app, [
        "run", "--landscape", str(landscape_file), str(policy_file), "-o", str(tmp_path),
    ])
    assert result.exit_code == 0, result.output
    call_args = mock_run.call_args
    policies = call_args[0][0]
    assert len(policies) == 1
    assert policies[0].policy_concept == "Fraud"

    prof_path = tmp_path / "enriched-domain-context.yaml"
    assert prof_path.exists(), f"Expected {prof_path} to exist"
    written = yaml.safe_load(prof_path.read_text())
    assert "version" in written
    assert "risks" in written
    assert "policy_contexts" in written

    assert (tmp_path / "enriched-risk-landscape.html").exists()
    assert (tmp_path / "enriched-domain-context.html").exists()
    assert (tmp_path / "enriched-taxonomy.html").exists()
    assert (tmp_path / "enriched-run-report.html").exists()


@patch("refiner.cli.export_taxonomy")
@patch("refiner.cli._create_onto_handlers")
@patch("refiner.cli.create_client")
@patch("refiner.cli.run_pipeline")
def test_cli_run_framework_labels_and_cross_mappings(mock_run, mock_create_client, mock_onto, mock_export, tmp_path, monkeypatch):
    """Framework labels are set on RiskSummary and cross-mappings are populated."""
    monkeypatch.setenv("REFINER_BASE_URL", "http://localhost:8000/v1")
    monkeypatch.setenv("REFINER_MODEL", "test-model")

    policy_file = _make_policy_file(tmp_path)
    landscape_file = _make_landscape_file(tmp_path)
    state = _make_completed_state()
    state.domain_context.risks[0].risk_framework = "IBM Risk Atlas"
    state.domain_context.risks[0].cross_mappings = [{"id": "owasp-llm-x", "mapping_type": "close"}]
    mock_run.return_value = state
    mock_create_client.return_value = MagicMock()
    mock_onto.return_value = {}
    mock_export.return_value = ({"name": "test"}, [])

    result = runner.invoke(app, ["run", "--landscape", str(landscape_file), str(policy_file), "-o", str(tmp_path)])
    assert result.exit_code == 0, result.output

    prof_path = tmp_path / "test-domain-context.yaml"
    written = yaml.safe_load(prof_path.read_text())
    risk = written["risks"][0]
    assert risk["risk_framework"] == "IBM Risk Atlas"
    assert risk["cross_mappings"] == [{"id": "owasp-llm-x", "mapping_type": "close"}]


@patch("refiner.cli.export_taxonomy")
@patch("refiner.cli._create_onto_handlers")
@patch("refiner.cli.create_client")
@patch("refiner.cli.run_pipeline")
def test_cli_run_policy_source_from_enriched(mock_run, mock_create_client, mock_onto, mock_export, tmp_path, monkeypatch):
    """PolicySourceRef is populated from enriched PolicyProfile."""
    monkeypatch.setenv("REFINER_BASE_URL", "http://localhost:8000/v1")
    monkeypatch.setenv("REFINER_MODEL", "test-model")

    policy_file = _make_enriched_policy_file(tmp_path)
    landscape_file = _make_landscape_file(tmp_path)
    mock_run.return_value = _make_completed_state()
    mock_create_client.return_value = MagicMock()
    mock_onto.return_value = {}
    mock_export.return_value = ({"entries": []}, [])

    result = runner.invoke(app, ["run", "--landscape", str(landscape_file), str(policy_file), "-o", str(tmp_path)])
    assert result.exit_code == 0, result.output

    prof_path = tmp_path / "enriched-domain-context.yaml"
    written = yaml.safe_load(prof_path.read_text())
    assert written["policy_source"]["organization"] == "Test Org"
    assert written["policy_source"]["domain"] == "healthcare"
    assert written["policy_source"]["policy_count"] == 1


