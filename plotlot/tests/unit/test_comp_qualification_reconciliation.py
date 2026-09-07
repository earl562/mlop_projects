from plotlot.comps import CompPolicy, CompSubject, SaleEvidence, qualify_comps


def _subject() -> CompSubject:
    return CompSubject(
        parcel_id="0000012345",
        state="FL",
        county="Miami-Dade",
        latitude=25.76,
        longitude=-80.19,
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
        sale_price=price,
        sale_date="2026-04-15",
        date_precision="day",
        latitude=latitude,
        longitude=-80.19,
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


def test_conflict_connected_by_source_record_blocks_different_document_aliases() -> None:
    # Given two prices for one parcel and source record but different document aliases
    original = _land_evidence(1, 100_000, 25.7601)
    conflict = original.model_copy(
        update={
            "evidence_id": "sale-1-conflict",
            "sale_price": 900_000,
            "recorded_document": "instrument-alias-2",
        }
    )
    candidates = (
        original,
        conflict,
        _land_evidence(2, 200_000, 25.7602),
        _land_evidence(3, 300_000, 25.7603),
    )

    # When all available transaction identities are reconciled as a connected group
    result = qualify_comps(_subject(), candidates, CompPolicy(as_of="2026-09-04"))

    # Then neither conflicting alias is selected and two clean parcels are insufficient
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


def test_conflict_connected_by_document_blocks_different_source_record_aliases() -> None:
    # Given two prices for one parcel and document but different source-record aliases
    original = _land_evidence(1, 100_000, 25.7601)
    conflict = original.model_copy(
        update={
            "evidence_id": "sale-1-conflict",
            "sale_price": 900_000,
            "source_record_id": "source-alias-2",
        }
    )
    candidates = (
        original,
        conflict,
        _land_evidence(2, 200_000, 25.7602),
        _land_evidence(3, 300_000, 25.7603),
    )

    # When every available transaction identity participates in reconciliation
    result = qualify_comps(_subject(), candidates, CompPolicy(as_of="2026-09-04"))

    # Then both conflicting aliases are blocked from the valuation
    assert (
        result.status,
        tuple(decision.evidence_id for decision in result.accepted),
        tuple(decision.reasons for decision in result.rejected),
    ) == (
        "insufficient_evidence",
        ("sale-2", "sale-3"),
        (("conflicting_transaction_evidence",),) * 2,
    )


def test_local_source_record_ids_do_not_collide_across_source_namespaces() -> None:
    # Given distinct transfers whose providers both use the same local row identifier
    earlier = _land_evidence(1, 100_000, 25.7601)
    later = earlier.model_copy(
        update={
            "evidence_id": "sale-1-later",
            "sale_price": 150_000,
            "sale_date": "2026-05-15",
            "source_url": "https://other-county-system.example/sales",
            "recorded_document": "book-2/page-2",
        }
    )
    candidates = (
        earlier,
        later,
        _land_evidence(2, 200_000, 25.7602),
        _land_evidence(3, 300_000, 25.7603),
    )

    # When the local source identifiers are reconciled inside their source namespaces
    result = qualify_comps(_subject(), candidates, CompPolicy(as_of="2026-09-04"))

    # Then the later transfer represents the parcel without a false transaction conflict
    assert (
        result.status,
        tuple(decision.evidence_id for decision in result.accepted),
        tuple((decision.evidence_id, decision.reasons) for decision in result.rejected),
    ) == (
        "qualified",
        ("sale-1-later", "sale-2", "sale-3"),
        (("sale-1", ("not_selected",)),),
    )


def test_radius_gate_uses_full_precision_before_rounding_display_distance() -> None:
    # Given a sale 3.0000004 miles from an equatorial subject and two nearby sales
    subject = _subject().model_copy(update={"latitude": 0, "longitude": 0})
    outside = _land_evidence(1, 100_000, 0).model_copy(update={"longitude": 0.043419481103232654})
    candidates = (
        outside,
        _land_evidence(2, 200_000, 0).model_copy(update={"longitude": 0.01}),
        _land_evidence(3, 300_000, 0).model_copy(update={"longitude": 0.02}),
    )

    # When qualification applies the hard three-mile policy boundary
    result = qualify_comps(subject, candidates, CompPolicy(as_of="2026-09-04"))

    # Then the true distance gates eligibility while its retained display value is rounded
    assert (
        result.status,
        result.rejected[0].reasons,
        result.rejected[0].distance_miles,
        result.value_median,
    ) == ("insufficient_evidence", ("outside_radius",), 3.0, None)
