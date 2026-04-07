from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.services.vc_parser import (
    USER_AGENTS,
    VcFetcher,
    parse_post_html,
    parse_rss_feed,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "vc"


def test_parse_rss_sample() -> None:
    xml = (FIXTURES / "sample.rss").read_text(encoding="utf-8")
    items = parse_rss_feed(xml)
    assert len(items) == 2
    assert items[0].title == "B2B SaaS для логистики"
    assert items[0].link == "https://vc.ru/finance/123456-b2b-saas"
    assert items[0].published is not None
    assert items[0].description == "Краткое описание поста в ленте."


def test_parse_post_saas_html() -> None:
    html = (FIXTURES / "post_saas.html").read_text(encoding="utf-8")
    post = parse_post_html(html, "https://vc.ru/finance/123456-b2b-saas")
    assert post.title == "B2B SaaS для логистики"
    assert "маршрутизации" in post.body_text
    assert len(post.comments) >= 1
    assert "Иван" in (post.comments[0].author or "")
    assert "Excel" in post.comments[0].text


def test_parse_post_minimal_html() -> None:
    html = (FIXTURES / "post_minimal.html").read_text(encoding="utf-8")
    post = parse_post_html(html, "https://vc.ru/test/minimal")
    assert post.title == "Минимальный пост"
    assert "Только текст" in post.body_text
    assert post.comments == []


def test_parse_post_comments_html() -> None:
    html = (FIXTURES / "post_comments.html").read_text(encoding="utf-8")
    post = parse_post_html(html, "https://vc.ru/test/comments")
    assert "CRM" in post.title
    assert len(post.comments) >= 2


def test_user_agents_count() -> None:
    assert len(USER_AGENTS) == 5


@pytest.mark.asyncio
async def test_fetch_text_throttle_and_user_agent_rotation(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    class Resp:
        async def __aenter__(self) -> Resp:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def text(self) -> str:
            return "<html><body><h1>x</h1></body></html>"

        def raise_for_status(self) -> None:
            return None

    uas: list[str | None] = []

    class Session:
        def get(self, url: str, headers: dict[str, str] | None = None, **kw: object) -> Resp:
            uas.append(headers.get("User-Agent") if headers else None)
            return Resp()

    fetcher = VcFetcher(session=Session(), throttle_min=1.5, throttle_max=2.5)
    await fetcher.fetch_text("https://example.com/a")
    await fetcher.fetch_text("https://example.com/b")
    assert len(sleeps) == 2
    assert 1.5 <= sleeps[0] <= 2.5
    assert 1.5 <= sleeps[1] <= 2.5
    assert uas[0] != uas[1] or len(USER_AGENTS) == 1
