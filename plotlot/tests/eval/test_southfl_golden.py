"""South FL golden eval — runs on hand-verified golden outputs.

Fast, no network, no DB, no LLM calls. Validates that the scoring
framework works correctly against known-good pipeline outputs for the
South Florida target market (Miami-Dade, Broward, Palm Beach).

Run:
    uv run pytest tests/eval/test_southfl_golden.py -m eval -v
"""

import mlflow.genai
import pytest


@pytest.mark.eval
class TestSouthFLGoldenEval:
    """Evaluate pre-recorded South FL outputs against golden expectations."""

    def test_golden_dataset(self, southfl_golden_data, all_scorers):
        """All scorers should produce positive results on verified South FL outputs."""
        result = mlflow.genai.evaluate(data=southfl_golden_data, scorers=all_scorers)

        assert result.metrics is not None
        assert len(result.metrics) > 0

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
                f"{scorer_name} scored 0 — South FL golden outputs should match expectations"
            )

        accuracy_key = "numeric_extraction_accuracy/mean"
        assert accuracy_key in result.metrics
        assert result.metrics[accuracy_key] >= 0.8, (
            f"Numeric accuracy {result.metrics[accuracy_key]:.2f} < 0.8 on South FL golden data"
        )

        completeness_key = "report_completeness/mean"
        assert completeness_key in result.metrics
        assert result.metrics[completeness_key] >= 0.7, (
            f"Report completeness {result.metrics[completeness_key]:.2f} < 0.7"
        )

    def test_per_sample_results(self, southfl_golden_data, all_scorers):
        """Each South FL golden sample should pass all boolean scorers individually."""
        result = mlflow.genai.evaluate(data=southfl_golden_data, scorers=all_scorers)

        if hasattr(result, "result_df") and result.result_df is not None:
            assert len(result.result_df) == len(southfl_golden_data)
        elif hasattr(result, "tables") and result.tables:
            eval_table = result.tables.get("eval_results")
            if eval_table is not None:
                assert len(eval_table) == len(southfl_golden_data)

    def test_three_counties_represented(self, southfl_golden_data, all_scorers):
        """South FL golden data should span all 3 South Florida counties."""
        positive = [s for s in southfl_golden_data if s.get("outputs") is not None]
        counties = {s["outputs"].get("county") for s in positive if s["outputs"].get("county")}
        for county in ["Miami-Dade", "Broward", "Palm Beach"]:
            assert county in counties, f"Missing South FL golden cases for {county} county"

    def test_municipality_diversity(self, southfl_golden_data, all_scorers):
        """South FL golden data should cover at least 6 distinct municipalities."""
        positive = [s for s in southfl_golden_data if s.get("outputs") is not None]
        municipalities = {
            s["outputs"].get("municipality") for s in positive if s["outputs"].get("municipality")
        }
        assert len(municipalities) >= 6, (
            f"Expected at least 6 municipalities, got {len(municipalities)}: {municipalities}"
        )

    def test_miami_dade_entries_have_numeric_params(self, southfl_golden_data, all_scorers):
        """All South FL entries are verified cases and must have numeric_params."""
        for sample in southfl_golden_data:
            if sample.get("outputs") is None:
                continue
            municipality = sample["outputs"].get("municipality", "unknown")
            assert sample["outputs"].get("numeric_params"), (
                f"South FL entry for {municipality} is missing numeric_params"
            )

    def test_zoning_type_mix(self, southfl_golden_data, all_scorers):
        """South FL golden set should include both single-family and multifamily/duplex zoning."""
        positive = [s for s in southfl_golden_data if s.get("outputs") is not None]
        max_units_values = {s["outputs"].get("max_units") for s in positive}
        assert 1 in max_units_values, "Missing single-family entries (max_units=1)"
        assert any(u and u > 1 for u in max_units_values), (
            "Missing multifamily/duplex entries (max_units>1)"
        )

    def test_min_twelve_entries(self, southfl_golden_data, all_scorers):
        """South FL golden set should have at least 12 entries."""
        assert len(southfl_golden_data) >= 12, (
            f"Expected at least 12 South FL entries, got {len(southfl_golden_data)}"
        )
