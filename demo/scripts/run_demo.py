#!/usr/bin/env python3
"""End-to-end ORT demo pipeline runner.

Convenience script wrapping ``demo run``.

Usage::

    python scripts/run_demo.py \\
        --policy ../policy_examples/rdash-nhs.json \\
        --model mistral-small-3-1-24b \\
        --model-url https://model-serving.example.com/v1 \\
        --config configs/garak.yaml

    # Dry run (print commands without executing)
    python scripts/run_demo.py \\
        --policy ../policy_examples/rdash-nhs.json \\
        --model mistral-small-3-1-24b \\
        --model-url https://model-serving.example.com/v1 \\
        --dry-run

Notebook equivalent::

    from pathlib import Path
    from demo.pipeline import run_pipeline

    run_pipeline(
        Path("../policy_examples/rdash-nhs.json"),
        "mistral-small-3-1-24b",
        "https://model-serving.example.com/v1",
        garak_config=Path("configs/garak.yaml"),
    )
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from demo.cli import main

if __name__ == "__main__":
    sys.argv = [sys.argv[0], "run"] + sys.argv[1:]
    main()
