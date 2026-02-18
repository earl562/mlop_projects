#!/usr/bin/env python
"""CI quality gate — exits non-zero if eval metrics drop below thresholds.

Usage:
    uv run python scripts/ci_eval_gate.py
    uv run python scripts/ci_eval_gate.py --tag "pr-123"

Exit codes:
    0 — All thresholds passed
    1 — One or more thresholds failed
"""

import argparse
import json
import sys
from pathlib import Path

# Add project root so imports work
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

GOLDEN_DATA_PATH = PROJECT_ROOT / "tests" / "eval" / "golden_data.json"

# Quality thresholds — tune these as the golden dataset grows
THRESHOLDS = {
    "report_completeness/mean": 0.6,
}


def main():
    parser = argparse.ArgumentParser(description="CI eval quality gate")
    parser.add_argument("--tag", default="ci", help="Tag for this eval run")
    args = parser.parse_args()

    import mlflow
    import mlflow.genai

    from plotlot.config import settings
    from tests.eval.scorers import ALL_SCORERS

    # Load golden data
    golden_data = json.loads(GOLDEN_DATA_PATH.read_text())
    print(f"Loaded {len(golden_data)} golden samples")

    # Setup MLflow
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    mlflow.set_experiment(settings.mlflow_experiment_name)

    # Run eval
    result = mlflow.genai.evaluate(data=golden_data, scorers=ALL_SCORERS)
    metrics = result.metrics or {}

    # Check thresholds
    failed = []
    print(f"\n{'=' * 50}")
    print(f"  Quality Gate — {args.tag}")
    print(f"{'=' * 50}")

    for metric_name, min_value in THRESHOLDS.items():
        actual = metrics.get(metric_name)
        if actual is None:
            print(f"  WARN: {metric_name} not found in results")
            continue
        status = "PASS" if actual >= min_value else "FAIL"
        print(f"  {status}: {metric_name} = {actual:.4f} (min: {min_value:.4f})")
        if actual < min_value:
            failed.append(metric_name)

    print(f"{'=' * 50}\n")

    if failed:
        print(f"FAILED: {len(failed)} threshold(s) not met: {', '.join(failed)}")
        sys.exit(1)
    else:
        print("All quality thresholds passed.")
        sys.exit(0)


if __name__ == "__main__":
    main()
