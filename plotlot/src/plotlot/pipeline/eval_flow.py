"""Evaluation flow — scheduled quality checks against golden dataset.

Runs the golden dataset through all scorers and checks that key metrics
meet minimum thresholds. Designed to run nightly or on-demand.

Usage:
    uv run python -m plotlot.pipeline.eval_flow
"""

import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


GOLDEN_DATA_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent / "tests" / "eval" / "golden_data.json"
)

# Minimum acceptable metric values — below these, the eval fails
DEFAULT_THRESHOLDS = {
    "report_completeness/mean": 0.6,
}


def load_golden_data(path: Path | None = None) -> list[dict]:
    """Load golden dataset from JSON file."""
    p = path or GOLDEN_DATA_PATH
    data = json.loads(p.read_text())
    logger.info("Loaded %d golden samples from %s", len(data), p)
    return data


def run_scorers(golden_data: list[dict]) -> dict:
    """Run all scorers via MLflow evaluate and return metrics."""
    import mlflow
    import mlflow.genai

    from plotlot.config import settings

    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    mlflow.set_experiment(settings.mlflow_experiment_name)

    # Import scorers from test module
    sys.path.insert(0, str(GOLDEN_DATA_PATH.parent.parent.parent))
    from tests.eval.scorers import ALL_SCORERS

    result = mlflow.genai.evaluate(data=golden_data, scorers=ALL_SCORERS)
    metrics = result.metrics or {}
    logger.info("Eval metrics: %s", metrics)
    return metrics


def check_thresholds(
    metrics: dict,
    thresholds: dict[str, float] | None = None,
) -> bool:
    """Check if all metrics meet minimum thresholds.

    Returns:
        True if all thresholds pass, False otherwise.
    """
    thresholds = thresholds or DEFAULT_THRESHOLDS
    passed = True

    for metric_name, min_value in thresholds.items():
        actual = metrics.get(metric_name)
        if actual is None:
            logger.warning("Threshold check: metric %r not found in results", metric_name)
            continue
        if actual < min_value:
            logger.error(
                "THRESHOLD FAILED: %s = %.4f (min: %.4f)",
                metric_name,
                actual,
                min_value,
            )
            passed = False
        else:
            logger.info(
                "Threshold passed: %s = %.4f (min: %.4f)",
                metric_name,
                actual,
                min_value,
            )

    return passed


def eval_quality_check(
    tag: str = "nightly",
    thresholds: dict[str, float] | None = None,
) -> bool:
    """Run evaluation and check quality thresholds.

    Args:
        tag: Label for this eval run (e.g., "nightly", "pr-123").
        thresholds: Optional custom thresholds. Uses DEFAULT_THRESHOLDS if None.

    Returns:
        True if all thresholds pass, False otherwise.
    """
    import mlflow

    from plotlot.config import settings
    from plotlot.observability.prompts import get_prompt_version, log_prompt_to_run

    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    mlflow.set_experiment(settings.mlflow_experiment_name)

    golden_data = load_golden_data()
    metrics = run_scorers(golden_data)
    passed = check_thresholds(metrics, thresholds)

    # Log results to MLflow
    with mlflow.start_run(run_name=f"eval_{tag}"):
        mlflow.set_tags(
            {
                "eval_tag": tag,
                "eval_type": "offline",
                "prompt_analysis_version": get_prompt_version("analysis"),
                "quality_gate": "passed" if passed else "failed",
            }
        )
        log_prompt_to_run("analysis")

        for key, val in metrics.items():
            if isinstance(val, (int, float)):
                mlflow.log_metric(key.replace("/", "_"), val)

        mlflow.set_tag("status", "completed")

    return passed


if __name__ == "__main__":
    result = eval_quality_check(tag="manual")
    sys.exit(0 if result else 1)
