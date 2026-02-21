"""Unit tests for scorer edge cases.

These run without MLflow evaluation — they test the scorer functions directly
for boundary conditions and edge cases.

Run:
    uv run pytest tests/eval/test_eval_scorers.py -v
"""

import pytest

from tests.eval.scorers import (
    confidence_acceptable,
    max_units_match,
    numeric_extraction_accuracy,
    report_completeness,
    setback_accuracy,
    zoning_district_match,
)


class TestNumericExtractionEdgeCases:
    def test_all_params_missing(self):
        """All expected params missing → score 0.0."""
        result = numeric_extraction_accuracy(
            outputs={"numeric_params": {}},
            expectations={
                "numeric_params": {
                    "max_density_units_per_acre": 6.0,
                    "setback_front_ft": 25.0,
                },
            },
        )
        assert result.value == 0.0

    def test_zero_expected_zero_actual(self):
        """Expected=0, actual=0 → match."""
        result = numeric_extraction_accuracy(
            outputs={"numeric_params": {"some_param": 0}},
            expectations={
                "numeric_params": {"some_param": 0},
            },
        )
        assert result.value == 1.0
        assert "OK" in result.rationale

    def test_no_expected_params(self):
        """No expected params → perfect score (nothing to check)."""
        result = numeric_extraction_accuracy(
            outputs={"numeric_params": {"a": 1}},
            expectations={"numeric_params": {}},
        )
        assert result.value == 1.0


class TestReportCompletenessEdgeCases:
    def test_empty_outputs(self):
        """All empty → low score."""
        result = report_completeness(outputs={}, expectations={})
        assert result.value < 0.5

    def test_full_outputs(self):
        """All fields present → perfect score."""
        result = report_completeness(
            outputs={
                "zoning_district": "R-1",
                "municipality": "Miami Gardens",
                "county": "Miami-Dade",
                "confidence": "high",
                "has_summary": True,
                "has_allowed_uses": True,
                "num_sources": 15,
            },
            expectations={},
        )
        assert result.value == 1.0


class TestConfidenceOrdering:
    def test_high_meets_medium(self):
        assert confidence_acceptable(
            outputs={"confidence": "high"},
            expectations={"confidence_min": "medium"},
        ) is True

    def test_low_fails_medium(self):
        assert confidence_acceptable(
            outputs={"confidence": "low"},
            expectations={"confidence_min": "medium"},
        ) is False

    def test_medium_meets_medium(self):
        assert confidence_acceptable(
            outputs={"confidence": "medium"},
            expectations={"confidence_min": "medium"},
        ) is True


class TestZoningDistrictMatch:
    def test_case_insensitive(self):
        assert zoning_district_match(
            outputs={"zoning_district": "rs-4"},
            expectations={"zoning_district": "RS-4"},
        ) is True

    def test_whitespace_stripped(self):
        assert zoning_district_match(
            outputs={"zoning_district": " R-1 "},
            expectations={"zoning_district": "R-1"},
        ) is True


class TestSetbackAccuracy:
    def test_all_setbacks_match(self):
        """All setbacks within tolerance → perfect score."""
        result = setback_accuracy(
            outputs={"numeric_params": {
                "setback_front_ft": 25.0,
                "setback_side_ft": 7.5,
                "setback_rear_ft": 25.0,
            }},
            expectations={
                "numeric_params": {
                    "setback_front_ft": 25.0,
                    "setback_side_ft": 7.5,
                    "setback_rear_ft": 25.0,
                },
                "numeric_tolerance": 0.1,
            },
        )
        assert result.value == 1.0

    def test_partial_setback_match(self):
        """One setback missing → partial score."""
        result = setback_accuracy(
            outputs={"numeric_params": {
                "setback_front_ft": 25.0,
                "setback_side_ft": 7.5,
            }},
            expectations={
                "numeric_params": {
                    "setback_front_ft": 25.0,
                    "setback_side_ft": 7.5,
                    "setback_rear_ft": 25.0,
                },
                "numeric_tolerance": 0.1,
            },
        )
        assert 0.0 < result.value < 1.0
        assert "MISSING" in result.rationale

    def test_no_expected_setbacks(self):
        """No expected setbacks → perfect score (nothing to check)."""
        result = setback_accuracy(
            outputs={"numeric_params": {"max_height_ft": 35.0}},
            expectations={"numeric_params": {"max_height_ft": 35.0}},
        )
        assert result.value == 1.0
        assert "No expected setbacks" in result.rationale


class TestMaxUnitsMatch:
    def test_none_values(self):
        assert max_units_match(
            outputs={"max_units": None},
            expectations={"max_units": 1},
        ) is False

    def test_both_none(self):
        assert max_units_match(
            outputs={"max_units": None},
            expectations={"max_units": None},
        ) is False
