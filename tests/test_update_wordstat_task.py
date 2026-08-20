"""Regression tests for the update_wordstat Celery task."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from app.workers.tasks import update_wordstat


class _FakeNiche:
    def __init__(self, niche_id: int, name: str) -> None:
        self.id = niche_id
        self.niche_name = name
        self.wordstat_requests = 0
        self.wordstat_trend = "stable"


class _FakeSession:
    """Async context manager session: hands out niches, tracks commits."""

    def __init__(self, niches: list[_FakeNiche]) -> None:
        self._niches = niches
        self.committed = False

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    async def execute(self, stmt: Any) -> MagicMock:
        res = MagicMock()
        res.scalars.return_value.all.return_value = self._niches
        return res

    async def commit(self) -> None:
        self.committed = True


def _fake_service(
    total_count: int, trend_for: dict[str, str] | None = None
) -> MagicMock:
    svc = MagicMock()
    trend_for = trend_for or {}

    def _dynamics(trend: str) -> list[dict[str, str]]:
        if trend == "growing":
            return [
                {"date": "2026-01-01T00:00:00Z", "count": "100"},
                {"date": "2026-02-01T00:00:00Z", "count": "110"},
                {"date": "2026-03-01T00:00:00Z", "count": "300"},
                {"date": "2026-04-01T00:00:00Z", "count": "400"},
            ]
        if trend == "declining":
            return [
                {"date": "2026-01-01T00:00:00Z", "count": "500"},
                {"date": "2026-02-01T00:00:00Z", "count": "480"},
                {"date": "2026-03-01T00:00:00Z", "count": "100"},
                {"date": "2026-04-01T00:00:00Z", "count": "80"},
            ]
        return [
            {"date": "2026-01-01T00:00:00Z", "count": "100"},
            {"date": "2026-02-01T00:00:00Z", "count": "105"},
            {"date": "2026-03-01T00:00:00Z", "count": "102"},
            {"date": "2026-04-01T00:00:00Z", "count": "110"},
        ]

    async def _get_keyword_stats(session: Any, keywords: list[str]) -> dict[str, Any]:
        phrase = keywords[0] if keywords else ""
        trend = trend_for.get(phrase, "stable")
        payload = {
            "totalCount": str(total_count),
            "top": [],
            "associations": [],
            "dynamics": _dynamics(trend),
        }
        return {"cached": False, "keywords": keywords, "payload": payload}

    svc.get_keyword_stats = _get_keyword_stats
    svc.aclose = AsyncMock()
    return svc


def _run_with(
    session: _FakeSession,
    total_count: int = 1234,
    trend_for: dict[str, str] | None = None,
) -> dict:
    with (
        patch("app.services.wordstat.WordstatService") as svc_cls,
        patch("app.workers.tasks.async_session_maker", return_value=session),
    ):
        svc_cls.return_value = _fake_service(total_count, trend_for)
        return update_wordstat()


def test_update_wordstat_sets_requests_and_trend() -> None:
    niches = [
        _FakeNiche(1, "маркетплейс для фермеров"),
        _FakeNiche(2, "растущий сегмент SaaS"),
    ]
    session = _FakeSession(niches)

    stats = _run_with(
        session,
        total_count=4321,
        trend_for={"растущий сегмент SaaS": "growing"},
    )

    assert stats["niches_updated"] == 2
    assert stats["errors"] == 0
    assert niches[0].wordstat_requests == 4321
    assert niches[0].wordstat_trend == "stable"
    # Рост в динамике GetDynamics → growing
    assert niches[1].wordstat_trend == "growing"
    assert session.committed


def test_update_wordstat_survives_single_niche_error() -> None:
    niches = [_FakeNiche(1, "ниша с ошибкой")]
    session = _FakeSession(niches)

    def _boom(session: Any, keywords: list[str]) -> dict[str, Any]:
        raise RuntimeError("Direct API недоступен")

    with (
        patch("app.services.wordstat.WordstatService") as svc_cls,
        patch("app.workers.tasks.async_session_maker", return_value=session),
    ):
        svc = MagicMock()
        svc.get_keyword_stats = _boom
        svc.aclose = AsyncMock()
        svc_cls.return_value = svc
        stats = update_wordstat()

    assert stats["niches_updated"] == 0
    assert stats["errors"] == 1
    assert session.committed
