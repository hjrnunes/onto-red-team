"""ORT demo pipeline CLI.

Subcommands::

    demo prepare  --run-dir <refiner-run> [--output-dir <demo-run>]
    demo utility  --run-dir <refiner-run> --demo-dir <demo-run>
    demo scan     --demo-dir <demo-run> --config <garak.yaml>
    demo report   --demo-dir <demo-run> --run-dir <refiner-run>
    demo run      --run-dir <refiner-run> --config <garak.yaml> [--output-dir <demo-run>]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="demo",
        description="Online Red Teaming pipeline",
    )
    sub = parser.add_subparsers(dest="command")

    # -- prepare --
    prep = sub.add_parser("prepare", help="Prepare ORT data from a refiner run")
    prep.add_argument("--run-dir", type=Path, required=True)
    prep.add_argument("--output-dir", type=Path, default=None)
    prep.add_argument("--take-per-intent", type=int, default=None)

    # -- utility --
    util = sub.add_parser("utility", help="Generate utility/blue-team prompts")
    util.add_argument("--run-dir", type=Path, required=True)
    util.add_argument("--demo-dir", type=Path, required=True)
    util.add_argument("--samples-per-risk", type=int, default=5)
    util.add_argument("--seed", type=int, default=None)
    util.add_argument("--take-per-intent", type=int, default=None)

    # -- scan --
    sc = sub.add_parser("scan", help="Run garak vulnerability scan")
    sc.add_argument("--demo-dir", type=Path, required=True)
    sc.add_argument("--config", type=Path, required=True)
    sc.add_argument("--cas-subdir", default="data/cas")

    # -- report --
    rep = sub.add_parser("report", help="Build ORT-enriched ART report")
    rep.add_argument("--demo-dir", type=Path, required=True)
    rep.add_argument("--run-dir", type=Path, required=True)
    rep.add_argument("--report", type=Path, default=None)
    rep.add_argument("--output", type=Path, default=None)

    # -- run (end-to-end from policy) --
    run = sub.add_parser("run", help="Full pipeline: policy + model → ART report")
    run.add_argument("--policy", type=Path, required=True, help="Policy JSON file")
    run.add_argument("--model", required=True, help="Model name (e.g. mistral-small-3-1-24b)")
    run.add_argument("--model-url", required=True, help="Model API base URL")
    run.add_argument("--config", type=Path, default=None, help="Garak config YAML")
    run.add_argument("--output-dir", type=Path, default=None)
    run.add_argument("--api-key", default=None, help="API key (or REFINER_API_KEY env var)")
    run.add_argument("--samples-per-risk", type=int, default=15)
    run.add_argument("--utility-samples", type=int, default=5)
    run.add_argument("--concurrency", type=int, default=5)
    run.add_argument("--seed", type=int, default=None)
    run.add_argument("--nexus-base-dir", type=Path, default=None)
    run.add_argument("--ontoquery-chroma-dir", type=Path, default=None)
    run.add_argument("--nexus-chroma-dir", type=Path, default=None)
    run.add_argument("--skip-ingest", action="store_true")
    run.add_argument("--skip-utility", action="store_true")
    run.add_argument("--skip-scan", action="store_true")
    run.add_argument("--dry-run", action="store_true", help="Print commands without executing")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "prepare":
        from demo.prepare import prepare, _find_file
        import yaml

        run_dir = args.run_dir.resolve()
        output_dir = args.output_dir
        if output_dir is None:
            dc_path = _find_file(run_dir, "*-domain-context.yaml")
            with open(dc_path) as f:
                dc = yaml.safe_load(f)
            slug = dc.get("run_slug", run_dir.name)
            output_dir = Path("demo_runs") / slug
        prepare(run_dir, output_dir.resolve(), take_per_intent=args.take_per_intent)

    elif args.command == "utility":
        from demo.utility import utility
        utility(
            args.run_dir.resolve(),
            args.demo_dir.resolve(),
            samples_per_risk=args.samples_per_risk,
            seed=args.seed,
            take_per_intent=args.take_per_intent,
        )

    elif args.command == "scan":
        from demo.scan import run_garak
        report = run_garak(
            args.config.resolve(),
            args.demo_dir.resolve(),
            cas_subdir=args.cas_subdir,
        )
        if report:
            print(f"\nReport: {report}")
        else:
            print("\nWarning: no report file found after scan", file=sys.stderr)

    elif args.command == "report":
        from demo.report import render_report
        demo_dir = args.demo_dir.resolve()
        run_dir = args.run_dir.resolve()
        output = args.output or (demo_dir / "report.html")

        print(f"Rendering report from {demo_dir.name} ...")
        html = render_report(demo_dir, run_dir, report_path=args.report)
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w") as f:
            f.write(html)
        print(f"Report written to {output}")

    elif args.command == "run":
        from demo.pipeline import run_pipeline
        run_pipeline(
            args.policy,
            args.model,
            args.model_url,
            garak_config=args.config,
            output_dir=args.output_dir,
            api_key=args.api_key,
            samples_per_risk=args.samples_per_risk,
            utility_samples=args.utility_samples,
            seed=args.seed,
            concurrency=args.concurrency,
            nexus_base_dir=args.nexus_base_dir,
            ontoquery_chroma_dir=args.ontoquery_chroma_dir,
            nexus_chroma_dir=args.nexus_chroma_dir,
            skip_ingest=args.skip_ingest,
            skip_utility=args.skip_utility,
            skip_scan=args.skip_scan,
            dry_run=args.dry_run,
        )


if __name__ == "__main__":
    main()
