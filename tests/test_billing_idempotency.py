from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import billing
from app.config import get_settings
from app.db.session import get_db
from app.models.processed_webhook import ProcessedWebhook
from app.models.user import User


def test_webhook_idempotent_payment_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YOOKASSA_WEBHOOK_ALLOW_UNVERIFIED", "true")
    get_settings.cache_clear()

    processed: dict[str, ProcessedWebhook] = {}
    user = User(id=1, email="pay@test.com", hashed_password="x")

    class _FakeResult:
        def __init__(self, row: object) -> None:
            self._row = row

        def scalar_one_or_none(self) -> object:
            return self._row

    class _FakeDb:
        async def execute(self, *args: object, **kwargs: object) -> _FakeResult:
            stmt = str(args[0])
            if "processed_webhooks" in stmt:
                return _FakeResult(processed.get("pay-123"))
            return _FakeResult(user)

        def add(self, obj: object) -> None:
            if isinstance(obj, ProcessedWebhook):
                processed[obj.payment_id] = obj

        async def commit(self) -> None:
            return None

    async def _fake_db():
        yield _FakeDb()

    app = FastAPI()
    app.include_router(billing.router, prefix="/v1/billing")
    app.dependency_overrides[get_db] = _fake_db

    body = {
        "event": "payment.succeeded",
        "object": {"id": "pay-123", "metadata": {"user_email": "pay@test.com"}},
    }
    with TestClient(app) as client:
        r1 = client.post(
            "/v1/billing/webhooks/yookassa",
            content=json.dumps(body),
            headers={"Content-Type": "application/json"},
        )
        r2 = client.post(
            "/v1/billing/webhooks/yookassa",
            content=json.dumps(body),
            headers={"Content-Type": "application/json"},
        )

    assert r1.status_code == 200
    assert r1.json()["status"] == "ok"
    assert r2.json()["status"] == "duplicate"
    get_settings.cache_clear()
