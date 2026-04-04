# Taxonomy Refiner — utility recipes
# Battery runs: uv run scripts/run_battery.py <run-name> [options]

# Download external ontologies (git clones + OBO/Commons files)
fetch-ontologies:
    bash scripts/fetch_ontologies.sh

# Index all ontologies into ontoquery ChromaDB (CCO + Commons + FIBO + OBO + D3FEND + CSO + bridges)
index-ontologies:
    cd ontoquery && uv run ontoquery index \
        ../ontologies/CommonCoreOntologies/src/cco-modules/ \
        ../ontologies/commons/ \
        ../ontologies/fibo/ \
        ../ontologies/obo/ \
        ../ontologies/d3fend-ontology/src/ontology/d3fend-protege.ttl \
        ../ontologies/cso/ \
        ../ontologies/lkif-core/ \
        ../ontologies/bridges/

# Ingest an arbitrary document (standalone utility)
ingest-doc input model_name model_url output="":
    cd refiner && uv run refiner ingest {{ input }} \
        {{ if output != "" { "--output " + output } else { "" } }} \
        --base-url {{ model_url }} \
        --model {{ model_name }} \
        --api-key {{ env("REFINER_API_KEY", "none") }}

# Run pipeline battery (delegates to Python)
battery *args:
    uv run scripts/run_battery.py {{args}}

# Build combined HTML report for a run directory
combined-report run_dir *args:
    uv run scripts/build_combined_report.py {{run_dir}} {{args}}
