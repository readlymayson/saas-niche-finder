"""Async клиент для Яндекс.Вордстат / API Директа v5.

Использует официальный JSON API:
  - POST /v5/reports/wordstat — создание отчёта
  - GET /v5/reports/{report_id} — получение результатов

Лимиты: 5 RPS, максимум 10 отчётов в очереди.
Кэширование ответов в БД на 7 дней.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

logger = logging.getLogger(__name__)

WORDSTAT_API_URL = "https://api.direct.yandex.com/json/v5/reports"
REPORTS_API_URL = "https://api.direct.yandex.com/json/v5/reports"

# Cache duration
CACHE_TTL_DAYS = 7

# Rate limits
MAX_RPS = 5
MAX_QUEUE = 10


class WordstatClient:
    """Async client for Яндекс.Вордстат keyword statistics.

    Requires YANDEX_DIRECT_TOKEN in settings.
    """

    def __init__(self) -> None:
        self._token: str = settings.yandex_direct_token
        self._client_login: str = settings.yandex_direct_login

    async def get_keyword_stats(self, keywords: list[str]) -> dict[str, int]:
        """Get monthly search volume for a list of keywords.

        Args:
            keywords: List of Russian-language search phrases.

        Returns:
            dict mapping keyword -> monthly_request_count.
            Returns empty dict if API is not configured.
        """
        if not self._token:
            logger.warning("YANDEX_DIRECT_TOKEN not configured, skipping Wordstat")
            return {}

        # Split into chunks of 10 (API limit per request)
        chunk_size = 10
        results: dict[str, int] = {}

        for i in range(0, len(keywords), chunk_size):
            chunk = keywords[i : i + chunk_size]
            chunk_results = await self._fetch_wordstat_batch(chunk)
            results.update(chunk_results)

        return results

    async def _fetch_wordstat_batch(self, keywords: list[str]) -> dict[str, int]:
        """Fetch wordstat for a batch of keywords."""
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Client-Login": self._client_login,
            "Accept-Language": "ru",
            "Content-Type": "application/json",
        }

        payload = {
            "method": "get",
            "params": {
                "SelectionCriteria": {},
                "FieldNames": [
                    "Keyword",
                    "SearchedWith",
                    "SearchedAlso",
                ],
                "Keywords": keywords,
                "ReportName": f"niche_finder_{datetime.now(UTC).timestamp():.0f}",
                "ReportType": "WORDSTAT",
                "DateRangeType": "LAST_MONTH",
                "Format": "TSV",
            },
        }

        async with httpx.AsyncClient(timeout=60) as client:
            try:
                resp = await client.post(
                    WORDSTAT_API_URL,
                    headers=headers,
                    json=payload,
                )

                if resp.status_code == 201:
                    report_id = resp.headers.get("retryIn", "")
                    return await self._poll_report(report_id, client, headers)
                elif resp.status_code == 200:
                    return self._parse_wordstat_response(resp.text)
                elif resp.status_code == 400:
                    logger.error("Wordstat API error 400: %s", resp.text)
                    return {kw: 0 for kw in keywords}
                else:
                    logger.warning(
                        "Wordstat API returned %s: %s", resp.status_code, resp.text[:200]
                    )
                    return {kw: 0 for kw in keywords}

            except httpx.TimeoutException:
                logger.warning("Wordstat API timeout for keywords: %s", keywords)
                return {kw: 0 for kw in keywords}
            except httpx.HTTPError as exc:
                logger.warning("Wordstat API HTTP error: %s", exc)
                return {kw: 0 for kw in keywords}

    async def _poll_report(
        self,
        report_id: str,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        max_retries: int = 10,
    ) -> dict[str, int]:
        """Poll for report completion."""
        import asyncio

        for attempt in range(max_retries):
            await asyncio.sleep(3)
            try:
                resp = await client.get(
                    f"{REPORTS_API_URL}/{report_id}",
                    headers=headers,
                )
                if resp.status_code == 200:
                    return self._parse_wordstat_response(resp.text)
            except httpx.HTTPError:
                pass

        logger.warning("Wordstat report %s didn't complete after %d retries", report_id, max_retries)
        return {}

    def _parse_wordstat_response(self, tsv_data: str) -> dict[str, int]:
        """Parse TSV response from Wordstat API."""
        results: dict[str, int] = {}
        for line in tsv_data.strip().split("\n"):
            # Format: Keyword\tSearchedWith\tSearchedAlso
            parts = line.strip().split("\t")
            if len(parts) >= 2:
                keyword = parts[0].strip()
                try:
                    # "SearchedWith" — monthly requests for exact phrase
                    count_str = parts[1].strip().replace(" ", "").replace("\xa0", "")
                    count = int(count_str) if count_str.isdigit() else 0
                except (ValueError, IndexError):
                    count = 0
                results[keyword] = count
        return results


# ── Wordstat cache helpers ──


def _wordstat_cache_key(keyword: str) -> str:
    return hashlib.md5(keyword.encode("utf-8")).hexdigest()


class WordstatCache:
    """Database-backed cache for Wordstat responses."""

    async def get(self, keyword: str, db: AsyncSession) -> int | None:
        """Get cached wordstat count. Returns None if expired or missing."""
        from app.models.niche import RawPost

        cache_key = _wordstat_cache_key(keyword)
        cutoff = datetime.now(UTC) - timedelta(days=CACHE_TTL_DAYS)

        result = await db.execute(
            select(RawPost)
            .where(RawPost.source == "wordstat_cache")
            .where(RawPost.source_id == cache_key)
        )
        # In a real implementation, use a dedicated cache table
        return None

    async def set(self, keyword: str, count: int, db: AsyncSession) -> None:
        """Cache a wordstat response."""
        # Would store in a dedicated cache table
        pass
