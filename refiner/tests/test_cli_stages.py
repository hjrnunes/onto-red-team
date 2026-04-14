import json
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock
from typer.testing import CliRunner
from refiner.cli import app

runner = CliRunner()


def test_map_risks_cli_produces_risk_landscape(tmp_path):
    # Create input PolicyDocument
    policy_doc = {
        "organization": {"name": "TestOrg", "roles": []},
        "domain": "banking",
        "policies": [
            {"policy_concept": "Fraud", "concept_definition": "Prompts about fraud"},
        ],
    }
    input_path = tmp_path / "test-enriched.json"
    input_path.write_text(json.dumps(policy_doc))

    out_dir = tmp_path / "output"
    out_dir.mkdir()

    with patch("refiner.cli._create_risk_handlers") as mock_rh, \
         patch("refiner.stages.identify_domains.identify_domains") as mock_id, \
         patch("refiner.stages.map_risks.map_risks") as mock_mr:

        mock_id.return_value = ["CCO", "Commons", "D3FEND", "CSO", "LKIF"]
        mock_mr.return_value = (
            [],  # mappings
            {},  # risk_details
            set(),  # seen_risk_ids
            {},  # related_risks
            {},  # risk_actions
        )
        mock_rh.return_value = {}

        result = runner.invoke(app, [
            "map-risks", str(input_path),
            "--output", str(out_dir),
            "--base-url", "http://localhost:8000/v1",
            "--model", "test-model",
            "--nexus-base-dir", "/tmp/nexus",
        ])

    assert result.exit_code == 0, result.output
    # Check that risk-landscape.yaml was written
    rl_files = list(out_dir.glob("*-risk-landscape.yaml"))
    assert len(rl_files) == 1
    landscape = yaml.safe_load(rl_files[0].read_text())
    assert "version" in landscape
    assert "selected_domains" in landscape


def test_ground_cli_produces_dcd(tmp_path):
    # Create input RiskLandscape YAML
    landscape_data = {
        "version": "0.1",
        "model": "test-model",
        "timestamp": "2026-04-14T12:00:00Z",
        "run_slug": "test",
        "selected_domains": ["CCO", "Commons"],
        "risks": [
            {"risk_id": "r1", "risk_name": "Risk One", "risk_description": "desc"},
        ],
        "policy_mappings": [
            {
                "policy_concept": "Policy A",
                "matched_risks": [
                    {"risk_id": "r1", "risk_name": "Risk One",
                     "relevance": "primary", "justification": "test"},
                ],
            },
        ],
    }
    rl_path = tmp_path / "test-risk-landscape.yaml"
    rl_path.write_text(yaml.dump(landscape_data))

    # Create policies file
    policy_doc = {
        "organization": {"name": "TestOrg", "roles": []},
        "domain": "test",
        "policies": [
            {"policy_concept": "Policy A", "concept_definition": "test policy"},
        ],
    }
    policies_path = tmp_path / "test-enriched.json"
    policies_path.write_text(json.dumps(policy_doc))

    out_dir = tmp_path / "output"
    out_dir.mkdir()

    with patch("refiner.cli._create_onto_handlers") as mock_oh, \
         patch("refiner.stages.anchor.anchor") as mock_anchor, \
         patch("refiner.stages.contextualize.contextualize") as mock_ctx:

        from refiner.models import DomainContextDocument
        mock_oh.return_value = {}
        mock_anchor.return_value = ([], {})
        mock_ctx.return_value = DomainContextDocument(
            model="test-model", run_slug="test",
            selected_domains=["CCO", "Commons"],
        )

        result = runner.invoke(app, [
            "ground", str(rl_path),
            "--policies", str(policies_path),
            "--output", str(out_dir),
            "--base-url", "http://localhost:8000/v1",
            "--model", "test-model",
        ])

    assert result.exit_code == 0, result.output
    dcd_files = list(out_dir.glob("*-domain-context.yaml"))
    assert len(dcd_files) == 1
