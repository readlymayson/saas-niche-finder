"""Сохранение сообщений Telegram в raw_posts (live Telethon или фикстуры)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from telethon.tl.custom.message import Message

from app.config import Settings, get_settings
from app.models.raw_post import RawPost
from app.services.pain_classifier import PainClassifier
from app.services.telegram_collector import TelegramCollector


def _tg_external_id(channel: str, message_id: int) -> str:
    ch = channel.lstrip("@")
    return f"{ch}:{message_id}"


async def upsert_telegram_message(
    session: AsyncSession,
    *,
    channel: str,
    message_id: int,
    body_text: str,
    title: str | None = None,
    url: str | None = None,
    extra: dict[str, Any] | None = None,
) -> bool:
    ext = _tg_external_id(channel, message_id)
    row = await session.execute(
        select(RawPost).where(RawPost.source == "telegram", RawPost.external_id == ext)
    )
    existing = row.scalar_one_or_none()
    merged_extra = dict(extra or {})
    if existing is not None:
        existing.body_text = body_text or existing.body_text
        existing.title = title or existing.title
        existing.url = url or existing.url
        if merged_extra:
            base = dict(existing.extra or {})
            base.update(merged_extra)
            existing.extra = base
        return False
    session.add(
        RawPost(
            source="telegram",
            external_id=ext,
            url=url,
            title=title,
            body_text=body_text,
            extra=merged_extra or None,
        )
    )
    return True


def _message_to_fields(
    message: Message, channel: str
) -> tuple[str, str | None, str | None, dict[str, Any]]:
    text = (message.message or "").strip()
    title = channel
    url = None
    extra: dict[str, Any] = {
        "channel": channel,
        "message_id": message.id,
    }
    if message.date:
        extra["date"] = message.date.isoformat()
    return text, title, url, extra


async def ingest_telegram_from_fixtures(
    session: AsyncSession,
    fixtures_path: Path,
    *,
    limit: int = 50,
    classify_pain: bool = True,
) -> dict[str, int]:
    inserted = 0
    skipped = 0
    clf = PainClassifier() if classify_pain else None
    path = fixtures_path / "messages.jsonl"
    if not path.is_file():
        return {"inserted": 0, "skipped": 0, "error": "missing messages.jsonl"}

    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f):
            if line_no >= limit:
                break
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            channel = str(row.get("channel", "@unknown"))
            message_id = int(row["message_id"])
            text = str(row.get("text", "")).strip()
            if not text:
                continue
            extra: dict[str, Any] = {"channel": channel, "message_id": message_id}
            if clf is not None:
                extra["pain_frequency"] = clf.pain_frequency(text)
                extra["pain_label"] = clf.predict_label(text)
            is_new = await upsert_telegram_message(
                session,
                channel=channel,
                message_id=message_id,
                body_text=text,
                title=channel,
                extra=extra,
            )
            if is_new:
                inserted += 1
            else:
                skipped += 1
    await session.commit()
    return {"inserted": inserted, "skipped": skipped}


async def ingest_telegram_channels(
    session: AsyncSession,
    channels: list[str],
    *,
    limit_per_channel: int = 30,
    settings: Settings | None = None,
    classify_pain: bool = True,
) -> dict[str, int]:
    cfg = settings or get_settings()
    collector = TelegramCollector.from_settings(cfg)
    clf = PainClassifier(cfg) if classify_pain else None
    inserted = 0
    skipped = 0
    errors: list[str] = []
    try:
        for channel in channels:
            ch = channel if channel.startswith("@") else f"@{channel}"
            try:
                async for message in collector.iter_channel_messages(ch, limit=limit_per_channel):
                    text, title, url, extra = _message_to_fields(message, ch)
                    if not text:
                        continue
                    if clf is not None:
                        extra["pain_frequency"] = clf.pain_frequency(text)
                        extra["pain_label"] = clf.predict_label(text)
                    is_new = await upsert_telegram_message(
                        session,
                        channel=ch,
                        message_id=int(message.id),
                        body_text=text,
                        title=title,
                        url=url,
                        extra=extra,
                    )
                    if is_new:
                        inserted += 1
                    else:
                        skipped += 1
            except Exception as e:
                errors.append(f"{ch}: {e}")
        await session.commit()
    finally:
        await collector.disconnect()
    result: dict[str, Any] = {"inserted": inserted, "skipped": skipped}
    if errors:
        result["errors"] = errors
    return result
