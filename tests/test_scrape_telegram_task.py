"""Regression tests for the scrape_telegram Celery task (TelegramCollector path)."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

from app.workers.tasks import scrape_telegram


class _FakeMessage:
    """Minimal stand-in for telethon Message objects used by the collector."""

    def __init__(self, message_id: int, text: str, sender_id: int | None = None) -> None:
        self.id = message_id
        self.message = text
        self.sender_id = sender_id
        self.date = datetime.now(UTC)


class _FakeCollector:
    """Stands in for TelegramCollector: yields messages then disconnects."""

    def __init__(self, messages: list[_FakeMessage]) -> None:
        self._messages = messages
        self.disconnected = False

    async def iter_channel_messages(self, channel: str, limit: int = 100) -> Any:
        # The real one is an async generator; emulate with a yield inside.
        for msg in self._messages[:limit]:
            yield msg

    async def disconnect(self) -> None:
        self.disconnected = True


class _FakeSession:
    """Async context manager session: tracks added RawPost objects."""

    def __init__(self) -> None:
        self.added: list[Any] = []
        self.committed = False

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    async def execute(self, stmt: Any) -> MagicMock:
        # No existing rows → every message is new
        res = MagicMock()
        res.scalar_one_or_none.return_value = None
        return res

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.committed = True


def _patch_async_session_maker(fake_session: _FakeSession) -> MagicMock:
    factory = MagicMock(return_value=fake_session)
    return patch(
        "app.workers.tasks.async_session_maker",
        new=factory,
    )


def test_scrape_telegram_saves_relevant_messages() -> None:
    """Relevant B2B messages are saved with external_id, irrelevant are skipped."""
    fake_collector = _FakeCollector(
        [
            _FakeMessage(1, "Ищем SaaS для автоматизации склада, большая боль", sender_id=77),
            _FakeMessage(2, "Обычная новость без ключевых слов", sender_id=78),
        ]
    )
    fake_session = _FakeSession()

    with (
        patch("app.services.telegram_collector.TelegramCollector") as cls,
        patch("app.config.settings") as settings_mock,
        _patch_async_session_maker(fake_session),
    ):
        settings_mock.telegram_channels = "@startup_news"
        settings_mock.telegram_ingest_limit_per_channel = 100
        cls.from_settings.return_value = fake_collector
        stats = scrape_telegram()

    assert stats["messages_fetched"] == 1
    assert stats["messages_saved"] == 1
    assert stats["errors"] == 0

    assert len(fake_session.added) == 1
    raw = fake_session.added[0]
    assert raw.source == "telegram"
    assert raw.external_id == "startup_news:1"
    assert raw.body_text == "Ищем SaaS для автоматизации склада, большая боль"
    assert fake_session.committed
    assert fake_collector.disconnected


def test_scrape_telegram_skips_existing_messages() -> None:
    """Messages already present (scalar_one_or_none not None) are not re-saved."""
    fake_collector = _FakeCollector([_FakeMessage(9, "B2B платформа для ниши")])
    fake_session = _FakeSession()
    existing_raw = SimpleNamespace(body_text="old", title="old", url=None, extra={})

    async def _execute(stmt: Any) -> MagicMock:
        res = MagicMock()
        res.scalar_one_or_none.return_value = existing_raw  # already exists
        return res

    fake_session.execute = _execute  # type: ignore[method-assign]

    with (
        patch("app.services.telegram_collector.TelegramCollector") as cls,
        patch("app.config.settings") as settings_mock,
        _patch_async_session_maker(fake_session),
    ):
        settings_mock.telegram_channels = "@startup_news"
        settings_mock.telegram_ingest_limit_per_channel = 100
        cls.from_settings.return_value = fake_collector
        stats = scrape_telegram()

    assert stats["messages_fetched"] == 1
    assert stats["messages_saved"] == 0
    assert len(fake_session.added) == 0
    assert fake_session.committed
