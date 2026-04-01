import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from typer.testing import CliRunner
from refiner.cli import app
from refiner.models import (
    Policy,
    PolicyClassification,
    PolicyRiskMapping,
    RiskVariationAxes,
    DomainContextProfile,
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
        classifications=[
            PolicyClassification(
                policy_concept="Fraud", concept_definition="About fraud",
                policy_type="A", justification="j",
            ),
        ],
        risk_mappings=[
            PolicyRiskMapping(
                policy_concept="Fraud", policy_type="A",
                matched_risks=[], cross_mappings=[],
            ),
        ],
        risk_details={},
        variation_axes=[],
        domain_context=[],
    )
    return state


@patch("refiner.cli.structure")
@patch("refiner.cli._create_risk_handlers")
@patch("refiner.cli._create_onto_handlers")
@patch("refiner.cli.create_client")
@patch("refiner.cli.run_pipeline")
def test_cli_run_full_pipeline(mock_run, mock_create_client, mock_onto, mock_risk, mock_structure, tmp_path, monkeypatch):
    monkeypatch.setenv("REFINER_BASE_URL", "http://localhost:8000/v1")
    monkeypatch.setenv("REFINER_MODEL", "test-model")

    policy_file = _make_policy_file(tmp_path)
    mock_run.return_value = _make_completed_state()
    mock_create_client.return_value = MagicMock()
    mock_risk.return_value = {}
    mock_onto.return_value = {}
    mock_structure.return_value = ({"name": "test"}, [])

    result = runner.invoke(app, ["run", str(policy_file)])
    assert result.exit_code == 0, result.output
    mock_run.assert_called_once()


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

    result = runner.invoke(app, ["run", "--until", "classify", str(policy_file)])
    assert result.exit_code == 0, result.output
    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs.get("until") == "classify"
