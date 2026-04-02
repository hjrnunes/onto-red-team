# Formal Reasoning Integration Design

**Date:** 2026-04-02
**Status:** Draft

## Problem

The pipeline uses ontologies purely as taxonomies — `rdfs:subClassOf` hierarchies, labels, definitions, and `rdfs:domain/range`. It ignores all formal OWL axioms, despite substantial axiom counts across CCO, D3FEND, and FIBO:

- **~106,000 OWL restrictions** (`owl:someValuesFrom`, `owl:allValuesFrom`) — the vast majority in FIBO (complex financial class definitions) and D3FEND (technique/artifact relationships)
- **~21,000 equivalence classes** — primarily FIBO (financial instrument classifications defined by intersection of properties)
- **~950 disjointness declarations** — CCO pairwise `owl:disjointWith` + D3FEND `owl:AllDisjointClasses` groups
- **~80 property hierarchies** and 5 transitive properties

Two specific gaps result:

1. **No validation of semantic coherence (A):** The LLM can select enumeration candidates that the ontology declares mutually exclusive. Example: two sibling CCO classes under the same parent that carry `owl:disjointWith` — the LLM sees them as similar (same parent, similar labels) but the ontology says they cannot co-occur. Currently ~950 disjoint declarations are ignored.

2. **Missed structurally-linked classes (B):** Semantic search (embedding similarity) misses classes that are formally related through OWL restrictions but use different vocabulary. Example: `InformationBearingArtifact` has a `someValuesFrom` restriction linking it to `InformationContentEntity` via `is_about` — a structurally relevant candidate that embedding search may not surface because the labels share no words.

Assessment data shows symptoms: FIBO `SecurityIdentifier` matching infosec "security" (semantic collision that restriction context could disambiguate), and narrow axis diversity from search-only discovery.

## Approach

**Targeted axiom extraction** into a sidecar store, consumed through the existing `onto_handlers` pattern. No OWL reasoner — we parse what's asserted, not what's entailed. Axioms are extracted once at `ontoquery index` time, persisted as JSON, and queried via dict lookups at runtime.

**Scale consideration:** The raw axiom volume is large (~106k restrictions, ~21k equivalences, ~950 disjoint) — the vast majority from FIBO's deeply axiomatized financial class definitions. At extraction time, we filter to only retain axioms for classes that exist in the ChromaDB index (i.e., classes with labels). This eliminates blank-node-only intermediate classes and anonymous restrictions that have no consumer in the pipeline. Estimated filtered output: ~5-15MB JSON depending on ontology mix.

Validation (A) is implemented as a post-processing filter in `contextualize`. Discovery (B) is implemented as a second expansion step in `anchor` after the existing `expand_candidates()`.

**No new LLM calls. No new pipeline stages. No new heavy dependencies.**

Future direction: hybrid approach with one-time reasoner precomputation during indexing (documented but not implemented).

## Design

### Component 1: Axiom Extraction (`ontoquery/src/ontoquery/axioms.py`)

New module responsible for extracting, persisting, and loading axiom indexes. Three indexes, all keyed by full class URI:

**Restrictions index** — `dict[str, list[dict]]`

Each restriction is `{"type": "someValuesFrom"|"allValuesFrom"|"hasValue", "property": str, "filler": str}`.

Extracted by walking: `<class> rdfs:subClassOf <bnode>` where `<bnode> rdf:type owl:Restriction`. For each restriction bnode, read `owl:onProperty` and then `owl:someValuesFrom`, `owl:allValuesFrom`, or `owl:hasValue`. Skip qualified cardinality (`owl:minQualifiedCardinality`, `owl:maxQualifiedCardinality`) — low value for prompt generation.

Also extract restrictions that appear inside `owl:equivalentClass` intersection definitions (walk `owl:intersectionOf` RDF lists, check each member for `rdf:type owl:Restriction`).

```python
def extract_restrictions(store) -> dict[str, list[dict]]:
    """Extract OWL restrictions from rdfs:subClassOf and owl:equivalentClass."""
```

**Disjointness index** — `dict[str, list[str]]`

Symmetric: if A disjoint with B, both `A -> [B]` and `B -> [A]` are stored.

Extracted from two patterns:
- `<class> owl:disjointWith <other>` — pairwise (CCO uses this)
- `<bnode> rdf:type owl:AllDisjointClasses; owl:members <list>` — walk the RDF list, make all pairs disjoint (D3FEND uses this)

```python
def extract_disjointness(store) -> dict[str, list[str]]:
    """Extract disjointness declarations (symmetric)."""
```

**Equivalence index** — `dict[str, list[dict]]`

Each equivalence is `{"type": "intersection"|"class", "members": list[str], "restrictions": list[dict]}`.

- Simple equivalences: `<class> owl:equivalentClass <other_named_class>` → `{"type": "class", "members": [other_uri], "restrictions": []}`
- Intersection equivalences: `<class> owl:equivalentClass <bnode>` where bnode has `owl:intersectionOf` → walk the RDF list, separate named class members from restriction bnodes

```python
def extract_equivalences(store) -> dict[str, list[dict]]:
    """Extract equivalence class definitions."""
```

**Orchestration and persistence:**

```python
def extract_axioms(backend: GraphBackend) -> dict:
    """Extract all axiom types from a backend's underlying store.

    Returns {"restrictions": ..., "disjointness": ..., "equivalences": ...}.

    Accesses the raw store via backend._store (oxigraph) or backend._graph (rdflib).
    Both stores support the same pattern-matching operations needed for axiom extraction
    but with different APIs — oxigraph uses quads_for_pattern(), rdflib uses triples().
    The extraction functions detect which store type they receive and use the appropriate API.
    """

def save_axioms(axioms: dict, path: Path) -> None:
    """Write axiom index to JSON file."""

def load_axioms(path: Path) -> dict | None:
    """Load axiom index from JSON file. Returns None if file doesn't exist."""
```

File location: `<chroma_dir>/axioms.json`, alongside the oxigraph store.

**Filtering by indexed classes:** After raw extraction, each index is filtered to retain only entries where the class URI (key) has a label in the backend (`backend.get_label(uri) is not None`). This removes axioms for anonymous/intermediate classes that are not in the ChromaDB index and therefore never appear as candidates. Filler URIs in restrictions and member URIs in equivalences are kept even if they're not indexed (they may be discovered through these axioms).

**RDF list traversal:** Both `owl:intersectionOf` and `owl:AllDisjointClasses` use RDF lists (`rdf:first`/`rdf:rest`/`rdf:nil` chains). A helper function walks these:

```python
def _traverse_rdf_list(store, list_head) -> list:
    """Walk rdf:first/rdf:rest chain, return list of nodes."""
```

**Blank node handling:** Restrictions and intersections are represented as blank nodes. The oxigraph store's `quads_for_pattern` returns `BlankNode` objects for these — we match on them but never persist them (we extract the structured data and discard the bnode identity).

**Store API abstraction:** Both oxigraph (`Store.quads_for_pattern`) and rdflib (`Graph.triples`) support pattern matching with wildcards. A thin adapter function normalizes the API:

```python
def _query_triples(store, subject, predicate, obj):
    """Yield (s, p, o) triples matching the pattern. Works with oxigraph Store or rdflib Graph."""
```

**Scale:** ~128k raw axioms across CCO+D3FEND+FIBO+OBO. After filtering to indexed classes, expected ~20-40k retained. Extraction is a single pass over the graph after loading — adds seconds to `ontoquery index`, not minutes. JSON output estimated 5-15MB depending on ontology mix.

### Component 2: Backend Protocol Extension (`ontoquery/src/ontoquery/backend.py`)

Three new methods added to `GraphBackend` protocol and both implementations:

```python
class GraphBackend(Protocol):
    # ... existing 10 methods ...
    def get_restrictions(self, class_uri: str) -> list[dict]: ...
    def get_disjoint_classes(self, class_uri: str) -> list[str]: ...
    def get_equivalent_axioms(self, class_uri: str) -> list[dict]: ...
```

**Constructor injection:** Both `OxigraphBackend` and `RdflibBackend` accept an optional `axioms` parameter in `__init__`:

```python
class OxigraphBackend:
    def __init__(self, store: ox.Store, axioms: dict | None = None):
        self._store = store
        self._axioms = axioms or {"restrictions": {}, "disjointness": {}, "equivalences": {}}

class RdflibBackend:
    def __init__(self, graph: Graph, axioms: dict | None = None):
        self._graph = graph
        self._axioms = axioms or {"restrictions": {}, "disjointness": {}, "equivalences": {}}
```

The `axioms` parameter defaults to `None`, so all existing callers (tests, direct construction) continue to work without changes. The three new methods are pure dict lookups:

```python
def get_restrictions(self, class_uri: str) -> list[dict]:
    return self._axioms.get("restrictions", {}).get(class_uri, [])
```

**Protocol structural typing note:** Adding methods to a `typing.Protocol` only affects code that explicitly checks `isinstance(obj, GraphBackend)`. Since the pipeline accesses backends through `onto_handlers` dicts (not Protocol checks), existing consumers are unaffected. The Protocol change documents the expanded contract. Both concrete implementations gain the methods, satisfying the Protocol structurally.

**Factory changes:** `load_backend()` calls `load_axioms(chroma_dir / "axioms.json")` and passes the result to the backend constructor. `create_index_backend()` calls `extract_axioms(backend)` after construction, then `save_axioms()`, and sets `backend._axioms = axioms` (since the backend is already constructed before extraction can run).

**Graceful degradation:** If `axioms.json` doesn't exist, `load_axioms()` returns `None`, and the backend initializes with empty axiom dicts. All three methods return empty lists. A warning is logged once: "Axiom index not found — run 'ontoquery index' to enable formal reasoning features."

### Component 3: MCP Server Tools (`ontoquery/src/ontoquery/mcp_server.py`)

Three new tools in `create_tool_handlers()`:

| Tool | Parameters | Returns |
|------|-----------|---------|
| `get_restrictions` | `class_uri` | List of restrictions (type, property, filler) |
| `get_disjoint_classes` | `class_uri` | List of class URIs known to be mutually exclusive |
| `get_equivalent_axioms` | `class_uri` | List of equivalence definitions (members + restrictions) |

Same pattern as existing tools. Added to the handler dict returned by `create_tool_handlers()`.

### Component 4: Disjointness Validation in Contextualize (`refiner/stages/contextualize.py`)

After the LLM returns filtered enumerations and after existing post-processing (self-reference filter, domain filter, URI validation), add a disjointness check.

**Relevance ranking:** A helper maps relevance strings to comparable integers:

```python
def _relevance_rank(relevance: str) -> int:
    return {"high": 3, "medium": 2, "low": 1}.get(relevance, 0)
```

**Logic:** For each axis's validated enumerations, check all pairs for disjointness. When a conflict is found, keep the enumeration with higher relevance (high > medium > low). If tied, keep the one that appeared first (stable ordering).

The algorithm is greedy: it iterates through enumerations in order, and when it encounters a conflict with an already-kept enumeration, it removes the lower-relevance one. In multi-way disjoint scenarios (A⊥B, B⊥C, A⊥C), this means the first enum processed has an advantage — it gets to remove its conflicts before they can remove later ones. This is acceptable because: (1) enumerations arrive relevance-sorted from the LLM, so higher-relevance items naturally come first; (2) keeping more items from a disjoint set would violate the ontology's mutual exclusivity constraint.

When the current enum loses a conflict (lower relevance than a conflicting enum), it marks itself as removed and breaks out of the inner loop immediately — no point checking further conflicts for a removed enum.

```python
# After valid_enums is built...
if onto_handlers.get("get_disjoint_classes"):
    filtered_by_disjoint = []
    removed_uris: set[str] = set()
    for enum in valid_enums:
        if enum.class_uri in removed_uris:
            continue
        disjoints = set(onto_handlers["get_disjoint_classes"](enum.class_uri))
        conflicting = [e for e in valid_enums if e.class_uri in disjoints and e.class_uri not in removed_uris]
        for conflict in conflicting:
            if _relevance_rank(enum.relevance) >= _relevance_rank(conflict.relevance):
                removed_uris.add(conflict.class_uri)
            else:
                removed_uris.add(enum.class_uri)
                break  # Current enum is removed, stop checking its conflicts
        if enum.class_uri not in removed_uris:
            filtered_by_disjoint.append(enum)
    valid_enums = filtered_by_disjoint
```

**Restriction context in LLM prompt:** Before the LLM call, if the axis class has restrictions, include them in the prompt so the LLM can make informed filtering decisions:

```
Axis: InformationBearingArtifact (http://...)
Roles: object, instrument
Ontology constraints:
  - must have part some PageOfInformationBearingEntity
  - is about some InformationContentEntity
Subclasses:
  - MaterialCopyOfABook: ... [satisfies: has part some Page]
  - DigitalDocument: ...
```

This is additive to the existing prompt structure (~2-3 extra lines per axis when restrictions exist). The LLM uses this as context but the formal disjointness check is the hard filter.

**Pipeline events:**

| Event | Fields |
|-------|--------|
| `disjoint_filtered` | `axis_uri`, `kept`, `filtered`, `risk_id` |
| `restriction_context_added` | `axis_uri`, `restriction_count` |

### Component 5: Restriction-Based Discovery in Anchor (`refiner/stages/anchor.py`)

After `expand_candidates()` returns its frequency-ranked candidates, add a second expansion step using restrictions and equivalences.

**Restriction expansion:** For each candidate from search, look up its restrictions. Each filler class is a structurally related candidate:

```python
restriction_candidates = []
seen_uris = {c["uri"] for c in candidates}
for c in candidates:
    for r in onto_handlers["get_restrictions"](c["uri"]):
        filler = r.get("filler", "")
        if not filler or filler in seen_uris:
            continue
        defn = onto_handlers["get_class_definition"](filler)
        if defn is None:
            continue
        seen_uris.add(filler)
        restriction_candidates.append({
            "uri": filler,
            "label": defn.get("label", ""),
            "hit_count": 0,
            "best_distance": 0.0,
            "query_sources": ["restriction"],
            "restriction_property": r.get("property", ""),
            "restriction_from": c["uri"],
        })
```

**Equivalence expansion:** For each candidate, if it has equivalence axioms with named class members, add those members:

```python
for c in candidates:
    for eq in onto_handlers["get_equivalent_axioms"](c["uri"]):
        for member in eq.get("members", []):
            if member in seen_uris:
                continue
            defn = onto_handlers["get_class_definition"](member)
            if defn is None:
                continue
            seen_uris.add(member)
            restriction_candidates.append({
                "uri": member,
                "label": defn.get("label", ""),
                "hit_count": 0,
                "best_distance": 0.0,
                "query_sources": ["equivalence"],
            })
```

**Cap and merge:** Maximum 3 additional candidates from restriction/equivalence expansion combined. Prevents the candidate list from ballooning (D3FEND classes can have 6+ restrictions each). After collection:

```python
# Cap at 3 additional candidates
restriction_candidates = restriction_candidates[:3]
# Merge into main candidate list before enrichment
candidates = candidates + restriction_candidates
```

The merged list then flows into the existing enrichment loop (`get_class_definition`, `get_siblings`) and LLM prompt building. The enrichment loop already handles arbitrary candidate dicts — restriction-sourced candidates have the same shape (`uri`, `label`, `hit_count`, `best_distance`, `query_sources`) plus optional metadata fields (`restriction_property`, `restriction_from`) that are used only for prompt annotation.

**LLM prompt annotation:** Restriction-sourced candidates get a different annotation than search-sourced ones:

```
- InformationContentEntity — A generically dependent... [from restriction: is_about on InformationBearingArtifact]
```

**Domain filtering:** Restriction/equivalence candidates go through the same domain filter as search candidates (`derive_source_ontology(uri) in selected_domains`).

**Pipeline events:**

| Event | Fields |
|-------|--------|
| `restriction_expansion` | `risk_id`, `source_uri`, `candidates_added`, `source_type` ("restriction" or "equivalence") |

### Component 6: Evaluation Metrics (`refiner/src/refiner/evaluate.py`)

**`aggregate_stage_quality` updates:** Three new event type handlers:

```python
elif etype == "disjoint_filtered":
    df = s.setdefault("disjoint_filtered", [])
    df.append({
        "risk_id": event["risk_id"],
        "axis_uri": event["axis_uri"],
        "kept": event["kept"],
        "filtered": event["filtered"],
    })
elif etype == "restriction_expansion":
    re = s.setdefault("restriction_expansions", [])
    re.append({
        "risk_id": event["risk_id"],
        "source_uri": event["source_uri"],
        "candidates_added": event["candidates_added"],
        "source_type": event["source_type"],
    })
elif etype == "restriction_context_added":
    s["restriction_contexts_added"] = s.get("restriction_contexts_added", 0) + 1
```

**Two new metric functions,** both derived from pipeline events:

**`compute_disjoint_filter_rate`** — From `disjoint_filtered` events: count of risks where at least one enumeration was removed due to disjointness. Fraction over total risks with enumerations. Answers: "are the ontology axioms catching things the LLM missed?"

**`compute_restriction_discovery_rate`** — From `restriction_expansion` events and selected axes: fraction of axes that originated from restriction/equivalence sources rather than search. Answers: "are formal axioms finding axes that search alone wouldn't?"

Both slot into the `stage_quality` section of evaluation output. Wired into `run_evaluation()` alongside the existing `compute_candidate_expansion_effectiveness`.

### Component 7: CLI Integration (`ontoquery/src/ontoquery/cli.py`)

The `index` command gets axiom extraction added after graph loading:

```python
# After: backend = create_index_backend(files, chroma_dir)
from ontoquery.axioms import extract_axioms, save_axioms
axioms = extract_axioms(backend)
save_axioms(axioms, chroma_dir / "axioms.json")
backend._axioms = axioms  # Attach to backend for immediate use
print(f"Axiom index: {sum(len(v) for v in axioms['restrictions'].values())} restrictions, "
      f"{sum(len(v) for v in axioms['disjointness'].values()) // 2} disjoint pairs, "
      f"{sum(len(v) for v in axioms['equivalences'].values())} equivalences")
```

No new CLI commands. Axiom extraction is part of `ontoquery index`.

## Files Changed

| File | Change |
|------|--------|
| `ontoquery/src/ontoquery/axioms.py` | **New.** Extraction, persistence, RDF list traversal |
| `ontoquery/src/ontoquery/backend.py` | 3 new protocol methods, axiom loading in both backends |
| `ontoquery/src/ontoquery/cli.py` | Axiom extraction in `index` command |
| `ontoquery/src/ontoquery/mcp_server.py` | 3 new tools |
| `refiner/src/refiner/stages/anchor.py` | Restriction/equivalence candidate expansion |
| `refiner/src/refiner/stages/contextualize.py` | Disjointness post-filter, restriction context in prompt |
| `refiner/src/refiner/evaluate.py` | 2 new metrics, wired into `run_evaluation()` |
| `ontoquery/tests/test_axioms.py` | **New.** Extraction, persistence, blank node traversal tests |
| `ontoquery/tests/test_backend.py` | New protocol method tests, graceful degradation |
| `ontoquery/tests/test_mcp_server.py` | New tool tests |
| `refiner/tests/test_anchor.py` | Restriction/equivalence expansion tests |
| `refiner/tests/test_contextualize.py` | Disjointness filtering tests |
| `refiner/tests/test_evaluate.py` | New metric tests |

## Backward Compatibility

- `axioms.json` absent → all 3 new methods return empty lists. Pipeline behaves identically to current. Warning logged once.
- Backend constructors: `axioms` parameter defaults to `None`. All existing `OxigraphBackend(store)` and `RdflibBackend(graph)` calls continue to work unchanged.
- No changes to existing stage signatures. `onto_handlers` gets new optional keys.
- No new LLM calls. Restriction context is additive to existing prompts.
- `ontoquery index` must be re-run to generate `axioms.json`. Old indexes work without it.
- Existing tests unaffected — new handler keys are only accessed via `.get()` guards.

## What This Does NOT Do

- **No full OWL reasoner.** Extraction is syntactic, not semantic. We parse asserted axioms, not entailed ones. Future: hybrid with reasoner precomputation at index time.
- **No cross-ontology inference.** CCO restrictions and FIBO restrictions are not composed.
- **No SHACL or shape validation.** We use OWL axioms directly.
- **No cardinality reasoning.** We skip `owl:minCardinality`/`owl:maxCardinality`.
- **No property chain expansion.** CCO has only 2 chain axioms — not enough volume to justify.
- **No transitive closure.** D3FEND has 5 transitive properties but computing transitive closure would require a reasoning step.
