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
| Telecom                       | **NORIA-O** + UCO Observable + TMF Open API extracts  | No                     | Direct CCO bridge (~10 axioms)                             | Multi-source. No single telecom ontology exists. Not loaded.   |
| Insurance                     | **FIBO FND/FBC** + **OMRSE** + custom extension       | OMRSE yes (OBO)        | Via FIBO's Commons bridge                                  | OMRSE has InsurancePolicy, InsuredPartyRole, PayerRole, etc.   |
| Government                    | **DPV EU AI Act** + CPSV-AP + Core Person + W3C ORG   | No                     | Direct CCO bridge (~10 axioms)                             | DPV has ~170 AI Act concepts. NIEM for US scope. Not loaded.   |
| Manufacturing                 | IOF                                                   | Yes (explicit BFO+CCO) | Already in `ontologies/ontology/`                          | Not a priority vertical currently.                             |
| Content Safety (cross-domain) | **CSO** (~195 classes)                                | No (standalone)        | N/A                                                        | Always-included. 9 harm categories.                            |
| Cybersecurity (cross-domain)  | **D3FEND** (4,366 classes)                            | OWL 2 DL, CCO mapping  | Has `d3fend-cco.ttl` mapping                               | ATT&CK + CWE + ATLAS (AI) + SPARTA. Always-included.          |
| Demographics (cross-domain)   | **GSSO** (~13k) + **HANCESTRO** (~1.3k)              | Yes (OBO Foundry)      | None needed                                                | Protected characteristics for bias testing. Always-included.   |
| Social Entities (cross-domain)| **OMRSE** (~600 classes)                              | Yes (OBO Foundry)      | None needed                                                | Insurance/healthcare/legal roles and contracts.                |
| Data Use (cross-domain)       | **DUO** (~45 classes)                                 | Yes (OBO Foundry)      | None needed                                                | Data use conditions for privacy/governance.                    |
| Legal/Regulatory (cross-domain)| **LKIF Core** (~208 classes)                         | No (own upper level)   | CCO bridge (11 axioms, `bridges/cco-lkif.ttl`)             | Norms, obligations, prohibitions, rights. Always-included.     |

OMG Commons (22 modules, MIT) is the interoperability hub: IOF maps to it, FIBO imports ~16 modules from it.

## Files in `ontologies/`

| Directory                 | Source              | Classes         | Format | Notes                                               |
|---------------------------|---------------------|-----------------|--------|-----------------------------------------------------|
| `CommonCoreOntologies/`   | CCO (ISO standard)  | ~5,000          | `.ttl` | Key modules in `src/cco-modules/`                   |
| `commons/`                | OMG Commons         | 22 modules      | `.rdf` | Bridge hub for FIBO interop                         |
| `fibo/`                   | FIBO Q4 2025        | ~1,500 (subset) | `.rdf` | 297 files across 10 domains                         |
| `obo/`                    | OBO Foundry         | ~95k            | `.owl` | ogms, mondo-base, hp-base, uberon-base, maxo, oae, gsso, hancestro, omrse, duo |
| `lkif-core/`              | LKIF Core (ESTRELLA)| ~208            | `.owl` | 15 modules: norm, expression, action, legal-action, role, etc.             |
| `d3fend-ontology/`        | MITRE D3FEND v1.3.0 | 4,366           | `.ttl` | Main: `src/ontology/d3fend-protege.ttl`             |
| `cso/`                    | Custom (CSO)        | 195             | `.ttl` | 9 harm categories, namespace `cso:`                 |
| `ontology/`               | IOF                 | varies          | `.rdf` | Manufacturing/supply chain                          |
| `bridges/cco-commons.ttl` | Custom              | 14 axioms       | `.ttl` | CCO->Commons bridge for FIBO interop                |
| `bridges/cco-lkif.ttl`    | Custom              | 11 axioms       | `.ttl` | CCO->LKIF bridge for legal/regulatory interop       |
| `bridges/lkif-labels.ttl` | Generated           | 205 labels      | `.ttl` | rdfs:label for LKIF classes (generated by fetch script) |
| `dron-base.owl`           | Drug Ontology       | ~770k           | `.owl` | Excluded from indexing (too large, few definitions) |

## CCO->Commons Bridge

Located at `ontologies/bridges/cco-commons.ttl`. 14 `rdfs:subClassOf` axioms (conservative, no `owl:equivalentClass`):

- **Entity bridges (7):** Agent, Person, Organization, Document, Legal Instrument, Geospatial Region, Designative ICE
- **Role bridges (6):** Authority Role, Occupation Role, Org Member Role, Commercial Role, Citizen Role, Contractor Role
- **Not bridged:** Facility (Material Artifact != Location in BFO) — handled via direct `_CATEGORY_ROLES` entry

Purpose: enables FIBO classes to get semantic roles via superclass walk through Commons URIs.

## CCO->LKIF Bridge

Located at `ontologies/bridges/cco-lkif.ttl`. 11 `rdfs:subClassOf` axioms (conservative):

- **Entity bridges (4):** Agent, Person, Organisation, Action
- **Normative bridges (5):** Norm→Process Regulation, Prohibition→Process Prohibition, Obligation→Process Requirement,
  Legal Source→Prescriptive ICE, Legal Document→Document Content Entity
- **Expression bridges (2):** Expression→ICE, Proposition→ICE

LKIF classes are made subclasses of CCO classes (LKIF→CCO direction) to integrate into the BFO hierarchy.

**LKIF Label Generation:** LKIF Core uses URI fragments as class names (e.g., `norm.owl#Prohibition`) without
`rdfs:label` annotations. The fetch script generates `bridges/lkif-labels.ttl` with 205 derived labels so the
indexer can pick them up.

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
