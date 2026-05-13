"""Stripe billing integration for PlotLot subscriptions.

Routes:
    GET  /api/v1/subscription/status  — current user's plan + usage
    POST /api/v1/stripe/webhook       — Stripe event handler (checkout, invoice)

Subscription lifecycle:
    1. User clicks "Upgrade" on frontend
    2. Frontend calls POST /api/stripe/checkout (Next.js route) → Stripe Checkout URL
    3. User completes payment on Stripe
    4. Stripe sends checkout.session.completed webhook here
    5. This handler marks user as "pro" in UserSubscription table
    6. On subscription cancellation (customer.subscription.deleted), revert to "free"

Free tier: 5 analyses/month. Pro tier ($49/month): unlimited.
"""

from __future__ import annotations

import logging
from typing import Any, cast

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from plotlot.api.auth import require_auth
from plotlot.config import settings
from plotlot.storage.db import get_session
from plotlot.storage.models import UserSubscription

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["billing"])

FREE_ANALYSIS_LIMIT = 5


def _get_analyses_used(sub: UserSubscription) -> int:
    return cast(int, sub.analyses_used)


def _set_plan(sub: UserSubscription, plan: str) -> None:
    setattr(sub, "plan", plan)


def _set_stripe_customer_id(sub: UserSubscription, customer_id: str | None) -> None:
    setattr(sub, "stripe_customer_id", customer_id)


def _set_stripe_subscription_id(sub: UserSubscription, subscription_id: str | None) -> None:
    setattr(sub, "stripe_subscription_id", subscription_id)


def _set_analyses_used(sub: UserSubscription, analyses_used: int) -> None:
    setattr(sub, "analyses_used", analyses_used)


async def get_or_create_subscription(session: AsyncSession, user_id: str) -> UserSubscription:
    """Fetch or create a UserSubscription row for the given user_id."""
    result = await session.execute(
        select(UserSubscription).where(UserSubscription.user_id == user_id)
    )
    sub = result.scalar_one_or_none()
    if sub is None:
        sub = UserSubscription(user_id=user_id, plan="free", analyses_used=0)
        session.add(sub)
        await session.flush()
    return sub


async def check_analysis_limit(request: Request) -> None:
    """Raise 402 if the authenticated user has exceeded their free tier limit.

    Used as a FastAPI dependency on POST /analyze.  Anonymous users
    (auth disabled) pass through unconditionally.
    """
    user: dict[str, Any] | None = getattr(request.state, "user", None)
    if user is None or user.get("user_id") == "anonymous":
        return  # anonymous — no limit enforcement yet

    db = await get_session()
    try:
        sub = await get_or_create_subscription(db, user["user_id"])

        if sub.plan == "pro":
            return  # unlimited

        analyses_used = _get_analyses_used(sub)

        if analyses_used >= FREE_ANALYSIS_LIMIT:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "error": "usage_limit_exceeded",
                    "limit": FREE_ANALYSIS_LIMIT,
                    "used": analyses_used,
                    "message": (
                        f"Free tier limit of {FREE_ANALYSIS_LIMIT} analyses/month reached. "
                        "Upgrade to Pro for unlimited access."
                    ),
                },
            )

        _set_analyses_used(sub, analyses_used + 1)
        await db.commit()
    finally:
        await db.close()


@router.get("/subscription/status")
async def subscription_status(
    request: Request,
    user: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    """Return the current user's subscription plan and usage."""
    db = await get_session()
    try:
        sub = await get_or_create_subscription(db, user["user_id"])
        return {
            "plan": sub.plan,
            "analyses_used": _get_analyses_used(sub),
            "analyses_limit": None if sub.plan == "pro" else FREE_ANALYSIS_LIMIT,
            "stripe_customer_id": sub.stripe_customer_id,
        }
    finally:
        await db.close()


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request) -> dict[str, str]:
    """Handle Stripe webhook events.

    Stripe must be configured to send:
    - checkout.session.completed  → mark user as Pro
    - customer.subscription.deleted → revert user to Free
    - invoice.paid                → reset monthly usage counter
    """
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=503, detail="Stripe not configured")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)
    except stripe.SignatureVerificationError:
        logger.warning("Invalid Stripe webhook signature")
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as exc:
        logger.error("Stripe webhook parse error: %s", exc)
        raise HTTPException(status_code=400, detail="Webhook parse error")

    session = await get_session()
    try:
        if event["type"] == "checkout.session.completed":
            await _handle_checkout_completed(session, event["data"]["object"])
        elif event["type"] == "customer.subscription.deleted":
            await _handle_subscription_deleted(session, event["data"]["object"])
        elif event["type"] == "invoice.paid":
            await _handle_invoice_paid(session, event["data"]["object"])
        else:
            logger.debug("Unhandled Stripe event type: %s", event["type"])
    finally:
        await session.close()

    return {"status": "ok"}


async def _handle_checkout_completed(session: AsyncSession, checkout: dict[str, Any]) -> None:
    """Upgrade user to Pro when Stripe Checkout completes."""
    clerk_user_id: str | None = checkout.get("client_reference_id")
    stripe_customer_id: str | None = checkout.get("customer")
    stripe_subscription_id: str | None = checkout.get("subscription")

    if not clerk_user_id:
        logger.error("checkout.session.completed missing client_reference_id")
        return

    sub = await get_or_create_subscription(session, clerk_user_id)
    _set_plan(sub, "pro")
    _set_stripe_customer_id(sub, stripe_customer_id)
    _set_stripe_subscription_id(sub, stripe_subscription_id)
    await session.commit()
    logger.info("User %s upgraded to Pro (customer=%s)", clerk_user_id, stripe_customer_id)


async def _handle_subscription_deleted(session: AsyncSession, subscription: dict[str, Any]) -> None:
    """Revert user to Free when subscription is cancelled."""
    stripe_customer_id: str | None = subscription.get("customer")
    if not stripe_customer_id:
        return

    result = await session.execute(
        select(UserSubscription).where(UserSubscription.stripe_customer_id == stripe_customer_id)
    )
    sub = result.scalar_one_or_none()
    if sub:
        _set_plan(sub, "free")
        _set_stripe_subscription_id(sub, None)
        await session.commit()
        logger.info("User %s reverted to Free (subscription cancelled)", sub.user_id)


async def _handle_invoice_paid(session: AsyncSession, invoice: dict[str, Any]) -> None:
    """Reset monthly analysis counter on invoice payment (billing cycle renewal)."""
    stripe_customer_id: str | None = invoice.get("customer")
    if not stripe_customer_id:
        return

    result = await session.execute(
        select(UserSubscription).where(UserSubscription.stripe_customer_id == stripe_customer_id)
    )
    sub = result.scalar_one_or_none()
    if sub and sub.plan == "pro":
        _set_analyses_used(sub, 0)
        await session.commit()
        logger.info("Reset analysis counter for Pro user %s", sub.user_id)
