"""Сборка черновика ниши: Вордстат (с кэшем) + ответ YandexGPT."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.services.wordstat import WordstatService
from app.services.yandex_gpt import YandexGptClient


async def build_niche_draft(
    session: AsyncSession,
    keyword: str,
    *,
    settings: Settings | None = None,
    force_wordstat_refresh: bool = False,
) -> dict[str, Any]:
    cfg = settings or get_settings()
    ws = WordstatService(cfg)
    try:
        wordstat_block = await ws.get_keyword_stats(
            session,
            [keyword],
            force_refresh=force_wordstat_refresh,
        )
    finally:
        await ws.aclose()

    summary = json.dumps(wordstat_block.get("payload"), ensure_ascii=False)[:4000]
    gpt = YandexGptClient(cfg)
    try:
        yandex_gpt_raw = await gpt.niche_card_draft(keyword, wordstat_summary=summary)
    finally:
        await gpt.aclose()

    return {
        "keyword": keyword,
        "wordstat": wordstat_block,
        "yandex_gpt": yandex_gpt_raw,
    }
