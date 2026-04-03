import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from run_battery import load_config


def test_load_config_resolves_relative_paths(tmp_path):
    cfg_file = tmp_path / "battery.yaml"
    cfg_file.write_text(
        """\
policy_dir: policy_examples
runs_dir: runs
nexus_base_dir: /absolute/path
ontoquery_chroma_dir: ontoquery/.chroma
nexus_chroma_dir: nexus-mcp/.chroma
samples_per_risk: 15
tracking_uri: https://mlflow.example.com
policies:
  - swb
  - generic
models:
  phi-4: http://localhost:1234/v1
"""
    )
    cfg = load_config(cfg_file)
    assert cfg["policy_dir"] == tmp_path / "policy_examples"
    assert cfg["runs_dir"] == tmp_path / "runs"
    assert cfg["nexus_base_dir"] == Path("/absolute/path")
    assert cfg["ontoquery_chroma_dir"] == tmp_path / "ontoquery/.chroma"
    assert cfg["nexus_chroma_dir"] == tmp_path / "nexus-mcp/.chroma"
    assert cfg["samples_per_risk"] == 15
    assert cfg["tracking_uri"] == "https://mlflow.example.com"
    assert cfg["policies"] == ["swb", "generic"]
    assert cfg["models"] == {"phi-4": "http://localhost:1234/v1"}


def test_load_config_missing_required_field(tmp_path):
    cfg_file = tmp_path / "battery.yaml"
    cfg_file.write_text("policies:\n  - swb\n")
    try:
        load_config(cfg_file)
        assert False, "Should have raised"
    except SystemExit:
        pass
