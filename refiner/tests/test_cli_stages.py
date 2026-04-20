import json
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock
from typer.testing import CliRunner
from refiner.cli import app

runner = CliRunner()


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

        from refiner.models import DomainContext
        mock_oh.return_value = {}
        mock_anchor.return_value = ([], {})
        mock_ctx.return_value = DomainContext(
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
