"""Regression tests for v1 router route ordering.

Static paths like /v1/niches/export must be registered BEFORE dynamic
paths like /v1/niches/{niche_id}, otherwise FastAPI matches "export"
as an integer niche_id and returns 422 instead of streaming the export.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api import v1


class _FakeScalars:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return self._rows


class _FakeResult:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def scalars(self) -> _FakeScalars:
        return _FakeScalars(self._rows)


class _FakeDb:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    async def execute(self, *args: object, **kwargs: object) -> _FakeResult:
        _ = args, kwargs
        return _FakeResult(self._rows)


async def _fake_db() -> _FakeDb:
    return _FakeDb([])


def test_export_route_registered_before_dynamic_niche_id() -> None:
    """Static /niches/export must precede /niches/{niche_id} in route order."""
    paths = [r.path for r in v1.router.routes]
    export_index = paths.index("/niches/export")
    dynamic_index = paths.index("/niches/{niche_id}")
    assert export_index < dynamic_index, (
        "/niches/export must be registered before /niches/{niche_id}, "
        f"got export at {export_index}, dynamic at {dynamic_index}: {paths}"
    )


def test_export_endpoint_returns_200_not_422() -> None:
    """GET /v1/niches/export must hit the export handler, not niche_id path."""
    from fastapi import FastAPI

    from app.deps import verify_api_token

    app = FastAPI()
    app.include_router(v1.router, prefix="/v1")
    app.dependency_overrides[verify_api_token] = lambda: None
    app.dependency_overrides[v1.get_db] = _fake_db

    with TestClient(app) as client:
        resp = client.get("/v1/niches/export?format=csv")

    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/csv")
    assert "id,niche_name" in resp.text
