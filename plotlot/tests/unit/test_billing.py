"""Regression tests for PlotLot billing state transitions and enforcement."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import stripe
from fastapi import HTTPException
from starlette.requests import Request

from plotlot.api.billing import (
    _handle_checkout_completed,
    _handle_invoice_paid,
    _handle_subscription_deleted,
    check_analysis_limit,
    stripe_webhook,
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


@pytest.mark.asyncio
async def test_subscription_status_returns_free_shape_with_limit():
    request = Request({"type": "http", "path": "/", "client": ("127.0.0.1", 1)})
    session = AsyncMock()
    sub = SimpleNamespace(
        user_id="user_123",
        plan="free",
        stripe_customer_id=None,
        stripe_subscription_id=None,
        analyses_used=2,
    )

    with (
        patch("plotlot.api.billing.get_session", new=AsyncMock(return_value=session)),
        patch("plotlot.api.billing.get_or_create_subscription", new=AsyncMock(return_value=sub)),
    ):
        payload = await subscription_status(request, {"user_id": "user_123"})

    assert payload == {
        "plan": "free",
        "analyses_used": 2,
        "analyses_limit": 5,
        "stripe_customer_id": None,
    }


@pytest.mark.asyncio
async def test_check_analysis_limit_increments_free_user_under_limit():
    request = Request({"type": "http", "path": "/", "client": ("127.0.0.1", 1)})
    request.state.user = {"user_id": "user_free"}
    session = AsyncMock()
    sub = SimpleNamespace(
        user_id="user_free",
        plan="free",
        stripe_customer_id=None,
        stripe_subscription_id=None,
        analyses_used=2,
    )

    with (
        patch("plotlot.api.billing.get_session", new=AsyncMock(return_value=session)),
        patch("plotlot.api.billing.get_or_create_subscription", new=AsyncMock(return_value=sub)),
    ):
        await check_analysis_limit(request)

    assert sub.analyses_used == 3
    session.commit.assert_awaited_once()
    session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_analysis_limit_allows_pro_user_without_increment():
    request = Request({"type": "http", "path": "/", "client": ("127.0.0.1", 1)})
    request.state.user = {"user_id": "user_pro"}
    session = AsyncMock()
    sub = SimpleNamespace(
        user_id="user_pro",
        plan="pro",
        stripe_customer_id="cus_pro",
        stripe_subscription_id="sub_pro",
        analyses_used=42,
    )

    with (
        patch("plotlot.api.billing.get_session", new=AsyncMock(return_value=session)),
        patch("plotlot.api.billing.get_or_create_subscription", new=AsyncMock(return_value=sub)),
    ):
        await check_analysis_limit(request)

    assert sub.analyses_used == 42
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_stripe_webhook_returns_503_when_secret_key_missing():
    request = Request({"type": "http", "path": "/", "client": ("127.0.0.1", 1)})
    with patch("plotlot.api.billing.settings") as mock_settings:
        mock_settings.stripe_secret_key = ""
        with pytest.raises(HTTPException) as exc:
            await stripe_webhook(request)
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_stripe_webhook_rejects_invalid_signature():
    request = MagicMock(spec=Request)
    request.body = AsyncMock(return_value=b'{"type":"checkout.session.completed"}')
    request.headers = {"stripe-signature": "t=123,v1=bad"}

    with (
        patch("plotlot.api.billing.settings") as mock_settings,
        patch(
            "plotlot.api.billing.stripe.Webhook.construct_event",
            side_effect=stripe.SignatureVerificationError("bad sig", "raw"),
        ),
    ):
        mock_settings.stripe_secret_key = "sk_test"
        mock_settings.stripe_webhook_secret = "whsec_test"
        with pytest.raises(HTTPException) as exc:
            await stripe_webhook(request)
    assert exc.value.status_code == 400
    assert "signature" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_stripe_webhook_rejects_parse_error():
    request = MagicMock(spec=Request)
    request.body = AsyncMock(return_value=b"not json")
    request.headers = {"stripe-signature": "t=123,v1=bad"}

    with (
        patch("plotlot.api.billing.settings") as mock_settings,
        patch(
            "plotlot.api.billing.stripe.Webhook.construct_event",
            side_effect=ValueError("parse error"),
        ),
    ):
        mock_settings.stripe_secret_key = "sk_test"
        mock_settings.stripe_webhook_secret = "whsec_test"
        with pytest.raises(HTTPException) as exc:
            await stripe_webhook(request)
    assert exc.value.status_code == 400
    assert "parse" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_stripe_webhook_handles_checkout_completed_event():
    request = MagicMock(spec=Request)
    request.body = AsyncMock(return_value=b"{}")
    request.headers = {"stripe-signature": "t=1,v1=ok"}
    session = AsyncMock()

    event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "client_reference_id": "user_xyz",
                "customer": "cus_xyz",
                "subscription": "sub_xyz",
            }
        },
    }

    with (
        patch("plotlot.api.billing.settings") as mock_settings,
        patch(
            "plotlot.api.billing.stripe.Webhook.construct_event",
            return_value=event,
        ),
        patch("plotlot.api.billing.get_session", new=AsyncMock(return_value=session)),
        patch(
            "plotlot.api.billing._handle_checkout_completed",
            new=AsyncMock(),
        ) as mock_handler,
    ):
        mock_settings.stripe_secret_key = "sk_test"
        mock_settings.stripe_webhook_secret = "whsec_test"
        result = await stripe_webhook(request)

    assert result == {"status": "ok"}
    mock_handler.assert_awaited_once()
    session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_stripe_webhook_ignores_unknown_event_type():
    request = MagicMock(spec=Request)
    request.body = AsyncMock(return_value=b"{}")
    request.headers = {"stripe-signature": "t=1,v1=ok"}
    session = AsyncMock()

    event = {"type": "customer.created", "data": {"object": {}}}

    with (
        patch("plotlot.api.billing.settings") as mock_settings,
        patch(
            "plotlot.api.billing.stripe.Webhook.construct_event",
            return_value=event,
        ),
        patch("plotlot.api.billing.get_session", new=AsyncMock(return_value=session)),
        patch("plotlot.api.billing._handle_checkout_completed", new=AsyncMock()) as mock_co,
        patch("plotlot.api.billing._handle_subscription_deleted", new=AsyncMock()) as mock_del,
        patch("plotlot.api.billing._handle_invoice_paid", new=AsyncMock()) as mock_inv,
    ):
        mock_settings.stripe_secret_key = "sk_test"
        mock_settings.stripe_webhook_secret = "whsec_test"
        result = await stripe_webhook(request)

    assert result == {"status": "ok"}
    mock_co.assert_not_awaited()
    mock_del.assert_not_awaited()
    mock_inv.assert_not_awaited()


@pytest.mark.asyncio
async def test_stripe_webhook_dispatches_subscription_deleted_event():
    request = MagicMock(spec=Request)
    request.body = AsyncMock(return_value=b"{}")
    request.headers = {"stripe-signature": "t=1,v1=ok"}
    session = AsyncMock()

    subscription_obj = {"customer": "cus_cancel", "id": "sub_cancel", "status": "canceled"}
    event = {
        "type": "customer.subscription.deleted",
        "data": {"object": subscription_obj},
    }

    with (
        patch("plotlot.api.billing.settings") as mock_settings,
        patch(
            "plotlot.api.billing.stripe.Webhook.construct_event",
            return_value=event,
        ),
        patch("plotlot.api.billing.get_session", new=AsyncMock(return_value=session)),
        patch("plotlot.api.billing._handle_subscription_deleted", new=AsyncMock()) as mock_del,
        patch("plotlot.api.billing._handle_checkout_completed", new=AsyncMock()) as mock_co,
        patch("plotlot.api.billing._handle_invoice_paid", new=AsyncMock()) as mock_inv,
    ):
        mock_settings.stripe_secret_key = "sk_test"
        mock_settings.stripe_webhook_secret = "whsec_test"
        result = await stripe_webhook(request)

    assert result == {"status": "ok"}
    mock_del.assert_awaited_once_with(session, subscription_obj)
    mock_co.assert_not_awaited()
    mock_inv.assert_not_awaited()
    session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_stripe_webhook_dispatches_invoice_paid_event():
    request = MagicMock(spec=Request)
    request.body = AsyncMock(return_value=b"{}")
    request.headers = {"stripe-signature": "t=1,v1=ok"}
    session = AsyncMock()

    invoice_obj = {"customer": "cus_renew", "id": "in_renew", "amount_paid": 4900}
    event = {
        "type": "invoice.paid",
        "data": {"object": invoice_obj},
    }

    with (
        patch("plotlot.api.billing.settings") as mock_settings,
        patch(
            "plotlot.api.billing.stripe.Webhook.construct_event",
            return_value=event,
        ),
        patch("plotlot.api.billing.get_session", new=AsyncMock(return_value=session)),
        patch("plotlot.api.billing._handle_invoice_paid", new=AsyncMock()) as mock_inv,
        patch("plotlot.api.billing._handle_checkout_completed", new=AsyncMock()) as mock_co,
        patch("plotlot.api.billing._handle_subscription_deleted", new=AsyncMock()) as mock_del,
    ):
        mock_settings.stripe_secret_key = "sk_test"
        mock_settings.stripe_webhook_secret = "whsec_test"
        result = await stripe_webhook(request)

    assert result == {"status": "ok"}
    mock_inv.assert_awaited_once_with(session, invoice_obj)
    mock_co.assert_not_awaited()
    mock_del.assert_not_awaited()
    session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_subscription_deleted_no_op_when_no_customer_id():
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session = AsyncMock()
    session.execute.return_value = result

    await _handle_subscription_deleted(session, {"customer": None})

    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_invoice_paid_no_op_when_no_customer_id():
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session = AsyncMock()
    session.execute.return_value = result

    await _handle_invoice_paid(session, {"customer": None})

    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_invoice_paid_no_op_when_user_is_free_plan():
    sub = SimpleNamespace(
        user_id="user_free",
        plan="free",
        stripe_customer_id="cus_free",
        stripe_subscription_id=None,
        analyses_used=3,
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = sub
    session = AsyncMock()
    session.execute.return_value = result

    await _handle_invoice_paid(session, {"customer": "cus_free"})

    assert sub.analyses_used == 3
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_checkout_completed_skips_when_no_client_reference_id():
    session = AsyncMock()

    with patch(
        "plotlot.api.billing.get_or_create_subscription",
        new=AsyncMock(),
    ) as mock_get_or_create:
        await _handle_checkout_completed(
            session,
            {"client_reference_id": None, "customer": "cus_orphan", "subscription": "sub_orphan"},
        )

    mock_get_or_create.assert_not_awaited()
    session.commit.assert_not_awaited()
