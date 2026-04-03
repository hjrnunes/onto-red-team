# ontoquery — Ontology Query CLI + MCP Server

Semantic search and graph traversal over ontology files. Indexes ontologies into ChromaDB (semantic search) +
oxigraph (graph traversal), exposes both via CLI and MCP server.

## CLI

```bash
cd ontoquery

# Index all ontologies
uv run ontoquery index \
  ../ontologies/CommonCoreOntologies/src/cco-modules/ \
  ../ontologies/commons/ ../ontologies/fibo/ ../ontologies/obo/ \
  ../ontologies/d3fend-ontology/src/ontology/d3fend-protege.ttl \
  ../ontologies/cso/ ../ontologies/bridges/

# Semantic search
uv run ontoquery search "Executive Compensation" "Information about compensation of senior executives"

# Navigate class hierarchy
uv run ontoquery navigate "https://www.commoncoreontologies.org/ont00000449"
```

## MCP Server

Entry point: `ontoquery-mcp` (stdio transport, FastMCP)

11 tools: `search_classes`, `search_domains`, `get_class_definition`, `get_subclasses`, `get_superclasses`,
`get_siblings`, `get_properties`, `explore_class`, `get_restrictions`, `get_disjoint_classes`,
`get_equivalent_axioms`

## Source Layout

```
ontoquery/src/ontoquery/
  cli.py          # Typer CLI: index, search, navigate
  backend.py      # GraphBackend Protocol + OxigraphBackend + RdflibBackend
  axioms.py       # OWL axiom extraction, persistence, loading
  graph.py        # rdflib graph utilities (siblings, subclasses, class definition)
  index.py        # ChromaDB indexing, semantic search, per-domain collections
  mcp_server.py   # MCP server with 11 tools
```

## Key Implementation Details

### Graph Backend

`GraphBackend` protocol (`typing.Protocol`) with two implementations:

- **`OxigraphBackend`** (default): Rust-based via pyoxigraph, RocksDB persistent store at `.chroma/oxigraph/`.
  Parses 338 files in ~5s. Startup from persistent store: 8ms.
- **`RdflibBackend`** (fallback): Pure Python, N-Triples cache at `.chroma/graph.nt`.

Factory functions: `create_index_backend(files, chroma_dir)` for indexing, `load_backend(chroma_dir, source_dirs)`
for runtime. Pattern matching (`quads_for_pattern`) used for all traversals.

### Per-Domain Collections

`index_domain_classes()` creates per-domain ChromaDB collections (one per ontology domain). `search_domains()` queries
them independently. `derive_domain(uri)` maps URIs to domain keys by namespace pattern. This prevents CSO's plain
English labels from crowding out technical classes in search results.

### OWL Axiom Extraction

`axioms.py` extracts restrictions, disjointness, equivalences at index time. Store-agnostic adapter works with both
oxigraph and rdflib. Persisted as `axioms.json` sidecar. Backend protocol extended with `get_restrictions()`,
`get_disjoint_classes()`, `get_equivalent_axioms()`.

### Design Patterns

- **`create_tool_handlers()`** — separates tool logic from MCP transport for testing
- **Lazy-singleton `_get_handlers()`** — heavy state loaded once on first tool call
- **Format detection**: explicit `format="turtle"` for `.ttl`, `format="xml"` for `.rdf`/`.owl`
- **`owl:imports` not followed** — include imported files in indexed directory
- **ChromaDB upserts batched at 5000** (max ChromaDB batch is 5461)
- **RocksDB lock**: only one process can hold write lock

### Index Sizes (tested)

| Configuration | Classes | Files |
|---------------|---------|-------|
| Full (CCO + Commons + FIBO + OBO + D3FEND + CSO) | ~90,228 | 344 |
| Without D3FEND | 85,643 | 338 |
| Healthcare (CCO + OBO without DRON) | 82,526 | 17 |
| Financial Services (CCO + Commons + FIBO) | 4,509 | 332 |
