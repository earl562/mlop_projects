#!/usr/bin/env python
"""Run PlotLot evaluation suite and log results to MLflow.

Usage:
    uv run python scripts/run_eval.py --tag "baseline-v2.1"
    uv run python scripts/run_eval.py --tag "new-prompt-v1" --live

Modes:
    Offline (default): Runs scorers against pre-recorded golden outputs.
    Live (--live): Runs the full pipeline for each golden address, then scores.
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import mlflow
import mlflow.genai

# Add project root to path so imports work
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from plotlot.config import settings  # noqa: E402
from plotlot.observability.prompts import get_prompt_version, log_prompt_to_run  # noqa: E402

GOLDEN_DATA_PATH = PROJECT_ROOT / "tests" / "eval" / "golden_data.json"


def _get_git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _load_scorers():
    from tests.eval.scorers import ALL_SCORERS

    return ALL_SCORERS


def run_offline_eval(golden_data: list[dict], scorers: list, tag: str) -> dict:
    """Run offline eval and log to MLflow."""
    result = mlflow.genai.evaluate(data=golden_data, scorers=scorers)

    metrics = result.metrics or {}
    print(f"\n{'=' * 60}")
    print(f"  PlotLot Offline Eval — {tag}")
    print(f"{'=' * 60}")
    print(f"  Samples: {len(golden_data)}")
    for key, val in sorted(metrics.items()):
        print(f"  {key}: {val:.4f}" if isinstance(val, float) else f"  {key}: {val}")
    print(f"{'=' * 60}\n")

    return metrics


def main():
    parser = argparse.ArgumentParser(description="Run PlotLot evaluation")
    parser.add_argument(
        "--tag", required=True, help="Tag for this eval run (e.g., 'baseline-v2.1')"
    )
    parser.add_argument("--live", action="store_true", help="Run live pipeline instead of offline")
    args = parser.parse_args()

    # Load golden data
    golden_data = json.loads(GOLDEN_DATA_PATH.read_text())
    print(f"Loaded {len(golden_data)} golden samples")

    # Setup MLflow
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    mlflow.set_experiment("plotlot-eval")

    scorers = _load_scorers()
    git_sha = _get_git_sha()
    timestamp = datetime.now(timezone.utc).isoformat()

    with mlflow.start_run(run_name=f"eval_{args.tag}"):
        mlflow.set_tags(
            {
                "eval_tag": args.tag,
                "eval_type": "live" if args.live else "offline",
                "git_sha": git_sha,
                "timestamp": timestamp,
                "prompt_analysis_version": get_prompt_version("analysis"),
                "golden_sample_count": str(len(golden_data)),
            }
        )
        log_prompt_to_run("analysis")

        if args.live:
            print("Live eval not yet implemented — run the live pytest instead:")
            print("  uv run pytest tests/eval/test_eval_live.py -m 'eval and e2e' -v")
            mlflow.set_tag("status", "skipped")
            return

        metrics = run_offline_eval(golden_data, scorers, args.tag)

        # Log all metrics
        for key, val in metrics.items():
            if isinstance(val, (int, float)):
                mlflow.log_metric(key.replace("/", "_"), val)

        # Log golden data as artifact
        mlflow.log_dict(golden_data, "golden_data.json")
        mlflow.set_tag("status", "completed")

    print("Results logged to MLflow experiment: plotlot-eval")


if __name__ == "__main__":
    main()
