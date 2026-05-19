"""Tests for cache quality gate — _should_cache()."""

from plotlot.api.cache import _should_cache


class TestShouldCache:
    def test_good_report_cached(self):
        report = {
            "zoning_district": "RS-4",
            "confidence": "high",
            "numeric_params": {"max_height_ft": 35},
        }
        assert _should_cache(report) is True

    def test_medium_confidence_cached(self):
        report = {
            "zoning_district": "RS-4",
            "confidence": "medium",
            "numeric_params": {"max_height_ft": 35},
        }
        assert _should_cache(report) is True

    def test_low_confidence_rejected(self):
        report = {
            "zoning_district": "RS-4",
            "confidence": "low",
            "numeric_params": {"max_height_ft": 35},
        }
        assert _should_cache(report) is False

    def test_missing_district_rejected(self):
        report = {
            "zoning_district": "",
            "confidence": "high",
            "numeric_params": {"max_height_ft": 35},
        }
        assert _should_cache(report) is False

    def test_none_district_rejected(self):
        report = {
            "zoning_district": None,
            "confidence": "high",
            "numeric_params": {"max_height_ft": 35},
        }
        assert _should_cache(report) is False

    def test_no_district_key_rejected(self):
        report = {
            "confidence": "high",
            "numeric_params": {"max_height_ft": 35},
        }
        assert _should_cache(report) is False

    def test_none_numeric_params_rejected(self):
        report = {
            "zoning_district": "RS-4",
            "confidence": "high",
            "numeric_params": None,
        }
        assert _should_cache(report) is False

    def test_missing_numeric_params_rejected(self):
        report = {
            "zoning_district": "RS-4",
            "confidence": "high",
        }
        assert _should_cache(report) is False

    def test_empty_report_rejected(self):
        assert _should_cache({}) is False

    def test_all_bad_signals_rejected(self):
        report = {
            "zoning_district": "",
            "confidence": "low",
            "numeric_params": None,
        }
        assert _should_cache(report) is False
