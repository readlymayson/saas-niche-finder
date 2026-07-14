"""Telegram channel parser using Telethon.

Collects messages from B2B-related Telegram channels.
Respects rate limits with FloodWait handling (30 msg/min).
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Default channels to scrape (B2B / startup / venture in Russia)
DEFAULT_CHANNELS: list[str] = [
    "https://t.me/sibersibir",
    "https://t.me/rusven_rus",
    "https://t.me/russtarup",
    "https://t.me/probiznes",
    "https://t.me/bizness_online",
]

# Rate limit: max 30 messages per minute (Telegram restriction)
TG_RATE_PER_MINUTE = 30
TG_RATE_WINDOW = 60.0  # seconds

# B2B-related keywords to filter useful messages
B2B_KEYWORDS: list[str] = [
    "b2b", "B2B",
    "saas", "SaaS",
    "стартап", "startup",
    "бизнес", "business",
    "венчур", "venture",
    "инвестици",
    "предпринимател",
    "ниша",
    "идея",
    "проблем", "боль",
    "автоматизаци",
    "софт",
    "платформ",
    "сервис",
]


def _is_b2b_relevant(text: str) -> bool:
    """Check if a message is relevant to B2B niche analysis."""
    if not text:
        return False
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in B2B_KEYWORDS)


def _extract_links(text: str) -> list[str]:
    """Extract URLs from text."""
    return re.findall(r"https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+[^\s]*", text)


class TelegramParser:
    """Async Telegram message collector.

    Uses Telethon to scrape messages from public channels.
    """

    def __init__(
        self,
        api_id: int = 0,
        api_hash: str = "",
        phone: str = "",
        channels: list[str] | None = None,
    ) -> None:
        self._api_id = api_id
        self._api_hash = api_hash
        self._phone = phone
        self._channels = channels or DEFAULT_CHANNELS
        self._client: Any = None

    async def _get_client(self) -> Any:
        """Lazy-init Telethon client."""
        if self._client is not None:
            return self._client

        if not self._api_id or not self._api_hash:
            logger.warning(
                "Telegram API credentials not configured. "
                "Set TELEGRAM_API_ID and TELEGRAM_API_HASH env vars."
            )
            return None

        from telethon import TelegramClient

        self._client = TelegramClient(
            "nichefinder_tg_session",
            self._api_id,
            self._api_hash,
        )
        await self._client.start(phone=self._phone)
        return self._client

    async def scrape_recent_messages(
        self,
        channel_username: str,
        hours_back: int = 24,
        limit: int = 100,
    ) -> list[dict]:
        """Scrape recent messages from a Telegram channel.

        Args:
            channel_username: Channel @username or t.me URL
            hours_back: How far back to look
            limit: Max messages to return

        Returns:
            List of dicts with: text, author, url, published_at, source_id
        """
        client = await self._get_client()
        if client is None:
            logger.warning("Telegram client not available, skipping scrape")
            return []

        # Extract username from URL if needed
        username = channel_username
        if "t.me/" in username:
            username = username.rsplit("t.me/", 1)[-1].split("/")[0]

        try:
            entity = await client.get_entity(username)
        except Exception as exc:
            logger.warning("Cannot get entity for %s: %s", username, exc)
            return []

        since = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        messages: list[dict] = []

        try:
            async for msg in client.iter_messages(entity, offset_date=since, limit=limit):
                if not msg.message:
                    continue

                text = msg.message.strip()
                if not _is_b2b_relevant(text):
                    continue

                messages.append({
                    "source_id": str(msg.id),
                    "text": text,
                    "author": msg.sender_id and str(msg.sender_id) or None,
                    "published_at": msg.date.isoformat() if msg.date else None,
                    "links": _extract_links(text),
                })

                # Rate limiting: max TG_RATE_PER_MINUTE per window
                if len(messages) % TG_RATE_PER_MINUTE == 0:
                    await asyncio.sleep(TG_RATE_WINDOW)

        except Exception as exc:
            # FloodWait is handled by Telethon automatically
            logger.warning("Error scraping %s: %s", username, exc)

        return messages

    async def scrape_all_channels(
        self,
        hours_back: int = 24,
        limit_per_channel: int = 50,
    ) -> list[dict]:
        """Scrape all configured channels."""
        all_messages: list[dict] = []
        for channel in self._channels:
            logger.info("Scraping channel: %s", channel)
            msgs = await self.scrape_recent_messages(
                channel,
                hours_back=hours_back,
                limit=limit_per_channel,
            )
            all_messages.extend(msgs)
            await asyncio.sleep(5)  # pause between channels
        return all_messages

    async def close(self) -> None:
        if self._client:
            await self._client.disconnect()
            self._client = None
