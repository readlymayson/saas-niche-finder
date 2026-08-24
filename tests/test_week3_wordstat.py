from __future__ import annotations

import asyncio

import httpx
import pytest

from app.config import Settings
from app.services.wordstat import (
    AsyncRateLimiter,
    WordstatAPIError,
    WordstatClient,
    YandexSearchApiClient,
    normalize_keywords,
    parse_dynamics_trend,
    parse_total_count,
    wordstat_cache_key,
)


def test_normalize_keywords_dedup_and_cap() -> None:
    got = normalize_keywords([" a ", "a", "b"], max_count=2)
    assert got == ["a", "b"]
    with pytest.raises(ValueError):
        normalize_keywords(["x", "y", "z"], max_count=2)


def test_wordstat_cache_key_stable() -> None:
    assert wordstat_cache_key(["b", "a"]) == wordstat_cache_key(["a", "b"])


def test_empty_wordstat_api_url_falls_back_to_default() -> None:
    # ${VAR:-} в compose даёт пустую строку — она не должна ломать URL
    settings = Settings(wordstat_api_url="")
    assert settings.wordstat_api_url == "https://searchapi.api.cloud.yandex.net/v2/wordstat"
    settings2 = Settings(wordstat_api_url="https://example.com/v2/wordstat")
    assert settings2.wordstat_api_url == "https://example.com/v2/wordstat"


def test_empty_wordstat_trend_days_falls_back_to_default() -> None:
    # ${VAR:-} в compose даёт пустую строку — она не должна ломать int
    settings = Settings(wordstat_trend_days="")
    assert settings.wordstat_trend_days == 400
    settings2 = Settings(wordstat_trend_days=180)
    assert settings2.wordstat_trend_days == 180


def test_parse_total_count_variants() -> None:
    assert parse_total_count({"totalCount": "12345"}) == 12345
    assert parse_total_count({"totalCount": 999}) == 999
    assert parse_total_count({}) == 0
    assert parse_total_count({"totalCount": None}) == 0
    assert parse_total_count({"totalCount": "abc"}) == 0


def test_parse_dynamics_trend_growing() -> None:
    payload = {
        "results": [
            {"date": "2026-01-01T00:00:00Z", "count": "100"},
            {"date": "2026-02-01T00:00:00Z", "count": "110"},
            {"date": "2026-03-01T00:00:00Z", "count": "300"},
            {"date": "2026-04-01T00:00:00Z", "count": "400"},
        ]
    }
    assert parse_dynamics_trend(payload) == "growing"


def test_parse_dynamics_trend_declining() -> None:
    payload = {
        "results": [
            {"date": "2026-01-01T00:00:00Z", "count": "500"},
            {"date": "2026-02-01T00:00:00Z", "count": "480"},
            {"date": "2026-03-01T00:00:00Z", "count": "100"},
            {"date": "2026-04-01T00:00:00Z", "count": "80"},
        ]
    }
    assert parse_dynamics_trend(payload) == "declining"


def test_parse_dynamics_trend_yoy_growing() -> None:
    """Сезонность: тот же месяц год назад выше/ниже — сравниваем YoY."""
    payload = {"results": [
        {"date": "2025-08-01T00:00:00Z", "count": "100"},
        {"date": "2025-09-01T00:00:00Z", "count": "105"},
        {"date": "2025-10-01T00:00:00Z", "count": "110"},
        {"date": "2025-11-01T00:00:00Z", "count": "115"},
        {"date": "2025-12-01T00:00:00Z", "count": "120"},
        {"date": "2026-01-01T00:00:00Z", "count": "125"},
        {"date": "2026-02-01T00:00:00Z", "count": "130"},
        {"date": "2026-03-01T00:00:00Z", "count": "135"},
        {"date": "2026-04-01T00:00:00Z", "count": "140"},
        {"date": "2026-05-01T00:00:00Z", "count": "145"},
        {"date": "2026-06-01T00:00:00Z", "count": "150"},
        {"date": "2026-07-01T00:00:00Z", "count": "155"},
        {"date": "2026-08-01T00:00:00Z", "count": "200"},  # vs 2025-08: +100%
    ]}
    assert parse_dynamics_trend(payload) == "growing"


def test_parse_dynamics_trend_yoy_declining() -> None:
    payload = {"results": [
        {"date": "2025-08-01T00:00:00Z", "count": "400"},
        {"date": "2025-09-01T00:00:00Z", "count": "390"},
        {"date": "2025-10-01T00:00:00Z", "count": "380"},
        {"date": "2025-11-01T00:00:00Z", "count": "370"},
        {"date": "2025-12-01T00:00:00Z", "count": "360"},
        {"date": "2026-01-01T00:00:00Z", "count": "350"},
        {"date": "2026-02-01T00:00:00Z", "count": "340"},
        {"date": "2026-03-01T00:00:00Z", "count": "330"},
        {"date": "2026-04-01T00:00:00Z", "count": "320"},
        {"date": "2026-05-01T00:00:00Z", "count": "310"},
        {"date": "2026-06-01T00:00:00Z", "count": "300"},
        {"date": "2026-07-01T00:00:00Z", "count": "290"},
        {"date": "2026-08-01T00:00:00Z", "count": "100"},  # vs 2025-08: -75%
    ]}
    assert parse_dynamics_trend(payload) == "declining"


def test_parse_dynamics_trend_yoy_stable() -> None:
    """YoY-стабильно: 2026-08 = 2025-08 (±5%) → stable, несмотря на всплески."""
    payload = {"results": [
        {"date": "2025-08-01T00:00:00Z", "count": "200"},
        {"date": "2025-09-01T00:00:00Z", "count": "190"},
        {"date": "2025-10-01T00:00:00Z", "count": "300"},
        {"date": "2025-11-01T00:00:00Z", "count": "180"},
        {"date": "2025-12-01T00:00:00Z", "count": "310"},
        {"date": "2026-01-01T00:00:00Z", "count": "170"},
        {"date": "2026-02-01T00:00:00Z", "count": "320"},
        {"date": "2026-03-01T00:00:00Z", "count": "160"},
        {"date": "2026-04-01T00:00:00Z", "count": "330"},
        {"date": "2026-05-01T00:00:00Z", "count": "150"},
        {"date": "2026-06-01T00:00:00Z", "count": "340"},
        {"date": "2026-07-01T00:00:00Z", "count": "140"},
        {"date": "2026-08-01T00:00:00Z", "count": "210"},  # vs 2025-08: +5%
    ]}
    assert parse_dynamics_trend(payload) == "stable"


def test_parse_dynamics_trend_stable_and_short() -> None:
    assert parse_dynamics_trend({"results": [{"count": "10"}, {"count": "11"}]}) == "stable"
    assert parse_dynamics_trend({"results": []}) == "stable"
    assert parse_dynamics_trend({}) == "stable"


def test_parse_dynamics_trend_dynamics_key_alias() -> None:
    """Агрегированный payload сервиса хранит динамику под ключом `dynamics`."""
    payload = {
        "dynamics": [
            {"date": "2026-01-01T00:00:00Z", "count": "100"},
            {"date": "2026-02-01T00:00:00Z", "count": "110"},
            {"date": "2026-03-01T00:00:00Z", "count": "300"},
            {"date": "2026-04-01T00:00:00Z", "count": "400"},
        ]
    }
    assert parse_dynamics_trend(payload) == "growing"


@pytest.mark.asyncio
async def test_rate_limiter_spacing(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []

    async def fake_sleep(t: float) -> None:
        sleeps.append(t)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    lim = AsyncRateLimiter(10.0)
    await lim.acquire()
    await lim.acquire()
    assert len(sleeps) == 1
    assert sleeps[0] > 0.09


@pytest.mark.asyncio
async def test_yandex_search_api_missing_key() -> None:
    # Явно без ключа, чтобы тест не зависел от .env
    settings = Settings(wordstat_api_key=None, wordstat_folder_id=None)
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={}))
    async with httpx.AsyncClient(transport=transport) as http:
        client = YandexSearchApiClient(settings, http_client=http)
        try:
            with pytest.raises(WordstatAPIError):
                await client.call("topRequests", {})
        finally:
            await client.aclose()


@pytest.mark.asyncio
async def test_wordstat_client_top_and_dynamics_roundtrip() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("Authorization", "").startswith("Api-key")
        if str(request.url).endswith("topRequests"):
            return httpx.Response(200, json={"totalCount": "42", "results": []})
        if str(request.url).endswith("dynamics"):
            return httpx.Response(200, json={"results": [{"count": "5"}, {"count": "7"}]})
        return httpx.Response(404, text="not found")

    settings = Settings(
        wordstat_api_key="test-key",
        yandex_gpt_folder_id="b1gXXXX",
    )
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        api = YandexSearchApiClient(settings, http_client=http)
        wc = WordstatClient(api)
        top = await wc.get_top("софт для такси")
        assert top.get("totalCount") == "42"
        dyn = await wc.get_dynamics("софт для такси")
        assert len(dyn.get("results")) == 2
        await api.aclose()


@pytest.mark.asyncio
async def test_yandex_gpt_client_mock() -> None:
    from app.services.yandex_gpt import YandexGptClient

    async def handler(request: httpx.Request) -> httpx.Response:
        assert "Api-Key" in request.headers.get("Authorization", "")
        return httpx.Response(
            200,
            json={"result": {"alternatives": [{"message": {"text": "ok"}}]}},
        )

    settings = Settings(
        yandex_gpt_api_key="key",
        yandex_gpt_folder_id="b1gXXXX",
    )
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        gpt = YandexGptClient(settings, http_client=http)
        out = await gpt.complete("тест")
        assert "result" in out
        await gpt.aclose()
