import json
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from ontoquery.backend import load_backend
from ontoquery.index import OntologyIndex


def _chroma_dir() -> Path:
    return Path(os.environ.get("ONTOQUERY_CHROMA_DIR", ".chroma"))


def _load_state(chroma_dir: Path):
    """Load ChromaDB index and graph backend. Returns (index, backend)."""
    idx = OntologyIndex(chroma_dir)
    try:
        source_dir = idx.get_source_dir()
    except Exception:
        raise RuntimeError(
            f"No index found at {chroma_dir}. Run 'ontoquery index' first."
        )

    try:
        dirs = [Path(d) for d in json.loads(source_dir)]
    except (json.JSONDecodeError, TypeError):
        dirs = [Path(source_dir)]
    backend = load_backend(chroma_dir, source_dirs=dirs)

    return idx, backend


def create_tool_handlers(chroma_dir: Path) -> dict:
    """Create tool handler functions. Returns dict of name -> callable.

    Used by tests to call tool logic directly without MCP transport.
    """
    idx, backend = _load_state(chroma_dir)

    def search_classes(query: str, top_k: int = 10) -> list[dict]:
        return idx.search_raw(query, top_k=top_k)

    def search_domains(
        query: str, domains: list[str], top_k_per_domain: int = 10,
    ) -> dict[str, list[dict]]:
        return idx.search_domains(query, domains, top_k_per_domain=top_k_per_domain)

    def get_class_definition(class_uri: str) -> dict | None:
        return backend.get_class_definition(class_uri)

    def get_subclasses(class_uri: str, depth: int = 1) -> list[dict]:
        return backend.get_subclasses_recursive(class_uri, depth=depth)

    def get_superclasses(class_uri: str) -> list[dict]:
        return backend.get_superclasses(class_uri)

    def get_siblings(class_uri: str) -> list[dict]:
        return backend.get_siblings(class_uri)

    def get_properties(class_uri: str) -> list[dict]:
        return backend.get_properties(class_uri)

    def explore_class(class_uri: str) -> dict | None:
        defn = get_class_definition(class_uri)
        if defn is None:
            return None
        defn["subclasses"] = get_subclasses(class_uri, depth=1)
        defn["siblings"] = get_siblings(class_uri)
        defn["properties"] = get_properties(class_uri)
        return defn

    def get_restrictions(class_uri: str) -> list[dict]:
        return backend.get_restrictions(class_uri)

    def get_disjoint_classes(class_uri: str) -> list[str]:
        return backend.get_disjoint_classes(class_uri)

    def get_equivalent_axioms(class_uri: str) -> list[dict]:
        return backend.get_equivalent_axioms(class_uri)

    return {
        "search_classes": search_classes,
        "search_domains": search_domains,
        "get_class_definition": get_class_definition,
        "get_subclasses": get_subclasses,
        "get_superclasses": get_superclasses,
        "get_siblings": get_siblings,
        "get_properties": get_properties,
        "explore_class": explore_class,
        "get_restrictions": get_restrictions,
        "get_disjoint_classes": get_disjoint_classes,
        "get_equivalent_axioms": get_equivalent_axioms,
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


@mcp.tool()
def get_restrictions(class_uri: str) -> str:
    """Get OWL restrictions (someValuesFrom, allValuesFrom) for a class."""
    return json.dumps(_get_handlers()["get_restrictions"](class_uri))


@mcp.tool()
def get_disjoint_classes(class_uri: str) -> str:
    """Get classes declared mutually exclusive with this class."""
    return json.dumps(_get_handlers()["get_disjoint_classes"](class_uri))


@mcp.tool()
def get_equivalent_axioms(class_uri: str) -> str:
    """Get equivalence class definitions (intersection members and restrictions)."""
    return json.dumps(_get_handlers()["get_equivalent_axioms"](class_uri))


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
