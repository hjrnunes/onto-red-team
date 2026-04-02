# CCO→Commons Bridge Ontology Design

## Goal

Create a bridge ontology (~14 `rdfs:subClassOf` axioms) mapping CCO classes to OMG Commons classes, enabling semantic role derivation for FIBO/Commons classes in the refiner pipeline and laying the groundwork for future cross-ontology candidate discovery.

## Problem

CCO (BFO-based, ~5,000 classes) and OMG Commons (~200 classes, upper-ontology-agnostic) share many conceptual overlaps (Agent, Organization, Role, Document, Location) but have no formal axioms connecting them. FIBO imports ~16 Commons modules, so FIBO classes trace up to Commons — but never reach CCO or BFO. This causes two problems in the pipeline:

1. **No role derivation for FIBO classes:** `derive_roles()` in `anchor.py` walks the superclass chain looking for BFO/CCO URIs in `_CATEGORY_ROLES`. FIBO classes trace up to Commons classes (e.g., `cmns-org:FormalOrganization`) which are not in the map. The walk terminates without assigning a semantic role, falling back to the LLM-assigned role.

2. **No structural link between ontology families:** CCO and Commons classes exist in the same graph but have no `rdfs:subClassOf` paths connecting them. This prevents any future cross-ontology traversal (e.g., discovering FIBO subclasses of Commons classes from a CCO starting point). The bridge axioms establish these paths, even though the current `expand_candidates()` code does not yet exploit superclass→subclass discovery.

## Approach

- **Conservative `rdfs:subClassOf` only** — CCO classes declared as subclasses of Commons classes. No `owl:equivalentClass`. Safe: superclass walking from CCO reaches Commons (and from there, FIBO classes are already connected via their own imports). No risk of unintended entailments.
- **Standalone TTL file** — `ontologies/bridges/cco-commons.ttl` included in the `ontoquery index` command. Axioms become part of the graph and are automatically available to restriction/equivalence expansion and superclass walking. No code changes for loading.
- **`_CATEGORY_ROLES` extension** — Commons class URIs added to the role derivation map in `anchor.py` so that FIBO classes walking up to Commons classes get semantic roles assigned.

## Bridge Axioms (14)

All axioms are `rdfs:subClassOf` (CCO class is a subclass of Commons class).

### Entity Bridges (7)

| CCO Class | CCO URI | Commons Class | Commons URI |
|-----------|---------|---------------|-------------|
| Agent | `cco:ont00001017` | Agent | `cmns-pts:Agent` |
| Person | `cco:ont00001262` | Party | `cmns-pts:Party` |
| Person | `cco:ont00001262` | LegalPerson | `cmns-org:LegalPerson` |
| Organization | `cco:ont00001180` | FormalOrganization | `cmns-org:FormalOrganization` |
| Document Content Entity | `cco:ont00002039` | Document | `cmns-doc:Document` |
| Legal Instrument | `cco:ont00001346` | LegalDocument | `cmns-doc:LegalDocument` |
| Geospatial Region | `cco:ont00000472` | Location | `cmns-loc:Location` |

**Rationale:**
- **Agent→Agent:** Both represent entities capable of performing actions. CCO Agent is a BFO Material Entity bearing an Agent Capability; Commons Agent is a top-level actor concept. Subsumption is safe — every CCO Agent is a Commons Agent.
- **Person→Party+LegalPerson:** Commons `Party` covers persons and organizations; `LegalPerson` covers entities with legal rights. Natural persons satisfy both. Two axioms on Person because Commons uses these as independent classification dimensions (FIBO specializes both).
- **Organization→FormalOrganization:** CCO Organization requires rules and member roles — matches Commons FormalOrganization (recognized in legal jurisdiction). Not mapped to plain `Organization` because CCO's definition is already formal.
- **Document Content Entity→Document:** CCO's `ont00002039` (altLabel "Document") is the content-level document class. Maps cleanly to Commons Document (unitary expression of intellectual work). Note: CCO's `Information Bearing Artifact` (the physical carrier) is deliberately NOT bridged — Commons Document is about content, not carrier.
- **Legal Instrument→LegalDocument:** Direct conceptual match — both represent formally executed documents evidencing legally enforceable rights/obligations.
- **Geospatial Region→Location:** CCO Geospatial Region is a geographic area. Maps to Commons Location (place/position in space).

**Not bridged — Facility:** CCO Facility (`ont00000192`) is a Material Artifact (BFO Material Entity), not a spatial entity. Asserting `Facility rdfs:subClassOf Location` would violate BFO's fundamental distinction between material and immaterial entities. Instead, Facility is added directly to `_CATEGORY_ROLES` with `["location"]` to achieve the desired role derivation without a false ontological claim.

### Identifier Bridge (1)

| CCO Class | CCO URI | Commons Class | Commons URI |
|-----------|---------|---------------|-------------|
| Designative ICE | `cco:ont00000686` | Identifier | `cmns-id:Identifier` |

**Rationale:** CCO's Designative Information Content Entity is defined as an ICE that "uniquely distinguishes an entity within a specified context" — functionally identical to Commons Identifier. FIBO uses `cmns-id:Identifier` extensively for financial instrument identifiers (LEI, ISIN, CUSIP).

### Role Bridges (6)

| CCO Role | CCO URI | Commons Role | Commons URI |
|----------|---------|-------------|-------------|
| Authority Role | `cco:ont00000187` | StructuralRole | `cmns-rlcmp:StructuralRole` |
| Occupation Role | `cco:ont00000984` | FunctionalRole | `cmns-rlcmp:FunctionalRole` |
| Organization Member Role | `cco:ont00000175` | PartyRole | `cmns-pts:PartyRole` |
| Commercial Role | `cco:ont00000485` | StructuralRole | `cmns-rlcmp:StructuralRole` |
| Citizen Role | `cco:ont00000987` | PartyRole | `cmns-pts:PartyRole` |
| Contractor Role | `cco:ont00000506` | FunctionalRole | `cmns-rlcmp:FunctionalRole` |

**Rationale:**
- Commons organizes roles into three categories: `StructuralRole` (hierarchical/competence), `FunctionalRole` (capability-based), `PartyRole` (participation in situations). CCO roles map naturally:
  - Authority Role → StructuralRole: authority is about hierarchical position
  - Commercial Role → StructuralRole: for-profit status is about the organization's identity/position, not a capability
  - Occupation/Contractor → FunctionalRole: both are about what the agent does/provides
  - Organization Member/Citizen → PartyRole: participation in an organization or polity

## Pipeline Change: `_CATEGORY_ROLES` Extension

`derive_roles()` in `anchor.py` walks superclass chains looking for known URIs. Currently only BFO/CCO URIs are in the map. Adding Commons URIs enables role derivation for FIBO classes.

New entries in `_CATEGORY_ROLES`:

```python
# Commons categories (reached via FIBO superclass chains)
"https://www.omg.org/spec/Commons/PartiesAndSituations/Agent": ["agent"],
"https://www.omg.org/spec/Commons/PartiesAndSituations/Party": ["agent"],
"https://www.omg.org/spec/Commons/PartiesAndSituations/PartyRole": ["agent"],
"https://www.omg.org/spec/Commons/RolesAndCompositions/Role": ["agent"],
"https://www.omg.org/spec/Commons/RolesAndCompositions/FunctionalRole": ["agent", "instrument"],
"https://www.omg.org/spec/Commons/RolesAndCompositions/StructuralRole": ["agent"],
"https://www.omg.org/spec/Commons/Organizations/Organization": ["agent"],
"https://www.omg.org/spec/Commons/Organizations/FormalOrganization": ["agent"],
"https://www.omg.org/spec/Commons/Organizations/LegalEntity": ["agent"],
"https://www.omg.org/spec/Commons/Organizations/LegalPerson": ["agent"],
"https://www.omg.org/spec/Commons/Documents/Document": ["object"],
"https://www.omg.org/spec/Commons/Documents/LegalDocument": ["object"],
"https://www.omg.org/spec/Commons/Identifiers/Identifier": ["object", "instrument"],
"https://www.omg.org/spec/Commons/Locations/Location": ["location"],
# CCO Facility — not bridged (Material Artifact, not spatial), but needs location role
"https://www.commoncoreontologies.org/ont00000192": ["location"],
```

**Ordering note:** `derive_roles()` walks the superclass chain and returns on the *first* URI match in `_CATEGORY_ROLES`. What matters is which URI is encountered first in the ontology hierarchy, not dict insertion order. CCO classes naturally walk through CCO superclasses first (from the original ontology), so CCO entries match before Commons entries when both are in the chain. The single-path walk (follows first named superclass from `get_superclasses()`) means graph store iteration order can affect which branch is taken when multiple superclasses exist — but the role mappings are harmonized so this rarely produces different results.

## Example Traversal Paths

**Role derivation for FIBO class (primary benefit):**
```
derive_roles("fibo-be-le-lei:LegalEntity")
  walk: LegalEntity → cmns-org:LegalEntity
  _CATEGORY_ROLES["cmns-org:LegalEntity"] = ["agent"]
  → returns ["agent"]
```

**Without bridge (current behavior):**
```
derive_roles("fibo-be-le-lei:LegalEntity")
  walk: LegalEntity → cmns-org:LegalEntity → cmns-org:FormalOrganization
        → cmns-org:Organization → cmns-pts:Party → cmns-pts:Agent → (no BFO/CCO hit)
  → returns None (falls back to LLM-assigned role)
```

**Structural foundation for future cross-ontology discovery:**

The bridge axioms add `rdfs:subClassOf` triples to the graph (e.g., `cco:Organization rdfs:subClassOf cmns-org:FormalOrganization`). This makes the cross-ontology path visible to `get_superclasses()`. The current `expand_candidates()` code does not exploit this — it follows OWL restrictions and equivalences, not superclass→subclass relationships. However, the bridge lays the groundwork for a future enhancement where expansion could discover FIBO subclasses of Commons classes reached via bridge axioms.

## File Layout

```
ontologies/
  bridges/
    cco-commons.ttl    # 14 rdfs:subClassOf axioms, ~60 lines
```

## Integration Points

1. **`just index-ontologies`** — add `../ontologies/bridges/` to the index command
2. **`anchor.py`** — extend `_CATEGORY_ROLES` dict with ~15 entries (14 Commons URIs + 1 CCO Facility)
3. **No changes to:** `backend.py`, `axioms.py`, `contextualize.py`, `identify_domains.py`, `derive_source_ontology()`, `mcp_server.py`

## Testing

- **Bridge axiom verification:** Index with bridge file, verify `get_superclasses(cco:ont00001017)` includes `cmns-pts:Agent`
- **Role derivation for Commons URIs:** Test `derive_roles()` with Commons class URIs directly, verify correct roles returned from `_CATEGORY_ROLES`
- **Role derivation via walk:** Mock `get_superclasses` to return a Commons URI, verify `derive_roles()` reaches the Commons entry in `_CATEGORY_ROLES`
- **Facility role:** Test `derive_roles(cco:ont00000192)` returns `["location"]` via direct `_CATEGORY_ROLES` entry (no bridge axiom)
- **No regression:** Existing tests pass unchanged

## Intentional Non-Goals

- **Property bridges** (`rdfs:subPropertyOf`): CCO and Commons properties (e.g., `cco:has_agent` vs `cmns-pts:isPlayedBy`) are not bridged. The pipeline doesn't use property relationships for traversal. Can be added later.
- **`owl:equivalentClass`**: Even for near-exact matches (Legal Instrument ≡ LegalDocument), equivalence is avoided. `rdfs:subClassOf` gives us everything we need without risking unintended entailments.
- **Information Bearing Artifact bridge**: Not mapped to `cmns-doc:Document` — IBA is a physical carrier, Document is about content. The content-level class (Document Content Entity) is bridged instead.
- **Time bridges**: CCO TimeOntology and Commons DatesAndTimes have overlapping concepts but different structures. Not bridged — temporal classes rarely appear as variation axes.
- **Currency bridges**: No Commons equivalent exists.

## Known Limitations

- **`derive_roles()` single-path walk:** The function follows only the first named superclass from `get_superclasses()` at each step. When a class has multiple superclasses (e.g., `cmns-org:LegalEntity` has both `FormalOrganization` and `LegalPerson`), only one path is followed. The choice depends on graph store iteration order, which is non-deterministic. In practice, the `_CATEGORY_ROLES` entries are harmonized (both paths resolve to `["agent"]` for organizational classes), so this rarely produces different results.
- **No cross-ontology candidate discovery:** The bridge axioms make CCO→Commons superclass paths visible in the graph, but `expand_candidates()` in the anchor stage does not use superclass→subclass traversal for candidate discovery. It follows OWL restrictions and equivalence axioms only. Cross-ontology candidate discovery (e.g., finding FIBO `Bank` as a subclass of `cmns-org:FormalOrganization` when starting from `cco:Organization`) would require extending `expand_candidates()` — a future enhancement.
