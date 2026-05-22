from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import auth
from app.db.session import get_db


class _UnusedDb:
    """Стенд сессии БД: при 422 тело не проходит валидацию, хендлер не вызывается."""


async def _fake_db() -> AsyncGenerator[_UnusedDb, None]:
    yield _UnusedDb()


def test_register_short_password_returns_422() -> None:
    app = FastAPI()
    app.include_router(auth.router, prefix="/auth")
    app.dependency_overrides[get_db] = _fake_db

    with TestClient(app) as client:
        resp = client.post(
            "/auth/register",
            json={"email": "user@example.com", "password": "short"},
        )

    assert resp.status_code == 422
