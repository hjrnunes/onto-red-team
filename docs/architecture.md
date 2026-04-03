# Architecture

## Purpose

Transform client content policies (JSON) into standards-aligned risk taxonomies with structured domain context, for
red-team prompt generation against LLM deployments.

## Project Context

Built on the **AI Atlas Nexus** ontology and knowledge graph
(`/Users/hjrnunes/workspace/redhat/ibm/ai-atlas-nexus`), which integrates 10 AI risk frameworks with 600+ unique risk
entries and cross-taxonomy mappings (IBM Risk Atlas, NIST AI RMF, OWASP Top 10 for LLMs, AIR 2024, MIT AI Risk
Repository, AILuminate, Credo, AIUC-1, CSIRO).

## End-to-End Data Flow

```
Client policies (JSON/Markdown)
        |
        v
[refiner ingest] ── LLM enrichment ──> PolicyDocument (enriched JSON)
        |
        v
[refiner run] ── 6-stage LLM pipeline ──> taxonomy.yaml + domain-context.yaml
        |       (uses ontoquery + nexus-mcp handlers)
        v
[refiner emit] ── pure Python sampling ──> dataset.jsonl
        |
        v
[redteam] ── sdg_hub LLM flow ──> adversarial_prompts.jsonl
        |
        v
[refiner evaluate] ── metrics + optional judge ──> evaluation.json
```

## Key Concepts

### Three-Layer Ontology Stack

1. **CCO** (mid-level) — semantic constraints and class definitions. e.g. `cco:AuthorityRole`,
   `cco:FinancialInstrument`, `cco:ProcessProhibition`
2. **Domain Ontology** (industry-level) — enumerations. FIBO for banking, OBO/SNOMED for healthcare, IOF for
   manufacturing
3. **Client Instances** — specific named entities from the policy JSON (anchors)

### CCO Classes as Variation Axes

Client entities are instances of CCO classes. The class defines the variation space for prompt generation — not just
"Jenny Carlson (CEO)" but any `cco:Person` bearing `cco:AuthorityRole`. Each risk has multiple variation axes, each
grounded in a CCO class.

### Cross-Mapping Amplifies Prompt Generation

A single client risk maps to multiple risks across the 600+ in the knowledge graph. Each cross-mapped risk provides an
alternative framing, producing more diverse adversarial prompts from a single policy concept.

## Directory Structure

```
ontoquery/                 # Ontology MCP server + CLI (rdflib, pyoxigraph, chromadb)
nexus-mcp/                 # AI Atlas Nexus MCP server (chromadb, ai-atlas-nexus)
refiner/                   # LLM pipeline: policy -> taxonomy + domain context (instructor, openai)
redteam/                   # Adversarial prompt generation via sdg_hub
ontologies/                # Ontology files (CCO, Commons, FIBO, OBO, D3FEND, CSO, bridges)
policy_examples/           # Sample policy files (swb, generic, aramco)
runs/                      # Pipeline run outputs (gitignored)
docs/                      # Project documentation
  superpowers/             # Implementation specs and plans (historical)
```

## Related Projects

- **AI Atlas Nexus**: `/Users/hjrnunes/workspace/redhat/ibm/ai-atlas-nexus`
    - Schema: `src/ai_atlas_nexus/ai_risk_ontology/schema/` (LinkML YAML)
    - Knowledge graph data: `src/ai_atlas_nexus/data/knowledge_graph/` (auto-discovered YAML)
    - Mappings: `src/ai_atlas_nexus/data/mappings/` (SSSOM TSV)
    - Python API: `AIAtlasNexus(base_dir=...)` for loading and querying

## Design Notes (Obsidian)

Detailed design thinking lives in Obsidian vault notes:

- **AI Atlas Nexus - Client Policy Taxonomies** — Policy classification methodology (A/B/C/D types), enrichment,
  cross-mapping, gap analysis
- **AI Atlas Nexus - Ontology Overview** — Schema modules, core entities, the 10 integrated risk frameworks
- **AI Atlas Nexus - Domain Context Generation** — Three-layer ontology stack, variation axes, LLM querying strategy
- **AI Atlas Nexus - Domain Ontology Selection** — Ontology selection for 5 priority verticals, bridge strategies
- **AI Atlas Nexus - Industrial Ontology Portal Survey** — Survey of ~136 ontologies, tiered by CCO alignment
