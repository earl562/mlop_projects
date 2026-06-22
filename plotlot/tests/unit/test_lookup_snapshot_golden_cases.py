from __future__ import annotations

from plotlot.pipeline.lookup_snapshot_golden_cases import (
    lookup_snapshot_golden_case_by_address,
    lookup_snapshot_golden_case_by_id,
)


def test_lookup_snapshot_golden_case_loader_maps_verified_fixture_fields() -> None:
    # Given: an address that exists in the hand-verified South Florida fixture corpus.
    address = "171 NE 209th Ter, Miami, FL 33179"

    # When: the lookup-correctness fixture is resolved by address.
    case = lookup_snapshot_golden_case_by_address(address)

    # Then: the fixture is converted into expected lookup snapshot fields.
    assert case is not None
    expected = {field.key: field.value for field in case.expected_fields}
    assert expected["jurisdiction.municipality"] == "Miami Gardens"
    assert expected["jurisdiction.county"] == "Miami-Dade"
    assert expected["zoning.district"] == "R-1"
    assert expected["calc.max_units"] == 1
    assert expected["calc.governing_constraint"] == "density"
    assert case.required_calculations == ("max_units",)
    assert lookup_snapshot_golden_case_by_id(case.case_id) == case
