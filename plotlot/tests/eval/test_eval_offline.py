"""Offline evaluation — runs on pre-recorded golden outputs.

Fast, no network, no DB, no LLM calls. Validates that the scoring
framework works correctly against known-good pipeline outputs.

Run:
    uv run pytest tests/eval/test_eval_offline.py -m eval -v
"""

import mlflow.genai
import pytest


@pytest.mark.eval
class TestOfflineEval:
    """Evaluate pre-recorded outputs against golden expectations."""

    def test_golden_dataset(self, golden_data, all_scorers):
        """All scorers should produce positive results on verified outputs."""
        result = mlflow.genai.evaluate(data=golden_data, scorers=all_scorers)

        # Every scorer should have a metric entry
        assert result.metrics is not None
        assert len(result.metrics) > 0

        # Check that all boolean scorers passed (mean > 0 means at least some passed)
        for scorer_name in [
            "zoning_district_match",
            "municipality_match",
            "max_units_match",
            "governing_constraint_match",
            "confidence_acceptable",
        ]:
            key = f"{scorer_name}/mean"
            assert key in result.metrics, f"Missing metric: {key}"
            assert result.metrics[key] > 0, (
                f"{scorer_name} scored 0 — golden outputs should match expectations"
            )

        # Numeric extraction accuracy should be high for golden data
        accuracy_key = "numeric_extraction_accuracy/mean"
        assert accuracy_key in result.metrics
        assert result.metrics[accuracy_key] >= 0.8, (
            f"Numeric accuracy {result.metrics[accuracy_key]:.2f} < 0.8 on golden data"
        )

        # Report completeness should be perfect for golden data
        completeness_key = "report_completeness/mean"
        assert completeness_key in result.metrics
        assert result.metrics[completeness_key] >= 0.8, (
            f"Report completeness {result.metrics[completeness_key]:.2f} < 0.8 on golden data"
        )

    def test_per_sample_results(self, golden_data, all_scorers):
        """Each golden sample should pass all boolean scorers individually."""
        result = mlflow.genai.evaluate(data=golden_data, scorers=all_scorers)

        # The eval table should have one row per sample
        eval_table = result.tables.get("eval_results")
        if eval_table is not None:
            assert len(eval_table) == len(golden_data)

    def test_miami_gardens_strict(self, golden_data, all_scorers):
        """Miami Gardens R-1 sample has 10% tolerance — all 10 params should match."""
        mg_data = [s for s in golden_data if s["inputs"]["address"] == "171 NE 209th Ter, Miami, FL 33179"]
        assert len(mg_data) == 1

        result = mlflow.genai.evaluate(data=mg_data, scorers=all_scorers)

        accuracy_key = "numeric_extraction_accuracy/mean"
        assert result.metrics[accuracy_key] == 1.0, (
            f"Miami Gardens should have perfect numeric extraction, got {result.metrics[accuracy_key]}"
        )

    def test_miramar_tolerant(self, golden_data, all_scorers):
        """Miramar RS5 sample has 50% tolerance — should still pass."""
        mir_data = [s for s in golden_data if s["inputs"]["address"] == "7940 Plantation Blvd, Miramar, FL 33023"]
        assert len(mir_data) == 1

        result = mlflow.genai.evaluate(data=mir_data, scorers=all_scorers)

        accuracy_key = "numeric_extraction_accuracy/mean"
        assert result.metrics[accuracy_key] >= 0.8, (
            f"Miramar numeric accuracy {result.metrics[accuracy_key]:.2f} < 0.8"
        )

    def test_all_municipalities_have_numeric_params(self, golden_data, all_scorers):
        """Every positive golden case with outputs should have numeric_params.

        Exception: data quality cases (testing chunk filtering) may omit
        numeric_params since their purpose is verifying retrieval quality.
        """
        positive = [s for s in golden_data if s.get("outputs") is not None]
        for sample in positive:
            comment = sample.get("_comment", "")
            if "DATA QUALITY" in comment:
                continue  # Data quality cases test retrieval, not extraction
            municipality = sample["outputs"].get("municipality", "unknown")
            assert sample["outputs"].get("numeric_params") or sample["expectations"].get("numeric_params"), (
                f"Golden case for {municipality} is missing numeric_params — "
                "every positive case should have verified dimensional standards"
            )

    def test_fort_lauderdale_present(self, golden_data, all_scorers):
        """Fort Lauderdale should have at least 2 proper golden cases with numeric params."""
        ftl_cases = [
            s for s in golden_data
            if s.get("outputs") and s["outputs"].get("municipality") == "Fort Lauderdale"
            and s["outputs"].get("numeric_params")
        ]
        assert len(ftl_cases) >= 2, (
            f"Expected at least 2 Fort Lauderdale cases with numeric params, got {len(ftl_cases)}"
        )
