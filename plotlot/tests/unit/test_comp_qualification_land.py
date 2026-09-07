import json
from dataclasses import asdict

from plotlot.comps import CompPolicy, CompSubject, SaleEvidence, qualify_comps


def _subject() -> CompSubject:
    return CompSubject(
        parcel_id="0000012345",
        state="FL",
        county="Miami-Dade",
        address="100 Subject St",
        latitude=25.7600,
        longitude=-80.1900,
        lot_size_sqft=43_560,
        property_type="land",
        category="land",
        zoning_code="T5",
        neighborhood="Brickell",
        waterfront=False,
    )


def _land_evidence(index: int, price: float, latitude: float) -> SaleEvidence:
    return SaleEvidence(
        evidence_id=f"sale-{index}",
        parcel_id=f"00000900{index}",
        state="FL",
        county="Miami-Dade",
        address=f"{index} Comp St",
        sale_price=price,
        sale_date="2026-04-15",
        date_precision="day",
        latitude=latitude,
        longitude=-80.1900,
        lot_size_sqft=43_560,
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


def test_land_result_is_qualified_when_three_recent_comparable_sales_exist() -> None:
    # Given three verified one-acre land sales near the one-acre subject
    candidates = tuple(
        _land_evidence(index, price, 25.7600 + index / 10_000)
        for index, price in enumerate((100_000.0, 200_000.0, 300_000.0), start=1)
    )
    policy = CompPolicy(as_of="2026-09-04")

    # When the public qualification engine evaluates the category
    result = qualify_comps(_subject(), candidates, policy)

    # Then it returns a comp-backed price-per-acre range
    assert (
        result.status,
        len(result.accepted),
        result.value_low,
        result.value_median,
        result.value_high,
        result.value_basis,
    ) == ("qualified", 3, 150_000.0, 200_000.0, 250_000.0, "price_per_acre")


def test_review_after_as_of_preserves_repeatable_sale_evaluation() -> None:
    # Given user-reviewed evidence attested one day after the frozen sale-evaluation date
    candidates = tuple(
        _land_evidence(index, 200_000, 25.7600 + index / 10_000).model_copy(
            update={
                "source_kind": "user_reviewed",
                "source_url": "",
                "qualification_code": "",
                "reviewed_by": "analyst@example.com",
                "reviewed_at": "2026-09-05T01:00:00+00:00",
            }
        )
        for index in range(1, 4)
    )

    # When the historical as-of policy evaluates sale facts separately from audit timing
    result = qualify_comps(_subject(), candidates, CompPolicy(as_of="2026-09-04"))

    # Then valid later attestations remain eligible
    assert (result.status, len(result.accepted), result.rejected) == ("qualified", 3, ())


def test_repeat_transfers_of_one_parcel_count_as_one_comparable_property() -> None:
    # Given three distinct qualified transfers of the same non-subject parcel
    candidates = tuple(
        _land_evidence(index, 100_000 + index * 10_000, 25.7601).model_copy(
            update={
                "parcel_id": "0000099999",
                "sale_date": f"2026-0{index + 1}-15",
                "source_record_id": f"transfer-{index}",
                "recorded_document": f"book-{index}/page-1",
            }
        )
        for index in range(1, 4)
    )

    # When the qualification engine applies the independent-property minimum
    result = qualify_comps(_subject(), candidates, CompPolicy(as_of="2026-09-04"))

    # Then only the latest transfer represents the parcel and no valuation is produced
    assert (
        result.status,
        tuple(decision.evidence_id for decision in result.accepted),
        tuple(decision.reasons for decision in result.rejected),
        result.value_median,
    ) == ("insufficient_evidence", ("sale-3",), (("not_selected",), ("not_selected",)), None)


def test_conflicting_transaction_duplicates_block_every_conflicting_candidate() -> None:
    # Given two rows for one recorded transaction that disagree on price
    original = _land_evidence(1, 100_000, 25.7601)
    conflict = original.model_copy(update={"evidence_id": "sale-1-conflict", "sale_price": 900_000})
    candidates = (
        original,
        conflict,
        _land_evidence(2, 200_000, 25.7602),
        _land_evidence(3, 300_000, 25.7603),
    )

    # When transaction evidence is reconciled before comp selection
    result = qualify_comps(_subject(), candidates, CompPolicy(as_of="2026-09-04"))

    # Then neither conflicting row can become a comp value
    assert (
        result.status,
        tuple(decision.evidence_id for decision in result.accepted),
        tuple((decision.evidence_id, decision.reasons) for decision in result.rejected),
        result.value_median,
    ) == (
        "insufficient_evidence",
        ("sale-2", "sale-3"),
        (
            ("sale-1", ("conflicting_transaction_evidence",)),
            ("sale-1-conflict", ("conflicting_transaction_evidence",)),
        ),
        None,
    )


def test_exact_transaction_duplicates_count_once() -> None:
    # Given two matching evidence rows for the same recorded transaction
    original = _land_evidence(1, 100_000, 25.7601)
    duplicate = original.model_copy(update={"evidence_id": "sale-1-copy"})
    candidates = (
        duplicate,
        original,
        _land_evidence(2, 200_000, 25.7602),
        _land_evidence(3, 300_000, 25.7603),
    )

    # When transaction evidence is reconciled before comp selection
    result = qualify_comps(_subject(), candidates, CompPolicy(as_of="2026-09-04"))

    # Then a deterministic representative counts once and the duplicate remains auditable
    assert (
        result.status,
        tuple(decision.evidence_id for decision in result.accepted),
        tuple((decision.evidence_id, decision.reasons) for decision in result.rejected),
    ) == (
        "qualified",
        ("sale-1", "sale-2", "sale-3"),
        (("sale-1-copy", ("duplicate_transaction",)),),
    )


def test_duplicate_evidence_ids_cannot_bypass_max_selection() -> None:
    # Given two distinct parcels reuse one ambiguous evidence identifier
    candidates = tuple(
        _land_evidence(index, 100_000 + index * 10_000, 25.7600 + index / 10_000)
        for index in range(1, 7)
    )
    candidates = (
        candidates[0].model_copy(update={"evidence_id": "shared-id"}),
        *candidates[1:5],
        candidates[5].model_copy(update={"evidence_id": "shared-id"}),
    )

    # When qualification applies a three-comp selection limit
    result = qualify_comps(_subject(), candidates, CompPolicy(as_of="2026-09-04", max_comps=3))

    # Then both ambiguous identifiers are rejected and exactly three unique sales are selected
    assert (
        len(result.accepted),
        tuple(
            decision.evidence_id
            for decision in result.rejected
            if decision.evidence_id == "shared-id"
        ),
        tuple(
            decision.reasons for decision in result.rejected if decision.evidence_id == "shared-id"
        ),
    ) == (3, ("shared-id", "shared-id"), (("duplicate_evidence_id",),) * 2)


def test_non_finite_derived_price_is_rejected_before_result_serialization() -> None:
    # Given finite input numbers whose price-per-acre division would overflow
    subject = _subject().model_copy(update={"lot_size_sqft": 5e-324})
    candidates = (
        _land_evidence(1, 1e308, 25.7601).model_copy(update={"lot_size_sqft": 5e-324}),
        _land_evidence(2, 5e-324, 25.7602).model_copy(update={"lot_size_sqft": 5e-324}),
        _land_evidence(3, 1e-323, 25.7603).model_copy(update={"lot_size_sqft": 5e-324}),
    )

    # When qualification derives normalized comp values
    result = qualify_comps(subject, candidates, CompPolicy(as_of="2026-09-04"))

    # Then the overflowing candidate is rejected and insufficient values remain null
    assert (
        result.status,
        result.rejected[0].reasons,
        result.value_low,
        result.value_median,
        result.value_high,
    ) == ("insufficient_evidence", ("non_finite_derived_value",), None, None, None)


def test_complete_recent_month_is_eligible() -> None:
    # Given three sales reported at month precision wholly inside the policy window
    candidates = tuple(
        _land_evidence(index, 200_000, 25.7600 + index / 10_000).model_copy(
            update={"sale_date": "2025-10", "date_precision": "month"}
        )
        for index in range(1, 4)
    )

    # When the qualification engine evaluates their complete date ranges
    result = qualify_comps(_subject(), candidates, CompPolicy(as_of="2026-09-04"))

    # Then month-precision evidence is eligible without inventing a day
    assert (result.status, len(result.accepted), result.rejected) == ("qualified", 3, ())


def test_selection_is_deterministic_for_reversed_input() -> None:
    # Given six qualifying candidates supplied farthest-first
    candidates = tuple(
        reversed(
            tuple(
                _land_evidence(index, index * 100_000, 25.7600 + index / 10_000)
                for index in range(1, 7)
            )
        )
    )

    # When the policy limits the result to three comparable properties
    result = qualify_comps(_subject(), candidates, CompPolicy(as_of="2026-09-04", max_comps=3))

    # Then the three nearest candidates are returned in stable distance order
    assert tuple(decision.evidence_id for decision in result.accepted) == (
        "sale-1",
        "sale-2",
        "sale-3",
    )


def test_full_result_is_strict_json_serializable() -> None:
    # Given a qualified result retaining evidence provenance and decisions
    result = qualify_comps(
        _subject(),
        tuple(
            _land_evidence(index, index * 100_000, 25.7600 + index / 10_000)
            for index in range(1, 4)
        ),
        CompPolicy(as_of="2026-09-04"),
    )

    # When the existing report serialization path converts the dataclass result
    serialized = json.dumps(asdict(result), allow_nan=False)

    # Then every retained value is JSON-safe and dates remain precision-preserving strings
    payload = json.loads(serialized)
    assert (
        payload["status"],
        payload["accepted"][0]["sale_date"],
        payload["accepted"][0]["date_precision"],
    ) == ("qualified", "2026-04-15", "day")


def test_land_subject_requires_explicit_land_property_type() -> None:
    # Given a land-category subject and candidates whose property type is unknown
    subject = _subject().model_copy(update={"property_type": "unknown"})
    candidates = tuple(
        _land_evidence(index, index * 100_000, 25.7600 + index / 10_000).model_copy(
            update={"property_type": "unknown"}
        )
        for index in range(1, 4)
    )

    # When qualification evaluates comparability without an explicit land type
    result = qualify_comps(subject, candidates, CompPolicy(as_of="2026-09-04"))

    # Then the set abstains instead of treating unknown type as comparable land
    assert (
        result.status,
        tuple(decision.reasons for decision in result.rejected),
        result.value_median,
    ) == (
        "insufficient_evidence",
        (("missing_subject_property_type",),) * 3,
        None,
    )
