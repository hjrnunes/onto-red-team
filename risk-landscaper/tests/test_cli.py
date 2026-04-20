import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from typer.testing import CliRunner

from risk_landscaper.cli import app


runner = CliRunner()


def test_run_missing_file():
    result = runner.invoke(app, ["run", "/nonexistent/policy.json", "--output", "/tmp/out", "--base-url", "http://localhost:8000/v1", "--model", "test"])
    assert result.exit_code != 0
    assert "does not exist" in result.output


def test_run_missing_base_url(tmp_path):
    policy_file = tmp_path / "test.json"
    policy_file.write_text(json.dumps([{"policy_concept": "Test", "concept_definition": "Def"}]))
    result = runner.invoke(app, ["run", str(policy_file), "--output", str(tmp_path / "out"), "--model", "test"])
    assert result.exit_code != 0
    assert "base-url" in result.output.lower() or "required" in result.output.lower()


def test_run_missing_model(tmp_path):
    policy_file = tmp_path / "test.json"
    policy_file.write_text(json.dumps([{"policy_concept": "Test", "concept_definition": "Def"}]))
    result = runner.invoke(app, ["run", str(policy_file), "--output", str(tmp_path / "out"), "--base-url", "http://localhost:8000/v1"])
    assert result.exit_code != 0
    assert "model" in result.output.lower() or "required" in result.output.lower()
