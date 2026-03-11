"""Tests for property_type auto-detection in _extract_numeric_params."""

from plotlot.pipeline.lookup import _extract_numeric_params


class TestPropertyTypeAutoDetect:
    def test_explicit_property_type_preserved(self):
        args = {
            "property_type": "commercial_mf",
            "zoning_district": "RS-4",
            "max_height_ft": "35",
        }
        params = _extract_numeric_params(args)
        assert params is not None
        assert params.property_type == "commercial_mf"

    def test_rs_prefix_single_family(self):
        args = {"zoning_district": "RS-4", "max_height_ft": "35"}
        params = _extract_numeric_params(args)
        assert params is not None
        assert params.property_type == "single_family"

    def test_re_prefix_single_family(self):
        args = {"zoning_district": "RE-1", "max_height_ft": "35"}
        params = _extract_numeric_params(args)
        assert params is not None
        assert params.property_type == "single_family"

    def test_r_prefix_single_family(self):
        args = {"zoning_district": "R-2", "max_height_ft": "35"}
        params = _extract_numeric_params(args)
        assert params is not None
        assert params.property_type == "single_family"

    def test_rm_prefix_multifamily(self):
        args = {"zoning_district": "RM-16", "max_height_ft": "45"}
        params = _extract_numeric_params(args)
        assert params is not None
        assert params.property_type == "multifamily"

    def test_rm_high_density_commercial_mf(self):
        args = {
            "zoning_district": "RM-50",
            "max_density_units_per_acre": "25",
            "max_height_ft": "100",
        }
        params = _extract_numeric_params(args)
        assert params is not None
        assert params.property_type == "commercial_mf"

    def test_rd_prefix_multifamily(self):
        args = {"zoning_district": "RD-3", "max_height_ft": "35"}
        params = _extract_numeric_params(args)
        assert params is not None
        assert params.property_type == "multifamily"

    def test_mf_prefix_multifamily(self):
        args = {"zoning_district": "MF-2", "max_height_ft": "45"}
        params = _extract_numeric_params(args)
        assert params is not None
        assert params.property_type == "multifamily"

    def test_c_prefix_commercial(self):
        args = {"zoning_district": "C-1", "max_height_ft": "60"}
        params = _extract_numeric_params(args)
        assert params is not None
        assert params.property_type == "commercial"

    def test_b_prefix_commercial(self):
        args = {"zoning_district": "B-2", "max_height_ft": "50"}
        params = _extract_numeric_params(args)
        assert params is not None
        assert params.property_type == "commercial"

    def test_mu_prefix_commercial(self):
        args = {"zoning_district": "MU-1A", "max_height_ft": "75"}
        params = _extract_numeric_params(args)
        assert params is not None
        assert params.property_type == "commercial_mf"

    def test_unknown_district_no_type(self):
        args = {"zoning_district": "PU-1", "max_height_ft": "35"}
        params = _extract_numeric_params(args)
        assert params is not None
        assert params.property_type is None

    def test_empty_district_no_type(self):
        args = {"zoning_district": "", "max_height_ft": "35"}
        params = _extract_numeric_params(args)
        assert params is not None
        assert params.property_type is None

    def test_case_insensitive(self):
        args = {"zoning_district": "rs-8", "max_height_ft": "35"}
        params = _extract_numeric_params(args)
        assert params is not None
        assert params.property_type == "single_family"

    def test_no_params_returns_none(self):
        args = {}
        params = _extract_numeric_params(args)
        assert params is None
