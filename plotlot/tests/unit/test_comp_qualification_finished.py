from typing import Literal

from plotlot.comps import CompPolicy, CompSubject, SaleEvidence, qualify_comps

FinishedCategory = Literal["resale", "new_construction"]


def _subject(category: FinishedCategory) -> CompSubject:
    return CompSubject(
        parcel_id="0000012345",
        state="FL",
        county="Miami-Dade",
        latitude=25.76,
        longitude=-80.19,
        building_area_sqft=10_000,
        property_type="multifamily",
        category=category,
    )


def _candidate(index: int, category: FinishedCategory) -> SaleEvidence:
    return SaleEvidence(
        evidence_id=f"finished-{index}",
        parcel_id=f"00000800{index}",
        state="FL",
        county="Miami-Dade",
        sale_price=(index + 1) * 400_000,
        sale_date="2026-05-15",
        date_precision="day",
        latitude=25.7601 + index / 100_000,
        longitude=-80.19,
        building_area_sqft=10_000,
        units=index + 1,
        property_type="multifamily",
        category=category,
        classification_basis="county qualified improved sale code 01",
        transaction_status="closed",
        qualification="qualified",
        qualification_code="01",
        source_kind="county",
        source_url="https://county.example/sales",
        source_record_id=f"finished-record-{index}",
        recorded_document=f"book-2/page-{index}",
        construction_completed_date="2026-04-01" if category == "new_construction" else "",
        completion_source="https://county.example/co/123" if category == "new_construction" else "",
    )


def test_finished_sales_produce_price_per_unit_only_with_explicit_units() -> None:
    # Given three comparable resale properties with explicit finished area and units
    candidates = tuple(_candidate(index, "resale") for index in range(1, 4))

    # When the finished category is qualified
    result = qualify_comps(_subject("resale"), candidates, CompPolicy(as_of="2026-09-04"))

    # Then valuation uses observed price per unit without inferring a unit count
    assert (
        result.status,
        result.value_low,
        result.value_median,
        result.value_high,
        result.value_basis,
    ) == ("qualified", 400_000.0, 400_000.0, 400_000.0, "price_per_unit")


def test_missing_candidate_units_blocks_finished_valuation() -> None:
    # Given one finished candidate without an explicit unit count
    candidates = (
        _candidate(1, "resale").model_copy(update={"units": None}),
        _candidate(2, "resale"),
        _candidate(3, "resale"),
    )

    # When the finished category is qualified
    result = qualify_comps(_subject("resale"), candidates, CompPolicy(as_of="2026-09-04"))

    # Then the candidate is rejected and the insufficient result has null values
    assert (
        result.status,
        result.rejected[0].reasons,
        result.value_low,
        result.value_median,
        result.value_high,
    ) == ("insufficient_evidence", ("missing_units",), None, None, None)


def test_new_construction_requires_completion_before_sale() -> None:
    # Given one purported new build completed after its sale and two completed before sale
    candidates = (
        _candidate(1, "new_construction").model_copy(
            update={"construction_completed_date": "2026-06-01"}
        ),
        _candidate(2, "new_construction"),
        _candidate(3, "new_construction"),
    )

    # When new-construction evidence is qualified
    result = qualify_comps(_subject("new_construction"), candidates, CompPolicy(as_of="2026-09-04"))

    # Then post-sale completion evidence is excluded and cannot support a value
    assert (
        result.status,
        result.rejected[0].reasons,
        result.value_median,
    ) == ("insufficient_evidence", ("construction_not_completed_before_sale",), None)


def test_new_construction_requires_a_canonical_completion_day() -> None:
    # Given one new-build candidate whose completion date omits ISO separators
    candidates = (
        _candidate(1, "new_construction").model_copy(
            update={"construction_completed_date": "20260401"}
        ),
        _candidate(2, "new_construction"),
        _candidate(3, "new_construction"),
    )

    # When new-construction evidence is qualified
    result = qualify_comps(_subject("new_construction"), candidates, CompPolicy(as_of="2026-09-04"))

    # Then the imprecise completion claim cannot support a completed sale category
    assert (result.status, result.rejected[0].reasons, result.value_median) == (
        "insufficient_evidence",
        ("invalid_construction_completion_date",),
        None,
    )
