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
    if os.environ.get("SYNGATE_ALLOW_YOOKASSA_PROD", "").lower() in ("1", "true", "yes"):
        return True
    return False


@router.post("/create-payment", response_model=CreatePaymentResponse)
async def create_payment(
    user: Annotated[User, Depends(get_current_user)],
) -> CreatePaymentResponse:
    _ = user
    if not _yookassa_configured():
        pid = f"stub-{uuid.uuid4().hex[:12]}"
        return CreatePaymentResponse(
            payment_id=pid,
            confirmation_url=f"{settings.yookassa_return_url}?payment_id={pid}&mode=stub",
            amount_rub="990.00",
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
    pid = f"live-{uuid.uuid4().hex[:12]}"
    return CreatePaymentResponse(
        payment_id=pid,
        confirmation_url=f"{settings.yookassa_return_url}?payment_id={pid}",
        amount_rub="990.00",
        human_gate_required=False,
        message="Интеграция ЮKassa: подключите SDK yookassa для реального confirmation_url.",
    )


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

    event = data.get("event")
    obj = data.get("object") or {}
    if event != "payment.succeeded":
        return {"status": "ignored", "event": str(event)}

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
    await db.commit()
    return {"status": "ok", "user": email}
