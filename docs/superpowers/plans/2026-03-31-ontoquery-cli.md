# ontoquery CLI Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a CLI tool that indexes OWL/RDF ontology files into ChromaDB and provides semantic search and hierarchy navigation for LLM-driven ontology querying.

**Architecture:** Three-module package — `graph.py` (rdflib parsing + SPARQL extraction), `index.py` (ChromaDB indexing + search), `cli.py` (Typer entry points). The graph and index layers are independent and reusable for the future MCP server.

**Tech Stack:** Python 3.11+, uv, rdflib, chromadb, typer

**Spec:** `docs/superpowers/specs/2026-03-31-ontoquery-cli-design.md`

---

## File Structure

| File | Responsibility |
|---|---|
| `ontoquery/pyproject.toml` | uv project config, dependencies, CLI entry point |
| `ontoquery/src/ontoquery/__init__.py` | Package init |
| `ontoquery/src/ontoquery/graph.py` | rdflib graph loading from directory, SPARQL class extraction, hierarchy/property queries |
| `ontoquery/src/ontoquery/index.py` | ChromaDB persistent collection management, upsert classes, semantic search |
| `ontoquery/src/ontoquery/cli.py` | Typer app with `index`, `search`, `navigate` commands |
| `ontoquery/tests/conftest.py` | Shared fixtures (tiny TTL ontology, temp directories) |
| `ontoquery/tests/test_graph.py` | Tests for graph loading and SPARQL extraction |
| `ontoquery/tests/test_index.py` | Tests for ChromaDB indexing and search |
| `ontoquery/tests/test_cli.py` | Integration tests for CLI commands |

---

### Task 1: Project scaffolding

**Files:**
- Create: `ontoquery/pyproject.toml`
- Create: `ontoquery/src/ontoquery/__init__.py`
- Create: `ontoquery/src/ontoquery/cli.py` (stub)
- Create: `ontoquery/src/ontoquery/graph.py` (stub)
- Create: `ontoquery/src/ontoquery/index.py` (stub)
- Create: `ontoquery/tests/__init__.py`
- Create: `ontoquery/tests/conftest.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[project]
name = "ontoquery"
version = "0.1.0"
description = "CLI tool for indexing and querying OWL/RDF ontologies"
requires-python = ">=3.11"
dependencies = [
    "rdflib>=7.0",
    "chromadb>=0.5",
    "typer>=0.12",
]

[project.scripts]
ontoquery = "ontoquery.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/ontoquery"]

[tool.pytest.ini_options]
testpaths = ["tests"]

[project.optional-dependencies]
dev = ["pytest>=8.0"]
```

- [ ] **Step 2: Create stub modules**

`src/ontoquery/__init__.py`:
```python
```

`src/ontoquery/graph.py`:
```python
```

`src/ontoquery/index.py`:
```python
```

`src/ontoquery/cli.py`:
```python
import typer

app = typer.Typer()

if __name__ == "__main__":
    app()
```

`tests/__init__.py`:
```python
```

- [ ] **Step 3: Create test fixtures in conftest.py**

This fixture provides a minimal TTL ontology string and a temp directory with TTL and RDF files for testing. The TTL includes classes with `skos:definition`, `rdfs:comment`, and one class with no label (to test skip behavior). The RDF/XML file includes a class with `iof-av:naturalLanguageDefinition`.

```python
import os
import pytest


SAMPLE_TTL = """\
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .

<http://example.org/ont#ClassA> a owl:Class ;
    rdfs:label "Agent" ;
    skos:definition "An entity that acts." .

<http://example.org/ont#ClassB> a owl:Class ;
    rdfs:label "Organization" ;
    rdfs:comment "A group of agents." .

<http://example.org/ont#ClassC> a owl:Class ;
    rdfs:subClassOf <http://example.org/ont#ClassA> .

<http://example.org/ont#ClassD> a owl:Class ;
    rdfs:label "Person" ;
    skos:definition "A human agent." ;
    rdfs:subClassOf <http://example.org/ont#ClassA> .

<http://example.org/ont#prop1> a owl:ObjectProperty ;
    rdfs:label "member of" ;
    rdfs:domain <http://example.org/ont#ClassD> ;
    rdfs:range <http://example.org/ont#ClassB> .
"""

SAMPLE_RDF = """\
<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
         xmlns:owl="http://www.w3.org/2002/07/owl#"
         xmlns:iof-av="https://spec.industrialontologies.org/ontology/annotation/">
  <owl:Class rdf:about="http://example.org/iof#Machine">
    <rdfs:label xml:lang="en">Machine</rdfs:label>
    <iof-av:naturalLanguageDefinition xml:lang="en">A device that performs work.</iof-av:naturalLanguageDefinition>
  </owl:Class>
</rdf:RDF>
"""


@pytest.fixture
def sample_ontology_dir(tmp_path):
    """Create a temp directory with sample TTL and RDF files."""
    ttl_file = tmp_path / "test.ttl"
    ttl_file.write_text(SAMPLE_TTL)
    rdf_file = tmp_path / "test.rdf"
    rdf_file.write_text(SAMPLE_RDF)
    return tmp_path


@pytest.fixture
def chroma_dir(tmp_path):
    """Provide a temp directory for ChromaDB storage."""
    d = tmp_path / "chroma"
    d.mkdir()
    return d
```

- [ ] **Step 4: Install dependencies with uv**

Run: `cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/ontoquery && uv sync --all-extras`
Expected: dependencies installed, `.venv` created

- [ ] **Step 5: Verify pytest runs with no tests**

Run: `cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/ontoquery && uv run pytest -v`
Expected: "no tests ran" or similar, exit 0 (no import errors)

- [ ] **Step 6: Commit**

```bash
cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/ontoquery
git init
git add pyproject.toml src/ tests/
git commit -m "chore: scaffold ontoquery project with dependencies and test fixtures"
```

---

### Task 2: graph.py — file discovery and parsing

**Files:**
- Modify: `ontoquery/src/ontoquery/graph.py`
- Create: `ontoquery/tests/test_graph.py`

- [ ] **Step 1: Write failing test for file discovery**

```python
from ontoquery.graph import find_ontology_files


def test_find_ontology_files(sample_ontology_dir):
    files = find_ontology_files(sample_ontology_dir)
    extensions = {f.suffix for f in files}
    assert extensions == {".ttl", ".rdf"}
    assert len(files) == 2


def test_find_ontology_files_recursive(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    (tmp_path / "top.ttl").write_text("")
    (sub / "nested.rdf").write_text("")
    files = find_ontology_files(tmp_path)
    assert len(files) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/ontoquery && uv run pytest tests/test_graph.py -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Implement find_ontology_files**

```python
from pathlib import Path


def find_ontology_files(directory: Path) -> list[Path]:
    """Recursively find all .ttl and .rdf files under directory."""
    directory = Path(directory)
    files = []
    for ext in ("*.ttl", "*.rdf"):
        files.extend(directory.rglob(ext))
    return sorted(files)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/ontoquery && uv run pytest tests/test_graph.py -v`
Expected: PASS

- [ ] **Step 5: Write failing test for graph loading**

```python
from ontoquery.graph import load_graph


def test_load_graph(sample_ontology_dir):
    graph = load_graph(sample_ontology_dir)
    # Should have loaded triples from both files
    assert len(graph) > 0


def test_load_graph_skips_bad_files(tmp_path):
    (tmp_path / "bad.ttl").write_text("this is not valid turtle @@@@")
    (tmp_path / "good.ttl").write_text(
        '@prefix owl: <http://www.w3.org/2002/07/owl#> .\n'
        '<http://example.org/X> a owl:Class .\n'
    )
    graph = load_graph(tmp_path)
    assert len(graph) > 0  # good.ttl was loaded despite bad.ttl failing
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/ontoquery && uv run pytest tests/test_graph.py::test_load_graph -v`
Expected: FAIL

- [ ] **Step 7: Implement load_graph**

```python
import sys
from rdflib import Graph


FORMAT_MAP = {".ttl": "turtle", ".rdf": "xml"}


def load_graph(directory: Path) -> Graph:
    """Parse all .ttl and .rdf files under directory into a single rdflib Graph."""
    g = Graph()
    for f in find_ontology_files(directory):
        fmt = FORMAT_MAP.get(f.suffix)
        if fmt is None:
            continue
        try:
            g.parse(str(f), format=fmt)
        except Exception as e:
            print(f"Warning: skipping {f.name}: {e}", file=sys.stderr)
    return g
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/ontoquery && uv run pytest tests/test_graph.py -v`
Expected: all PASS

- [ ] **Step 9: Commit**

```bash
git add src/ontoquery/graph.py tests/test_graph.py
git commit -m "feat: add ontology file discovery and rdflib graph loading"
```

---

### Task 3: graph.py — SPARQL class extraction

**Files:**
- Modify: `ontoquery/src/ontoquery/graph.py`
- Modify: `ontoquery/tests/test_graph.py`

- [ ] **Step 1: Write failing test for class extraction**

```python
from ontoquery.graph import extract_classes, load_graph


def test_extract_classes(sample_ontology_dir):
    graph = load_graph(sample_ontology_dir)
    classes = extract_classes(graph)
    uris = {c["uri"] for c in classes}

    # ClassA (Agent) - has label + skos:definition
    assert "http://example.org/ont#ClassA" in uris
    # ClassB (Organization) - has label + rdfs:comment
    assert "http://example.org/ont#ClassB" in uris
    # ClassC - no label, should be skipped
    assert "http://example.org/ont#ClassC" not in uris
    # ClassD (Person) - has label + skos:definition
    assert "http://example.org/ont#ClassD" in uris
    # IOF Machine - has label + iof-av:naturalLanguageDefinition
    assert "http://example.org/iof#Machine" in uris


def test_extract_classes_definitions(sample_ontology_dir):
    graph = load_graph(sample_ontology_dir)
    classes = extract_classes(graph)
    by_uri = {c["uri"]: c for c in classes}

    assert by_uri["http://example.org/ont#ClassA"]["definition"] == "An entity that acts."
    assert by_uri["http://example.org/ont#ClassB"]["definition"] == "A group of agents."
    assert by_uri["http://example.org/iof#Machine"]["definition"] == "A device that performs work."


def test_extract_classes_labels(sample_ontology_dir):
    graph = load_graph(sample_ontology_dir)
    classes = extract_classes(graph)
    by_uri = {c["uri"]: c for c in classes}

    assert by_uri["http://example.org/ont#ClassA"]["label"] == "Agent"
    assert by_uri["http://example.org/ont#ClassD"]["label"] == "Person"


def test_extract_classes_source_file(sample_ontology_dir):
    graph = load_graph(sample_ontology_dir)
    classes = extract_classes(graph, source_file="test.ttl")
    for c in classes:
        assert c["source_file"] == "test.ttl"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/ontoquery && uv run pytest tests/test_graph.py::test_extract_classes -v`
Expected: FAIL

- [ ] **Step 3: Implement extract_classes**

```python
from rdflib import OWL, RDF, RDFS, SKOS, Namespace, URIRef

IOF_AV = Namespace("https://spec.industrialontologies.org/ontology/annotation/")


def extract_classes(graph: Graph, source_file: str = "") -> list[dict]:
    """Extract all OWL classes with label and definition from the graph."""
    classes = []
    seen = set()

    for cls in graph.subjects(RDF.type, OWL.Class):
        if not isinstance(cls, URIRef):
            continue
        uri = str(cls)
        if uri in seen:
            continue
        seen.add(uri)

        label = _get_label(graph, cls)
        if label is None:
            continue

        definition = _get_definition(graph, cls)
        classes.append({
            "uri": uri,
            "label": label,
            "definition": definition,
            "source_file": source_file,
        })

    return classes


def _get_label(graph: Graph, uri: URIRef) -> str | None:
    """Get label from rdfs:label or skos:prefLabel."""
    for pred in (RDFS.label, SKOS.prefLabel):
        for obj in graph.objects(uri, pred):
            return str(obj)
    return None


def _get_definition(graph: Graph, uri: URIRef) -> str | None:
    """Get definition with fallback: skos:definition > iof-av:naturalLanguageDefinition > rdfs:comment."""
    for pred in (SKOS.definition, IOF_AV.naturalLanguageDefinition, RDFS.comment):
        for obj in graph.objects(uri, pred):
            return str(obj)
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/ontoquery && uv run pytest tests/test_graph.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/ontoquery/graph.py tests/test_graph.py
git commit -m "feat: add SPARQL class extraction with definition fallback chain"
```

---

### Task 4: graph.py — hierarchy and property navigation

**Files:**
- Modify: `ontoquery/src/ontoquery/graph.py`
- Modify: `ontoquery/tests/test_graph.py`

- [ ] **Step 1: Write failing test for superclasses**

```python
from ontoquery.graph import get_superclasses, load_graph


def test_get_superclasses(sample_ontology_dir):
    graph = load_graph(sample_ontology_dir)
    supers = get_superclasses(graph, "http://example.org/ont#ClassD")
    uris = {s["uri"] for s in supers}
    assert "http://example.org/ont#ClassA" in uris


def test_get_superclasses_filters_blank_nodes(sample_ontology_dir):
    graph = load_graph(sample_ontology_dir)
    supers = get_superclasses(graph, "http://example.org/ont#ClassD")
    # All results should have string URIs, no blank nodes
    for s in supers:
        assert s["uri"].startswith("http")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/ontoquery && uv run pytest tests/test_graph.py::test_get_superclasses -v`
Expected: FAIL

- [ ] **Step 3: Implement get_superclasses**

```python
def get_superclasses(graph: Graph, class_uri: str) -> list[dict]:
    """Get direct named superclasses (filters out blank nodes)."""
    uri = URIRef(class_uri)
    results = []
    for parent in graph.objects(uri, RDFS.subClassOf):
        if not isinstance(parent, URIRef):
            continue
        label = _get_label(graph, parent)
        results.append({"uri": str(parent), "label": label})
    return results
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/ontoquery && uv run pytest tests/test_graph.py::test_get_superclasses -v`
Expected: PASS

- [ ] **Step 5: Write failing test for subclasses**

```python
from ontoquery.graph import get_subclasses


def test_get_subclasses(sample_ontology_dir):
    graph = load_graph(sample_ontology_dir)
    subs = get_subclasses(graph, "http://example.org/ont#ClassA")
    uris = {s["uri"] for s in subs}
    # ClassC has no label but is still a subclass structurally
    assert "http://example.org/ont#ClassD" in uris
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/ontoquery && uv run pytest tests/test_graph.py::test_get_subclasses -v`
Expected: FAIL

- [ ] **Step 7: Implement get_subclasses**

```python
def get_subclasses(graph: Graph, class_uri: str) -> list[dict]:
    """Get direct named subclasses."""
    uri = URIRef(class_uri)
    results = []
    for child in graph.subjects(RDFS.subClassOf, uri):
        if not isinstance(child, URIRef):
            continue
        label = _get_label(graph, child)
        results.append({"uri": str(child), "label": label})
    return results
```

- [ ] **Step 8: Run test to verify it passes**

Run: `cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/ontoquery && uv run pytest tests/test_graph.py::test_get_subclasses -v`
Expected: PASS

- [ ] **Step 9: Write failing test for properties**

```python
from ontoquery.graph import get_properties


def test_get_properties_domain(sample_ontology_dir):
    graph = load_graph(sample_ontology_dir)
    props = get_properties(graph, "http://example.org/ont#ClassD")
    # ClassD is domain of "member of" with range ClassB
    assert len(props) >= 1
    prop = next(p for p in props if p["label"] == "member of")
    assert prop["role"] == "domain"
    assert prop["other_class"]["uri"] == "http://example.org/ont#ClassB"


def test_get_properties_range(sample_ontology_dir):
    graph = load_graph(sample_ontology_dir)
    props = get_properties(graph, "http://example.org/ont#ClassB")
    # ClassB is range of "member of"
    prop = next(p for p in props if p["label"] == "member of")
    assert prop["role"] == "range"
    assert prop["other_class"]["uri"] == "http://example.org/ont#ClassD"
```

- [ ] **Step 10: Run tests to verify they fail**

Run: `cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/ontoquery && uv run pytest tests/test_graph.py::test_get_properties_domain -v`
Expected: FAIL

- [ ] **Step 11: Implement get_properties**

```python
def get_properties(graph: Graph, class_uri: str) -> list[dict]:
    """Get properties where this class appears as domain or range."""
    uri = URIRef(class_uri)
    results = []

    # Properties where this class is the domain
    for prop in graph.subjects(RDFS.domain, uri):
        if not isinstance(prop, URIRef):
            continue
        prop_label = _get_label(graph, prop)
        for range_cls in graph.objects(prop, RDFS.range):
            if not isinstance(range_cls, URIRef):
                continue
            results.append({
                "uri": str(prop),
                "label": prop_label,
                "role": "domain",
                "other_class": {
                    "uri": str(range_cls),
                    "label": _get_label(graph, range_cls),
                },
            })

    # Properties where this class is the range
    for prop in graph.subjects(RDFS.range, uri):
        if not isinstance(prop, URIRef):
            continue
        prop_label = _get_label(graph, prop)
        for domain_cls in graph.objects(prop, RDFS.domain):
            if not isinstance(domain_cls, URIRef):
                continue
            results.append({
                "uri": str(prop),
                "label": prop_label,
                "role": "range",
                "other_class": {
                    "uri": str(domain_cls),
                    "label": _get_label(graph, domain_cls),
                },
            })

    return results
```

- [ ] **Step 12: Run tests to verify they pass**

Run: `cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/ontoquery && uv run pytest tests/test_graph.py -v`
Expected: all PASS

- [ ] **Step 13: Commit**

```bash
git add src/ontoquery/graph.py tests/test_graph.py
git commit -m "feat: add hierarchy navigation and property lookup"
```

---

### Task 5: index.py — ChromaDB indexing and search

**Files:**
- Modify: `ontoquery/src/ontoquery/index.py`
- Create: `ontoquery/tests/test_index.py`

- [ ] **Step 1: Write failing test for indexing classes**

```python
from ontoquery.index import OntologyIndex


def test_index_classes(chroma_dir):
    classes = [
        {"uri": "http://example.org/ont#ClassA", "label": "Agent", "definition": "An entity that acts."},
        {"uri": "http://example.org/ont#ClassB", "label": "Organization", "definition": None},
    ]
    idx = OntologyIndex(chroma_dir)
    idx.index_classes(classes, source_dir="/some/path")
    assert idx.count() == 2


def test_index_stores_source_dir(chroma_dir):
    idx = OntologyIndex(chroma_dir)
    idx.index_classes([], source_dir="/some/path")
    assert idx.get_source_dir() == "/some/path"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/ontoquery && uv run pytest tests/test_index.py -v`
Expected: FAIL

- [ ] **Step 3: Implement OntologyIndex — init, index_classes, count, get_source_dir**

```python
from pathlib import Path
import chromadb


COLLECTION_NAME = "ontology_classes"


class OntologyIndex:
    def __init__(self, chroma_dir: Path):
        self._chroma_dir = Path(chroma_dir)
        self._client = chromadb.PersistentClient(path=str(self._chroma_dir))
        self._collection = None

    def _get_or_create_collection(self, metadata: dict | None = None) -> chromadb.Collection:
        if metadata is not None:
            # Delete existing to do a clean re-index
            try:
                self._client.delete_collection(COLLECTION_NAME)
            except Exception:
                pass  # Collection may not exist yet
            self._collection = self._client.create_collection(
                name=COLLECTION_NAME,
                metadata=metadata,
            )
        else:
            self._collection = self._client.get_collection(name=COLLECTION_NAME)
        return self._collection

    def index_classes(self, classes: list[dict], source_dir: str) -> None:
        """Index extracted classes into ChromaDB. Overwrites existing collection."""
        # Delete graph cache since we're re-indexing
        cache_path = self._chroma_dir / "graph.nt"
        if cache_path.exists():
            cache_path.unlink()

        collection = self._get_or_create_collection(
            metadata={"source_dir": source_dir}
        )
        if not classes:
            return

        ids = []
        documents = []
        metadatas = []
        for cls in classes:
            uri = cls["uri"]
            label = cls["label"]
            definition = cls.get("definition")
            source_file = cls.get("source_file", "")

            doc = f"{label}: {definition}" if definition else label
            ids.append(uri)
            documents.append(doc)
            metadatas.append({
                "uri": uri,
                "label": label,
                "definition": definition or "",
                "source_file": source_file,
            })

        collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

    def count(self) -> int:
        collection = self._get_or_create_collection()
        return collection.count()

    def get_source_dir(self) -> str:
        collection = self._get_or_create_collection()
        return collection.metadata["source_dir"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/ontoquery && uv run pytest tests/test_index.py -v`
Expected: PASS

- [ ] **Step 5: Write failing test for search**

```python
def test_search(chroma_dir):
    classes = [
        {"uri": "http://example.org/ont#ClassA", "label": "Agent", "definition": "An entity that acts."},
        {"uri": "http://example.org/ont#ClassB", "label": "Financial Instrument", "definition": "A tradeable asset."},
        {"uri": "http://example.org/ont#ClassC", "label": "Organization", "definition": "A group of agents."},
    ]
    idx = OntologyIndex(chroma_dir)
    idx.index_classes(classes, source_dir="/some/path")

    results = idx.search("Investment Advice", "Strategies for stock market investment", top_k=2)
    assert len(results) <= 2
    # Each result should have the expected fields
    for r in results:
        assert "uri" in r
        assert "label" in r
        assert "definition" in r
        assert "distance" in r


def test_search_no_collection(chroma_dir):
    idx = OntologyIndex(chroma_dir)
    try:
        idx.search("test", "test")
        assert False, "Should have raised"
    except ValueError:
        pass
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/ontoquery && uv run pytest tests/test_index.py::test_search -v`
Expected: FAIL

- [ ] **Step 7: Implement search**

```python
    def search(self, concept: str, description: str, top_k: int = 10) -> list[dict]:
        """Semantic search for ontology classes matching a policy concept."""
        try:
            collection = self._get_or_create_collection()
        except Exception:
            raise ValueError("No index found. Run 'ontoquery index' first.")

        query = f"{concept}: {description}"
        results = collection.query(query_texts=[query], n_results=top_k)

        output = []
        for i in range(len(results["ids"][0])):
            meta = results["metadatas"][0][i]
            output.append({
                "uri": meta["uri"],
                "label": meta["label"],
                "definition": meta["definition"] or None,
                "distance": results["distances"][0][i],
                "source_file": meta.get("source_file", ""),
            })
        return output
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/ontoquery && uv run pytest tests/test_index.py -v`
Expected: all PASS

- [ ] **Step 9: Commit**

```bash
git add src/ontoquery/index.py tests/test_index.py
git commit -m "feat: add ChromaDB indexing and semantic search"
```

---

### Task 6: graph.py — N-Triples caching for navigate

**Files:**
- Modify: `ontoquery/src/ontoquery/graph.py`
- Modify: `ontoquery/tests/test_graph.py`

- [ ] **Step 1: Write failing test for cached graph loading**

```python
from ontoquery.graph import load_graph_cached


def test_load_graph_cached_creates_cache(sample_ontology_dir, tmp_path):
    cache_path = tmp_path / "graph.nt"
    graph = load_graph_cached(sample_ontology_dir, cache_path)
    assert len(graph) > 0
    assert cache_path.exists()


def test_load_graph_cached_uses_cache(sample_ontology_dir, tmp_path):
    cache_path = tmp_path / "graph.nt"
    # First call creates cache
    graph1 = load_graph_cached(sample_ontology_dir, cache_path)
    count1 = len(graph1)
    # Second call loads from cache (we can verify by checking it still works)
    graph2 = load_graph_cached(sample_ontology_dir, cache_path)
    assert len(graph2) == count1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/ontoquery && uv run pytest tests/test_graph.py::test_load_graph_cached_creates_cache -v`
Expected: FAIL

- [ ] **Step 3: Implement load_graph_cached**

```python
def load_graph_cached(directory: Path, cache_path: Path) -> Graph:
    """Load graph from cache if available, otherwise parse and cache."""
    cache_path = Path(cache_path)
    if cache_path.exists():
        g = Graph()
        g.parse(str(cache_path), format="nt")
        return g

    g = load_graph(directory)
    g.serialize(str(cache_path), format="nt")
    return g
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/ontoquery && uv run pytest tests/test_graph.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/ontoquery/graph.py tests/test_graph.py
git commit -m "feat: add N-Triples caching for graph loading"
```

---

### Task 7: cli.py — index command

**Files:**
- Modify: `ontoquery/src/ontoquery/cli.py`
- Create: `ontoquery/tests/test_cli.py`

- [ ] **Step 1: Write failing test for index command**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/ontoquery && uv run pytest tests/test_cli.py::test_index_command -v`
Expected: FAIL

- [ ] **Step 3: Implement index command**

The CLI uses `ONTOQUERY_CHROMA_DIR` env var (defaulting to `.chroma` in cwd) so tests can override the storage location.

```python
import json
import sys
import os
from pathlib import Path
import typer
from rdflib import Graph
from ontoquery.graph import extract_classes, find_ontology_files, FORMAT_MAP
from ontoquery.index import OntologyIndex

app = typer.Typer()


def _chroma_dir() -> Path:
    return Path(os.environ.get("ONTOQUERY_CHROMA_DIR", ".chroma"))


@app.command()
def index(directory: Path):
    """Index all ontology files in a directory into ChromaDB."""
    if not directory.exists():
        typer.echo(f"Error: directory {directory} does not exist", err=True)
        raise typer.Exit(1)

    files = find_ontology_files(directory)
    typer.echo(f"Found {len(files)} ontology files")

    # Parse each file individually so we can track source_file per class
    all_classes = {}  # uri -> class dict (deduplicates, last write wins)
    for f in files:
        fmt = FORMAT_MAP.get(f.suffix)
        if fmt is None:
            continue
        try:
            g = Graph()
            g.parse(str(f), format=fmt)
        except Exception as e:
            print(f"Warning: skipping {f.name}: {e}", file=sys.stderr)
            continue
        for cls in extract_classes(g, source_file=f.name):
            all_classes[cls["uri"]] = cls

    classes = list(all_classes.values())
    idx = OntologyIndex(_chroma_dir())
    idx.index_classes(classes, source_dir=str(directory.resolve()))

    typer.echo(f"{len(files)} files parsed, {len(classes)} classes indexed")


if __name__ == "__main__":
    app()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/ontoquery && uv run pytest tests/test_cli.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ontoquery/cli.py tests/test_cli.py
git commit -m "feat: add index CLI command"
```

---

### Task 8: cli.py — search command

**Files:**
- Modify: `ontoquery/src/ontoquery/cli.py`
- Modify: `ontoquery/tests/test_cli.py`

- [ ] **Step 1: Write failing test for search command**

```python
import json


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/ontoquery && uv run pytest tests/test_cli.py::test_search_command -v`
Expected: FAIL

- [ ] **Step 3: Implement search command**

```python
@app.command()
def search(
    concept: str,
    description: str,
    top_k: int = typer.Option(10, "--top-k", help="Number of results to return"),
):
    """Search indexed ontology classes for a policy concept."""
    try:
        idx = OntologyIndex(_chroma_dir())
        results = idx.search(concept, description, top_k=top_k)
    except (ValueError, Exception) as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    typer.echo(json.dumps(results, indent=2))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/ontoquery && uv run pytest tests/test_cli.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/ontoquery/cli.py tests/test_cli.py
git commit -m "feat: add search CLI command"
```

---

### Task 9: cli.py — navigate command

**Files:**
- Modify: `ontoquery/src/ontoquery/cli.py`
- Modify: `ontoquery/tests/test_cli.py`

- [ ] **Step 1: Write failing test for navigate command**

```python
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
    # Should have "member of" property
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/ontoquery && uv run pytest tests/test_cli.py::test_navigate_command -v`
Expected: FAIL

- [ ] **Step 3: Implement navigate command**

```python
from rdflib import URIRef, RDF
from rdflib.namespace import OWL
from ontoquery.graph import (
    load_graph_cached, get_superclasses, get_subclasses, get_properties, _get_label,
)


@app.command()
def navigate(
    class_uri: str,
    direction: str = typer.Option("both", "--direction", help="up, down, or both"),
):
    """Navigate the class hierarchy for a given ontology class URI."""
    try:
        idx = OntologyIndex(_chroma_dir())
        source_dir = idx.get_source_dir()
    except (ValueError, Exception) as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    cache_path = _chroma_dir() / "graph.nt"
    graph = load_graph_cached(Path(source_dir), cache_path)

    # Check the URI exists as a class in the graph
    uri_ref = URIRef(class_uri)
    if (uri_ref, RDF.type, OWL.Class) not in graph:
        typer.echo(f"Error: {class_uri} not found as owl:Class in graph", err=True)
        raise typer.Exit(1)

    label = _get_label(graph, uri_ref)
    result = {"uri": class_uri, "label": label}

    if direction in ("up", "both"):
        result["superclasses"] = get_superclasses(graph, class_uri)
    if direction in ("down", "both"):
        result["subclasses"] = get_subclasses(graph, class_uri)

    result["properties"] = get_properties(graph, class_uri)

    typer.echo(json.dumps(result, indent=2))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/ontoquery && uv run pytest tests/test_cli.py -v`
Expected: all PASS

- [ ] **Step 5: Run full test suite**

Run: `cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/ontoquery && uv run pytest -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add src/ontoquery/cli.py tests/test_cli.py
git commit -m "feat: add navigate CLI command with N-Triples caching"
```

---

### Task 10: Smoke test against real ontologies

This is a manual verification task, not unit tests. Run the CLI against the actual CCO and IOF files.

**Files:** None modified

- [ ] **Step 1: Index CCO modules**

Run: `cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/ontoquery && uv run ontoquery index ../ontologies/CommonCoreOntologies/src/cco-modules/`
Expected: prints file count and class count (should be ~11 files, several hundred classes)

- [ ] **Step 2: Search for a banking concept**

Run: `cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/ontoquery && uv run ontoquery search "Executive Compensation" "Prompts that seek information about the compensation of senior executives"`
Expected: JSON array with relevant CCO classes (likely hits on Agent, Organization, Role-related classes)

- [ ] **Step 3: Navigate a result**

Pick a URI from the search results and run:
`uv run ontoquery navigate "<uri-from-search>"`
Expected: JSON with superclasses, subclasses, and properties

- [ ] **Step 4: Re-index with IOF**

Run: `cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/ontoquery && uv run ontoquery index ../ontologies/`
Expected: indexes both CCO and IOF files, higher class count

- [ ] **Step 5: Search for an Aramco concept**

Run: `cd /Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/ontoquery && uv run ontoquery search "Operational Security" "Circumvent safety protocols or exploit operational thresholds"`
Expected: JSON array with relevant classes from CCO and/or IOF

- [ ] **Step 6: Add .gitignore and commit**

Add `.chroma/` to `.gitignore`:

```
.chroma/
```

```bash
git add .gitignore
git commit -m "chore: add .gitignore for ChromaDB artifacts"
```
