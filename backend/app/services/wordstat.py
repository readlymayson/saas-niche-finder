"""
Клиент Яндекс.Директ JSON API v5: Вордстат + кэш PostgreSQL (TTL 7 дней).

Сверьте method/params с актуальной справкой Директа (пример — wordstatreports в ТЗ).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.models.wordstat_cache import WordstatCache


class WordstatAPIError(Exception):
    def __init__(self, payload: dict[str, Any]) -> None:
        super().__init__(str(payload))
        self.payload = payload


def normalize_keywords(keywords: list[str], *, max_count: int) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for k in keywords:
        s = " ".join((k or "").strip().split())
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    if len(out) > max_count:
        msg = f"Не более {max_count} ключевых фраз в одном запросе"
        raise ValueError(msg)
    if not out:
        msg = "Пустой список ключевых фраз"
        raise ValueError(msg)
    return out


def wordstat_cache_key(normalized_keywords: list[str]) -> str:
    sorted_kw = sorted(normalized_keywords)
    payload = json.dumps(sorted_kw, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AsyncRateLimiter:
    def __init__(self, max_per_second: float) -> None:
        self._interval = 1.0 / max_per_second if max_per_second > 0 else 0.0
        self._lock = asyncio.Lock()
        self._next_at = 0.0

    async def acquire(self) -> None:
        if self._interval <= 0:
            return
        async with self._lock:
            now = time.monotonic()
            wait = self._next_at - now
            if wait > 0:
                await asyncio.sleep(wait)
            self._next_at = time.monotonic() + self._interval


class YandexDirectJsonClient:
    """POST на `.../json/v5/{service}` с Bearer OAuth."""

    def __init__(
        self,
        settings: Settings,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._base = settings.yandex_direct_api_url.rstrip("/")
        self._limiter = AsyncRateLimiter(settings.wordstat_max_rps)
        self._own_client = http_client is None
        self._client = http_client or httpx.AsyncClient(timeout=120.0)

    async def aclose(self) -> None:
        if self._own_client:
            await self._client.aclose()

    def _headers(self) -> dict[str, str]:
        token = self._settings.yandex_direct_oauth_token
        if not token:
            msg = "Задайте YANDEX_DIRECT_OAUTH_TOKEN"
            raise WordstatAPIError({"error_string": msg})
        h: dict[str, str] = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
        }
        if self._settings.yandex_direct_client_login:
            h["Client-Login"] = self._settings.yandex_direct_client_login
        return h

    async def call(self, service: str, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base}/{service.lstrip('/')}"
        await self._limiter.acquire()
        resp = await self._client.post(url, headers=self._headers(), json=body)
        resp.raise_for_status()
        data = resp.json()
        err = data.get("error")
        if err:
            if isinstance(err, dict):
                raise WordstatAPIError(err)
            raise WordstatAPIError({"error": err})
        result = data.get("result")
        return result if isinstance(result, dict) else {}


def _pick_report_id(obj: dict[str, Any]) -> str | None:
    for key in ("ReportId", "reportId", "report_id", "Id"):
        v = obj.get(key)
        if v is not None:
            return str(v)
    return None


class WordstatClient:
    def __init__(self, direct: YandexDirectJsonClient) -> None:
        self._d = direct

    async def request_wordstat_report(self, keywords: list[str]) -> str:
        """Запрос отчёта Вордстат: method=get, Keywords, WORDSTAT_REPORT (как в ТЗ)."""
        body = {
            "method": "get",
            "params": {
                "SelectionCriteria": {"Keywords": keywords},
                "ReportType": "WORDSTAT_REPORT",
            },
        }
        res = await self._d.call("wordstatreports", body)
        rid = _pick_report_id(res)
        if not rid and isinstance(res.get("Reports"), list) and res["Reports"]:
            rid = _pick_report_id(res["Reports"][0])
        if not rid:
            msg = "Не удалось извлечь ReportId из ответа wordstatreports"
            raise WordstatAPIError({"error_string": msg, "result": res})
        return rid

    async def fetch_report_json(
        self,
        report_id: str,
        *,
        retries: int = 30,
        delay_sec: float = 2.0,
    ) -> dict[str, Any]:
        """
        Получить готовый отчёт. При отложенной генерации — повторы с паузой.
        """
        last_err: Exception | None = None
        for _ in range(max(1, retries)):
            body = {"method": "get", "params": {"SelectionCriteria": {"ReportIds": [report_id]}}}
            try:
                res = await self._d.call("reports", body)
                return res
            except WordstatAPIError as e:
                last_err = e
                detail = str(e.payload).lower()
                if "not ready" in detail or "еще" in detail or "wait" in detail:
                    await asyncio.sleep(delay_sec)
                    continue
                raise
            except httpx.HTTPStatusError as e:
                last_err = e
                if e.response.status_code in (201, 202):
                    await asyncio.sleep(delay_sec)
                    continue
                raise
        if last_err:
            raise last_err
        msg = "Истекло время ожидания отчёта Вордстат"
        raise TimeoutError(msg)


class WordstatService:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: WordstatClient | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._direct = YandexDirectJsonClient(self._settings)
        self._client = client or WordstatClient(self._direct)

    async def aclose(self) -> None:
        await self._direct.aclose()

    async def get_keyword_stats(
        self,
        session: AsyncSession,
        keywords: list[str],
        *,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        max_k = self._settings.wordstat_max_keywords_per_report
        normalized = normalize_keywords(keywords, max_count=max_k)
        key = wordstat_cache_key(normalized)
        now = datetime.now(UTC)
        if not force_refresh:
            q = await session.execute(
                select(WordstatCache).where(
                    WordstatCache.cache_key == key,
                    WordstatCache.expires_at > now,
                )
            )
            hit = q.scalar_one_or_none()
            if hit:
                return {"cached": True, "keywords": hit.keywords, "payload": hit.report_payload}
        report_id = await self._client.request_wordstat_report(normalized)
        report_data = await self._client.fetch_report_json(report_id)
        ttl_days = self._settings.wordstat_cache_ttl_days
        expires = now + timedelta(days=ttl_days)

        row = await session.execute(select(WordstatCache).where(WordstatCache.cache_key == key))
        existing = row.scalar_one_or_none()
        if existing:
            existing.keywords = normalized
            existing.report_payload = report_data
            existing.fetched_at = now
            existing.expires_at = expires
        else:
            session.add(
                WordstatCache(
                    cache_key=key,
                    keywords=normalized,
                    report_payload=report_data,
                    fetched_at=now,
                    expires_at=expires,
                )
            )
        await session.commit()
        return {
            "cached": False,
            "keywords": normalized,
            "payload": report_data,
            "report_id": report_id,
        }
