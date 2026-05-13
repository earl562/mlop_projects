"""Regression tests for PlotLot billing state transitions and enforcement."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from plotlot.api.billing import (
    _handle_checkout_completed,
    _handle_invoice_paid,
    _handle_subscription_deleted,
    check_analysis_limit,
    subscription_status,
)


@pytest.mark.asyncio
async def test_handle_checkout_completed_marks_subscription_pro():
    sub = SimpleNamespace(
        user_id="user_123",
        plan="free",
        stripe_customer_id=None,
        stripe_subscription_id=None,
        analyses_used=2,
    )
    session = AsyncMock()

    with patch("plotlot.api.billing.get_or_create_subscription", new=AsyncMock(return_value=sub)):
        await _handle_checkout_completed(
            session,
            {
                "client_reference_id": "user_123",
                "customer": "cus_123",
                "subscription": "sub_123",
            },
        )

    assert sub.plan == "pro"
    assert sub.stripe_customer_id == "cus_123"
    assert sub.stripe_subscription_id == "sub_123"
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_subscription_deleted_reverts_plan():
    sub = SimpleNamespace(
        user_id="user_123",
        plan="pro",
        stripe_customer_id="cus_123",
        stripe_subscription_id="sub_123",
        analyses_used=4,
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = sub
    session = AsyncMock()
    session.execute.return_value = result

    await _handle_subscription_deleted(session, {"customer": "cus_123"})

    assert sub.plan == "free"
    assert sub.stripe_subscription_id is None
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_invoice_paid_resets_usage_for_pro():
    sub = SimpleNamespace(
        user_id="user_123",
        plan="pro",
        stripe_customer_id="cus_123",
        stripe_subscription_id="sub_123",
        analyses_used=4,
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = sub
    session = AsyncMock()
    session.execute.return_value = result

    await _handle_invoice_paid(session, {"customer": "cus_123"})

    assert sub.analyses_used == 0
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_analysis_limit_allows_anonymous_requests():
    request = Request({"type": "http"})
    request.state.user = {"user_id": "anonymous"}

    with patch("plotlot.api.billing.get_session", new=AsyncMock()) as mock_get_session:
        await check_analysis_limit(request)

    mock_get_session.assert_not_called()


@pytest.mark.asyncio
async def test_check_analysis_limit_raises_when_free_tier_exhausted():
    request = Request({"type": "http"})
    request.state.user = {"user_id": "user_123"}
    session = AsyncMock()
    sub = SimpleNamespace(
        user_id="user_123",
        plan="free",
        stripe_customer_id=None,
        stripe_subscription_id=None,
        analyses_used=5,
    )

    with (
        patch("plotlot.api.billing.get_session", new=AsyncMock(return_value=session)),
        patch("plotlot.api.billing.get_or_create_subscription", new=AsyncMock(return_value=sub)),
    ):
        with pytest.raises(HTTPException) as exc:
            await check_analysis_limit(request)

    assert exc.value.status_code == 402
    assert exc.value.detail["error"] == "usage_limit_exceeded"
    session.commit.assert_not_awaited()
    session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_subscription_status_returns_pro_shape():
    request = Request({"type": "http"})
    session = AsyncMock()
    sub = SimpleNamespace(
        user_id="user_123",
        plan="pro",
        stripe_customer_id="cus_123",
        stripe_subscription_id="sub_123",
        analyses_used=7,
    )

    with (
        patch("plotlot.api.billing.get_session", new=AsyncMock(return_value=session)),
        patch("plotlot.api.billing.get_or_create_subscription", new=AsyncMock(return_value=sub)),
    ):
        payload = await subscription_status(request, {"user_id": "user_123"})

    assert payload == {
        "plan": "pro",
        "analyses_used": 7,
        "analyses_limit": None,
        "stripe_customer_id": "cus_123",
    }
    session.close.assert_awaited_once()
