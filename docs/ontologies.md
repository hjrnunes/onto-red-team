# Ontologies

## Foundation

**BFO** (Basic Formal Ontology) is the ISO-standard top-level ontology (~35 classes). **CCO** (Common Core Ontologies)
is the mid-level (~5,000 classes). Domain ontologies extend from BFO or BFO+CCO. All BFO-based ontologies share the
same fundamental distinctions (Continuant vs Occurrent, Material Entity, Role, Process, etc.) which makes multi-ontology
composition possible.

Other mid-level ontologies (not BFO-based): DOLCE+DUL, SUMO (IEEE), UFO (OntoUML). We use BFO+CCO because of its
domain ontology ecosystem.

## Domain Ontologies by Industry

| Industry                      | Domain Ontologies                                     | BFO?                   | Bridge Strategy                                            | Notes                                                          |
|-------------------------------|-------------------------------------------------------|------------------------|------------------------------------------------------------|----------------------------------------------------------------|
| Banking/Finance               | **FIBO** (~1,500 class subset) + OMG Commons          | No (Commons-based)     | CCO->Commons bridge (14 axioms, `bridges/cco-commons.ttl`) | ACTUS contract types included. KYC/AML extension needed.       |
| Healthcare                    | **OGMS** + MONDO + HPO + UBERON + MAXO + OAE          | All yes (OBO Foundry)  | None needed                                                | ~82k classes (DRON excluded). SNOMED CT + RxNorm via API only. |
| Telecom                       | **NORIA-O** + UCO Observable + TMF Open API extracts  | No                     | Direct CCO bridge (~10 axioms)                             | Multi-source. No single telecom ontology exists.               |
| Insurance                     | **FIBO FND/FBC** + custom extension (~50-100 classes) | No                     | Via FIBO's Commons bridge                                  | No mature insurance ontology exists anywhere.                  |
| Government                    | **DPV EU AI Act** + CPSV-AP + Core Person + W3C ORG   | No                     | Direct CCO bridge (~10 axioms)                             | DPV has ~170 AI Act concepts. NIEM for US scope.               |
| Manufacturing                 | IOF                                                   | Yes (explicit BFO+CCO) | Already in `ontologies/ontology/`                          | Not a priority vertical currently.                             |
| Content Safety (cross-domain) | **CSO** (~195 classes)                                | No (standalone)        | N/A                                                        | Always-included. 9 harm categories.                            |
| Cybersecurity (cross-domain)  | **D3FEND** (4,366 classes)                            | OWL 2 DL, CCO mapping  | Has `d3fend-cco.ttl` mapping                               | ATT&CK + CWE + ATLAS (AI) + SPARTA. Always-included.           |

OMG Commons (22 modules, MIT) is the interoperability hub: IOF maps to it, FIBO imports ~16 modules from it.

## Files in `ontologies/`

| Directory                 | Source              | Classes         | Format | Notes                                               |
|---------------------------|---------------------|-----------------|--------|-----------------------------------------------------|
| `CommonCoreOntologies/`   | CCO (ISO standard)  | ~5,000          | `.ttl` | Key modules in `src/cco-modules/`                   |
| `commons/`                | OMG Commons         | 22 modules      | `.rdf` | Bridge hub for FIBO interop                         |
| `fibo/`                   | FIBO Q4 2025        | ~1,500 (subset) | `.rdf` | 297 files across 10 domains                         |
| `obo/`                    | OBO Foundry         | ~82k            | `.owl` | ogms, mondo-base, hp-base, uberon-base, maxo, oae   |
| `d3fend-ontology/`        | MITRE D3FEND v1.3.0 | 4,366           | `.ttl` | Main: `src/ontology/d3fend-protege.ttl`             |
| `cso/`                    | Custom (CSO)        | 195             | `.ttl` | 9 harm categories, namespace `cso:`                 |
| `ontology/`               | IOF                 | varies          | `.rdf` | Manufacturing/supply chain                          |
| `bridges/cco-commons.ttl` | Custom              | 14 axioms       | `.ttl` | CCO->Commons bridge for FIBO interop                |
| `dron-base.owl`           | Drug Ontology       | ~770k           | `.owl` | Excluded from indexing (too large, few definitions) |

## CCO->Commons Bridge

Located at `ontologies/bridges/cco-commons.ttl`. 14 `rdfs:subClassOf` axioms (conservative, no `owl:equivalentClass`):

- **Entity bridges (7):** Agent, Person, Organization, Document, Legal Instrument, Geospatial Region, Designative ICE
- **Role bridges (6):** Authority Role, Occupation Role, Org Member Role, Commercial Role, Citizen Role, Contractor Role
- **Not bridged:** Facility (Material Artifact != Location in BFO) — handled via direct `_CATEGORY_ROLES` entry

Purpose: enables FIBO classes to get semantic roles via superclass walk through Commons URIs.

## Definition Extraction

Ontology classes are indexed with definitions extracted via fallback chain:
`skos:definition` > `iof-av:naturalLanguageDefinition` > `obo:IAO_0000115` > `d3f:definition` > `rdfs:comment`

## OWL Axiom Extraction

At index time, `axioms.py` extracts:

- **Restrictions**: `owl:Restriction` (someValuesFrom, allValuesFrom, hasValue) from `rdfs:subClassOf` and
  `owl:equivalentClass` intersections
- **Disjointness**: `owl:disjointWith` + `owl:AllDisjointClasses` with RDF list traversal
- **Equivalences**: `owl:equivalentClass` (simple and intersection)

Persisted as `axioms.json` sidecar. Loaded into backends at runtime. Filtered to indexed classes only.

## Finding CCO-aligned Ontologies

- CCO home page project list: https://commoncoreontologies.github.io/cco-webpage/
- Industrial Ontology Portal: https://industryportal.enit.fr/ontologies/CCO
- OBO Foundry (BFO-aligned, bio/medical): https://obofoundry.org
