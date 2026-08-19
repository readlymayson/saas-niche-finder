from __future__ import annotations

import asyncio

import httpx
import pytest

from app.config import Settings
from app.services.wordstat import (
    AsyncRateLimiter,
    WordstatAPIError,
    WordstatClient,
    YandexDirectJsonClient,
    extract_total_shows,
    normalize_keywords,
    wordstat_cache_key,
)


def test_normalize_keywords_dedup_and_cap() -> None:
    got = normalize_keywords([" a ", "a", "b"], max_count=2)
    assert got == ["a", "b"]
    with pytest.raises(ValueError):
        normalize_keywords(["x", "y", "z"], max_count=2)


def test_wordstat_cache_key_stable() -> None:
    assert wordstat_cache_key(["b", "a"]) == wordstat_cache_key(["a", "b"])


def test_extract_total_shows_sums_report_data() -> None:
    payload = {
        "Reports": [
            {
                "ReportData": [
                    {"Shows": 1000, "SearchedWith": [{"Shows": 50}, {"Shows": 25}]},
                    {"Shows": 200, "SearchedWith": []},
                ]
            },
            {"ReportData": [{"shows": 75}]},
        ]
    }
    assert extract_total_shows(payload) == 1350


def test_extract_total_shows_empty_payload() -> None:
    assert extract_total_shows({}) == 0
    assert extract_total_shows({"Reports": None}) == 0
    assert extract_total_shows({"Reports": [{"ReportData": "nope"}]}) == 0


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
async def test_yandex_direct_missing_token() -> None:
    settings = Settings()
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={}))) as http:
        client = YandexDirectJsonClient(settings, http_client=http)
        try:
            with pytest.raises(WordstatAPIError):
                await client.call("reports", {})
        finally:
            await client.aclose()


@pytest.mark.asyncio
async def test_wordstat_client_report_roundtrip() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).rstrip("/").endswith("wordstatreports"):
            return httpx.Response(200, json={"result": {"ReportId": 42}})
        if str(request.url).rstrip("/").endswith("reports"):
            return httpx.Response(200, json={"result": {"status": "done"}})
        return httpx.Response(404, text="not found")

    settings = Settings(yandex_direct_oauth_token="test-token")
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        direct = YandexDirectJsonClient(settings, http_client=http)
        wc = WordstatClient(direct)
        rid = await wc.request_wordstat_report(["софт для такси"])
        assert rid == "42"
        data = await wc.fetch_report_json(rid, retries=1)
        assert data.get("status") == "done"
        await direct.aclose()


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
