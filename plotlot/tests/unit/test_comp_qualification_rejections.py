import pytest

from plotlot.comps import CompPolicy, CompSubject, SaleEvidence, qualify_comps


def _subject() -> CompSubject:
    return CompSubject(
        parcel_id="0000012345",
        state="FL",
        county="Miami-Dade",
        latitude=25.76,
        longitude=-80.19,
        lot_size_sqft=10_000,
        property_type="land",
        category="land",
        zoning_code="T5",
        neighborhood="Brickell",
        waterfront=False,
    )


def _candidate(index: int) -> SaleEvidence:
    return SaleEvidence(
        evidence_id=f"sale-{index}",
        parcel_id=f"00000900{index}",
        state="FL",
        county="Miami-Dade",
        sale_price=200_000,
        sale_date="2026-04-15",
        date_precision="day",
        latitude=25.7601 + index / 100_000,
        longitude=-80.19,
        lot_size_sqft=10_000,
        property_type="land",
        category="land",
        classification_basis="county qualified vacant sale code 01",
        transaction_status="closed",
        qualification="qualified",
        qualification_code="01",
        source_kind="county",
        source_url="https://county.example/sales",
        source_record_id=f"record-{index}",
        recorded_document=f"book-1/page-{index}",
        zoning_code="T5",
        neighborhood="Brickell",
        waterfront=False,
    )


@pytest.mark.parametrize(
    ("candidate", "expected_reason"),
    [
        (_candidate(1).model_copy(update={"parcel_id": ""}), "missing_parcel_id"),
        (_candidate(1).model_copy(update={"parcel_id": "   "}), "missing_parcel_id"),
        (
            _candidate(1).model_copy(update={"parcel_id": "123-45"}),
            "subject_transaction",
        ),
        (_candidate(1).model_copy(update={"sale_price": 0}), "invalid_sale_price"),
        (_candidate(1).model_copy(update={"sale_date": ""}), "missing_sale_date"),
        (_candidate(1).model_copy(update={"sale_date": "2026-99-40"}), "invalid_sale_date"),
        (
            _candidate(1).model_copy(update={"sale_date": "2026-04", "date_precision": "day"}),
            "invalid_sale_date",
        ),
        (
            _candidate(1).model_copy(update={"date_precision": "unknown"}),
            "unknown_date_precision",
        ),
        (_candidate(1).model_copy(update={"sale_date": "2027-01-01"}), "future_sale_date"),
        (
            _candidate(1).model_copy(update={"sale_date": "2025-08", "date_precision": "month"}),
            "outside_date_window",
        ),
        (
            _candidate(1).model_copy(update={"sale_date": "2025-09", "date_precision": "month"}),
            "date_range_straddles_cutoff",
        ),
        (
            _candidate(1).model_copy(update={"sale_date": "2026-09", "date_precision": "month"}),
            "date_range_straddles_as_of",
        ),
        (
            _candidate(1).model_copy(update={"transaction_status": "pending"}),
            "transaction_not_closed",
        ),
        (
            _candidate(1).model_copy(update={"qualification": "disqualified"}),
            "qualification_not_qualified",
        ),
        (
            _candidate(1).model_copy(update={"multi_parcel": True}),
            "multi_parcel_transaction",
        ),
        (
            _candidate(1).model_copy(update={"property_changed": True}),
            "property_changed_since_sale",
        ),
        (
            _candidate(1).model_copy(update={"conflict_flags": ("stale_image",)}),
            "evidence_conflict",
        ),
        (_candidate(1).model_copy(update={"latitude": None}), "missing_coordinates"),
        (_candidate(1).model_copy(update={"longitude": -80.30}), "outside_radius"),
        (_candidate(1).model_copy(update={"state": "CA"}), "jurisdiction_mismatch"),
        (_candidate(1).model_copy(update={"category": "resale"}), "category_mismatch"),
        (
            _candidate(1).model_copy(update={"property_type": "single_family"}),
            "property_type_mismatch",
        ),
        (_candidate(1).model_copy(update={"lot_size_sqft": None}), "missing_lot_size"),
        (
            _candidate(1).model_copy(update={"lot_size_sqft": 20_000}),
            "size_outside_tolerance",
        ),
        (
            _candidate(1).model_copy(update={"source_kind": "listing"}),
            "unsupported_source_kind",
        ),
        (
            _candidate(1).model_copy(
                update={"source_kind": "user_reviewed", "qualification_code": ""}
            ),
            "missing_or_invalid_review_attestation",
        ),
        (_candidate(1).model_copy(update={"source_url": ""}), "missing_source_url"),
        (
            _candidate(1).model_copy(update={"qualification_code": ""}),
            "missing_qualification_code",
        ),
        (
            _candidate(1).model_copy(update={"source_record_id": "", "recorded_document": ""}),
            "missing_record_reference",
        ),
        (
            _candidate(1).model_copy(
                update={"source_record_id": "   ", "recorded_document": "   "}
            ),
            "missing_record_reference",
        ),
        (
            _candidate(1).model_copy(update={"classification_basis": ""}),
            "missing_classification_basis",
        ),
        (
            _candidate(1).model_copy(update={"classification_basis": "   "}),
            "missing_classification_basis",
        ),
        (_candidate(1).model_copy(update={"zoning_code": "T6"}), "zoning_mismatch"),
        (
            _candidate(1).model_copy(update={"neighborhood": "Wynwood"}),
            "neighborhood_mismatch",
        ),
        (_candidate(1).model_copy(update={"waterfront": True}), "waterfront_mismatch"),
    ],
)
def test_unreliable_land_evidence_is_rejected(
    candidate: SaleEvidence, expected_reason: str
) -> None:
    # Given one unreliable candidate and two otherwise qualifying sales
    candidates = (candidate, _candidate(2), _candidate(3))

    # When the qualification engine evaluates the set
    result = qualify_comps(_subject(), candidates, CompPolicy(as_of="2026-09-04"))

    # Then the unreliable candidate is excluded for the auditable reason
    assert (result.status, result.rejected[0].evidence_id, result.rejected[0].reasons) == (
        "insufficient_evidence",
        "sale-1",
        (expected_reason,),
    )


def test_explicit_gift_qualification_code_cannot_be_marked_as_qualified() -> None:
    # Given a county row that contradicts its qualified flag with an explicit gift code
    gift = _candidate(1).model_copy(
        update={
            "qualification_code": "gift",
            "classification_basis": "gift / non-arm-length transfer",
        }
    )

    # When the qualification engine evaluates it with two clean sales
    result = qualify_comps(
        _subject(), (gift, _candidate(2), _candidate(3)), CompPolicy(as_of="2026-09-04")
    )

    # Then the contradictory non-market transfer is excluded from comp values
    assert (
        result.status,
        result.rejected[0].evidence_id,
        result.rejected[0].reasons,
        result.value_median,
    ) == ("insufficient_evidence", "sale-1", ("non_market_transfer",), None)
