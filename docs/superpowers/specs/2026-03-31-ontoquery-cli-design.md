# ontoquery CLI — Design Spec

CLI tool for indexing and querying OWL/RDF ontologies. Prototype for the ontology MCP server. Three commands: index ontology files into a ChromaDB vector store, search for candidate classes given a policy concept, and navigate class hierarchies.

## Project Structure

```
ontoquery/
  pyproject.toml
  src/
    ontoquery/
      __init__.py
      cli.py          # Typer CLI entry points
      backend.py      # GraphBackend Protocol + OxigraphBackend + RdflibBackend
      graph.py        # rdflib graph utilities (used by RdflibBackend)
      index.py        # ChromaDB indexing + semantic search
```

### Dependencies

- `pyoxigraph` — Rust-based RDF store (65x faster parsing, RocksDB persistence)
- `rdflib` — pure-Python RDF library (fallback backend)
- `chromadb` — local persistent vector store with default embedding model (all-MiniLM-L6-v2)
- `typer` — CLI framework

### Runtime artifacts

- `.chroma/` directory (gitignored) — ChromaDB store + `oxigraph/` RocksDB persistent graph store (or `graph.nt` rdflib cache as fallback)

## Commands

### `ontoquery index <directory>`

Recursively finds all `.ttl`, `.rdf`, and `.owl` files under `<directory>`. Parses all files into a graph backend (oxigraph by default, rdflib as fallback) and persists the graph for runtime queries. Extracts OWL classes:

- URI
- Label: `rdfs:label` or `skos:prefLabel`
- Definition, in fallback order: `skos:definition` > `iof-av:naturalLanguageDefinition` > `rdfs:comment`

The IOF ontology uses `iof-av:naturalLanguageDefinition` (namespace `https://spec.industrialontologies.org/ontology/annotation/`) rather than `rdfs:comment` or `skos:definition`, so the extraction must check all three predicates.

Classes without a label are skipped.

`owl:imports` are NOT followed. To get labels for imported classes (e.g. BFO classes referenced as superclasses), include the imported ontology files in the indexed directory.

Upserts into a ChromaDB persistent collection:

| ChromaDB field | Value |
|---|---|
| document | `"{label}: {definition}"` (or `"{label}"` if no definition) |
| metadata | `{"uri": "...", "label": "...", "source_file": "..."}` |
| id | The class URI (deduplicates across files) |

The source directory path is stored in the ChromaDB collection metadata so that `navigate` can reload the graph without the user re-specifying the directory.

Re-running overwrites the existing collection (clean re-index).

Output: summary of files parsed and classes indexed.

### `ontoquery search <concept> <description> [--top-k 10]`

Takes a policy concept name and description. Builds query string `"{concept}: {description}"`. Queries ChromaDB with `top_k` results.

Returns JSON array:

```json
[
  {
    "uri": "https://www.commoncoreontologies.org/ont00000123",
    "label": "Financial Instrument",
    "definition": "An Artifact that...",
    "distance": 0.42,
    "source_file": "ArtifactOntology.ttl"
  }
]
```

### `ontoquery navigate <class-uri> [--direction both]`

Loads the graph backend from the persistent store (oxigraph RocksDB at `.chroma/oxigraph/`, or rdflib NT cache at `.chroma/graph.nt` as fallback). Given a class URI, returns:

- **superclasses** — direct `rdfs:subClassOf` parents, filtering out blank nodes and OWL restrictions
- **subclasses** — direct children
- **properties** — object/data properties where this class appears as `rdfs:domain` or `rdfs:range`, with property label and the other class in the relationship. Note: many OWL ontologies (including CCO and IOF) express relationships via `owl:Restriction` on `rdfs:subClassOf` rather than global `rdfs:domain`/`rdfs:range` declarations, so this will return empty for many classes. Restriction extraction is a future enhancement.

`--direction` flag: `up` (superclasses only), `down` (subclasses only), `both` (default).

Returns JSON:

```json
{
  "uri": "https://www.commoncoreontologies.org/ont00000123",
  "label": "Financial Instrument",
  "superclasses": [
    {"uri": "...", "label": "Artifact"}
  ],
  "subclasses": [
    {"uri": "...", "label": "Debt Instrument"},
    {"uri": "...", "label": "Equity Instrument"}
  ],
  "properties": [
    {
      "uri": "...",
      "label": "has creator",
      "role": "domain",
      "other_class": {"uri": "...", "label": "Agent"}
    }
  ]
}
```

## Data Flow

### Index

```
.ttl/.rdf/.owl files → GraphBackend parse → extract classes → ChromaDB upsert
                      → persist graph (oxigraph: RocksDB, rdflib: N-Triples)
                      → store source dir in collection metadata
```

### Search

```
(concept, description) → query string → ChromaDB similarity search → JSON results
```

### Navigate

```
class URI → load GraphBackend from persistent store
          → oxigraph: open RocksDB (~8ms) OR rdflib: load N-Triples (~50s)
          → pattern-match for superclasses, subclasses, domain/range properties
          → JSON result
```

The `GraphBackend` protocol (`backend.py`) abstracts over two implementations:
- **OxigraphBackend** (default): Rust-based via pyoxigraph. Parses 338 files in ~5s (vs ~6min rdflib). Uses RocksDB persistent store — startup is ~8ms.
- **RdflibBackend** (fallback): Pure Python. Caches parsed graph as `.chroma/graph.nt` N-Triples dump. Startup loads from cache (~50s for full ontology set).

Both implementations use pattern matching (not SPARQL) for traversal queries. The protocol uses `typing.Protocol` (structural subtyping — Python's equivalent of Clojure protocols).

## Error Handling

- **Index**: skip unparseable files with a warning, continue with the rest
- **Search**: error if no collection exists yet (tell user to run index first)
- **Navigate**: error if URI not found in graph

## Known Limitations

- **Duplicate classes from merged/archived files**: Recursive file discovery may pick up merged ontology files (e.g. `CommonCoreOntologiesMerged.ttl`) and archived previous versions alongside the modular source files. URI-based deduplication in ChromaDB handles this, but `source_file` metadata will reflect whichever file was processed last. Users should point at specific subdirectories (e.g. `ontologies/CommonCoreOntologies/src/cco-modules/`) to avoid this.
- **Property coverage**: `rdfs:domain`/`rdfs:range` declarations are sparse in CCO and IOF. Most class relationships are expressed via `owl:Restriction`. The `navigate` properties output will be empty for many classes.
- **No `owl:imports` resolution**: Cross-ontology superclass references will appear as bare URIs without labels unless the imported ontology files are included in the indexed directory.

## What This Is Not

This CLI does not integrate with the AI Atlas Nexus knowledge graph. That is a separate MCP server concern. This tool covers only the ontology query layer: CCO, IOF, and any other OWL/RDF ontologies loaded from local files.
