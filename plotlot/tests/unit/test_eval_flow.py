"""Tests for the eval quality check flow."""

from plotlot.pipeline.eval_flow import check_thresholds


class TestCheckThresholds:
    def test_all_pass(self):
        """All metrics above thresholds → True."""
        metrics = {"accuracy/mean": 0.9, "completeness/mean": 0.8}
        thresholds = {"accuracy/mean": 0.5, "completeness/mean": 0.6}
        assert check_thresholds(metrics, thresholds) is True

    def test_one_fails(self):
        """One metric below threshold → False."""
        metrics = {"accuracy/mean": 0.3, "completeness/mean": 0.8}
        thresholds = {"accuracy/mean": 0.5, "completeness/mean": 0.6}
        assert check_thresholds(metrics, thresholds) is False

    def test_missing_metric_still_passes(self):
        """Missing metric in results doesn't cause failure."""
        metrics = {"completeness/mean": 0.8}
        thresholds = {"accuracy/mean": 0.5, "completeness/mean": 0.6}
        assert check_thresholds(metrics, thresholds) is True

    def test_empty_thresholds(self):
        """No thresholds → always passes."""
        assert check_thresholds({"a": 0.1}, {}) is True
