"""Billing service — YooKassa payment integration and quota management."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

# ──────────────────────────────────────────
# Tier definitions
# ──────────────────────────────────────────


@dataclass(frozen=True)
class BillingTier:
    slug: str
    name: str
    price_rub: int
    requests_per_min: int
    requests_per_month: int
    duration_days: int


TIERS: dict[str, BillingTier] = {
    "free": BillingTier(
        slug="free",
        name="Free (Sandbox)",
        price_rub=0,
        requests_per_min=10,
        requests_per_month=100,
        duration_days=30,
    ),
    "developer": BillingTier(
        slug="developer",
        name="Developer",
        price_rub=15_000,
        requests_per_min=300,
        requests_per_month=10_000,
        duration_days=30,
    ),
    "enterprise": BillingTier(
        slug="enterprise",
        name="Enterprise",
        price_rub=50_000,
        requests_per_min=3000,
        requests_per_month=100_000,
        duration_days=30,
    ),
}


def get_tier(tier_slug: str) -> BillingTier | None:
    return TIERS.get(tier_slug)


def get_default_tier() -> BillingTier:
    return TIERS["free"]


# ──────────────────────────────────────────
# YooKassa payment helpers
# ──────────────────────────────────────────

YOOKASSA_API_URL = "https://api.yookassa.ru/v3"


def _create_idempotency_key() -> str:
    return uuid.uuid4().hex


async def create_payment(
    tier_slug: str,
    user_email: str,
    description: str | None = None,
) -> dict | None:
    """Create a YooKassa payment for the given tier.

    Returns payment JSON with confirmation_url or None if YooKassa not configured.
    """
    tier = get_tier(tier_slug)
    if tier is None or tier.price_rub <= 0:
        return None

    if not settings.yookassa_shop_id or not settings.yookassa_secret_key:
        # YooKassa not configured — return mock for dev
        return _mock_payment(tier, user_email)

    async with httpx.AsyncClient() as client:
        auth = (settings.yookassa_shop_id, settings.yookassa_secret_key)
        payload = {
            "amount": {"value": f"{tier.price_rub:.2f}", "currency": "RUB"},
            "capture": True,
            "confirmation": {
                "type": "redirect",
                "return_url": f"{settings.dashboard_url}/billing/success",
            },
            "description": description or f"Тариф {tier.name} — {tier.price_rub} ₽",
            "metadata": {"tier": tier_slug, "user_email": user_email},
        }
        headers = {
            "Idempotence-Key": _create_idempotency_key(),
            "Content-Type": "application/json",
        }
        try:
            resp = await client.post(
                f"{YOOKASSA_API_URL}/payments",
                json=payload,
                auth=auth,
                headers=headers,
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError:
            return None


async def confirm_payment(
    payment_id: str,
    db: AsyncSession,
) -> bool:
    """Confirm a payment and activate the user's subscription.

    Called by YooKassa webhook (payment.succeeded).
    Returns True if subscription was activated.
    """
    if not settings.yookassa_shop_id or not settings.yookassa_secret_key:
        # Dev mode — fetch mock
        return await _confirm_mock_payment(payment_id, db)

    async with httpx.AsyncClient() as client:
        auth = (settings.yookassa_shop_id, settings.yookassa_secret_key)
        try:
            resp = await client.get(
                f"{YOOKASSA_API_URL}/payments/{payment_id}",
                auth=auth,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError:
            return False

    if data.get("status") != "succeeded":
        return False

    metadata = data.get("metadata", {})
    tier_slug = metadata.get("tier", "free")
    user_email = metadata.get("user_email", "")

    if not user_email:
        return False

    result = await db.execute(
        select(User).where(User.email == user_email)  # noqa: F821
    )
    user = result.scalar_one_or_none()
    if user is None:
        return False

    tier = get_tier(tier_slug) or get_default_tier()
    user.subscription_tier = tier_slug
    user.yookassa_payment_id = payment_id
    user.subscription_expires_at = datetime.now(UTC) + timedelta(days=tier.duration_days)
    await db.commit()
    return True


# ──────────────────────────────────────────
# Dev / Mock helpers
# ──────────────────────────────────────────

_MOCK_PAYMENTS: dict[str, dict] = {}


def _mock_payment(tier: BillingTier, user_email: str) -> dict:
    """Create a mock payment for local development."""
    payment_id = f"mock-{uuid.uuid4().hex[:12]}"
    _MOCK_PAYMENTS[payment_id] = {
        "id": payment_id,
        "status": "pending",
        "metadata": {"tier": tier.slug, "user_email": user_email},
    }
    return {
        "id": payment_id,
        "status": "pending",
        "confirmation": {
            "confirmation_url": f"/mock-payment/confirm?payment_id={payment_id}",
            "type": "redirect",
        },
    }


async def _confirm_mock_payment(payment_id: str, db: AsyncSession) -> bool:
    """Confirm a mock payment (dev mode)."""
    payment = _MOCK_PAYMENTS.get(payment_id)
    if payment is None:
        return False

    metadata = payment.get("metadata", {})
    tier_slug = metadata.get("tier", "free")
    user_email = metadata.get("user_email", "")

    if not user_email:
        return False

    from app.models.user import User

    result = await db.execute(select(User).where(User.email == user_email))
    user = result.scalar_one_or_none()
    if user is None:
        return False

    tier = get_tier(tier_slug) or get_default_tier()
    user.subscription_tier = tier_slug
    user.yookassa_payment_id = payment_id
    user.subscription_expires_at = datetime.now(UTC) + timedelta(days=tier.duration_days)
    await db.commit()
    return True
