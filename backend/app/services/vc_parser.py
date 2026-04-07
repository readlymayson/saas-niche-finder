"""Парсер VC.ru: RSS + HTML постов и комментариев (aiohttp + BeautifulSoup)."""

from __future__ import annotations

import asyncio
import random
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import aiohttp
from bs4 import BeautifulSoup

VC_RSS_DEFAULT = "https://vc.ru/rss"

# Лимит: ~1 запрос / 2 с (план: random.uniform(1.5, 2.5) между запросами)
THROTTLE_SECONDS_MIN = 1.5
THROTTLE_SECONDS_MAX = 2.5

USER_AGENTS: tuple[str, ...] = (
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) "
        "Gecko/20100101 Firefox/133.0"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:133.0) "
        "Gecko/20100101 Firefox/133.0"
    ),
)


@dataclass(frozen=True)
class RssItem:
    title: str
    link: str
    published: datetime | None
    description: str | None


@dataclass(frozen=True)
class VcComment:
    text: str
    author: str | None = None


@dataclass
class VcPost:
    title: str
    url: str
    body_text: str
    comments: list[VcComment] = field(default_factory=list)


def _strip_ns(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _find_text(elem: ET.Element, *names: str) -> str | None:
    for child in elem:
        if _strip_ns(child.tag).lower() in names:
            t = (child.text or "").strip()
            if t:
                return t
    return None


def _parse_rfc822_date(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        dt = parsedate_to_datetime(s.strip())
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt
    except (TypeError, ValueError, OverflowError):
        return None


def parse_rss_feed(xml_text: str) -> list[RssItem]:
    """Разбор RSS 2.0 (VC.ru и совместимые ленты)."""
    root = ET.fromstring(xml_text)
    channel = root
    if _strip_ns(root.tag).lower() == "rss":
        channel = root[0] if len(root) else root
    items: list[RssItem] = []
    for elem in channel:
        if _strip_ns(elem.tag).lower() != "item":
            continue
        title = _find_text(elem, "title") or ""
        link = _find_text(elem, "link") or ""
        pub_raw = _find_text(elem, "pubdate")
        desc = _find_text(elem, "description")
        pub = _parse_rfc822_date(pub_raw)
        items.append(
            RssItem(title=title.strip(), link=link.strip(), published=pub, description=desc)
        )
    return items


def _text_from_element(soup: BeautifulSoup, selectors: list[str]) -> str:
    for sel in selectors:
        node = soup.select_one(sel)
        if node:
            return node.get_text("\n", strip=True)
    return ""


def parse_post_html(html: str, url: str) -> VcPost:
    """Извлечение заголовка, текста и комментариев из HTML страницы поста."""
    soup = BeautifulSoup(html, "lxml")
    title_selectors = [
        "h1.content-header__title",
        "h1.article__title",
        "article h1",
        "h1",
    ]
    title = ""
    for sel in title_selectors:
        h = soup.select_one(sel)
        if h:
            title = h.get_text(strip=True)
            break

    body_selectors = [
        ".article__content",
        ".content__text",
        ".l-entry__content",
        "article",
    ]
    body = _text_from_element(soup, body_selectors)

    comments: list[VcComment] = []
    for block in soup.select(".comments__item-comment, .comment, [data-testid='comment']"):
        text = block.get_text("\n", strip=True)
        if not text:
            continue
        author_el = block.select_one(".comment__author, .user-name, [data-testid='author']")
        author = author_el.get_text(strip=True) if author_el else None
        comments.append(VcComment(text=text, author=author))

    return VcPost(title=title, url=url, body_text=body, comments=comments)


class VcFetcher:
    """HTTP-клиент с ротацией User-Agent и паузой между запросами."""

    def __init__(
        self,
        session: aiohttp.ClientSession | None = None,
        *,
        throttle_min: float = THROTTLE_SECONDS_MIN,
        throttle_max: float = THROTTLE_SECONDS_MAX,
        user_agents: tuple[str, ...] = USER_AGENTS,
    ) -> None:
        self._session = session
        self._owns_session = session is None
        self._throttle_min = throttle_min
        self._throttle_max = throttle_max
        self._user_agents = user_agents
        self._ua_index = 0

    def _next_user_agent(self) -> str:
        ua = self._user_agents[self._ua_index % len(self._user_agents)]
        self._ua_index += 1
        return ua

    async def _throttle(self) -> None:
        await asyncio.sleep(random.uniform(self._throttle_min, self._throttle_max))

    async def __aenter__(self) -> VcFetcher:
        if self._session is None:
            timeout = aiohttp.ClientTimeout(total=60)
            self._session = aiohttp.ClientSession(timeout=timeout)
            self._owns_session = True
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._owns_session and self._session is not None:
            await self._session.close()
            self._session = None

    async def fetch_text(self, url: str) -> str:
        if self._session is None:
            raise RuntimeError("VcFetcher must be used as async context manager or pass session")
        await self._throttle()
        headers = {"User-Agent": self._next_user_agent(), "Accept-Language": "ru-RU,ru;q=0.9"}
        async with self._session.get(url, headers=headers, raise_for_status=True) as resp:
            return await resp.text()

    async def fetch_rss(self, rss_url: str = VC_RSS_DEFAULT) -> list[RssItem]:
        xml_text = await self.fetch_text(rss_url)
        return parse_rss_feed(xml_text)

    async def fetch_posts_from_rss(
        self,
        rss_url: str = VC_RSS_DEFAULT,
        *,
        limit: int = 100,
    ) -> list[VcPost]:
        """RSS → HTML постов до limit штук (с паузой между HTTP-запросами)."""
        items = await self.fetch_rss(rss_url)
        out: list[VcPost] = []
        for item in items:
            if len(out) >= limit:
                break
            if not item.link:
                continue
            html = await self.fetch_text(item.link)
            out.append(parse_post_html(html, item.link))
        return out
