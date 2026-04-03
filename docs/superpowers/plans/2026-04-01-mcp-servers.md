# MCP Servers Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build two MCP servers — one wrapping the ontoquery ontology engine, one wrapping the AI Atlas Nexus risk knowledge graph — enabling Claude to interactively generate risk taxonomies and domain context from client content policies.

**Architecture:** The ontology MCP server extends the existing `ontoquery/` package with new graph utility functions and an MCP transport layer. The nexus MCP server is a new `nexus-mcp/` uv project that wraps the `AIAtlasNexus` Python API plus a ChromaDB semantic index over risk descriptions. Both use stdio transport for Claude Code integration.

**Tech Stack:** Python 3.11+, uv, mcp[cli] (FastMCP), rdflib, chromadb, ai-atlas-nexus (git dep), pytest

**Spec:** `docs/superpowers/specs/2026-04-01-mcp-servers-design.md`

---

## File Structure

### Ontology MCP Server (extending ontoquery/)

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `ontoquery/pyproject.toml` | Add `mcp[cli]` dependency, `ontoquery-mcp` script entry |
| Modify | `ontoquery/src/ontoquery/graph.py` | Add `get_siblings()`, `get_subclasses_recursive()`, `get_class_definition()` |
| Modify | `ontoquery/src/ontoquery/index.py` | Add `search_raw()` single-parameter search method |
| Create | `ontoquery/src/ontoquery/mcp_server.py` | FastMCP server with 7 tools, startup loading |
| Modify | `ontoquery/tests/conftest.py` | Extend sample TTL with deeper hierarchy for new tests |
| Create | `ontoquery/tests/test_graph_extended.py` | Tests for get_siblings, get_subclasses_recursive, get_class_definition |
| Create | `ontoquery/tests/test_mcp_server.py` | Tests for MCP server tool functions |

### Nexus MCP Server (new project)

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `nexus-mcp/pyproject.toml` | uv project: mcp[cli], chromadb, ai-atlas-nexus git dep |
| Create | `nexus-mcp/src/nexus_mcp/__init__.py` | Package init |
| Create | `nexus-mcp/src/nexus_mcp/risk_index.py` | ChromaDB index over risk descriptions |
| Create | `nexus-mcp/src/nexus_mcp/server.py` | FastMCP server with 8 tools, startup loading |
| Create | `nexus-mcp/tests/__init__.py` | Test package init |
| Create | `nexus-mcp/tests/conftest.py` | Mock AIAtlasNexus fixtures |
| Create | `nexus-mcp/tests/test_risk_index.py` | Tests for RiskIndex class |
| Create | `nexus-mcp/tests/test_server.py` | Tests for MCP server tool functions |

---

## Phase 1: Ontology MCP Server

### Task 1: New graph utility functions

**Files:**
- Modify: `ontoquery/tests/conftest.py`
- Create: `ontoquery/tests/test_graph_extended.py`
- Modify: `ontoquery/src/ontoquery/graph.py`

#### Step 1.1: Extend test fixtures with deeper hierarchy

- [ ] **Add richer sample TTL to conftest.py**

Add `EXTENDED_SAMPLE_TTL` and a `extended_ontology_dir` fixture to `conftest.py`. This extends the existing sample with extra classes for testing siblings and recursive subclasses:

```python
EXTENDED_SAMPLE_TTL = """\
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .

<http://example.org/ont#ClassA> a owl:Class ;
    rdfs:label "Agent" ;
    skos:definition "An entity that acts." .

<http://example.org/ont#ClassB> a owl:Class ;
    rdfs:label "Organization" ;
    rdfs:comment "A group of agents." .

<http://example.org/ont#ClassD> a owl:Class ;
    rdfs:label "Person" ;
    skos:definition "A human agent." ;
    rdfs:subClassOf <http://example.org/ont#ClassA> .

<http://example.org/ont#ClassE> a owl:Class ;
    rdfs:label "Software Agent" ;
    skos:definition "An autonomous software entity." ;
    rdfs:subClassOf <http://example.org/ont#ClassA> .

<http://example.org/ont#ClassF> a owl:Class ;
    rdfs:label "Employee" ;
    skos:definition "A person employed by an organization." ;
    rdfs:subClassOf <http://example.org/ont#ClassD> .

<http://example.org/ont#ClassG> a owl:Class ;
    rdfs:label "Manager" ;
    skos:definition "An employee who manages others." ;
    rdfs:subClassOf <http://example.org/ont#ClassF> .

<http://example.org/ont#prop1> a owl:ObjectProperty ;
    rdfs:label "member of" ;
    rdfs:domain <http://example.org/ont#ClassD> ;
    rdfs:range <http://example.org/ont#ClassB> .
"""


@pytest.fixture
def extended_ontology_dir(tmp_path):
    """Create a temp directory with extended hierarchy for testing."""
    ttl_file = tmp_path / "extended.ttl"
    ttl_file.write_text(EXTENDED_SAMPLE_TTL)
    return tmp_path
```

Hierarchy:
```
ClassA (Agent)
├── ClassD (Person)
│   └── ClassF (Employee)
│       └── ClassG (Manager)
└── ClassE (Software Agent)
ClassB (Organization) — standalone
```

- [ ] **Commit**

```bash
cd ontoquery && git add tests/conftest.py && git commit -m "test: add extended ontology fixture for hierarchy tests"
```

#### Step 1.2: get_siblings (TDD)

- [ ] **Write failing test**

Create `ontoquery/tests/test_graph_extended.py`:

```python
from ontoquery.graph import load_graph, get_siblings


def test_get_siblings(extended_ontology_dir):
    graph = load_graph(extended_ontology_dir)
    siblings = get_siblings(graph, "http://example.org/ont#ClassD")
    uris = {s["uri"] for s in siblings}
    # Person and Software Agent are both subclasses of Agent
    assert "http://example.org/ont#ClassE" in uris
    # Should not include self
    assert "http://example.org/ont#ClassD" not in uris


def test_get_siblings_includes_shared_parent(extended_ontology_dir):
    graph = load_graph(extended_ontology_dir)
    siblings = get_siblings(graph, "http://example.org/ont#ClassD")
    for s in siblings:
        assert "shared_parent" in s
        assert s["shared_parent"]["uri"] == "http://example.org/ont#ClassA"


def test_get_siblings_no_siblings(extended_ontology_dir):
    graph = load_graph(extended_ontology_dir)
    # Manager has no siblings under Employee
    siblings = get_siblings(graph, "http://example.org/ont#ClassG")
    assert len(siblings) == 0


def test_get_siblings_root_class(extended_ontology_dir):
    graph = load_graph(extended_ontology_dir)
    # Agent has no named superclass in this ontology, so no siblings
    siblings = get_siblings(graph, "http://example.org/ont#ClassA")
    assert len(siblings) == 0
```

- [ ] **Run test to verify it fails**

Run: `cd ontoquery && uv run pytest tests/test_graph_extended.py::test_get_siblings -v`
Expected: FAIL with `ImportError: cannot import name 'get_siblings'`

- [ ] **Implement get_siblings in graph.py**

Add to `ontoquery/src/ontoquery/graph.py`:

```python
def get_siblings(graph: Graph, class_uri: str) -> list[dict]:
    """Get other classes that share the same direct superclass."""
    uri = URIRef(class_uri)
    results = []
    seen = set()
    for parent in graph.objects(uri, RDFS.subClassOf):
        if not isinstance(parent, URIRef):
            continue
        parent_label = _get_label(graph, parent)
        for sibling in graph.subjects(RDFS.subClassOf, parent):
            if not isinstance(sibling, URIRef):
                continue
            if sibling == uri:
                continue
            sib_str = str(sibling)
            if sib_str in seen:
                continue
            seen.add(sib_str)
            results.append({
                "uri": sib_str,
                "label": _get_label(graph, sibling),
                "shared_parent": {"uri": str(parent), "label": parent_label},
            })
    return results
```

- [ ] **Run tests to verify they pass**

Run: `cd ontoquery && uv run pytest tests/test_graph_extended.py -v -k siblings`
Expected: 4 PASSED

- [ ] **Commit**

```bash
cd ontoquery && git add src/ontoquery/graph.py tests/test_graph_extended.py && git commit -m "feat: add get_siblings() to graph module"
```

#### Step 1.3: get_subclasses_recursive (TDD)

- [ ] **Write failing test**

Append to `ontoquery/tests/test_graph_extended.py`:

```python
from ontoquery.graph import get_subclasses_recursive


def test_get_subclasses_recursive_depth_1(extended_ontology_dir):
    graph = load_graph(extended_ontology_dir)
    subs = get_subclasses_recursive(graph, "http://example.org/ont#ClassA", depth=1)
    uris = {s["uri"] for s in subs}
    assert "http://example.org/ont#ClassD" in uris
    assert "http://example.org/ont#ClassE" in uris
    # Should NOT include grandchildren at depth 1
    assert "http://example.org/ont#ClassF" not in uris


def test_get_subclasses_recursive_depth_2(extended_ontology_dir):
    graph = load_graph(extended_ontology_dir)
    subs = get_subclasses_recursive(graph, "http://example.org/ont#ClassA", depth=2)
    uris = {s["uri"] for s in subs}
    assert "http://example.org/ont#ClassD" in uris
    assert "http://example.org/ont#ClassE" in uris
    assert "http://example.org/ont#ClassF" in uris
    # Should NOT include great-grandchildren at depth 2
    assert "http://example.org/ont#ClassG" not in uris


def test_get_subclasses_recursive_depth_3(extended_ontology_dir):
    graph = load_graph(extended_ontology_dir)
    subs = get_subclasses_recursive(graph, "http://example.org/ont#ClassA", depth=3)
    uris = {s["uri"] for s in subs}
    assert "http://example.org/ont#ClassG" in uris


def test_get_subclasses_recursive_includes_depth(extended_ontology_dir):
    graph = load_graph(extended_ontology_dir)
    subs = get_subclasses_recursive(graph, "http://example.org/ont#ClassA", depth=3)
    by_uri = {s["uri"]: s for s in subs}
    assert by_uri["http://example.org/ont#ClassD"]["depth"] == 1
    assert by_uri["http://example.org/ont#ClassF"]["depth"] == 2
    assert by_uri["http://example.org/ont#ClassG"]["depth"] == 3


def test_get_subclasses_recursive_leaf_node(extended_ontology_dir):
    graph = load_graph(extended_ontology_dir)
    subs = get_subclasses_recursive(graph, "http://example.org/ont#ClassG", depth=5)
    assert len(subs) == 0
```

- [ ] **Run test to verify it fails**

Run: `cd ontoquery && uv run pytest tests/test_graph_extended.py::test_get_subclasses_recursive_depth_1 -v`
Expected: FAIL with `ImportError: cannot import name 'get_subclasses_recursive'`

- [ ] **Implement get_subclasses_recursive in graph.py**

Add to `ontoquery/src/ontoquery/graph.py`:

```python
from collections import deque


def get_subclasses_recursive(graph: Graph, class_uri: str, depth: int = 1) -> list[dict]:
    """Get subclasses up to `depth` levels deep using BFS."""
    results = []
    seen = set()
    queue = deque()
    queue.append((URIRef(class_uri), 0))
    seen.add(class_uri)

    while queue:
        current_uri, current_depth = queue.popleft()
        if current_depth >= depth:
            continue
        for child in graph.subjects(RDFS.subClassOf, current_uri):
            if not isinstance(child, URIRef):
                continue
            child_str = str(child)
            if child_str in seen:
                continue
            seen.add(child_str)
            results.append({
                "uri": child_str,
                "label": _get_label(graph, child),
                "depth": current_depth + 1,
            })
            queue.append((child, current_depth + 1))

    return results
```

- [ ] **Run tests to verify they pass**

Run: `cd ontoquery && uv run pytest tests/test_graph_extended.py -v -k recursive`
Expected: 5 PASSED

- [ ] **Commit**

```bash
cd ontoquery && git add src/ontoquery/graph.py tests/test_graph_extended.py && git commit -m "feat: add get_subclasses_recursive() with BFS depth traversal"
```

#### Step 1.4: get_class_definition (TDD)

- [ ] **Write failing test**

Append to `ontoquery/tests/test_graph_extended.py`:

```python
from ontoquery.graph import get_class_definition


def test_get_class_definition(extended_ontology_dir):
    graph = load_graph(extended_ontology_dir)
    result = get_class_definition(graph, "http://example.org/ont#ClassD")
    assert result["uri"] == "http://example.org/ont#ClassD"
    assert result["label"] == "Person"
    assert result["definition"] == "A human agent."
    assert any(s["uri"] == "http://example.org/ont#ClassA" for s in result["superclasses"])


def test_get_class_definition_no_definition(extended_ontology_dir):
    graph = load_graph(extended_ontology_dir)
    result = get_class_definition(graph, "http://example.org/ont#ClassB")
    assert result["label"] == "Organization"
    assert result["definition"] == "A group of agents."  # from rdfs:comment fallback


def test_get_class_definition_not_found(extended_ontology_dir):
    graph = load_graph(extended_ontology_dir)
    result = get_class_definition(graph, "http://example.org/nonexistent")
    assert result is None
```

- [ ] **Run test to verify it fails**

Run: `cd ontoquery && uv run pytest tests/test_graph_extended.py::test_get_class_definition -v`
Expected: FAIL with `ImportError: cannot import name 'get_class_definition'`

- [ ] **Implement get_class_definition in graph.py**

Add to `ontoquery/src/ontoquery/graph.py`:

```python
def get_class_definition(graph: Graph, class_uri: str) -> dict | None:
    """Get label, definition, and immediate superclasses for a class."""
    uri = URIRef(class_uri)
    if (uri, RDF.type, OWL.Class) not in graph:
        return None
    label = _get_label(graph, uri)
    if label is None:
        return None
    definition = _get_definition(graph, uri)
    superclasses = get_superclasses(graph, class_uri)
    return {
        "uri": class_uri,
        "label": label,
        "definition": definition,
        "superclasses": superclasses,
    }
```

- [ ] **Run tests to verify they pass**

Run: `cd ontoquery && uv run pytest tests/test_graph_extended.py -v -k "class_definition"`
Expected: 3 PASSED

- [ ] **Run all existing tests to check nothing is broken**

Run: `cd ontoquery && uv run pytest -v`
Expected: All tests PASS (existing 29 + new 12 = 41)

- [ ] **Commit**

```bash
cd ontoquery && git add src/ontoquery/graph.py tests/test_graph_extended.py && git commit -m "feat: add get_class_definition() to graph module"
```

---

### Task 2: Add search_raw to OntologyIndex

**Files:**
- Modify: `ontoquery/tests/test_index.py`
- Modify: `ontoquery/src/ontoquery/index.py`

- [ ] **Write failing test**

Append to `ontoquery/tests/test_index.py`:

```python
def test_search_raw(chroma_dir):
    classes = [
        {"uri": "http://example.org/ont#ClassA", "label": "Agent", "definition": "An entity that acts."},
        {"uri": "http://example.org/ont#ClassB", "label": "Financial Instrument", "definition": "A tradeable asset."},
        {"uri": "http://example.org/ont#ClassC", "label": "Organization", "definition": "A group of agents."},
    ]
    idx = OntologyIndex(chroma_dir)
    idx.index_classes(classes, source_dir="/some/path")

    results = idx.search_raw("tradeable financial asset", top_k=2)
    assert len(results) <= 2
    assert results[0]["label"] == "Financial Instrument"
    for r in results:
        assert "uri" in r
        assert "label" in r
        assert "definition" in r
        assert "distance" in r


def test_search_raw_no_collection(chroma_dir):
    idx = OntologyIndex(chroma_dir)
    try:
        idx.search_raw("test")
        assert False, "Should have raised"
    except ValueError:
        pass
```

- [ ] **Run test to verify it fails**

Run: `cd ontoquery && uv run pytest tests/test_index.py::test_search_raw -v`
Expected: FAIL with `AttributeError: 'OntologyIndex' object has no attribute 'search_raw'`

- [ ] **Implement search_raw in index.py**

Add to `ontoquery/src/ontoquery/index.py`, in the `OntologyIndex` class:

```python
def search_raw(self, query: str, top_k: int = 10) -> list[dict]:
    """Semantic search with a single query string (for MCP tool use)."""
    try:
        collection = self._get_or_create_collection()
    except Exception:
        raise ValueError("No index found. Run 'ontoquery index' first.")

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

- [ ] **Run tests to verify they pass**

Run: `cd ontoquery && uv run pytest tests/test_index.py -v`
Expected: All PASS (existing 4 + new 2 = 6)

- [ ] **Commit**

```bash
cd ontoquery && git add src/ontoquery/index.py tests/test_index.py && git commit -m "feat: add search_raw() single-parameter search to OntologyIndex"
```

---

### Task 3: Ontology MCP server

**Files:**
- Modify: `ontoquery/pyproject.toml`
- Create: `ontoquery/src/ontoquery/mcp_server.py`
- Create: `ontoquery/tests/test_mcp_server.py`

#### Step 3.1: Add dependency and script entry point

- [ ] **Update pyproject.toml**

Add `mcp[cli]` to dependencies and `ontoquery-mcp` to scripts:

In `ontoquery/pyproject.toml`, add `"mcp[cli]>=1.0"` to the `dependencies` list and `ontoquery-mcp = "ontoquery.mcp_server:main"` to `[project.scripts]`.

- [ ] **Commit**

```bash
cd ontoquery && git add pyproject.toml && git commit -m "build: add mcp[cli] dependency and ontoquery-mcp script entry"
```

#### Step 3.2: Write MCP server tests

- [ ] **Write tests for all 7 tool functions**

Create `ontoquery/tests/test_mcp_server.py`. These test the tool handler functions directly (not via MCP transport), using the existing `extended_ontology_dir` and `chroma_dir` fixtures:

```python
import json
import pytest
from ontoquery.index import OntologyIndex
from ontoquery.graph import load_graph, extract_classes
from ontoquery.mcp_server import (
    create_tool_handlers,
)


EXTENDED_SAMPLE_TTL = """\
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .

<http://example.org/ont#ClassA> a owl:Class ;
    rdfs:label "Agent" ;
    skos:definition "An entity that acts." .

<http://example.org/ont#ClassB> a owl:Class ;
    rdfs:label "Organization" ;
    rdfs:comment "A group of agents." .

<http://example.org/ont#ClassD> a owl:Class ;
    rdfs:label "Person" ;
    skos:definition "A human agent." ;
    rdfs:subClassOf <http://example.org/ont#ClassA> .

<http://example.org/ont#ClassE> a owl:Class ;
    rdfs:label "Software Agent" ;
    skos:definition "An autonomous software entity." ;
    rdfs:subClassOf <http://example.org/ont#ClassA> .

<http://example.org/ont#ClassF> a owl:Class ;
    rdfs:label "Employee" ;
    skos:definition "A person employed by an organization." ;
    rdfs:subClassOf <http://example.org/ont#ClassD> .

<http://example.org/ont#prop1> a owl:ObjectProperty ;
    rdfs:label "member of" ;
    rdfs:domain <http://example.org/ont#ClassD> ;
    rdfs:range <http://example.org/ont#ClassB> .
"""


@pytest.fixture
def tools(tmp_path):
    """Set up index + graph and return tool handlers dict."""
    # Write ontology file
    ttl_file = tmp_path / "ontology" / "test.ttl"
    ttl_file.parent.mkdir()
    ttl_file.write_text(EXTENDED_SAMPLE_TTL)

    # Build index
    chroma_dir = tmp_path / "chroma"
    chroma_dir.mkdir()
    ontology_dir = tmp_path / "ontology"
    graph = load_graph(ontology_dir)
    classes = extract_classes(graph, source_file="test.ttl")
    idx = OntologyIndex(chroma_dir)
    idx.index_classes(classes, source_dir=str(ontology_dir))

    # Cache graph
    cache_path = chroma_dir / "graph.nt"
    graph.serialize(str(cache_path), format="nt")

    return create_tool_handlers(chroma_dir)


def test_search_classes(tools):
    result = tools["search_classes"](query="human person agent", top_k=3)
    assert len(result) <= 3
    assert any(r["label"] == "Person" for r in result)


def test_get_class_definition(tools):
    result = tools["get_class_definition"](class_uri="http://example.org/ont#ClassD")
    assert result["label"] == "Person"
    assert result["definition"] == "A human agent."
    assert any(s["uri"] == "http://example.org/ont#ClassA" for s in result["superclasses"])


def test_get_class_definition_not_found(tools):
    result = tools["get_class_definition"](class_uri="http://example.org/nonexistent")
    assert result is None


def test_get_subclasses(tools):
    result = tools["get_subclasses"](class_uri="http://example.org/ont#ClassA", depth=1)
    uris = {r["uri"] for r in result}
    assert "http://example.org/ont#ClassD" in uris
    assert "http://example.org/ont#ClassE" in uris


def test_get_subclasses_recursive(tools):
    result = tools["get_subclasses"](class_uri="http://example.org/ont#ClassA", depth=2)
    uris = {r["uri"] for r in result}
    assert "http://example.org/ont#ClassF" in uris


def test_get_superclasses(tools):
    result = tools["get_superclasses"](class_uri="http://example.org/ont#ClassD")
    uris = {r["uri"] for r in result}
    assert "http://example.org/ont#ClassA" in uris


def test_get_siblings(tools):
    result = tools["get_siblings"](class_uri="http://example.org/ont#ClassD")
    uris = {r["uri"] for r in result}
    assert "http://example.org/ont#ClassE" in uris
    assert "http://example.org/ont#ClassD" not in uris


def test_get_properties(tools):
    result = tools["get_properties"](class_uri="http://example.org/ont#ClassD")
    assert any(p["label"] == "member of" for p in result)


def test_explore_class(tools):
    result = tools["explore_class"](class_uri="http://example.org/ont#ClassD")
    assert result["label"] == "Person"
    assert result["definition"] == "A human agent."
    assert "superclasses" in result
    assert "subclasses" in result
    assert "siblings" in result
    assert "properties" in result
    assert any(s["uri"] == "http://example.org/ont#ClassE" for s in result["siblings"])
```

- [ ] **Run tests to verify they fail**

Run: `cd ontoquery && uv run pytest tests/test_mcp_server.py::test_search_classes -v`
Expected: FAIL with `ImportError: cannot import name 'create_tool_handlers' from 'ontoquery.mcp_server'`

#### Step 3.3: Implement MCP server

- [ ] **Create mcp_server.py**

Create `ontoquery/src/ontoquery/mcp_server.py`:

```python
import json
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from ontoquery.graph import (
    get_class_definition as _get_class_def,
    get_subclasses_recursive,
    get_superclasses as _get_supers,
    get_siblings as _get_sibs,
    get_properties as _get_props,
    load_graph_cached,
)
from ontoquery.index import OntologyIndex


def _chroma_dir() -> Path:
    return Path(os.environ.get("ONTOQUERY_CHROMA_DIR", ".chroma"))


def _load_state(chroma_dir: Path):
    """Load ChromaDB index and rdflib graph. Returns (index, graph)."""
    idx = OntologyIndex(chroma_dir)
    try:
        source_dir = idx.get_source_dir()
    except Exception:
        raise RuntimeError(
            f"No index found at {chroma_dir}. Run 'ontoquery index' first."
        )

    cache_path = chroma_dir / "graph.nt"
    if not cache_path.exists():
        raise RuntimeError(
            f"No graph cache at {cache_path}. Run 'ontoquery index' first."
        )

    try:
        dirs = [Path(d) for d in json.loads(source_dir)]
    except (json.JSONDecodeError, TypeError):
        dirs = [Path(source_dir)]
    graph = load_graph_cached(dirs, cache_path)

    return idx, graph


def create_tool_handlers(chroma_dir: Path) -> dict:
    """Create tool handler functions. Returns dict of name -> callable.

    Used by tests to call tool logic directly without MCP transport.
    """
    idx, graph = _load_state(chroma_dir)

    def search_classes(query: str, top_k: int = 10) -> list[dict]:
        return idx.search_raw(query, top_k=top_k)

    def get_class_definition(class_uri: str) -> dict | None:
        return _get_class_def(graph, class_uri)

    def get_subclasses(class_uri: str, depth: int = 1) -> list[dict]:
        return get_subclasses_recursive(graph, class_uri, depth=depth)

    def get_superclasses(class_uri: str) -> list[dict]:
        return _get_supers(graph, class_uri)

    def get_siblings(class_uri: str) -> list[dict]:
        return _get_sibs(graph, class_uri)

    def get_properties(class_uri: str) -> list[dict]:
        return _get_props(graph, class_uri)

    def explore_class(class_uri: str) -> dict | None:
        defn = get_class_definition(class_uri)
        if defn is None:
            return None
        defn["subclasses"] = get_subclasses(class_uri, depth=1)
        defn["siblings"] = get_siblings(class_uri)
        defn["properties"] = get_properties(class_uri)
        return defn

    return {
        "search_classes": search_classes,
        "get_class_definition": get_class_definition,
        "get_subclasses": get_subclasses,
        "get_superclasses": get_superclasses,
        "get_siblings": get_siblings,
        "get_properties": get_properties,
        "explore_class": explore_class,
    }


mcp = FastMCP("ontoquery")

_handlers = None


def _get_handlers():
    global _handlers
    if _handlers is not None:
        return _handlers
    _handlers = create_tool_handlers(_chroma_dir())
    return _handlers


@mcp.tool()
def search_classes(query: str, top_k: int = 10) -> str:
    """Semantic search over indexed ontology class labels and definitions."""
    return json.dumps(_get_handlers()["search_classes"](query, top_k))


@mcp.tool()
def get_class_definition(class_uri: str) -> str:
    """Get label, definition, and superclasses for an ontology class."""
    result = _get_handlers()["get_class_definition"](class_uri)
    if result is None:
        return json.dumps({"error": f"Class {class_uri} not found"})
    return json.dumps(result)


@mcp.tool()
def get_subclasses(class_uri: str, depth: int = 1) -> str:
    """Get subclasses of an ontology class, optionally recursive up to depth levels."""
    return json.dumps(_get_handlers()["get_subclasses"](class_uri, depth))


@mcp.tool()
def get_superclasses(class_uri: str) -> str:
    """Get direct named superclasses of an ontology class."""
    return json.dumps(_get_handlers()["get_superclasses"](class_uri))


@mcp.tool()
def get_siblings(class_uri: str) -> str:
    """Get other classes that share the same direct superclass."""
    return json.dumps(_get_handlers()["get_siblings"](class_uri))


@mcp.tool()
def get_properties(class_uri: str) -> str:
    """Get properties where this class appears as domain or range."""
    return json.dumps(_get_handlers()["get_properties"](class_uri))


@mcp.tool()
def explore_class(class_uri: str) -> str:
    """Get everything about a class: definition, superclasses, subclasses, siblings, and properties."""
    result = _get_handlers()["explore_class"](class_uri)
    if result is None:
        return json.dumps({"error": f"Class {class_uri} not found"})
    return json.dumps(result)


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
```

**Implementation note:** The MCP tool functions use a lazy-singleton `_get_handlers()` that loads state (ChromaDB + rdflib graph) once on first call and caches it at module level. Same pattern as the nexus server.

- [ ] **Run tests to verify they pass**

Run: `cd ontoquery && uv run pytest tests/test_mcp_server.py -v`
Expected: All 9 PASSED

- [ ] **Run all tests to check nothing is broken**

Run: `cd ontoquery && uv run pytest -v`
Expected: All tests PASS

- [ ] **Commit**

```bash
cd ontoquery && git add src/ontoquery/mcp_server.py tests/test_mcp_server.py && git commit -m "feat: add ontology MCP server with 7 tools"
```

#### Step 3.4: Manual integration test

- [ ] **Verify MCP server starts**

Requires a pre-existing index. If you have one at `ontoquery/.chroma/`, run:

```bash
cd ontoquery && uv run ontoquery-mcp
```

Expected: server starts and waits for stdio input. Ctrl+C to stop.

If no index exists, first run:

```bash
cd ontoquery && uv run ontoquery index ../ontologies/CommonCoreOntologies/src/cco-modules/
```

Then retry the server start.

---

## Phase 2: Nexus MCP Server

### Task 4: Scaffold nexus-mcp project

**Files:**
- Create: `nexus-mcp/pyproject.toml`
- Create: `nexus-mcp/src/nexus_mcp/__init__.py`
- Create: `nexus-mcp/tests/__init__.py`
- Create: `nexus-mcp/tests/conftest.py`

- [ ] **Create project directory structure**

```bash
mkdir -p nexus-mcp/src/nexus_mcp nexus-mcp/tests
```

- [ ] **Create pyproject.toml**

Create `nexus-mcp/pyproject.toml`:

```toml
[project]
name = "nexus-mcp"
version = "0.1.0"
description = "MCP server for AI Atlas Nexus risk knowledge graph"
requires-python = ">=3.11"
dependencies = [
    "mcp[cli]>=1.0",
    "chromadb>=0.5",
    "ai-atlas-nexus @ git+https://github.com/IBM/ai-atlas-nexus.git@main",
]

[project.scripts]
nexus-mcp = "nexus_mcp.server:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/nexus_mcp"]

[tool.pytest.ini_options]
testpaths = ["tests"]

[project.optional-dependencies]
dev = ["pytest>=8.0"]
```

- [ ] **Create package init files**

Create `nexus-mcp/src/nexus_mcp/__init__.py` and `nexus-mcp/tests/__init__.py` as empty files.

- [ ] **Create conftest.py with mock fixtures**

Create `nexus-mcp/tests/conftest.py`:

```python
import pytest
from dataclasses import dataclass, field


@dataclass
class MockRisk:
    id: str
    name: str
    description: str = ""
    concern: str = ""
    tag: str = ""
    risk_type: str = "output"
    descriptor: list = field(default_factory=list)
    isDefinedByTaxonomy: str = ""
    isPartOf: str = ""
    exact_mappings: list = field(default_factory=list)
    close_mappings: list = field(default_factory=list)
    broad_mappings: list = field(default_factory=list)
    narrow_mappings: list = field(default_factory=list)
    related_mappings: list = field(default_factory=list)
    hasRelatedAction: list = field(default_factory=list)
    type: str = "Risk"


@dataclass
class MockAction:
    id: str
    name: str
    description: str = ""
    type: str = "Action"


@dataclass
class MockTaxonomy:
    id: str
    name: str
    description: str = ""
    type: str = "RiskTaxonomy"


@dataclass
class MockGroup:
    id: str
    name: str
    isDefinedByTaxonomy: str = ""
    type: str = "RiskGroup"


MOCK_RISKS = [
    MockRisk(
        id="atlas-prompt-injection",
        name="Prompt injection",
        description="An attacker crafts input to manipulate an LLM.",
        concern="Attackers can override system instructions.",
        tag="prompt-injection",
        isDefinedByTaxonomy="ibm-risk-atlas",
        isPartOf="ibm-risk-atlas-robustness",
        exact_mappings=["llm01-prompt-injection"],
        related_mappings=["atlas-jailbreaking"],
    ),
    MockRisk(
        id="atlas-confidential-data-in-prompt",
        name="Confidential data in prompt",
        description="Users may inadvertently or intentionally include confidential information in prompts.",
        concern="Sensitive data may be exposed or logged.",
        tag="confidential-data-in-prompt",
        isDefinedByTaxonomy="ibm-risk-atlas",
        isPartOf="ibm-risk-atlas-privacy",
        close_mappings=["llm022025-sensitive-information-disclosure"],
    ),
    MockRisk(
        id="llm01-prompt-injection",
        name="LLM01: Prompt Injection",
        description="Prompt injection involves crafting inputs that alter the LLM's behavior.",
        concern="May lead to unauthorized actions or data exposure.",
        tag="llm01",
        isDefinedByTaxonomy="owasp-llm-top-10",
        isPartOf="owasp-llm-top-10-group",
    ),
    MockRisk(
        id="llm022025-sensitive-information-disclosure",
        name="LLM02: Sensitive Information Disclosure",
        description="LLMs may reveal sensitive information in responses.",
        concern="Confidential data leakage through model outputs.",
        tag="llm02",
        isDefinedByTaxonomy="owasp-llm-top-10",
        isPartOf="owasp-llm-top-10-group",
    ),
    MockRisk(
        id="atlas-social-hacking-attack",
        name="Social hacking attack",
        description="An attacker uses social engineering to manipulate users via AI.",
        concern="Users may be tricked into unsafe actions.",
        tag="social-hacking-attack",
        isDefinedByTaxonomy="ibm-risk-atlas",
        isPartOf="ibm-risk-atlas-misuse",
    ),
]

MOCK_ACTIONS = [
    MockAction(
        id="action-input-validation",
        name="Input validation",
        description="Validate and sanitize all inputs before processing.",
    ),
    MockAction(
        id="action-output-filtering",
        name="Output filtering",
        description="Filter model outputs to remove sensitive information.",
    ),
]

MOCK_TAXONOMIES = [
    MockTaxonomy(id="ibm-risk-atlas", name="IBM AI Risk Atlas", description="Comprehensive AI risk taxonomy"),
    MockTaxonomy(id="owasp-llm-top-10", name="OWASP Top 10 for LLMs", description="Top 10 LLM vulnerabilities"),
]

MOCK_GROUPS = [
    MockGroup(id="ibm-risk-atlas-robustness", name="Robustness", isDefinedByTaxonomy="ibm-risk-atlas"),
    MockGroup(id="ibm-risk-atlas-privacy", name="Privacy", isDefinedByTaxonomy="ibm-risk-atlas"),
    MockGroup(id="ibm-risk-atlas-misuse", name="Misuse", isDefinedByTaxonomy="ibm-risk-atlas"),
    MockGroup(id="owasp-llm-top-10-group", name="OWASP LLM Top 10", isDefinedByTaxonomy="owasp-llm-top-10"),
]


# Link actions to risks
MOCK_RISKS[0].hasRelatedAction = ["action-input-validation"]
MOCK_RISKS[1].hasRelatedAction = ["action-output-filtering"]


@pytest.fixture
def chroma_dir(tmp_path):
    d = tmp_path / "chroma"
    d.mkdir()
    return d


@pytest.fixture
def mock_risks():
    return MOCK_RISKS


@pytest.fixture
def mock_actions():
    return MOCK_ACTIONS


@pytest.fixture
def mock_taxonomies():
    return MOCK_TAXONOMIES


@pytest.fixture
def mock_groups():
    return MOCK_GROUPS
```

- [ ] **Install project dependencies**

```bash
cd nexus-mcp && uv sync
```

- [ ] **Commit**

```bash
cd nexus-mcp && git add pyproject.toml src/ tests/ && git commit -m "feat: scaffold nexus-mcp project with mock fixtures"
```

---

### Task 5: RiskIndex class

**Files:**
- Create: `nexus-mcp/tests/test_risk_index.py`
- Create: `nexus-mcp/src/nexus_mcp/risk_index.py`

- [ ] **Write failing tests**

Create `nexus-mcp/tests/test_risk_index.py`:

```python
from nexus_mcp.risk_index import RiskIndex


def test_index_risks(chroma_dir, mock_risks):
    idx = RiskIndex(chroma_dir)
    idx.index_risks(mock_risks)
    assert idx.count() == len(mock_risks)


def test_search(chroma_dir, mock_risks):
    idx = RiskIndex(chroma_dir)
    idx.index_risks(mock_risks)

    results = idx.search("prompt injection attack", top_k=3)
    assert len(results) <= 3
    assert results[0]["name"] == "Prompt injection" or results[0]["name"] == "LLM01: Prompt Injection"
    for r in results:
        assert "id" in r
        assert "name" in r
        assert "description" in r
        assert "taxonomy" in r
        assert "distance" in r


def test_search_filtered_by_taxonomy(chroma_dir, mock_risks):
    idx = RiskIndex(chroma_dir)
    idx.index_risks(mock_risks)

    results = idx.search("injection", top_k=10, taxonomy="ibm-risk-atlas")
    for r in results:
        assert r["taxonomy"] == "ibm-risk-atlas"


def test_search_no_index(chroma_dir):
    idx = RiskIndex(chroma_dir)
    try:
        idx.search("test")
        assert False, "Should have raised"
    except ValueError:
        pass


def test_needs_reindex_empty(chroma_dir, mock_risks):
    idx = RiskIndex(chroma_dir)
    assert idx.needs_reindex(len(mock_risks)) is True


def test_needs_reindex_current(chroma_dir, mock_risks):
    idx = RiskIndex(chroma_dir)
    idx.index_risks(mock_risks)
    assert idx.needs_reindex(len(mock_risks)) is False


def test_needs_reindex_stale(chroma_dir, mock_risks):
    idx = RiskIndex(chroma_dir)
    idx.index_risks(mock_risks)
    # Simulate adding a new risk
    assert idx.needs_reindex(len(mock_risks) + 1) is True
```

- [ ] **Run test to verify it fails**

Run: `cd nexus-mcp && uv run pytest tests/test_risk_index.py::test_index_risks -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'nexus_mcp.risk_index'`

- [ ] **Implement RiskIndex**

Create `nexus-mcp/src/nexus_mcp/risk_index.py`:

```python
from pathlib import Path

import chromadb


COLLECTION_NAME = "risk_entries"


class RiskIndex:
    def __init__(self, chroma_dir: Path):
        self._chroma_dir = Path(chroma_dir)
        self._client = chromadb.PersistentClient(path=str(self._chroma_dir))

    def index_risks(self, risks: list) -> None:
        """Index risk entries into ChromaDB. Overwrites existing collection."""
        try:
            self._client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass

        collection = self._client.create_collection(name=COLLECTION_NAME)

        if not risks:
            return

        ids = []
        documents = []
        metadatas = []
        for risk in risks:
            doc_parts = [f"{risk.name}: {risk.description}"]
            if risk.concern:
                doc_parts.append(f"Concern: {risk.concern}")
            doc = ". ".join(doc_parts)

            ids.append(risk.id)
            documents.append(doc)
            metadatas.append({
                "id": risk.id,
                "name": risk.name,
                "description": risk.description or "",
                "concern": risk.concern or "",
                "taxonomy": risk.isDefinedByTaxonomy or "",
                "risk_type": risk.risk_type or "",
                "group": risk.isPartOf or "",
            })

        batch_size = 5000
        for i in range(0, len(ids), batch_size):
            collection.upsert(
                ids=ids[i:i + batch_size],
                documents=documents[i:i + batch_size],
                metadatas=metadatas[i:i + batch_size],
            )

    def count(self) -> int:
        collection = self._client.get_collection(name=COLLECTION_NAME)
        return collection.count()

    def needs_reindex(self, expected_count: int) -> bool:
        """Check if the index needs rebuilding."""
        try:
            return self.count() != expected_count
        except Exception:
            return True

    def search(self, query: str, top_k: int = 10, taxonomy: str | None = None) -> list[dict]:
        """Semantic search over risk descriptions."""
        try:
            collection = self._client.get_collection(name=COLLECTION_NAME)
        except Exception:
            raise ValueError("No risk index found. Server must index risks on startup.")

        kwargs = {"query_texts": [query], "n_results": top_k}
        if taxonomy:
            kwargs["where"] = {"taxonomy": taxonomy}

        results = collection.query(**kwargs)

        output = []
        for i in range(len(results["ids"][0])):
            meta = results["metadatas"][0][i]
            output.append({
                "id": meta["id"],
                "name": meta["name"],
                "description": meta["description"] or None,
                "concern": meta["concern"] or None,
                "taxonomy": meta["taxonomy"],
                "distance": results["distances"][0][i],
            })
        return output
```

- [ ] **Run tests to verify they pass**

Run: `cd nexus-mcp && uv run pytest tests/test_risk_index.py -v`
Expected: 7 PASSED

- [ ] **Commit**

```bash
cd nexus-mcp && git add src/nexus_mcp/risk_index.py tests/test_risk_index.py && git commit -m "feat: add RiskIndex ChromaDB class for semantic risk search"
```

---

### Task 6: Nexus MCP server

**Files:**
- Create: `nexus-mcp/src/nexus_mcp/server.py`
- Create: `nexus-mcp/tests/test_server.py`

#### Step 6.1: Write server tests

- [ ] **Write tests for all 8 tool functions**

Create `nexus-mcp/tests/test_server.py`. These test the tool handler functions directly using mock data:

```python
import pytest
from nexus_mcp.risk_index import RiskIndex
from nexus_mcp.server import create_tool_handlers


@pytest.fixture
def tools(chroma_dir, mock_risks, mock_actions, mock_taxonomies, mock_groups):
    """Build risk index and return tool handlers."""
    idx = RiskIndex(chroma_dir)
    idx.index_risks(mock_risks)

    # Build lookup dicts simulating what the server does with AIAtlasNexus data
    risks_by_id = {r.id: r for r in mock_risks}
    actions_by_id = {a.id: a for a in mock_actions}
    taxonomies = mock_taxonomies
    groups = mock_groups

    return create_tool_handlers(
        risk_index=idx,
        risks_by_id=risks_by_id,
        actions_by_id=actions_by_id,
        taxonomies=taxonomies,
        groups=groups,
    )


def test_search_risks(tools):
    result = tools["search_risks"](query="prompt injection", top_k=3)
    assert len(result) <= 3
    assert any(r["name"] == "Prompt injection" for r in result)


def test_get_risk_details(tools):
    result = tools["get_risk_details"](risk_id="atlas-prompt-injection")
    assert result["name"] == "Prompt injection"
    assert result["risk_type"] == "output"
    assert result["taxonomy"] == "ibm-risk-atlas"


def test_get_risk_details_by_tag(tools):
    result = tools["get_risk_details"](risk_id="prompt-injection")
    assert result["name"] == "Prompt injection"


def test_get_risk_details_not_found(tools):
    result = tools["get_risk_details"](risk_id="nonexistent")
    assert result is None


def test_get_related_risks(tools):
    result = tools["get_related_risks"](risk_id="atlas-prompt-injection")
    assert len(result) >= 1
    # Should find llm01-prompt-injection as exact mapping
    exact = [r for r in result if r["mapping_type"] == "exact"]
    assert any(r["id"] == "llm01-prompt-injection" for r in exact)


def test_get_related_risks_includes_mapping_type(tools):
    result = tools["get_related_risks"](risk_id="atlas-prompt-injection")
    for r in result:
        assert r["mapping_type"] in ("exact", "close", "broad", "narrow", "related")


def test_get_related_actions(tools):
    result = tools["get_related_actions"](risk_id="atlas-prompt-injection")
    assert len(result) >= 1
    assert any(a["name"] == "Input validation" for a in result)


def test_list_taxonomies(tools):
    result = tools["list_taxonomies"]()
    assert len(result) == 2
    ibm = next(t for t in result if t["id"] == "ibm-risk-atlas")
    assert ibm["name"] == "IBM AI Risk Atlas"
    assert "risk_count" in ibm


def test_list_risk_groups(tools):
    result = tools["list_risk_groups"]()
    assert len(result) == 4


def test_list_risk_groups_filtered(tools):
    result = tools["list_risk_groups"](taxonomy="ibm-risk-atlas")
    assert all(g["taxonomy"] == "ibm-risk-atlas" for g in result)
    assert len(result) == 3


def test_explore_risk(tools):
    result = tools["explore_risk"](risk_id="atlas-prompt-injection")
    assert result["name"] == "Prompt injection"
    assert "related_risks" in result
    assert "related_actions" in result
    assert any(r["id"] == "llm01-prompt-injection" for r in result["related_risks"])


def test_gap_analysis(tools):
    descriptions = [
        "Prompts that seek to gain advice and strategies to commit fraud",
        "Prompts that attempt to inject malicious instructions into the model",
    ]
    result = tools["gap_analysis"](
        risk_descriptions=descriptions,
        target_taxonomy="ibm-risk-atlas",
        distance_threshold=1.5,  # generous threshold for mock data
    )
    assert "covered" in result
    assert "gaps" in result
    assert "coverage_pct" in result
    assert isinstance(result["coverage_pct"], float)
```

- [ ] **Run tests to verify they fail**

Run: `cd nexus-mcp && uv run pytest tests/test_server.py::test_search_risks -v`
Expected: FAIL with `ImportError: cannot import name 'create_tool_handlers' from 'nexus_mcp.server'`

#### Step 6.2: Implement server

- [ ] **Create server.py**

Create `nexus-mcp/src/nexus_mcp/server.py`:

```python
import json
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from nexus_mcp.risk_index import RiskIndex


def create_tool_handlers(
    risk_index: RiskIndex,
    risks_by_id: dict,
    actions_by_id: dict,
    taxonomies: list,
    groups: list,
) -> dict:
    """Create tool handler functions. Returns dict of name -> callable.

    Used by tests to call tool logic directly without MCP transport.
    """

    risks_by_tag = {}
    for risk in risks_by_id.values():
        if hasattr(risk, "tag") and risk.tag:
            risks_by_tag[risk.tag] = risk

    def search_risks(query: str, top_k: int = 10) -> list[dict]:
        return risk_index.search(query, top_k=top_k)

    def get_risk_details(risk_id: str) -> dict | None:
        risk = risks_by_id.get(risk_id) or risks_by_tag.get(risk_id)
        if risk is None:
            return None
        return {
            "id": risk.id,
            "name": risk.name,
            "description": risk.description,
            "concern": risk.concern,
            "risk_type": getattr(risk, "risk_type", None),
            "descriptor": getattr(risk, "descriptor", []),
            "taxonomy": getattr(risk, "isDefinedByTaxonomy", ""),
            "group": getattr(risk, "isPartOf", ""),
        }

    def get_related_risks(risk_id: str) -> list[dict]:
        risk = risks_by_id.get(risk_id) or risks_by_tag.get(risk_id)
        if risk is None:
            return []

        results = []
        mapping_attrs = [
            ("exact_mappings", "exact"),
            ("close_mappings", "close"),
            ("broad_mappings", "broad"),
            ("narrow_mappings", "narrow"),
            ("related_mappings", "related"),
        ]
        for attr, mapping_type in mapping_attrs:
            for ref_id in getattr(risk, attr, []):
                ref_risk = risks_by_id.get(ref_id)
                if ref_risk is None:
                    continue
                results.append({
                    "id": ref_risk.id,
                    "name": ref_risk.name,
                    "description": ref_risk.description,
                    "taxonomy": getattr(ref_risk, "isDefinedByTaxonomy", ""),
                    "mapping_type": mapping_type,
                })
        return results

    def get_related_actions(risk_id: str) -> list[dict]:
        risk = risks_by_id.get(risk_id) or risks_by_tag.get(risk_id)
        if risk is None:
            return []

        results = []
        for action_id in getattr(risk, "hasRelatedAction", []):
            action = actions_by_id.get(action_id)
            if action is None:
                continue
            results.append({
                "id": action.id,
                "name": action.name,
                "description": action.description,
            })
        return results

    def _is_risk_taxonomy(t) -> bool:
        """Check if object is a RiskTaxonomy (works with mocks and real LinkML objects)."""
        try:
            from ai_atlas_nexus.ai_risk_ontology.datamodel.ai_risk_ontology import RiskTaxonomy
            return isinstance(t, RiskTaxonomy)
        except ImportError:
            return getattr(t, "type", "") == "RiskTaxonomy"

    def _is_risk_group(g) -> bool:
        """Check if object is a RiskGroup (works with mocks and real LinkML objects)."""
        try:
            from ai_atlas_nexus.ai_risk_ontology.datamodel.ai_risk_ontology import RiskGroup
            return isinstance(g, RiskGroup)
        except ImportError:
            return getattr(g, "type", "") == "RiskGroup"

    def list_taxonomies() -> list[dict]:
        results = []
        for t in taxonomies:
            if not _is_risk_taxonomy(t):
                continue
            risk_count = sum(
                1 for r in risks_by_id.values()
                if getattr(r, "isDefinedByTaxonomy", "") == t.id
            )
            results.append({
                "id": t.id,
                "name": t.name,
                "description": getattr(t, "description", ""),
                "risk_count": risk_count,
            })
        return results

    def list_risk_groups(taxonomy: str | None = None) -> list[dict]:
        results = []
        for g in groups:
            if not _is_risk_group(g):
                continue
            g_taxonomy = getattr(g, "isDefinedByTaxonomy", "")
            if taxonomy and g_taxonomy != taxonomy:
                continue
            risk_count = sum(
                1 for r in risks_by_id.values()
                if getattr(r, "isPartOf", "") == g.id
            )
            results.append({
                "id": g.id,
                "name": g.name,
                "taxonomy": g_taxonomy,
                "risk_count": risk_count,
            })
        return results

    def explore_risk(risk_id: str) -> dict | None:
        details = get_risk_details(risk_id)
        if details is None:
            return None
        details["related_risks"] = get_related_risks(risk_id)
        details["related_actions"] = get_related_actions(risk_id)
        return details

    def gap_analysis(
        risk_descriptions: list[str],
        target_taxonomy: str = "ibm-risk-atlas",
        distance_threshold: float = 0.5,
    ) -> dict:
        # Get all risks from target taxonomy
        target_risks = {
            r.id: r for r in risks_by_id.values()
            if getattr(r, "isDefinedByTaxonomy", "") == target_taxonomy
        }

        covered = {}  # target_risk_id -> {target_risk, matched_description, distance}
        for desc in risk_descriptions:
            matches = risk_index.search(desc, top_k=5, taxonomy=target_taxonomy)
            for match in matches:
                if match["distance"] <= distance_threshold:
                    rid = match["id"]
                    if rid not in covered or match["distance"] < covered[rid]["distance"]:
                        covered[rid] = {
                            "target_risk": {"id": rid, "name": match["name"]},
                            "matched_description": desc,
                            "distance": match["distance"],
                        }

        gap_risks = []
        for rid, risk in target_risks.items():
            if rid not in covered:
                gap_risks.append({"id": rid, "name": risk.name})

        total = len(target_risks)
        coverage_pct = (len(covered) / total * 100) if total > 0 else 0.0

        return {
            "covered": list(covered.values()),
            "gaps": gap_risks,
            "coverage_pct": round(coverage_pct, 1),
        }

    return {
        "search_risks": search_risks,
        "get_risk_details": get_risk_details,
        "get_related_risks": get_related_risks,
        "get_related_actions": get_related_actions,
        "list_taxonomies": list_taxonomies,
        "list_risk_groups": list_risk_groups,
        "explore_risk": explore_risk,
        "gap_analysis": gap_analysis,
    }


# --- MCP Server ---

mcp = FastMCP("ai-atlas-nexus")

_handlers = None


def _get_handlers():
    global _handlers
    if _handlers is not None:
        return _handlers

    nexus_base_dir = os.environ.get("NEXUS_BASE_DIR")
    if not nexus_base_dir:
        raise RuntimeError("NEXUS_BASE_DIR environment variable must be set")

    from ai_atlas_nexus import AIAtlasNexus

    nexus = AIAtlasNexus(base_dir=nexus_base_dir)

    # Build lookup dicts
    all_risks = nexus.get_all_risks()
    risks_by_id = {r.id: r for r in all_risks}
    all_actions = nexus.get_all_actions()
    actions_by_id = {a.id: a for a in all_actions}
    taxonomies = nexus.get_all_taxonomies()
    groups = nexus.get_all("groups")

    # Build risk index
    chroma_dir = Path(os.environ.get("NEXUS_CHROMA_DIR", ".chroma"))
    chroma_dir.mkdir(parents=True, exist_ok=True)
    idx = RiskIndex(chroma_dir)
    if idx.needs_reindex(len(all_risks)):
        idx.index_risks(all_risks)

    _handlers = create_tool_handlers(
        risk_index=idx,
        risks_by_id=risks_by_id,
        actions_by_id=actions_by_id,
        taxonomies=taxonomies,
        groups=groups,
    )
    return _handlers


@mcp.tool()
def search_risks(query: str, top_k: int = 10) -> str:
    """Semantic search over risk descriptions across all frameworks."""
    return json.dumps(_get_handlers()["search_risks"](query, top_k))


@mcp.tool()
def get_risk_details(risk_id: str) -> str:
    """Get full details for a single risk entry."""
    result = _get_handlers()["get_risk_details"](risk_id)
    if result is None:
        return json.dumps({"error": f"Risk {risk_id} not found"})
    return json.dumps(result)


@mcp.tool()
def get_related_risks(risk_id: str) -> str:
    """Get cross-framework mappings for a risk, with mapping type (exact/close/broad/narrow/related)."""
    return json.dumps(_get_handlers()["get_related_risks"](risk_id))


@mcp.tool()
def get_related_actions(risk_id: str) -> str:
    """Get mitigation actions linked to a risk."""
    return json.dumps(_get_handlers()["get_related_actions"](risk_id))


@mcp.tool()
def list_taxonomies() -> str:
    """List all risk taxonomies in the knowledge graph."""
    return json.dumps(_get_handlers()["list_taxonomies"]())


@mcp.tool()
def list_risk_groups(taxonomy: str = "") -> str:
    """List risk groups, optionally filtered by taxonomy ID."""
    tax = taxonomy if taxonomy else None
    return json.dumps(_get_handlers()["list_risk_groups"](tax))


@mcp.tool()
def explore_risk(risk_id: str) -> str:
    """Get risk details + all cross-mappings + related actions in one call."""
    result = _get_handlers()["explore_risk"](risk_id)
    if result is None:
        return json.dumps({"error": f"Risk {risk_id} not found"})
    return json.dumps(result)


@mcp.tool()
def gap_analysis(risk_descriptions: list[str], target_taxonomy: str = "ibm-risk-atlas", distance_threshold: float = 0.5) -> str:
    """Compare client risk descriptions against a target taxonomy to find coverage gaps."""
    return json.dumps(_get_handlers()["gap_analysis"](risk_descriptions, target_taxonomy, distance_threshold))


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
```

- [ ] **Run tests to verify they pass**

Run: `cd nexus-mcp && uv run pytest tests/test_server.py -v`
Expected: All 12 PASSED

- [ ] **Run all nexus-mcp tests**

Run: `cd nexus-mcp && uv run pytest -v`
Expected: All tests PASS (7 risk_index + 12 server = 19)

- [ ] **Commit**

```bash
cd nexus-mcp && git add src/nexus_mcp/server.py tests/test_server.py && git commit -m "feat: add nexus MCP server with 8 tools"
```

#### Step 6.3: Manual integration test

- [ ] **Verify MCP server starts with real data**

```bash
cd nexus-mcp && NEXUS_BASE_DIR=/Users/hjrnunes/workspace/redhat/ibm/ai-atlas-nexus uv run nexus-mcp
```

Expected: server loads knowledge graph, indexes risks, and waits for stdio input. Ctrl+C to stop.

---

## Post-Implementation

After both servers are built and tested:

1. **Configure in Claude Code** — add both MCP servers to `.claude/settings.json` so Claude Code can use them:

```json
{
  "mcpServers": {
    "ontoquery": {
      "command": "uv",
      "args": ["--directory", "/path/to/ontoquery", "run", "ontoquery-mcp"],
      "env": {
        "ONTOQUERY_CHROMA_DIR": "/path/to/ontoquery/.chroma"
      }
    },
    "ai-atlas-nexus": {
      "command": "uv",
      "args": ["--directory", "/path/to/nexus-mcp", "run", "nexus-mcp"],
      "env": {
        "NEXUS_BASE_DIR": "/path/to/ai-atlas-nexus",
        "NEXUS_CHROMA_DIR": "/path/to/nexus-mcp/.chroma"
      }
    }
  }
}
```

2. **Index ontologies** (if not already done):

```bash
cd ontoquery && uv run ontoquery index ../ontologies/CommonCoreOntologies/src/cco-modules/ ../ontologies/commons/ ../ontologies/fibo/ ../ontologies/obo/
```

3. **Test interactively** — start a Claude Code conversation and verify the tools appear and work with a sample policy JSON.
