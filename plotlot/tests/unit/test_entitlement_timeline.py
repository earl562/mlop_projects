"""Tests for the entitlement timeline risk module."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from plotlot.core.types import CEQADocument, EntitlementTimelineRisk
from plotlot.pipeline.entitlement_timeline import (
    _check_active_permits,
    _estimate_timeline_range,
    _parse_ceqa_llm_response,
    _risk_level,
    assess_timeline_risk,
)


# ---------------------------------------------------------------------------
# CEQA document classification
# ---------------------------------------------------------------------------


def test_parse_ceqa_llm_response_empty():
    assert _parse_ceqa_llm_response("[]") == []


def test_parse_ceqa_llm_response_valid():
    raw = '[{"doc_type": "EIR", "status": "in_progress", "description": "Test EIR", "lead_agency": "City of SD", "source_url": "https://example.com"}]'
    docs = _parse_ceqa_llm_response(raw)
    assert len(docs) == 1
    assert docs[0].doc_type == "EIR"
    assert docs[0].status == "in_progress"


def test_parse_ceqa_llm_response_markdown_fenced():
    raw = '```json\n[{"doc_type": "MND", "status": "completed", "description": "Test MND"}]\n```'
    docs = _parse_ceqa_llm_response(raw)
    assert len(docs) == 1
    assert docs[0].doc_type == "MND"


# ---------------------------------------------------------------------------
# Timeline estimation
# ---------------------------------------------------------------------------


def test_timeline_by_right_no_ceqa():
    est_min, est_max, drivers = _estimate_timeline_range("by_right", [], "low")
    assert est_min == 2.0
    assert est_max == 6.0
    assert len(drivers) == 0


def test_timeline_by_right_with_ceqa_eir():
    docs = [
        CEQADocument(
            doc_type="EIR",
            status="in_progress",
            description="Draft EIR for mixed-use project",
        )
    ]
    est_min, est_max, drivers = _estimate_timeline_range("by_right", docs, "low")
    # Unverified CEQA leads are advisory only — they must NOT inflate the
    # deterministic by-right range, but they should surface as a flagged driver.
    assert est_max == 6.0
    assert any("EIR" in d and "unverified" in d.lower() for d in drivers)


def test_timeline_conditional_use():
    est_min, est_max, drivers = _estimate_timeline_range("conditional_use", [], "medium")
    assert est_min == 6.0
    assert any("public hearing" in d.lower() for d in drivers)


def test_timeline_rezoning():
    est_min, est_max, drivers = _estimate_timeline_range("rezoning", [], "high")
    assert est_min == 12.0
    assert est_max >= 30.0  # high complexity multiplier


def test_timeline_categorical_exemption_minimal_impact():
    docs = [
        CEQADocument(
            doc_type="CE",
            status="completed",
            description="Categorical exemption Class 32 infill",
        )
    ]
    est_min, est_max, _drivers = _estimate_timeline_range("by_right", docs, "low")
    assert pytest.approx(est_min, rel=0.1) == 2.0  # exemption = no CEQA timeline hit


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
# Full assess_timeline_risk (mocked network)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assess_timeline_risk_by_right_ca():
    with (
        patch(
            "plotlot.pipeline.entitlement_timeline._suggest_ceqa_documents",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "plotlot.pipeline.entitlement_timeline._check_active_permits",
            new=AsyncMock(return_value=False),
        ),
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
    assert result.confidence == "low"  # no CEQA docs found


@pytest.mark.asyncio
async def test_assess_timeline_risk_with_active_permits():
    with (
        patch(
            "plotlot.pipeline.entitlement_timeline._suggest_ceqa_documents",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "plotlot.pipeline.entitlement_timeline._check_active_permits",
            new=AsyncMock(return_value=True),
        ),
    ):
        result = await assess_timeline_risk(
            address="123 Main St",
            municipality="San Diego",
            county="San Diego",
            state="CA",
            entitlement_path="by_right",
            entitlement_complexity="low",
        )

    assert result.est_months_min == 2.0
    assert result.active_permits_exist is True
    assert any("permits" in n.lower() for n in result.notes)


@pytest.mark.asyncio
async def test_assess_timeline_risk_non_ca_skips_ceqa():
    with (
        patch(
            "plotlot.pipeline.entitlement_timeline._suggest_ceqa_documents",
            new=AsyncMock(return_value=[CEQADocument(doc_type="EIR", status="in_progress")]),
        ),
        patch(
            "plotlot.pipeline.entitlement_timeline._check_active_permits",
            new=AsyncMock(return_value=False),
        ),
    ):
        result = await assess_timeline_risk(
            address="123 Main St",
            municipality="Miami",
            county="Miami-Dade",
            state="FL",
            entitlement_path="by_right",
            entitlement_complexity="low",
        )
    assert result.est_months_min == 2.0
    assert result.confidence is not None


@pytest.mark.asyncio
async def test_assess_timeline_risk_api_failure_degrades_gracefully():
    with (
        patch(
            "plotlot.pipeline.entitlement_timeline._suggest_ceqa_documents",
            new=AsyncMock(side_effect=Exception("API unavailable")),
        ),
        patch(
            "plotlot.pipeline.entitlement_timeline._check_active_permits",
            new=AsyncMock(side_effect=Exception("timeout")),
        ),
    ):
        result = await assess_timeline_risk(
            address="123 Main St",
            municipality="San Diego",
            county="San Diego",
            state="CA",
            entitlement_path="conditional_use",
            entitlement_complexity="medium",
        )
    # Should still return a valid result with the base estimate
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
