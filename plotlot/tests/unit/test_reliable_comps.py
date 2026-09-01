"""Deterministic qualification tests for evidence-backed comparable sales."""

from __future__ import annotations

from datetime import date, datetime, timezone

from plotlot.application.market.comps import qualify_comps
from plotlot.application.market.models import (
    ComparableSale,
    ComparableSource,
    CompConfidence,
    CompPolicy,
    CompStatus,
    ExclusionReason,
    SubjectProperty,
)


AS_OF = date(2026, 9, 1)


def _source(record_id: str, provider: str = "county_recorder") -> ComparableSource:
    return ComparableSource(
        provider=provider,
        record_id=record_id,
        source_url=f"https://example.test/sales/{record_id}",
        retrieved_at=datetime(2026, 8, 31, tzinfo=timezone.utc),
    )


def _sale(
    sale_id: str,
    *,
    address: str | None = None,
    price: float = 500_000,
    sold: date = date(2026, 3, 1),
    latitude: float = 25.990,
    longitude: float = -80.230,
    property_type: str = "multifamily",
    lot_size_sqft: float = 10_000,
    building_sqft: float = 5_000,
    source: ComparableSource | None = None,
) -> ComparableSale:
    return ComparableSale(
        sale_id=sale_id,
        address=address or f"{sale_id} Example Ave, Miramar, FL",
        sale_price=price,
        sale_date=sold,
        latitude=latitude,
        longitude=longitude,
        property_type=property_type,
        lot_size_sqft=lot_size_sqft,
        building_sqft=building_sqft,
        source=source if source is not None else _source(sale_id),
        evidence_id=f"ev_{sale_id}",
    )


def _subject() -> SubjectProperty:
    return SubjectProperty(
        address="100 Main St, Miramar, FL",
        latitude=25.990,
        longitude=-80.230,
        property_type="multifamily",
        lot_size_sqft=10_000,
        building_sqft=5_000,
    )


def test_qualification_excludes_unreliable_sales_with_explicit_reasons():
    duplicate_source = _source("same-record")
    missing_source = _sale("missing-source").model_copy(update={"source": None})
    sales = [
        _sale("subject", address="100 main st, miramar, fl"),
        _sale("duplicate-original", source=duplicate_source),
        _sale("duplicate-copy", source=duplicate_source),
        missing_source,
        _sale("stale", sold=date(2021, 1, 1)),
        _sale("distant", latitude=26.500),
        _sale("wrong-type", property_type="retail"),
        _sale("wrong-size", lot_size_sqft=30_000),
        _sale("good-1", price=480_000),
        _sale("good-2", price=500_000),
        _sale("good-3", price=520_000),
    ]

    result = qualify_comps(_subject(), sales, CompPolicy(), as_of=AS_OF)
    excluded = {item.sale_id: set(item.reasons) for item in result.excluded}

    assert ExclusionReason.SUBJECT_PROPERTY in excluded["subject"]
    assert ExclusionReason.DUPLICATE in excluded["duplicate-copy"]
    assert ExclusionReason.MISSING_PROVENANCE in excluded["missing-source"]
    assert ExclusionReason.STALE in excluded["stale"]
    assert ExclusionReason.OUTSIDE_RADIUS in excluded["distant"]
    assert ExclusionReason.PROPERTY_TYPE_MISMATCH in excluded["wrong-type"]
    assert ExclusionReason.LOT_SIZE_MISMATCH in excluded["wrong-size"]
    assert result.status == CompStatus.QUALIFIED


def test_qualification_removes_normalized_price_outlier():
    sales = [
        _sale("normal-1", price=480_000),
        _sale("normal-2", price=500_000),
        _sale("normal-3", price=510_000),
        _sale("normal-4", price=525_000),
        _sale("extreme", price=4_000_000),
    ]

    result = qualify_comps(_subject(), sales, CompPolicy(), as_of=AS_OF)

    excluded = {item.sale_id: set(item.reasons) for item in result.excluded}
    assert ExclusionReason.PRICE_OUTLIER in excluded["extreme"]
    assert {item.sale.sale_id for item in result.qualified} == {
        "normal-1",
        "normal-2",
        "normal-3",
        "normal-4",
    }


def test_qualification_abstains_with_fewer_than_three_supported_sales():
    result = qualify_comps(
        _subject(),
        [_sale("one"), _sale("two", price=520_000)],
        CompPolicy(min_comps=3),
        as_of=AS_OF,
    )

    assert result.status == CompStatus.INSUFFICIENT_EVIDENCE
    assert result.confidence == CompConfidence.INSUFFICIENT
    assert result.valuation_low is None
    assert result.valuation_median is None
    assert result.valuation_high is None
    assert "At least 3 qualified comparable sales are required" in result.message


def test_qualification_returns_ordered_value_range_and_evidence():
    result = qualify_comps(
        _subject(),
        [
            _sale("a", price=450_000),
            _sale("b", price=480_000, source=_source("b", "mls")),
            _sale("c", price=500_000),
            _sale("d", price=525_000, source=_source("d", "mls")),
            _sale("e", price=550_000),
            _sale("f", price=575_000, source=_source("f", "mls")),
        ],
        CompPolicy(),
        as_of=AS_OF,
    )

    assert result.status == CompStatus.QUALIFIED
    assert result.valuation_basis == "building_sqft"
    assert result.valuation_low < result.valuation_median < result.valuation_high
    assert result.confidence == CompConfidence.HIGH
    assert result.evidence_ids == ("ev_a", "ev_b", "ev_c", "ev_d", "ev_e", "ev_f")
