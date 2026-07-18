from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings, settings
from app.db.session import get_db
from app.deps import get_current_user
from app.models.processed_webhook import ProcessedWebhook
from app.models.user import User

router = APIRouter()


class CreatePaymentResponse(BaseModel):
    payment_id: str
    confirmation_url: str
    amount_rub: str
    human_gate_required: bool = True
    message: str | None = None


class YooKassaWebhookPayload(BaseModel):
    event: str
    object: dict[str, Any] = Field(default_factory=dict)


def _yookassa_configured() -> bool:
    return bool(settings.yookassa_shop_id and settings.yookassa_secret_key)


def _prod_billing_allowed() -> bool:
    return os.environ.get("SYNGATE_ALLOW_YOOKASSA_PROD", "").lower() in ("1", "true", "yes")


def _create_live_payment(user: User) -> CreatePaymentResponse:
    from yookassa import Configuration, Payment

    cfg = get_settings()
    Configuration.configure(cfg.yookassa_shop_id, cfg.yookassa_secret_key)
    idempotence_key = str(uuid.uuid4())
    payload = {
        "amount": {"value": cfg.yookassa_amount_rub, "currency": "RUB"},
        "confirmation": {"type": "redirect", "return_url": cfg.yookassa_return_url},
        "capture": True,
        "save_payment_method": True,
        "description": "Подписка SaaS Niche Finder Pro",
        "metadata": {"user_email": user.email},
    }
    payment = Payment.create(payload, idempotence_key)
    confirmation = payment.confirmation
    url = getattr(confirmation, "confirmation_url", None) or cfg.yookassa_return_url
    return CreatePaymentResponse(
        payment_id=payment.id,
        confirmation_url=url,
        amount_rub=cfg.yookassa_amount_rub,
        human_gate_required=False,
        message=None,
    )


@router.post("/create-payment", response_model=CreatePaymentResponse)
async def create_payment(
    user: Annotated[User, Depends(get_current_user)],
) -> CreatePaymentResponse:
    if not _yookassa_configured():
        pid = f"stub-{uuid.uuid4().hex[:12]}"
        return CreatePaymentResponse(
            payment_id=pid,
            confirmation_url=f"{settings.yookassa_return_url}?payment_id={pid}&mode=stub",
            amount_rub=settings.yookassa_amount_rub,
            human_gate_required=True,
            message=(
                "ЮKassa не настроена (.env). Merchant + SYNGATE_ALLOW_YOOKASSA_PROD для prod."
            ),
        )
    if not _prod_billing_allowed():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Prod billing заблокирован SynGate. "
                "Нужен SYNGATE_ALLOW_YOOKASSA_PROD после human approve."
            ),
        )
    try:
        return _create_live_payment(user)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"ЮKassa Payment.create failed: {e}",
        ) from e


def _verify_yookassa_signature(body: bytes, signature: str | None) -> bool:
    if settings.yookassa_webhook_allow_unverified:
        return True
    secret = settings.yookassa_secret_key
    if not secret or not signature:
        return False
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, signature)


@router.post("/webhooks/yookassa")
async def yookassa_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    raw = await request.body()
    signature = request.headers.get("X-YooKassa-Signature")
    unverified_ok = get_settings().yookassa_webhook_allow_unverified
    if not _verify_yookassa_signature(raw, signature) and not unverified_ok:
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise HTTPException(status_code=400, detail="Invalid JSON") from e

    event = str(data.get("event", ""))
    obj = data.get("object") or {}
    if event != "payment.succeeded":
        return {"status": "ignored", "event": event}

    payment_id = str(obj.get("id") or "")
    if payment_id:
        seen = await db.execute(
            select(ProcessedWebhook).where(ProcessedWebhook.payment_id == payment_id)
        )
        if seen.scalar_one_or_none() is not None:
            return {"status": "duplicate", "payment_id": payment_id}

    metadata = obj.get("metadata") or {}
    email = metadata.get("user_email")
    if not isinstance(email, str):
        return {"status": "ignored", "reason": "no user_email in metadata"}

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        return {"status": "ignored", "reason": "user not found"}

    user.subscription_plan = "pro"
    user.subscription_status = "active"
    if payment_id:
        db.add(ProcessedWebhook(payment_id=payment_id, event=event))
    await db.commit()
    return {"status": "ok", "user": email}
