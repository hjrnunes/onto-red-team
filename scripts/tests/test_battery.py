import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from run_battery import load_config, resolve_policy_file


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


def test_resolve_raw_policy_json(tmp_path):
    policy_dir = tmp_path / "policies"
    policy_dir.mkdir()
    (policy_dir / "swb.json").write_text("{}")
    result = resolve_policy_file("swb", policy_dir, run_dir=tmp_path / "run", prefer_enriched=False)
    assert result == policy_dir / "swb.json"


def test_resolve_raw_policy_md(tmp_path):
    policy_dir = tmp_path / "policies"
    policy_dir.mkdir()
    (policy_dir / "rdash.md").write_text("# Policy")
    result = resolve_policy_file("rdash", policy_dir, run_dir=tmp_path / "run", prefer_enriched=False)
    assert result == policy_dir / "rdash.md"


def test_resolve_prefers_enriched(tmp_path):
    policy_dir = tmp_path / "policies"
    policy_dir.mkdir()
    (policy_dir / "swb.json").write_text("{}")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    enriched = run_dir / "swb-enriched.json"
    enriched.write_text("{}")
    result = resolve_policy_file("swb", policy_dir, run_dir=run_dir, prefer_enriched=True)
    assert result == enriched


def test_resolve_falls_back_to_raw_when_no_enriched(tmp_path):
    policy_dir = tmp_path / "policies"
    policy_dir.mkdir()
    (policy_dir / "swb.json").write_text("{}")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    result = resolve_policy_file("swb", policy_dir, run_dir=run_dir, prefer_enriched=True)
    assert result == policy_dir / "swb.json"


def test_resolve_missing_policy_raises(tmp_path):
    policy_dir = tmp_path / "policies"
    policy_dir.mkdir()
    try:
        resolve_policy_file("missing", policy_dir, run_dir=tmp_path / "run", prefer_enriched=False)
        assert False, "Should have raised"
    except FileNotFoundError:
        pass
