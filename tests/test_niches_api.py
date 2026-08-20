from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import niches
from app.config import settings
from app.deps import verify_api_token
from app.models.niche_idea import NicheIdea


class _FakeResult:
    def __init__(self, rows: list[NicheIdea]) -> None:
        self._rows = rows

    def scalars(self) -> list[NicheIdea]:
        return self._rows


class _FakeDb:
    async def execute(self, *args: object, **kwargs: object) -> _FakeResult:
        _ = args, kwargs
        return _FakeResult(
            [
                NicheIdea(
                    id=1, slug="crm-ru", title="CRM для SMB",
                    summary="Учет лидов", score=7.2,
                ),
                NicheIdea(
                    id=2, slug="hr-ats", title="ATS для рекрутинга",
                    summary="Подбор", score=5.5,
                ),
            ]
        )


async def _fake_db() -> AsyncGenerator[_FakeDb, None]:
    yield _FakeDb()


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.api_token}"}


def test_get_top_niches_returns_rows() -> None:
    app = FastAPI()
    app.include_router(niches.router, prefix="/v1")
    app.dependency_overrides[verify_api_token] = lambda: None
    app.dependency_overrides[niches.get_db] = _fake_db

    with TestClient(app) as client:
        resp = client.get("/v1/niches/top?limit=1&min_score=0", headers=_auth_headers())

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert data[0]["slug"] == "crm-ru"
