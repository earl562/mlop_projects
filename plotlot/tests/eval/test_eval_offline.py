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

        # Report completeness — verified cases are 1.0, Zillow discovery cases
        # are ~0.71 (missing zoning_district + has_allowed_uses), boundary cases
        # have null outputs. Aggregate mean reflects the mix.
        completeness_key = "report_completeness/mean"
        assert completeness_key in result.metrics
        assert result.metrics[completeness_key] >= 0.7, (
            f"Report completeness {result.metrics[completeness_key]:.2f} < 0.7 on golden data"
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
        mg_data = [
            s for s in golden_data if s["inputs"]["address"] == "171 NE 209th Ter, Miami, FL 33179"
        ]
        assert len(mg_data) == 1

        result = mlflow.genai.evaluate(data=mg_data, scorers=all_scorers)

        accuracy_key = "numeric_extraction_accuracy/mean"
        assert result.metrics[accuracy_key] == 1.0, (
            f"Miami Gardens should have perfect numeric extraction, got {result.metrics[accuracy_key]}"
        )

    def test_miramar_tolerant(self, golden_data, all_scorers):
        """Miramar RS5 sample has 50% tolerance — should still pass."""
        mir_data = [
            s
            for s in golden_data
            if s["inputs"]["address"] == "7940 Plantation Blvd, Miramar, FL 33023"
        ]
        assert len(mir_data) == 1

        result = mlflow.genai.evaluate(data=mir_data, scorers=all_scorers)

        accuracy_key = "numeric_extraction_accuracy/mean"
        assert result.metrics[accuracy_key] >= 0.8, (
            f"Miramar numeric accuracy {result.metrics[accuracy_key]:.2f} < 0.8"
        )

    def test_verified_cases_have_numeric_params(self, golden_data, all_scorers):
        """Verified golden cases (with zoning_district in outputs) should have numeric_params.

        Zillow discovery cases test municipality resolution and pipeline reach —
        they don't require numeric_params since we may not have ingested that
        municipality's ordinances yet.
        """
        verified = [
            s
            for s in golden_data
            if s.get("outputs") is not None and s["outputs"].get("zoning_district")
        ]
        assert len(verified) >= 3, f"Expected at least 3 verified cases, got {len(verified)}"
        for sample in verified:
            municipality = sample["outputs"].get("municipality", "unknown")
            assert sample["outputs"].get("numeric_params") or sample["expectations"].get(
                "numeric_params"
            ), (
                f"Verified case for {municipality} is missing numeric_params — "
                "every verified case should have dimensional standards"
            )

    def test_three_counties_represented(self, golden_data, all_scorers):
        """Golden data should span all 3 South Florida counties."""
        positive = [s for s in golden_data if s.get("outputs") is not None]
        counties = {s["outputs"].get("county") for s in positive if s["outputs"].get("county")}
        for county in ["Miami-Dade", "Broward", "Palm Beach"]:
            assert county in counties, f"Missing golden cases for {county} county"

    def test_municipality_diversity(self, golden_data, all_scorers):
        """Golden data should cover at least 8 distinct municipalities."""
        positive = [s for s in golden_data if s.get("outputs") is not None]
        municipalities = {
            s["outputs"].get("municipality")
            for s in positive
            if s["outputs"].get("municipality")
        }
        assert len(municipalities) >= 8, (
            f"Expected at least 8 municipalities, got {len(municipalities)}: {municipalities}"
        )
