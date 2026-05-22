from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import billing
from app.db.session import get_db
from app.deps import get_current_user
from app.models.user import User


async def _user() -> User:
    return User(id=1, email="pay@test.com", hashed_password="x")


def test_create_payment_stub_without_yookassa() -> None:
    app = FastAPI()
    app.include_router(billing.router, prefix="/v1/billing")
    app.dependency_overrides[get_current_user] = _user

    with TestClient(app) as client:
        resp = client.post("/v1/billing/create-payment")

    assert resp.status_code == 200
    data = resp.json()
    assert data["human_gate_required"] is True
    assert "stub-" in data["payment_id"]


def test_webhook_activates_pro(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import get_settings

    monkeypatch.setenv("YOOKASSA_WEBHOOK_ALLOW_UNVERIFIED", "true")
    get_settings.cache_clear()

    app = FastAPI()
    app.include_router(billing.router, prefix="/v1/billing")

    class _FakeResult:
        def scalar_one_or_none(self) -> User:
            return User(id=1, email="pay@test.com", hashed_password="x")

    class _FakeDb:
        async def execute(self, *args: object, **kwargs: object) -> _FakeResult:
            return _FakeResult()

        async def commit(self) -> None:
            return None

    async def _fake_db():
        yield _FakeDb()

    app.dependency_overrides[get_db] = _fake_db

    body = {
        "event": "payment.succeeded",
        "object": {"metadata": {"user_email": "pay@test.com"}},
    }
    with TestClient(app) as client:
        resp = client.post(
            "/v1/billing/webhooks/yookassa",
            content=json.dumps(body),
            headers={"Content-Type": "application/json"},
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    get_settings.cache_clear()
