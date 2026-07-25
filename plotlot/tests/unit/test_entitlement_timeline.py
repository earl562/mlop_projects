"""Tests for the entitlement timeline risk module."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from plotlot.core.types import CEQADocument, EntitlementTimelineRisk
from plotlot.pipeline.entitlement_timeline import (
    _check_active_permits,
    _estimate_timeline_range,
    _risk_level,
    assess_timeline_risk,
)

_CEQA = "plotlot.pipeline.ceqanet.find_parcel_ceqa"
_PERMITS = "plotlot.pipeline.entitlement_timeline._check_active_permits"


# ---------------------------------------------------------------------------
# Timeline estimation (deterministic base + strong CEQA adjustments)
# ---------------------------------------------------------------------------


def test_timeline_by_right_no_ceqa():
    est_min, est_max, drivers = _estimate_timeline_range("by_right", [], "low")
    assert est_min == 2.0
    assert est_max == 6.0
    assert len(drivers) == 0


def test_timeline_strong_active_eir_extends_range():
    docs = [CEQADocument(doc_type="EIR", status="in_progress", sch_number="2024010001")]
    est_min, est_max, drivers = _estimate_timeline_range("by_right", docs, "low")
    # A confirmed active EIR on the parcel legitimately drives the range up.
    assert est_min == 12.0
    assert est_max == 24.0
    assert any("Active EIR" in d and "2024010001" in d for d in drivers)


def test_timeline_strong_exemption_does_not_extend():
    docs = [CEQADocument(doc_type="NOE", status="exempt", sch_number="2024010002")]
    est_min, est_max, drivers = _estimate_timeline_range("by_right", docs, "low")
    assert (est_min, est_max) == (2.0, 6.0)
    assert any("complete" in d.lower() for d in drivers)


def test_timeline_conditional_use():
    est_min, est_max, drivers = _estimate_timeline_range("conditional_use", [], "medium")
    assert est_min == 6.0
    assert any("public hearing" in d.lower() for d in drivers)


def test_timeline_rezoning():
    est_min, est_max, drivers = _estimate_timeline_range("rezoning", [], "high")
    assert est_min == 12.0
    assert est_max >= 30.0


# ---------------------------------------------------------------------------
# Risk level classification
# ---------------------------------------------------------------------------


def test_risk_level_low():
    assert _risk_level(2.0, 5.0) == "low"


def test_risk_level_moderate():
    assert _risk_level(6.0, 14.0) == "moderate"


def test_risk_level_high():
    assert _risk_level(12.0, 30.0) == "high"


def test_risk_level_unknown():
    assert _risk_level(0.0, 0.0) == "unknown"


# ---------------------------------------------------------------------------
# Full assess_timeline_risk (mocked CEQAnet + permits)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assess_by_right_no_data_is_low():
    with (
        patch(_CEQA, new=AsyncMock(return_value=([], []))),
        patch(_PERMITS, new=AsyncMock(return_value=False)),
    ):
        result = await assess_timeline_risk(
            address="123 Main St, San Diego, CA",
            municipality="San Diego",
            county="San Diego",
            state="CA",
            entitlement_path="by_right",
            entitlement_complexity="low",
        )
    assert isinstance(result, EntitlementTimelineRisk)
    assert result.est_months_min == 2.0
    assert result.est_months_max == 6.0
    assert result.risk_level == "low"
    assert result.confidence == "low"


@pytest.mark.asyncio
async def test_assess_strong_ceqa_drives_high_confidence():
    strong = [CEQADocument(doc_type="EIR", status="in_progress", sch_number="2024010001")]
    with (
        patch(_CEQA, new=AsyncMock(return_value=(strong, []))),
        patch(_PERMITS, new=AsyncMock(return_value=False)),
    ):
        result = await assess_timeline_risk(
            address="123 Main St",
            municipality="San Diego",
            county="San Diego",
            state="CA",
            entitlement_path="by_right",
            entitlement_complexity="low",
        )
    assert result.confidence == "high"  # parcel-confirmed real filing
    assert result.risk_level == "high"
    assert result.est_months_max >= 24.0
    assert len(result.ceqa_documents) == 1
    assert any("confirmed on this parcel" in n for n in result.notes)


@pytest.mark.asyncio
async def test_assess_candidates_never_drive_timeline():
    cands = [
        CEQADocument(doc_type="EIR", status="in_progress", match_tier="candidate", sch_number="z")
    ]
    with (
        patch(_CEQA, new=AsyncMock(return_value=([], cands))),
        patch(_PERMITS, new=AsyncMock(return_value=False)),
    ):
        result = await assess_timeline_risk(
            address="123 Main St",
            municipality="San Diego",
            county="San Diego",
            state="CA",
            entitlement_path="by_right",
            entitlement_complexity="low",
        )
    # Candidates are carried but must NOT raise confidence or the range.
    assert result.confidence == "low"
    assert (result.est_months_min, result.est_months_max) == (2.0, 6.0)
    assert len(result.ceqa_candidates) == 1
    assert not result.ceqa_documents
    assert any("do not affect the timeline" in n for n in result.notes)


@pytest.mark.asyncio
async def test_assess_with_active_permits_is_medium():
    with (
        patch(_CEQA, new=AsyncMock(return_value=([], []))),
        patch(_PERMITS, new=AsyncMock(return_value=True)),
    ):
        result = await assess_timeline_risk(
            address="123 Main St",
            municipality="San Diego",
            county="San Diego",
            state="CA",
            entitlement_path="by_right",
            entitlement_complexity="low",
        )
    assert result.active_permits_exist is True
    assert result.confidence == "medium"
    assert any("permits" in n.lower() for n in result.notes)


@pytest.mark.asyncio
async def test_assess_non_ca_skips_ceqa():
    # State is FL → CEQAnet must not be consulted; a configured return is ignored.
    strong = [CEQADocument(doc_type="EIR", status="in_progress", sch_number="x")]
    with (
        patch(_CEQA, new=AsyncMock(return_value=(strong, []))) as ceqa_mock,
        patch(_PERMITS, new=AsyncMock(return_value=False)),
    ):
        result = await assess_timeline_risk(
            address="123 Main St",
            municipality="Miami",
            county="Miami-Dade",
            state="FL",
            entitlement_path="by_right",
            entitlement_complexity="low",
        )
    ceqa_mock.assert_not_called()
    assert result.est_months_min == 2.0
    assert result.confidence == "low"
    assert not result.ceqa_documents


@pytest.mark.asyncio
async def test_assess_api_failure_degrades_gracefully():
    with (
        patch(_CEQA, new=AsyncMock(side_effect=Exception("CEQAnet down"))),
        patch(_PERMITS, new=AsyncMock(side_effect=Exception("timeout"))),
    ):
        result = await assess_timeline_risk(
            address="123 Main St",
            municipality="San Diego",
            county="San Diego",
            state="CA",
            entitlement_path="conditional_use",
            entitlement_complexity="medium",
        )
    assert isinstance(result, EntitlementTimelineRisk)
    assert result.est_months_min == 6.0
    assert result.confidence == "low"


# ---------------------------------------------------------------------------
# Permit check — must read the real fetch_development_signals dict shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_active_permits_reads_correct_key():
    """Regression: _check_active_permits must read ``active_permit_count`` —
    the actual key fetch_development_signals returns — not ``active_permits``."""
    with patch(
        "plotlot.pipeline.permits.fetch_development_signals",
        new=AsyncMock(return_value={"active_permit_count": 2, "permit_count": 5}),
    ):
        assert await _check_active_permits("1234567890", "San Diego") is True

    with patch(
        "plotlot.pipeline.permits.fetch_development_signals",
        new=AsyncMock(return_value={"active_permit_count": 0, "permit_count": 3}),
    ):
        assert await _check_active_permits("1234567890", "San Diego") is False


@pytest.mark.asyncio
async def test_check_active_permits_no_apn_short_circuits():
    assert await _check_active_permits("", "San Diego") is False
