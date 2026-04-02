# Taxonomy Refiner — end-to-end pipeline commands
# Usage: just <recipe> <policy> <run>
# Example: just all swb my-test-run → runs/swb-my-test-run/

models_file := "models.json"
policies := "swb generic aramco healthcare rdash-nhs"

tracking_uri := "https://mlflow.taxonomy-refiner.orb.local"
policy_dir := "/Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/policy_examples"

api_key := env("REFINER_API_KEY", "none")

export MLFLOW_TRACKING_INSECURE_TLS := "true"
nexus_dir := "/Users/hjrnunes/workspace/redhat/ibm/ai-atlas-nexus"
onto_chroma := "/Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/ontoquery/.chroma"
nexus_chroma := "/Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/nexus-mcp/.chroma"
runs_dir := "/Users/hjrnunes/workspace/redhat/hjrnunes/taxonomy-refiner/runs"
samples_per_risk := "15"
run_tags := env("REFINER_RUN_TAGS", "")

# Run all policy examples for every model in models.json (parallel by model)
run-all run:
    #!/usr/bin/env bash
    set -euo pipefail
    pids=()
    model_names=()
    for model_name in $(jq -r 'keys[]' {{ models_file }}); do
        model_url=$(jq -r --arg m "$model_name" '.[$m]' {{ models_file }})
        run_name="${model_name}-{{ run }}"
        log="{{ runs_dir }}/${run_name}.log"
        echo "=== Starting $model_name (log: $log) ==="
        (
            for policy in {{ policies }}; do
                echo "--- $policy / $model_name ---"
                just all-with-model "$policy" "$run_name" "$model_name" "$model_url"
            done
        ) > "$log" 2>&1 &
        pids+=($!)
        model_names+=("$model_name")
    done
    echo "Waiting for ${#pids[@]} model(s)..."
    failed=0
    for i in "${!pids[@]}"; do
        if wait "${pids[$i]}"; then
            echo "=== ${model_names[$i]} done ==="
        else
            echo "=== ${model_names[$i]} FAILED (see {{ runs_dir }}/${model_names[$i]}-{{ run }}.log) ==="
            failed=1
        fi
    done
    if [ "$failed" -eq 1 ]; then exit 1; fi
    echo "All model runs complete."

# Run all policy examples for every model (flat JSON input, no ingest, sequential)
run-all-flat run:
    #!/usr/bin/env bash
    set -euo pipefail
    for model_name in $(jq -r 'keys[]' {{ models_file }}); do
        model_url=$(jq -r --arg m "$model_name" '.[$m]' {{ models_file }})
        run_name="${model_name}-{{ run }}"
        echo "=== $model_name ==="
        for policy in {{ policies }}; do
            echo "--- $policy / $model_name ---"
            just all-flat-with-model "$policy" "$run_name" "$model_name" "$model_url"
        done
    done
    echo "All model runs complete."

# Lookup model URL from models.json
[private]
model-url model_name:
    @jq -re --arg m "{{ model_name }}" '.[$m] // error("model not found: \($m)")' {{ models_file }}

# Run full pipeline: ingest → refine → emit → generate → evaluate (looks up model URL)
all policy run model_name:
    #!/usr/bin/env bash
    set -euo pipefail
    model_url=$(just model-url "{{ model_name }}")
    just all-with-model "{{ policy }}" "{{ run }}" "{{ model_name }}" "$model_url"

# Run pipeline without ingest (looks up model URL)
all-flat policy run model_name:
    #!/usr/bin/env bash
    set -euo pipefail
    model_url=$(just model-url "{{ model_name }}")
    just all-flat-with-model "{{ policy }}" "{{ run }}" "{{ model_name }}" "$model_url"

# Run full pipeline for a single policy+model: ingest → refine → emit → generate → evaluate
all-with-model policy run model_name model_url: (ingest policy run model_name model_url) (refine policy run model_name model_url) (emit policy run) (generate policy run model_name model_url) (evaluate policy run)

# Run pipeline for a single policy+model without ingest
all-flat-with-model policy run model_name model_url: (refine policy run model_name model_url) (emit policy run) (generate policy run model_name model_url) (evaluate policy run)

# Ingest policy document into enriched PolicyDocument format
ingest policy run model_name model_url:
    #!/usr/bin/env bash
    set -euo pipefail
    input=""; for ext in json md; do [ -f "{{ policy_dir }}/{{ policy }}.$ext" ] && input="{{ policy_dir }}/{{ policy }}.$ext" && break; done
    if [ -z "$input" ]; then echo "Error: no policy file found for {{ policy }}"; exit 1; fi
    mkdir -p {{ runs_dir }}/{{ policy }}-{{ run }}
    cd refiner && uv run refiner ingest "$input" \
        --output {{ runs_dir }}/{{ policy }}-{{ run }}/{{ policy }}-enriched.json \
        --base-url {{ model_url }} \
        --model {{ model_name }} \
        --api-key {{ api_key }}

# Ingest an arbitrary document (standalone)
ingest-doc input model_name model_url output="":
    cd refiner && uv run refiner ingest {{ input }} \
        {{ if output != "" { "--output " + output } else { "" } }} \
        --base-url {{ model_url }} \
        --model {{ model_name }} \
        --api-key {{ api_key }}

# Run refiner pipeline (uses enriched input from ingest if available)
refine policy run model_name model_url:
    #!/usr/bin/env bash
    set -euo pipefail
    # Snapshot chroma dirs to avoid RocksDB/ChromaDB lock conflicts with concurrent runs
    tmp_onto=$(mktemp -d)
    tmp_nexus=$(mktemp -d)
    cp -r {{ onto_chroma }}/ "$tmp_onto/"
    cp -r {{ nexus_chroma }}/ "$tmp_nexus/"
    cleanup() { rm -rf "$tmp_onto" "$tmp_nexus"; }
    trap cleanup EXIT
    enriched="{{ runs_dir }}/{{ policy }}-{{ run }}/{{ policy }}-enriched.json"
    if [ -f "$enriched" ]; then
        input="$enriched"
    else
        input=""; for ext in json md; do [ -f "{{ policy_dir }}/{{ policy }}.$ext" ] && input="{{ policy_dir }}/{{ policy }}.$ext" && break; done
        if [ -z "$input" ]; then echo "Error: no policy file found for {{ policy }}"; exit 1; fi
    fi
    tag_args=""
    for t in {{ run_tags }}; do tag_args="$tag_args --tag $t"; done
    cd refiner && uv run refiner run "$input" \
        --output {{ runs_dir }}/{{ policy }}-{{ run }} \
        --debug {{ runs_dir }}/{{ policy }}-{{ run }}/debug \
        --base-url {{ model_url }} \
        --model {{ model_name }} \
        --api-key {{ api_key }} \
        --nexus-base-dir {{ nexus_dir }} \
        --ontoquery-chroma-dir "$tmp_onto" \
        --nexus-chroma-dir "$tmp_nexus" \
        --track \
        --tracking-uri {{ tracking_uri }} \
        $tag_args

# Emit dataset from refiner output
emit policy run:
    #!/usr/bin/env bash
    set -euo pipefail
    enriched="{{ runs_dir }}/{{ policy }}-{{ run }}/{{ policy }}-enriched.json"
    if [ -f "$enriched" ]; then
        policies="$enriched"
    else
        policies=""; for ext in json md; do [ -f "{{ policy_dir }}/{{ policy }}.$ext" ] && policies="{{ policy_dir }}/{{ policy }}.$ext" && break; done
        if [ -z "$policies" ]; then echo "Error: no policy file found for {{ policy }}"; exit 1; fi
    fi
    cd refiner && uv run refiner emit {{ runs_dir }}/{{ policy }}-{{ run }} \
        --policies "$policies" \
        --samples-per-risk {{ samples_per_risk }} \
        --output {{ runs_dir }}/{{ policy }}-{{ run }}/dataset.jsonl

# Generate adversarial prompts via sdg_hub
generate policy run model_name model_url:
    cd redteam && uv run redteam {{ runs_dir }}/{{ policy }}-{{ run }}/dataset.jsonl \
        --model hosted_vllm/{{ model_name }} \
        --api-base {{ model_url }} \
        {{ if api_key != "none" { "--api-key " + api_key } else { "" } }} \
        --concurrency 5 \
        --output {{ runs_dir }}/{{ policy }}-{{ run }}/adversarial_prompts.jsonl

# Evaluate pipeline outputs
evaluate policy run:
    #!/usr/bin/env bash
    set -euo pipefail
    enriched="{{ runs_dir }}/{{ policy }}-{{ run }}/{{ policy }}-enriched.json"
    if [ -f "$enriched" ]; then
        policies="$enriched"
    else
        policies=""; for ext in json md; do [ -f "{{ policy_dir }}/{{ policy }}.$ext" ] && policies="{{ policy_dir }}/{{ policy }}.$ext" && break; done
        if [ -z "$policies" ]; then echo "Error: no policy file found for {{ policy }}"; exit 1; fi
    fi
    tag_args=""
    for t in {{ run_tags }}; do tag_args="$tag_args --tag $t"; done
    cd refiner && uv run refiner evaluate {{ runs_dir }}/{{ policy }}-{{ run }} \
        --emit {{ runs_dir }}/{{ policy }}-{{ run }}/dataset.jsonl \
        --adversarial {{ runs_dir }}/{{ policy }}-{{ run }}/adversarial_prompts.jsonl \
        --policies "$policies" \
        --track \
        --tracking-uri {{ tracking_uri }} \
        $tag_args

# Re-emit and regenerate (skip refiner)
regen policy run model_name model_url: (emit policy run) (generate policy run model_name model_url) (evaluate policy run)

# Index all ontologies into ontoquery ChromaDB (CCO + Commons + FIBO + OBO + D3FEND + CSO + bridges)
index-ontologies:
    cd ontoquery && uv run ontoquery index \
        ../ontologies/CommonCoreOntologies/src/cco-modules/ \
        ../ontologies/commons/ \
        ../ontologies/fibo/ \
        ../ontologies/obo/ \
        ../ontologies/d3fend-ontology/src/ontology/d3fend-protege.ttl \
        ../ontologies/cso/ \
        ../ontologies/bridges/
