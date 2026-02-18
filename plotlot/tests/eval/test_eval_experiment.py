"""Experiment-tracked evaluation — logs metrics as MLflow runs for comparison.

Each eval run becomes an MLflow experiment entry. You can compare:
- Current vs previous prompt versions
- Model A vs Model B (Kimi vs DeepSeek)
- Accuracy trends over time

Run:
    uv run pytest tests/eval/test_eval_experiment.py -m eval -v
"""

import mlflow
import mlflow.genai
import pytest


@pytest.mark.eval
class TestExperimentTrackedEval:
    def test_experiment_run_logged(self, golden_data, all_scorers):
        """Eval run logs all scorer metrics to MLflow experiment."""
        with mlflow.start_run(run_name="test_experiment_eval") as run:
            mlflow.set_tags({
                "eval_type": "offline",
                "test": "true",
            })

            result = mlflow.genai.evaluate(data=golden_data, scorers=all_scorers)

            # Log aggregate metrics to the run
            for key, val in (result.metrics or {}).items():
                if isinstance(val, (int, float)):
                    mlflow.log_metric(key.replace("/", "_"), val)

            mlflow.set_tag("status", "completed")

        # Verify run was logged
        assert run.info.run_id is not None
        assert result.metrics is not None
        assert len(result.metrics) > 0

    def test_per_county_metrics(self, golden_data, all_scorers):
        """Group golden data by county and log per-county accuracy."""
        counties = {}
        for sample in golden_data:
            county = sample["expectations"].get("county", "unknown")
            counties.setdefault(county, []).append(sample)

        with mlflow.start_run(run_name="test_per_county"):
            for county, samples in counties.items():
                result = mlflow.genai.evaluate(data=samples, scorers=all_scorers)
                for key, val in (result.metrics or {}).items():
                    if isinstance(val, (int, float)):
                        safe_key = f"{county.replace(' ', '_').replace('-', '_')}_{key.replace('/', '_')}"
                        mlflow.log_metric(safe_key, val)

            mlflow.set_tag("status", "completed")

        # Should have at least 2 counties in golden data
        assert len(counties) >= 2

    def test_scorer_summary_artifact(self, golden_data, all_scorers):
        """Log per-sample scorer results as a JSON artifact."""
        result = mlflow.genai.evaluate(data=golden_data, scorers=all_scorers)

        with mlflow.start_run(run_name="test_scorer_artifact"):
            # Log full eval table if available
            eval_table = result.tables.get("eval_results")
            if eval_table is not None:
                mlflow.log_table(eval_table, artifact_file="eval_results.json")

            # Log metrics summary
            mlflow.log_dict(
                {"metrics": result.metrics, "sample_count": len(golden_data)},
                "eval_summary.json",
            )
            mlflow.set_tag("status", "completed")
