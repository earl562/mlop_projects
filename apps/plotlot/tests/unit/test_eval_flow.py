"""Tests for the eval quality check flow."""

from pathlib import Path

import pytest

from plotlot.pipeline.eval_flow import (
    build_eval_run_manifest,
    check_thresholds,
    select_eval_samples,
)


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


class TestSelectEvalSamples:
    def test_respects_max_samples(self):
        data = [{"id": 1}, {"id": 2}, {"id": 3}]
        assert select_eval_samples(data, max_samples=2) == [{"id": 1}, {"id": 2}]

    def test_invalid_budget_raises(self):
        with pytest.raises(ValueError, match="max_samples"):
            select_eval_samples([{"id": 1}], max_samples=0)


class TestBuildEvalRunManifest:
    def test_includes_versioning_rewards_and_observations(self):
        manifest = build_eval_run_manifest(
            tag="pr-123",
            dataset_path=Path("tests/eval/golden_data.json"),
            sample_count=5,
            thresholds={"report_completeness/mean": 0.7},
            prompt_versions={"analysis": "v2", "chat_agent": "v2"},
            metrics={"report_completeness/mean": 0.81, "municipality_match/mean": 0.9},
            max_samples=5,
            git_commit="abc1234",
            passed=True,
        )

        assert manifest["protocol"] == "vero-inspired-v1"
        assert manifest["target_workflow"] == "plotlot-site-feasibility"
        assert manifest["versioning"]["git_commit"] == "abc1234"
        assert manifest["versioning"]["prompt_versions"]["analysis"] == "v2"
        assert manifest["budget"] == {"max_samples": 5, "evaluated_samples": 5}
        assert manifest["rewards"]["status"] == "passed"
        assert manifest["rewards"]["thresholds"]["report_completeness/mean"] == 0.7
        assert manifest["observations"]["metric_keys"] == [
            "municipality_match/mean",
            "report_completeness/mean",
        ]
