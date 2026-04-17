"""Run garak vulnerability scan against a target model.

Wraps garak CLI invocation, setting up paths so garak reads the CAS data
from the ORT run directory.

Usage::

    ort scan --demo-dir demo_runs/rdash-nhs --config configs/garak.yaml

Importable for notebooks::

    from demo.scan import run_garak, find_latest_report
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def run_garak(
    config_path: Path,
    demo_dir: Path,
    *,
    cas_subdir: str = "data/cas",
) -> Path | None:
    """Run garak with config, pointing CAS data to demo_dir.

    Sets XDG_DATA_HOME so garak reads trait_typology.json and intent_stubs/
    from the ORT run directory.

    Returns the path to the generated report.jsonl, or None on failure.
    """
    cas_dir = demo_dir / cas_subdir
    if not (cas_dir / "trait_typology.json").exists():
        raise FileNotFoundError(
            f"No trait_typology.json in {cas_dir}. Run 'demo prepare' first.",
        )

    # Garak expects CAS data at $XDG_DATA_HOME/garak/data/cas/
    # We point XDG_DATA_HOME so that the path resolves correctly
    xdg_data_home = str(demo_dir)
    garak_data_parent = cas_dir.parent.parent  # demo_dir
    if cas_subdir == "data/cas":
        xdg_data_home = str(demo_dir / "garak_home")
        garak_cas_target = Path(xdg_data_home) / "garak" / "data" / "cas"
        garak_cas_target.parent.mkdir(parents=True, exist_ok=True)
        if not garak_cas_target.exists():
            garak_cas_target.symlink_to(cas_dir.resolve())

    # Ensure garak_runs output directory exists
    runs_dir = demo_dir / "garak_runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    old_xdg = os.environ.get("XDG_DATA_HOME")
    os.environ["XDG_DATA_HOME"] = xdg_data_home

    # Reload garak._config if already imported (picks up new XDG_DATA_HOME)
    if "garak._config" in sys.modules:
        import importlib
        import garak._config
        importlib.reload(garak._config)

    try:
        import garak.cli
        garak.cli.main(["--config", str(config_path.resolve())])
    finally:
        if old_xdg is not None:
            os.environ["XDG_DATA_HOME"] = old_xdg
        else:
            os.environ.pop("XDG_DATA_HOME", None)

    return find_latest_report(demo_dir)


def find_latest_report(demo_dir: Path) -> Path | None:
    """Find the most recent garak report.jsonl in the ORT run directory."""
    # Check garak_runs/ first, then garak_home/
    for search_root in [demo_dir / "garak_runs", demo_dir / "garak_home"]:
        reports = sorted(
            search_root.rglob("*.report.jsonl"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if reports:
            return reports[0]
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Run garak vulnerability scan")
    parser.add_argument(
        "--demo-dir", type=Path, required=True,
        help="Path to ORT run directory (from 'demo prepare')",
    )
    parser.add_argument(
        "--config", type=Path, required=True,
        help="Path to garak.yaml configuration",
    )
    parser.add_argument(
        "--cas-subdir", default="data/cas",
        help="CAS subdirectory within ORT dir (default: data/cas; use data/cas_utility for utility scan)",
    )
    args = parser.parse_args()

    report = run_garak(
        args.config.resolve(),
        args.demo_dir.resolve(),
        cas_subdir=args.cas_subdir,
    )
    if report:
        print(f"\nReport: {report}")
    else:
        print("\nWarning: no report file found after scan", file=sys.stderr)


if __name__ == "__main__":
    main()
