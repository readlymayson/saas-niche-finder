"""Billing endpoints — payment, webhooks, and subscription management."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.deps import get_current_user
from app.models.user import User
from app.services.billing import TIERS, create_payment, get_tier

router = APIRouter()


class TierInfo(BaseModel):
    slug: str
    name: str
    price_rub: int
    requests_per_min: int
    requests_per_month: int
    duration_days: int


class PaymentRequest(BaseModel):
    tier_slug: str


class PaymentResponse(BaseModel):
    payment_id: str
    confirmation_url: str | None
    status: str


class SubscriptionStatus(BaseModel):
    tier: str
    is_active: bool
    expires_at: str | None
    requests_per_min: int
    requests_per_month: int


class WebhookPayload(BaseModel):
    event: str
    type: str
    object: dict


@router.get("/tiers", response_model=list[TierInfo])
async def list_tiers() -> list[TierInfo]:
    """List available subscription tiers with prices and limits."""
    return [
        TierInfo(
            slug=t.slug,
            name=t.name,
            price_rub=t.price_rub,
            requests_per_min=t.requests_per_min,
            requests_per_month=t.requests_per_month,
            duration_days=t.duration_days,
        )
        for t in TIERS.values()
    ]


@router.post("/subscribe", response_model=PaymentResponse)
async def subscribe(
    body: PaymentRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PaymentResponse:
    """Create a payment for a subscription tier.

    Returns a confirmation URL for redirect to YooKassa checkout.
    """
    tier = get_tier(body.tier_slug)
    if tier is None:
        raise HTTPException(status_code=404, detail=f"Tier '{body.tier_slug}' not found")

    if tier.price_rub <= 0:
        # Free tier — activate immediately
        from datetime import UTC, datetime

        user.subscription_tier = "free"
        user.subscription_expires_at = None
        await db.commit()
        return PaymentResponse(
            payment_id="free",
            confirmation_url=None,
            status="succeeded",
        )

    payment = await create_payment(body.tier_slug, user.email)
    if payment is None:
        raise HTTPException(
            status_code=502,
            detail="Payment service unavailable. Try again later.",
        )

    confirmation_url = None
    if "confirmation" in payment and "confirmation_url" in payment["confirmation"]:
        confirmation_url = payment["confirmation"]["confirmation_url"]

    return PaymentResponse(
        payment_id=payment["id"],
        confirmation_url=confirmation_url,
        status=payment["status"],
    )


@router.get("/subscription", response_model=SubscriptionStatus)
async def get_subscription(
    user: Annotated[User, Depends(get_current_user)],
) -> SubscriptionStatus:
    """Get current user's subscription status and limits."""
    tier = get_tier(user.subscription_tier)
    rpm = tier.requests_per_min if tier else 10
    rpm_month = tier.requests_per_month if tier else 100

    return SubscriptionStatus(
        tier=user.subscription_tier,
        is_active=user.subscription_tier != "free" or True,
        expires_at=user.subscription_expires_at.isoformat()
        if user.subscription_expires_at
        else None,
        requests_per_min=rpm,
        requests_per_month=rpm_month,
    )


@router.post("/webhook/yookassa")
async def yookassa_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """YooKassa payment webhook endpoint.

    Called by YooKassa on payment.succeeded event.
    Updates user subscription and quota.
    """
    from app.services.billing import confirm_payment

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event = body.get("event", "")
    if event != "payment.succeeded":
        return {"status": "ignored"}

    payment_obj = body.get("object", {})
    payment_id = payment_obj.get("id", "")

    if not payment_id:
        raise HTTPException(status_code=400, detail="Missing payment ID")

    success = await confirm_payment(payment_id, db)
    if not success:
        raise HTTPException(status_code=422, detail="Failed to confirm payment")

    return {"status": "ok"}
