import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unittest.mock import patch, MagicMock

from run_battery import (
    load_config,
    resolve_policy_file,
    build_ingest_cmd,
    build_refine_cmd,
    build_emit_cmd,
    build_generate_cmd,
    build_evaluate_cmd,
    run_model,
    format_summary_table,
)


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


def test_build_ingest_cmd():
    cmd, cwd = build_ingest_cmd(
        policy_file=Path("/p/swb.json"),
        run_dir=Path("/runs/swb-phi4-v1"),
        policy="swb",
        model_name="phi-4",
        model_url="http://localhost/v1",
        api_key="secret",
    )
    assert cwd == "refiner"
    assert cmd[:4] == ["uv", "run", "refiner", "ingest"]
    assert "/p/swb.json" in cmd
    assert "--output" in cmd
    assert "--api-key" in cmd
    assert "secret" in cmd


def test_build_refine_cmd():
    cmd, cwd = build_refine_cmd(
        input_file=Path("/runs/swb-phi4-v1/swb-enriched.json"),
        run_dir=Path("/runs/swb-phi4-v1"),
        model_name="phi-4",
        model_url="http://localhost/v1",
        api_key="secret",
        nexus_base_dir=Path("/nexus"),
        onto_chroma=Path("/tmp/onto"),
        nexus_chroma=Path("/tmp/nexus"),
        tracking_uri="https://mlflow.example.com",
        tags=["exp1", "exp2"],
    )
    assert cwd == "refiner"
    assert cmd[:4] == ["uv", "run", "refiner", "run"]
    assert "--track" in cmd
    assert cmd[cmd.index("--tag") + 1] == "exp1"
    tag_indices = [i for i, x in enumerate(cmd) if x == "--tag"]
    assert len(tag_indices) == 2


def test_build_refine_cmd_no_tags():
    cmd, _ = build_refine_cmd(
        input_file=Path("/in.json"),
        run_dir=Path("/runs/x"),
        model_name="m",
        model_url="http://u",
        api_key="k",
        nexus_base_dir=Path("/n"),
        onto_chroma=Path("/o"),
        nexus_chroma=Path("/c"),
        tracking_uri="https://t",
        tags=[],
    )
    assert "--tag" not in cmd


def test_build_emit_cmd():
    cmd, cwd = build_emit_cmd(
        run_dir=Path("/runs/swb-phi4-v1"),
        policy_file=Path("/p/swb.json"),
        samples_per_risk=15,
    )
    assert cwd == "refiner"
    assert "15" in cmd


def test_build_generate_cmd_with_key():
    cmd, cwd = build_generate_cmd(
        run_dir=Path("/runs/swb-phi4-v1"),
        model_name="phi-4",
        model_url="http://localhost/v1",
        api_key="secret",
    )
    assert cwd == "redteam"
    assert "--api-key" in cmd
    assert "secret" in cmd
    assert "hosted_vllm/phi-4" in cmd


def test_build_generate_cmd_no_key():
    cmd, _ = build_generate_cmd(
        run_dir=Path("/runs/swb-phi4-v1"),
        model_name="phi-4",
        model_url="http://localhost/v1",
        api_key="",
    )
    assert "--api-key" not in cmd


def test_build_evaluate_cmd():
    cmd, cwd = build_evaluate_cmd(
        run_dir=Path("/runs/swb-phi4-v1"),
        policy_file=Path("/p/swb.json"),
        tracking_uri="https://mlflow.example.com",
        tags=["exp1"],
    )
    assert cwd == "refiner"
    assert "--adversarial" in cmd
    assert "--track" in cmd
    assert cmd[cmd.index("--tag") + 1] == "exp1"


def _make_model_cfg(tmp_path):
    policy_dir = tmp_path / "policies"
    policy_dir.mkdir()
    (policy_dir / "swb.json").write_text("{}")
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    onto = tmp_path / "onto"
    onto.mkdir()
    nexus = tmp_path / "nexus"
    nexus.mkdir()
    return {
        "policy_dir": policy_dir,
        "runs_dir": runs_dir,
        "nexus_base_dir": Path("/nexus"),
        "ontoquery_chroma_dir": onto,
        "nexus_chroma_dir": nexus,
        "samples_per_risk": 15,
        "tracking_uri": "https://mlflow.example.com",
    }


def test_run_model_dry_run(tmp_path, capsys):
    cfg = _make_model_cfg(tmp_path)
    results = run_model(
        model_name="phi-4",
        model_url="http://localhost/v1",
        run_name="v1",
        policies=["swb"],
        cfg=cfg,
        api_key="secret",
        tags=[],
        skip_ingest=True,
        skip_refine=False,
        skip_generate=True,
        dry_run=True,
        repo_root=tmp_path,
    )
    assert results == {"swb": "OK"}
    out = capsys.readouterr().out
    assert "refiner" in out


def test_run_model_calls_subprocess(tmp_path):
    cfg = _make_model_cfg(tmp_path)
    mock_run = MagicMock()
    with patch("run_battery.subprocess.run", mock_run):
        results = run_model(
            model_name="phi-4",
            model_url="http://localhost/v1",
            run_name="v1",
            policies=["swb"],
            cfg=cfg,
            api_key="secret",
            tags=[],
            skip_ingest=True,
            skip_refine=True,
            skip_generate=True,
            dry_run=False,
            repo_root=tmp_path,
        )
    assert results == {"swb": "OK"}
    assert mock_run.call_count == 1
    call_args = mock_run.call_args
    assert "emit" in call_args[0][0]


def test_run_model_records_failure(tmp_path):
    cfg = _make_model_cfg(tmp_path)
    with patch("run_battery.subprocess.run", side_effect=Exception("boom")):
        results = run_model(
            model_name="phi-4",
            model_url="http://localhost/v1",
            run_name="v1",
            policies=["swb"],
            cfg=cfg,
            api_key="",
            tags=[],
            skip_ingest=True,
            skip_refine=True,
            skip_generate=True,
            dry_run=False,
            repo_root=tmp_path,
        )
    assert results["swb"] == "FAIL"


def test_format_summary_table():
    results = {
        "phi-4": {"swb": "OK", "generic": "OK"},
        "gemma": {"swb": "FAIL", "generic": "OK"},
    }
    table = format_summary_table(results, ["swb", "generic"])
    assert "phi-4" in table
    assert "gemma" in table
    assert "FAIL" in table
    assert "OK" in table
    lines = table.strip().split("\n")
    assert len(lines) == 3  # header + 2 policies


def test_format_summary_table_single():
    results = {"m1": {"p1": "OK"}}
    table = format_summary_table(results, ["p1"])
    assert "OK" in table
