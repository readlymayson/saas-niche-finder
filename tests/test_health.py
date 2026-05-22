from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import health


def test_health_endpoint_returns_ok() -> None:
    app = FastAPI()
    app.add_api_route("/health", health, methods=["GET"])
    with TestClient(app) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
