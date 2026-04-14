"""Advisory system prototype — chains analyze → configure → report."""
import argparse
import json
from pathlib import Path

from analyze import build_analysis
from configure import generate_garak_config, generate_nemo_config
from report import generate_report


def main():
    parser = argparse.ArgumentParser(
        description="Advisory system prototype: refiner output → coverage analysis → configs → report"
    )
    parser.add_argument("run_dir", nargs="?", type=Path, help="Refiner run directory")
    parser.add_argument("--policy", type=Path, help="Policy file (for domain identification)")
    parser.add_argument("--scenario", type=Path, help="Canned scenario JSON (fallback)")
    parser.add_argument("--output", type=Path, required=True, help="Output directory")
    args = parser.parse_args()

    if not args.run_dir and not args.scenario:
        parser.error("Either run_dir or --scenario must be provided")

    output = args.output
    output.mkdir(parents=True, exist_ok=True)

    # Stage 1: Analyze
    print("=== Stage 1: Coverage Analysis ===")
    analysis = build_analysis(
        run_dir=args.run_dir,
        policy_file=args.policy,
        scenario=args.scenario,
    )
    analysis_path = output / "analysis.json"
    with open(analysis_path, "w") as f:
        json.dump(analysis, f, indent=2)

    s = analysis["summary"]
    print(f"  {s['total_risks']} risks, {s['amplified_risks']} amplified")
    print(f"  {s['fully_covered']} covered, {s['partial_gaps']} partial, {s['no_coverage']} uncovered")

    # Stage 2: Configure
    print("\n=== Stage 2: Config Generation ===")
    generate_garak_config(analysis, output)
    generate_nemo_config(analysis, output)
    print("  garak.yaml")
    print("  nemo/config.yml + rails.co")

    # Stage 3: Report
    print("\n=== Stage 3: Advisory Report ===")
    generate_report(analysis, output)
    print(f"  advisory-report.md")

    print(f"\nAll artifacts written to {output}/")


if __name__ == "__main__":
    main()
