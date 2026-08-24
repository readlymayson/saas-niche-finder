"""
Клиент Яндекс Wordstat (Yandex Search API v2, синхронный REST) + кэш PostgreSQL.

Методы:
  - POST /v2/wordstat/topRequests   → GetTop (частотность за последние 30 дней)
  - POST /v2/wordstat/dynamics      → GetDynamics (динамика по периодам)

Аутентификация: API-ключ сервисного аккаунта (роль search-api.webSearch.user)
или IAM-токен, заголовок Authorization. Обязателен folderId (каталог).
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


def parse_total_count(payload: dict[str, Any]) -> int:
    """Извлечь суммарную частотность из ответа GetTop.

    Структура (Search API v2):
      {"totalCount": "123", "results": [{"phrase": "...", "count": "45"}], ...}
    Возвращает int(totalCount), при отсутствии — 0.
    """
    raw = payload.get("totalCount")
    if raw in (None, ""):
        return 0
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def parse_dynamics_trend(payload: dict[str, Any]) -> str:
    """Определить тренд по динамике частотности (GetDynamics).

    Читает сырой ответ GetDynamics (`results`) или агрегированный payload
    сервиса (`dynamics`). Точки отсортированы по дате (клиент возвращает
    хронологический порядок).

    Стратегия (устойчивая к сезонности):
      1. Если есть 12+ месячных точек — сравниваем последний месяц с тем же
         месяцем год назад (YoY, +-15% → growing/declining).
      2. Иначе — последнюю точку со средней предыдущих (похожий на старую
         логику порог, +-20%).
      3. Недостаточно данных (< 2 точек) → stable.
    """
    results = payload.get("results")
    if results is None:
        results = payload.get("dynamics")
    points: list[tuple[str, int]] = []
    for row in results or []:
        if not isinstance(row, dict):
            continue
        raw = row.get("count")
        if raw in (None, ""):
            continue
        try:
            points.append((row.get("date", ""), int(raw)))
        except (TypeError, ValueError):
            continue
    if len(points) < 2:
        return "stable"

    def _by_change(change: float, threshold: float) -> str:
        if change > threshold:
            return "growing"
        if change < -threshold:
            return "declining"
        return "stable"

    # 1. YoY: последняя месячная точка vs тот же месяц год назад
    last_date = points[-1][0]
    if len(points) >= 12 and len(last_date) >= 10:
        try:
            last_month = last_date[:7]  # "YYYY-MM"
            last_val = points[-1][1]
            year_before = str(int(last_month[:4]) - 1) + last_month[4:]
            for date, val in points:
                if date[:7] == year_before:
                    if val <= 0:
                        return "stable"
                    return _by_change((last_val - val) / val, 0.15)
        except (ValueError, TypeError):
            pass

    # 2. Fallback: последняя точка vs средняя предыдущих
    recent = points[-1][1]
    earlier = [v for _, v in points[:-1]]
    base = sum(earlier) / len(earlier)
    if base <= 0:
        return "stable"
    return _by_change((recent - base) / base, 0.20)


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


class YandexSearchApiClient:
    """POST на `{base}/{method}` (Search API v2) с Authorization: Api-key / Bearer."""

    def __init__(
        self,
        settings: Settings,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._base = settings.wordstat_api_url.rstrip("/")
        self._limiter = AsyncRateLimiter(settings.wordstat_max_rps)
        self._own_client = http_client is None
        self._client = http_client or httpx.AsyncClient(timeout=120.0)

    async def aclose(self) -> None:
        if self._own_client:
            await self._client.aclose()

    def _headers(self) -> dict[str, str]:
        key = self._settings.wordstat_api_key
        if not key:
            msg = "Задайте WORDSTAT_API_KEY (API-ключ сервисного аккаунта Yandex Search API)"
            raise WordstatAPIError({"error_string": msg})
        # Search API v2 принимает API-ключ как "Api-key <ключ>",
        # IAM-токен (JWT t1.../eyJ...) — как "Bearer <токен>".
        if key.startswith("t1.") or key.startswith("eyJ"):
            auth = f"Bearer {key}"
        else:
            auth = f"Api-key {key}"
        return {
            "Authorization": auth,
            "Content-Type": "application/json; charset=UTF-8",
        }

    def _folder_id(self) -> str:
        folder = self._settings.wordstat_folder_id or self._settings.yandex_gpt_folder_id
        if not folder:
            msg = "Задайте WORDSTAT_FOLDER_ID (или YANDEX_GPT_FOLDER_ID)"
            raise WordstatAPIError({"error_string": msg})
        return folder

    async def call(self, method: str, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base}/{method.lstrip('/')}"
        await self._limiter.acquire()
        resp = await self._client.post(url, headers=self._headers(), json=body)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict):
            return {}
        err = data.get("error")
        if err:
            if isinstance(err, dict):
                raise WordstatAPIError(err)
            raise WordstatAPIError({"error": err})
        return data


class WordstatClient:
    """Вызовы Wordstat Search API v2: GetTop и GetDynamics."""

    def __init__(self, api: YandexSearchApiClient) -> None:
        self._api = api

    def _base_body(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "regions": [self._api._settings.wordstat_region],
            "devices": ["DEVICE_ALL"],
            "folderId": self._api._folder_id(),
        }
        return body

    async def get_top(self, phrase: str, *, num_phrases: int = 10) -> dict[str, Any]:
        """GetTop: частотность фразы за последние 30 дней."""
        body: dict[str, Any] = {"phrase": phrase, "numPhrases": num_phrases}
        body.update(self._base_body())
        return await self._api.call("topRequests", body)

    async def get_dynamics(
        self,
        phrase: str,
        *,
        period: str = "PERIOD_MONTHLY",
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> dict[str, Any]:
        """GetDynamics: динамика частотности фразы по периодам.

        По умолчанию — окно из wordstat_trend_days (365 дней, чтобы покрыть
        тот же месяц год назад для YoY-тренда) помесячно. Для PERIOD_MONTHLY
        API требует fromDate = первый день месяца, toDate — последний день
        месяца (иначе 400 InvalidArgument).
        """
        now = datetime.now(UTC)
        if to_date:
            to_dt = datetime.fromisoformat(to_date.replace("Z", "+00:00"))
        else:
            to_dt = now
        if from_date:
            from_dt = datetime.fromisoformat(from_date.replace("Z", "+00:00"))
        else:
            from_dt = now - timedelta(days=self._api._settings.wordstat_trend_days)

        if period == "PERIOD_MONTHLY":
            # fromDate → 1-е число месяца; toDate → последний день месяца
            from_dt = from_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if to_dt.month == 12:
                next_month = to_dt.replace(year=to_dt.year + 1, month=1, day=1)
            else:
                next_month = to_dt.replace(month=to_dt.month + 1, day=1)
            last_day = next_month - timedelta(days=1)
            to_dt = last_day.replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            from_dt = from_dt.replace(hour=0, minute=0, second=0, microsecond=0)
            to_dt = to_dt.replace(hour=0, minute=0, second=0, microsecond=0)

        body: dict[str, Any] = {
            "phrase": phrase,
            "period": period,
            "fromDate": from_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "toDate": to_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        body.update(self._base_body())
        return await self._api.call("dynamics", body)


class WordstatService:
    """Сервис: GetTop (объём) + GetDynamics (тренд) с кэшем в PostgreSQL."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: WordstatClient | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._api = YandexSearchApiClient(self._settings)
        self._client = client or WordstatClient(self._api)

    async def aclose(self) -> None:
        await self._api.aclose()

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

        phrase = normalized[0]
        top = await self._client.get_top(phrase)
        dynamics = await self._client.get_dynamics(phrase)

        report_data = {
            "totalCount": top.get("totalCount"),
            "top": top.get("results") or [],
            "associations": top.get("associations") or [],
            "dynamics": dynamics.get("results") or [],
        }
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
            "totalCount": top.get("totalCount"),
        }
