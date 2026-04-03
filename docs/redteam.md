# redteam — Adversarial Prompt Generation

Generates adversarial prompts from the emit dataset using sdg_hub's LLM flow.

## Hybrid Integration

We do sampling + prompt building (refiner emit); sdg_hub does LLM execution + response parsing via a companion
flow (`flows/flow.yaml`: 3 blocks — LLMChatBlock, ResponseExtractor, JSONParser).

## CLI

```bash
cd redteam

# Generate adversarial prompts
uv run redteam /tmp/dataset.jsonl \
  --model hosted_vllm/my-model \
  --api-base http://localhost:8080/v1 \
  --concurrency 5 \
  --output /tmp/adversarial_prompts.jsonl
```

## Source Layout

```
redteam/
  src/redteam/generate.py          # CLI: load dataset, run flow, save results, build explorer
  flows/flow.yaml                  # sdg_hub flow (LLMChat -> Extractor -> JSONParser)
  tools/build_explorer.py          # Build HTML explorer from JSON/JSONL output
  tools/explorer_template.html     # Alpine.js + Tailwind template for browsing results
```

## End-to-End with justfile

```bash
# Full pipeline for one policy+model
just all swb my-run gemma-2-9b

# All policies, all models (parallel by model)
just run-all my-run

# Re-emit + regenerate (skip refiner)
just regen swb my-run gemma-2-9b
```
