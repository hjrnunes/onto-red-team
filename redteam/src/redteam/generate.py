"""Generate adversarial prompts from a refiner emit dataset via sdg_hub.

Usage:
    # Basic — model endpoint + dataset
    redteam /tmp/dataset.jsonl \
        --model hosted_vllm/my-model \
        --api-base http://localhost:8080/v1

    # Full options
    redteam /tmp/dataset.jsonl \
        --model hosted_vllm/my-model \
        --api-base http://localhost:8080/v1 \
        --api-key EMPTY \
        --concurrency 10 \
        --output /tmp/adversarial_prompts.jsonl

    # End-to-end from refiner pipeline output
    cd refiner
    uv run refiner emit /tmp/refiner-out --policies ../policy_examples/swb.json \
        --samples-per-risk 10 --seed 42 --output /tmp/dataset.jsonl
    cd ../redteam
    uv run redteam /tmp/dataset.jsonl \
        --model hosted_vllm/my-model \
        --api-base http://localhost:8080/v1
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import nest_asyncio
import pandas as pd
from sdg_hub import Flow

nest_asyncio.apply()

FLOW_YAML = Path(__file__).resolve().parent.parent.parent / "flows" / "flow.yaml"


def main():
    parser = argparse.ArgumentParser(
        description="Generate adversarial prompts from a refiner emit dataset via sdg_hub.",
    )
    parser.add_argument(
        "dataset",
        type=Path,
        help="Path to JSONL dataset from 'refiner emit'",
    )
    parser.add_argument(
        "--model",
        required=True,
        help="Model name (e.g. 'hosted_vllm/my-model', 'openai/gpt-4o')",
    )
    parser.add_argument(
        "--api-base",
        default=None,
        help="API base URL (e.g. 'http://localhost:8080/v1')",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="API key (or set OPENAI_API_KEY env var)",
    )
    parser.add_argument(
        "--flow",
        type=Path,
        default=None,
        help=f"Path to flow.yaml (default: {FLOW_YAML})",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=10,
        help="Max concurrent LLM requests (default: 10)",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Output JSONL path (default: <dataset-dir>/adversarial_prompts_<timestamp>.jsonl)",
    )
    args = parser.parse_args()

    # Resolve flow path
    flow_path = args.flow or FLOW_YAML
    if not flow_path.exists():
        print(f"Error: flow not found at {flow_path}", file=sys.stderr)
        sys.exit(1)

    # Load dataset
    if not args.dataset.exists():
        print(f"Error: dataset not found at {args.dataset}", file=sys.stderr)
        sys.exit(1)

    dataset = pd.read_json(args.dataset, lines=True)
    print(f"Loaded dataset: {len(dataset)} rows from {args.dataset.name}")
    print(f"Columns: {list(dataset.columns)}")

    # Load and configure flow
    flow = Flow.from_yaml(flow_path)
    print(f"Flow loaded: {flow_path.name}")

    model_kwargs = {"model": args.model}
    if args.api_base:
        model_kwargs["api_base"] = args.api_base
    if args.api_key:
        model_kwargs["api_key"] = args.api_key

    flow.set_model_config(**model_kwargs)
    print(f"Model configured: {args.model}")

    # Generate
    print(f"Generating with max_concurrency={args.concurrency}...")
    result = flow.generate(dataset, max_concurrency=args.concurrency)
    print(f"Result: {result.shape[0]} rows, {result.shape[1]} columns")

    # Show a sample
    if len(result) > 0:
        sample = result.iloc[0]
        print(f"\n--- Sample (row 0) ---")
        print(f"Policy: {sample.get('policy_concept', 'N/A')}")
        print(f"Risk: {sample.get('risk_name', 'N/A')}")
        prompt = sample.get("prompt", None)
        if prompt:
            preview = prompt[:200] + "..." if len(str(prompt)) > 200 else prompt
            print(f"Generated prompt: {preview}")

    # Save output
    output_path = args.output
    if output_path is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output_path = args.dataset.parent / f"adversarial_prompts_{timestamp}.jsonl"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Drop intermediate columns, keep metadata + generated prompt
    drop_cols = [c for c in result.columns if c in (
        "raw_response", "extract_response_content", "generation_prompt",
    )]
    output_df = result.drop(columns=drop_cols, errors="ignore")
    output_df.to_json(output_path, orient="records", lines=True)

    print(f"\nSaved {len(output_df)} rows to {output_path}")
    print(f"Output columns: {list(output_df.columns)}")


if __name__ == "__main__":
    main()
