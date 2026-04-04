import json
from typer.testing import CliRunner
from ontoquery.cli import app

runner = CliRunner()


def test_index_command(sample_ontology_dir, tmp_path, monkeypatch):
    monkeypatch.setenv("ONTOQUERY_CHROMA_DIR", str(tmp_path / "chroma"))
    result = runner.invoke(app, ["index", str(sample_ontology_dir)])
    assert result.exit_code == 0
    assert "files parsed" in result.stdout.lower() or "classes indexed" in result.stdout.lower()


def test_index_command_bad_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ONTOQUERY_CHROMA_DIR", str(tmp_path / "chroma"))
    result = runner.invoke(app, ["index", str(tmp_path / "nonexistent")])
    assert result.exit_code != 0


def test_search_command(sample_ontology_dir, tmp_path, monkeypatch):
    chroma = tmp_path / "chroma"
    monkeypatch.setenv("ONTOQUERY_CHROMA_DIR", str(chroma))

    # First index
    runner.invoke(app, ["index", str(sample_ontology_dir)])

    # Then search
    result = runner.invoke(app, ["search", "Agent", "An entity that performs actions"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert isinstance(data, list)
    assert len(data) > 0
    assert "uri" in data[0]
    assert "label" in data[0]
    assert "distance" in data[0]


def test_search_command_no_index(tmp_path, monkeypatch):
    monkeypatch.setenv("ONTOQUERY_CHROMA_DIR", str(tmp_path / "chroma"))
    result = runner.invoke(app, ["search", "test", "test"])
    assert result.exit_code != 0


def test_navigate_command(sample_ontology_dir, tmp_path, monkeypatch):
    chroma = tmp_path / "chroma"
    monkeypatch.setenv("ONTOQUERY_CHROMA_DIR", str(chroma))

    # Index first
    runner.invoke(app, ["index", str(sample_ontology_dir)])

    # Navigate to ClassD (Person) — should show ClassA as superclass
    result = runner.invoke(app, ["navigate", "http://example.org/ont#ClassD"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["uri"] == "http://example.org/ont#ClassD"
    assert data["label"] == "Person"
    super_uris = {s["uri"] for s in data["superclasses"]}
    assert "http://example.org/ont#ClassA" in super_uris
    assert len(data["properties"]) >= 1


def test_navigate_command_direction_up(sample_ontology_dir, tmp_path, monkeypatch):
    chroma = tmp_path / "chroma"
    monkeypatch.setenv("ONTOQUERY_CHROMA_DIR", str(chroma))
    runner.invoke(app, ["index", str(sample_ontology_dir)])

    result = runner.invoke(app, ["navigate", "http://example.org/ont#ClassD", "--direction", "up"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "superclasses" in data
    assert "subclasses" not in data


def test_navigate_command_direction_down(sample_ontology_dir, tmp_path, monkeypatch):
    chroma = tmp_path / "chroma"
    monkeypatch.setenv("ONTOQUERY_CHROMA_DIR", str(chroma))
    runner.invoke(app, ["index", str(sample_ontology_dir)])

    result = runner.invoke(app, ["navigate", "http://example.org/ont#ClassA", "--direction", "down"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "subclasses" in data
    assert "superclasses" not in data
    sub_uris = {s["uri"] for s in data["subclasses"]}
    assert "http://example.org/ont#ClassD" in sub_uris


def test_navigate_command_not_found(sample_ontology_dir, tmp_path, monkeypatch):
    chroma = tmp_path / "chroma"
    monkeypatch.setenv("ONTOQUERY_CHROMA_DIR", str(chroma))
    runner.invoke(app, ["index", str(sample_ontology_dir)])

    result = runner.invoke(app, ["navigate", "http://example.org/nonexistent"])
    assert result.exit_code != 0
