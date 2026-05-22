from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import ready


def test_ready_endpoint_db_ok() -> None:
    app = FastAPI()
    app.get("/ready")(ready)

    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock()

    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("app.main.engine") as engine:
        engine.connect.return_value = mock_cm
        with TestClient(app) as client:
            resp = client.get("/ready")

    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


def test_ready_endpoint_db_down() -> None:
    app = FastAPI()
    app.get("/ready")(ready)

    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(side_effect=ConnectionError("db down"))
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("app.main.engine") as engine:
        engine.connect.return_value = mock_cm
        with TestClient(app) as client:
            resp = client.get("/ready")

    assert resp.status_code == 200
    assert resp.json()["status"] == "degraded"
