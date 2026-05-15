"""Offline eval tests for Charlotte NC metro golden data.

Validates golden data structure and readiness — no API calls, no network.
These are UNIT tests that ensure the NC golden dataset is well-formed and
ready for integration with the PlotLot eval framework.

Run:
    uv run pytest tests/eval/test_nc_eval.py -v
"""

import re

import pytest

from .nc_golden_data import NC_GOLDEN_CASES, NC_MUNICIPALITIES, REQUIRED_CASE_FIELDS


class TestNCGoldenDataStructure:
    """Validate that each NC golden case has the required schema."""

    def test_golden_cases_not_empty(self):
        """NC golden dataset should have at least 5 test cases."""
        assert len(NC_GOLDEN_CASES) >= 5, (
            f"Expected at least 5 NC golden cases, got {len(NC_GOLDEN_CASES)}"
        )

    @pytest.mark.parametrize(
        "case",
        NC_GOLDEN_CASES,
        ids=[c["address"] for c in NC_GOLDEN_CASES],
    )
    def test_required_fields_present(self, case):
        """Each golden case must have all required fields."""
        missing = REQUIRED_CASE_FIELDS - set(case.keys())
        assert not missing, f"Case {case.get('address', '?')} missing fields: {missing}"

    @pytest.mark.parametrize(
        "case",
        NC_GOLDEN_CASES,
        ids=[c["address"] for c in NC_GOLDEN_CASES],
    )
    def test_state_is_nc(self, case):
        """All NC golden cases must have state 'NC'."""
        assert case["state"] == "NC", (
            f"Case {case['address']} has state={case['state']!r}, expected 'NC'"
        )

    @pytest.mark.parametrize(
        "case",
        NC_GOLDEN_CASES,
        ids=[c["address"] for c in NC_GOLDEN_CASES],
    )
    def test_county_is_mecklenburg(self, case):
        """Charlotte metro golden cases should be in Mecklenburg County."""
        assert case["county"] == "Mecklenburg", (
            f"Case {case['address']} has county={case['county']!r}, expected 'Mecklenburg'"
        )

    @pytest.mark.parametrize(
        "case",
        NC_GOLDEN_CASES,
        ids=[c["address"] for c in NC_GOLDEN_CASES],
    )
    def test_municipality_in_nc_config(self, case):
        """Each case's municipality must be in the expected NC municipality set."""
        assert case["municipality"] in NC_MUNICIPALITIES, (
            f"Municipality {case['municipality']!r} not in NC config: {NC_MUNICIPALITIES}"
        )


class TestNCAddressFormat:
    """Validate address formatting for geocoding readiness."""

    # Pattern: street number + street name + city + state + zip
    _ADDRESS_RE = re.compile(r"^\d+\s+.+,\s+\w[\w\s]*,\s+NC\s+\d{5}$")

    @pytest.mark.parametrize(
        "case",
        NC_GOLDEN_CASES,
        ids=[c["address"] for c in NC_GOLDEN_CASES],
    )
    def test_address_format_valid(self, case):
        """Address should match 'NUMBER STREET, CITY, NC ZIPCODE' pattern."""
        assert self._ADDRESS_RE.match(case["address"]), (
            f"Address {case['address']!r} does not match expected format "
            "'<number> <street>, <city>, NC <zip>'"
        )

    @pytest.mark.parametrize(
        "case",
        NC_GOLDEN_CASES,
        ids=[c["address"] for c in NC_GOLDEN_CASES],
    )
    def test_address_contains_municipality(self, case):
        """Address city portion should contain the case municipality."""
        # Extract city from address (between last two commas before state)
        parts = case["address"].split(",")
        assert len(parts) >= 3, f"Address {case['address']!r} has unexpected format"
        city_part = parts[-2].strip()
        assert case["municipality"] in city_part, (
            f"Municipality {case['municipality']!r} not found in address city portion {city_part!r}"
        )


class TestNCMunicipalityDiversity:
    """Validate that golden data covers the required municipality spread."""

    def test_covers_all_nc_municipalities(self):
        """Golden data should cover all expected Charlotte metro municipalities."""
        covered = {case["municipality"] for case in NC_GOLDEN_CASES}
        missing = NC_MUNICIPALITIES - covered
        assert not missing, f"NC golden data missing municipalities: {missing}"

    def test_at_least_five_distinct_municipalities(self):
        """Golden data should span at least 5 distinct municipalities."""
        municipalities = {case["municipality"] for case in NC_GOLDEN_CASES}
        assert len(municipalities) >= 5, (
            f"Expected at least 5 municipalities, got {len(municipalities)}: {municipalities}"
        )

    def test_charlotte_included(self):
        """Charlotte (city proper) must be in the golden dataset."""
        charlotte_cases = [c for c in NC_GOLDEN_CASES if c["municipality"] == "Charlotte"]
        assert len(charlotte_cases) >= 1, "No Charlotte cases in NC golden data"


class TestNCExpectedFields:
    """Validate expected_fields and expected_zone_prefix consistency."""

    @pytest.mark.parametrize(
        "case",
        NC_GOLDEN_CASES,
        ids=[c["address"] for c in NC_GOLDEN_CASES],
    )
    def test_expected_fields_is_list(self, case):
        """expected_fields must be a list."""
        assert isinstance(case["expected_fields"], list), (
            f"Case {case['address']}: expected_fields should be a list, "
            f"got {type(case['expected_fields']).__name__}"
        )

    @pytest.mark.parametrize(
        "case",
        NC_GOLDEN_CASES,
        ids=[c["address"] for c in NC_GOLDEN_CASES],
    )
    def test_expected_zone_prefix_is_string(self, case):
        """expected_zone_prefix must be a string."""
        assert isinstance(case["expected_zone_prefix"], str), (
            f"Case {case['address']}: expected_zone_prefix should be a string, "
            f"got {type(case['expected_zone_prefix']).__name__}"
        )

    def test_at_least_one_case_has_zone_prefix(self):
        """At least one NC golden case should have a non-empty zone prefix."""
        prefixed = [c for c in NC_GOLDEN_CASES if c["expected_zone_prefix"]]
        assert len(prefixed) >= 1, "No NC golden cases have expected_zone_prefix set"

    def test_at_least_one_case_has_expected_fields(self):
        """At least one NC golden case should have expected extraction fields."""
        with_fields = [c for c in NC_GOLDEN_CASES if c["expected_fields"]]
        assert len(with_fields) >= 1, "No NC golden cases have expected_fields"

    def test_valid_expected_field_names(self):
        """All expected_fields values should be recognized field names."""
        valid_fields = {
            "max_height",
            "setbacks",
            "max_density",
            "min_lot_area",
            "max_lot_coverage",
            "far",
            "max_stories",
            "min_unit_size",
            "parking",
            "min_lot_width",
        }
        for case in NC_GOLDEN_CASES:
            for field in case["expected_fields"]:
                assert field in valid_fields, (
                    f"Case {case['address']}: unknown expected_field {field!r}. "
                    f"Valid: {valid_fields}"
                )
