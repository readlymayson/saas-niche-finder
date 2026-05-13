"""
Сбор сообщений из Telegram через Telethon (user account).
Лимиты: не более 30 сообщений в минуту; flood_sleep_threshold=60 на клиенте.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.custom.message import Message

from app.config import Settings, get_settings


def _min_interval_sec(max_per_minute: int) -> float:
    if max_per_minute <= 0:
        return 0.0
    return 60.0 / float(max_per_minute)


@dataclass
class TelegramCollectorConfig:
    api_id: int
    api_hash: str
    session_path: Path | None
    session_string: str | None
    max_messages_per_minute: int
    flood_sleep_threshold: int


def settings_to_collector_config(settings: Settings) -> TelegramCollectorConfig:
    if settings.telegram_api_id is None or not settings.telegram_api_hash:
        msg = "Задайте TELEGRAM_API_ID и TELEGRAM_API_HASH для Telethon."
        raise ValueError(msg)
    path = Path(settings.telegram_session_path)
    return TelegramCollectorConfig(
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash,
        session_path=path if not settings.telegram_session_string else None,
        session_string=settings.telegram_session_string,
        max_messages_per_minute=settings.telegram_max_messages_per_minute,
        flood_sleep_threshold=settings.telethon_flood_sleep_threshold,
    )


class RateLimiter:
    """Простой лимитер: не чаще N раз в минуту (интервал между операциями)."""

    def __init__(self, max_per_minute: int) -> None:
        self._interval = _min_interval_sec(max_per_minute)
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


def build_telegram_client(cfg: TelegramCollectorConfig) -> TelegramClient:
    if cfg.session_string:
        session = StringSession(cfg.session_string)
        return TelegramClient(
            session,
            cfg.api_id,
            cfg.api_hash,
            flood_sleep_threshold=cfg.flood_sleep_threshold,
        )
    path = cfg.session_path or Path(".data/telegram.session")
    path.parent.mkdir(parents=True, exist_ok=True)
    return TelegramClient(
        str(path),
        cfg.api_id,
        cfg.api_hash,
        flood_sleep_threshold=cfg.flood_sleep_threshold,
    )


class TelegramCollector:
    """Обёртка над Telethon с лимитом 30 сообщений/мин (по умолчанию)."""

    def __init__(
        self,
        client: TelegramClient,
        rate_limiter: RateLimiter,
    ) -> None:
        self._client = client
        self._rate = rate_limiter

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> TelegramCollector:
        s = settings or get_settings()
        cfg = settings_to_collector_config(s)
        client = build_telegram_client(cfg)
        limiter = RateLimiter(cfg.max_messages_per_minute)
        return cls(client, limiter)

    @property
    def client(self) -> TelegramClient:
        return self._client

    async def iter_channel_messages(
        self,
        channel_username: str,
        *,
        limit: int = 100,
    ) -> AsyncIterator[Message]:
        """
        Итерирует последние сообщения канала/чата.
        Перед обработкой каждого сообщения ждёт согласно лимиту.
        """
        await self._client.connect()
        if not await self._client.is_user_authorized():
            msg = (
                "Telegram-сессия не авторизована. Запустите локальный логин "
                "(например, скрипт с client.start()) и сохраните сессию."
            )
            raise RuntimeError(msg)
        entity = await self._client.get_entity(channel_username)
        async for message in self._client.iter_messages(entity, limit=limit):
            await self._rate.acquire()
            yield message

    async def disconnect(self) -> None:
        await self._client.disconnect()
