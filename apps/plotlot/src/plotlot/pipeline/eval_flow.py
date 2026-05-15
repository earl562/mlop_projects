"""Evaluation flow — scheduled quality checks against golden dataset.

Runs the golden dataset through all scorers and checks that key metrics
meet minimum thresholds. Designed to run nightly or on-demand.

Usage:
    uv run python -m plotlot.pipeline.eval_flow
"""

import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
GOLDEN_DATA_PATH = PROJECT_ROOT / "tests" / "eval" / "golden_data.json"
EVAL_PROTOCOL_VERSION = "vero-inspired-v1"
EVAL_TARGET_WORKFLOW = "plotlot-site-feasibility"

# Minimum acceptable metric values — below these, the eval fails
DEFAULT_THRESHOLDS = {
    "report_completeness/mean": 0.7,
    "numeric_extraction_accuracy/mean": 0.7,
    "municipality_match/mean": 0.8,
    "confidence_acceptable/mean": 0.7,
}


def load_golden_data(path: Path | None = None) -> list[dict]:
    """Load golden dataset from JSON file."""
    p = path or GOLDEN_DATA_PATH
    data: list[dict] = json.loads(p.read_text())
    logger.info("Loaded %d golden samples from %s", len(data), p)
    return data


def select_eval_samples(golden_data: list[dict], max_samples: int | None = None) -> list[dict]:
    """Apply a deterministic sample budget to an eval dataset."""
    if max_samples is None:
        return golden_data
    if max_samples < 1:
        raise ValueError("max_samples must be >= 1")
    return golden_data[:max_samples]


def prompt_version_map() -> dict[str, str]:
    """Return the active prompt registry as a name -> version mapping."""
    from plotlot.observability.prompts import list_prompts

    return {prompt["name"]: prompt["version"] for prompt in list_prompts()}


def get_git_commit() -> str | None:
    """Return the current git commit for reproducible eval manifests."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
            check=False,
        )
    except OSError:
        return None

    commit = result.stdout.strip()
    return commit or None


def build_eval_run_manifest(
    *,
    tag: str,
    dataset_path: Path,
    sample_count: int,
    thresholds: dict[str, float],
    prompt_versions: dict[str, str],
    metrics: dict[str, Any],
    max_samples: int | None,
    git_commit: str | None,
    passed: bool,
) -> dict[str, Any]:
    """Build a VeRO-style manifest for a site-feasibility eval run."""
    return {
        "protocol": EVAL_PROTOCOL_VERSION,
        "target_workflow": EVAL_TARGET_WORKFLOW,
        "tag": tag,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "versioning": {
            "git_commit": git_commit,
            "dataset_path": str(dataset_path),
            "prompt_versions": prompt_versions,
        },
        "budget": {
            "max_samples": max_samples,
            "evaluated_samples": sample_count,
        },
        "rewards": {
            "status": "passed" if passed else "failed",
            "thresholds": thresholds,
            "metrics": metrics,
        },
        "observations": {
            "metric_keys": sorted(metrics.keys()),
            "artifacts": [
                "eval/eval_run_manifest.json",
                "eval/golden_data_slice.json",
                "prompts/*",
            ],
        },
    }


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
    max_samples: int | None = None,
) -> bool:
    """Run evaluation and check quality thresholds.

    Args:
        tag: Label for this eval run (e.g., "nightly", "pr-123").
        thresholds: Optional custom thresholds. Uses DEFAULT_THRESHOLDS if None.
        max_samples: Optional deterministic sample budget for offline evals.

    Returns:
        True if all thresholds pass, False otherwise.
    """
    import mlflow

    from plotlot.config import settings
    from plotlot.observability.prompts import log_prompt_to_run

    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    mlflow.set_experiment(settings.mlflow_experiment_name)

    effective_thresholds = thresholds or DEFAULT_THRESHOLDS
    golden_data = select_eval_samples(load_golden_data(), max_samples=max_samples)
    metrics = run_scorers(golden_data)
    passed = check_thresholds(metrics, effective_thresholds)
    prompts = prompt_version_map()
    manifest = build_eval_run_manifest(
        tag=tag,
        dataset_path=GOLDEN_DATA_PATH,
        sample_count=len(golden_data),
        thresholds=effective_thresholds,
        prompt_versions=prompts,
        metrics=metrics,
        max_samples=max_samples,
        git_commit=get_git_commit(),
        passed=passed,
    )

    # Log results to MLflow
    with mlflow.start_run(run_name=f"eval_{tag}"):
        prompt_tags = {
            "eval_tag": tag,
            "eval_type": "offline",
            "eval_protocol": EVAL_PROTOCOL_VERSION,
            "eval_target_workflow": EVAL_TARGET_WORKFLOW,
            "eval_sample_budget": str(max_samples or "all"),
            "eval_sample_count": str(len(golden_data)),
            "quality_gate": "passed" if passed else "failed",
        }
        if manifest["versioning"]["git_commit"]:
            prompt_tags["git_commit"] = manifest["versioning"]["git_commit"]
        for name, version in prompts.items():
            prompt_tags[f"prompt_{name}_version"] = version
        mlflow.set_tags(prompt_tags)

        for name in prompts:
            log_prompt_to_run(name)

        mlflow.log_dict(manifest, "eval/eval_run_manifest.json")
        mlflow.log_dict({"golden_data": golden_data}, "eval/golden_data_slice.json")

        for key, val in metrics.items():
            if isinstance(val, (int, float)):
                mlflow.log_metric(key.replace("/", "_"), val)

        mlflow.set_tag("status", "completed")

    return passed


if __name__ == "__main__":
    result = eval_quality_check(tag="manual")
    sys.exit(0 if result else 1)
