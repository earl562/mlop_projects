"""Regression test: ReportCache key must include analysis_type.

Prior to this fix, residential and datacenter analyses on the same address
shared a cache row (unique key was address_normalized only). A datacenter
report would be returned for a residential request and vice versa.

These tests verify that the cache functions accept and use analysis_type
as a second dimension of the cache key.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from plotlot.api.cache import cache_report, get_cached_report, normalize_address


# ---------------------------------------------------------------------------
# normalize_address — pure function, no I/O
# ---------------------------------------------------------------------------


def test_normalize_address_strips_and_lowercases():
    assert normalize_address("  123 Main St, Miami, FL  ") == "123 main st miami fl"


def test_normalize_address_collapses_punctuation():
    assert normalize_address("123 Main St. Miami FL") == "123 main st miami fl"


def test_normalize_address_same_result_for_variants():
    a = normalize_address("171 NE 209th Ter, Miami, FL 33179")
    b = normalize_address("171 ne 209th ter  miami  fl 33179")
    assert a == b


# ---------------------------------------------------------------------------
# get_cached_report — uses analysis_type in WHERE clause
# ---------------------------------------------------------------------------


@pytest.fixture
def _mock_db(monkeypatch):
    """Monkeypatch get_session to return a controllable async session."""
    session = AsyncMock()
    session.close = AsyncMock()
    monkeypatch.setattr("plotlot.api.cache.get_session", AsyncMock(return_value=session))
    return session


@pytest.mark.asyncio
async def test_get_cached_report_passes_analysis_type_to_query(_mock_db):
    """get_cached_report must include analysis_type in the WHERE clause."""
    # Simulate a cache miss so we can inspect the execute call
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    _mock_db.execute = AsyncMock(return_value=result_mock)

    await get_cached_report("123 Main St", analysis_type="datacenter")

    assert _mock_db.execute.called
    # Inspect the compiled WHERE clause string for analysis_type presence
    call_stmt = _mock_db.execute.call_args[0][0]
    compiled = str(call_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "datacenter" in compiled


@pytest.mark.asyncio
async def test_get_cached_report_default_is_residential(_mock_db):
    """Default analysis_type must be 'residential' for backward compat."""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    _mock_db.execute = AsyncMock(return_value=result_mock)

    await get_cached_report("123 Main St")

    call_stmt = _mock_db.execute.call_args[0][0]
    compiled = str(call_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "residential" in compiled


@pytest.mark.asyncio
async def test_get_cached_report_returns_hit(_mock_db):
    """Cache hit: should return report_json dict and increment hit_count."""
    cached_row = MagicMock()
    cached_row.id = 1
    cached_row.report_json = {"zoning_district": "I-1", "confidence": "high"}

    # First execute (SELECT) returns the cached row;
    # second execute (UPDATE hit_count) returns a dummy result.
    select_result = MagicMock()
    select_result.scalar_one_or_none.return_value = cached_row
    update_result = MagicMock()
    _mock_db.execute = AsyncMock(side_effect=[select_result, update_result])
    _mock_db.commit = AsyncMock()

    result = await get_cached_report("123 Main St", analysis_type="residential")

    assert result == {"zoning_district": "I-1", "confidence": "high"}
    assert _mock_db.commit.called


# ---------------------------------------------------------------------------
# cache_report — stores with correct analysis_type
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_report_passes_analysis_type_on_insert(_mock_db):
    """cache_report must persist analysis_type when inserting a new row."""
    # Simulate no existing row (cache miss on SELECT)
    select_result = MagicMock()
    select_result.scalar_one_or_none.return_value = None
    _mock_db.execute = AsyncMock(return_value=select_result)
    _mock_db.add = MagicMock()
    _mock_db.commit = AsyncMock()

    report = {
        "zoning_district": "I-1",
        "confidence": "high",
        "numeric_params": {"max_far": 2.0},
    }
    await cache_report("123 Main St", report, analysis_type="datacenter")

    assert _mock_db.add.called
    added_obj = _mock_db.add.call_args[0][0]
    assert added_obj.analysis_type == "datacenter"


@pytest.mark.asyncio
async def test_cache_report_default_analysis_type_is_residential(_mock_db):
    """Default analysis_type in cache_report is 'residential'."""
    select_result = MagicMock()
    select_result.scalar_one_or_none.return_value = None
    _mock_db.execute = AsyncMock(return_value=select_result)
    _mock_db.add = MagicMock()
    _mock_db.commit = AsyncMock()

    report = {
        "zoning_district": "R-1",
        "confidence": "high",
        "numeric_params": {"max_far": 0.5},
    }
    await cache_report("123 Main St", report)

    added_obj = _mock_db.add.call_args[0][0]
    assert added_obj.analysis_type == "residential"


@pytest.mark.asyncio
async def test_cache_report_skips_low_confidence(_mock_db):
    """Quality gate: low-confidence reports are not cached."""
    _mock_db.execute = AsyncMock()
    _mock_db.add = MagicMock()

    report = {"confidence": "low", "zoning_district": "R-1", "numeric_params": {}}
    await cache_report("123 Main St", report, analysis_type="residential")

    _mock_db.add.assert_not_called()
