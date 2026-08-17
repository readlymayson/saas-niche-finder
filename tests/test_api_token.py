"""Tests for the static API token auth (X-Api-Token / Bearer)."""

from __future__ import annotations

import hmac

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import v1
from app.config import settings
from app.db.session import get_db
from app.deps import _token_matches


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(v1.router, prefix="/v1")

    async def _no_db():
        raise RuntimeError("no db in test")

    # Valid-token tests should pass auth and then fail on DB access (500),
    # not crash the process with a raw ConnectionError.
    app.dependency_overrides[get_db] = _no_db
    return app


def test_missing_token_returns_401() -> None:
    app = _make_app()
    with TestClient(app) as client:
        resp = client.get("/v1/niches/top?limit=1")
    assert resp.status_code == 401


def test_wrong_token_returns_401() -> None:
    app = _make_app()
    with TestClient(app) as client:
        resp = client.get("/v1/niches/top?limit=1", headers={"X-Api-Token": "wrong-token"})
    assert resp.status_code == 401


def test_valid_token_via_header_passes_auth() -> None:
    """Valid token via X-Api-Token passes auth — endpoint then fails on DB (500), NOT 401."""
    app = _make_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get("/v1/niches/top?limit=1", headers={"X-Api-Token": settings.api_token})
    assert resp.status_code != 401


def test_valid_token_via_bearer_passes_auth() -> None:
    app = _make_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get(
            "/v1/niches/top?limit=1",
            headers={"Authorization": f"Bearer {settings.api_token}"},
        )
    assert resp.status_code != 401


def test_token_matches_constant_time() -> None:
    assert _token_matches(settings.api_token) is True
    assert _token_matches("") is False
    assert _token_matches(None) is False
    assert _token_matches("not-the-token") is False


def test_token_matching_is_case_sensitive() -> None:
    assert _token_matches(settings.api_token.upper()) is False


def test_hmac_compare_digest_behavior() -> None:
    # sanity: hmac.compare_digest with bytes behaves as expected
    a = b"abc"
    b = b"abc"
    c = b"abd"
    assert hmac.compare_digest(a, b)
    assert not hmac.compare_digest(a, c)


@pytest.mark.parametrize("header_value", ["", "   ", "Bearer", "Bearer "])
def test_malformed_authorization_returns_401(header_value: str) -> None:
    app = _make_app()
    with TestClient(app) as client:
        resp = client.get(
            "/v1/niches/top?limit=1",
            headers={"Authorization": header_value},
        )
    assert resp.status_code == 401
