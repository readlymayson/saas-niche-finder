"""Сохранение постов VC.ru в raw_posts (фикстуры или live RSS)."""

from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.raw_post import RawPost
from app.services.vc_parser import VcFetcher, parse_post_html, parse_rss_feed


def _external_id(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]


async def upsert_vc_post(
    session: AsyncSession,
    *,
    url: str,
    title: str,
    body_text: str,
    extra: dict | None = None,
) -> bool:
    ext = _external_id(url)
    row = await session.execute(
        select(RawPost).where(RawPost.source == "vc", RawPost.external_id == ext)
    )
    existing = row.scalar_one_or_none()
    if existing is not None:
        existing.title = title or existing.title
        existing.body_text = body_text or existing.body_text
        existing.url = url
        if extra:
            merged = dict(existing.extra or {})
            merged.update(extra)
            existing.extra = merged
        return False
    session.add(
        RawPost(
            source="vc",
            external_id=ext,
            url=url,
            title=title,
            body_text=body_text,
            extra=extra,
        )
    )
    return True


async def ingest_vc_from_fixtures(
    session: AsyncSession,
    fixtures_dir: Path,
    *,
    limit: int = 5,
) -> dict[str, int]:
    """Офлайн-ингест HTML/RSS из tests/fixtures/vc для dev и CI."""
    inserted = 0
    skipped = 0
    rss_path = fixtures_dir / "sample.rss"
    if rss_path.is_file():
        items = parse_rss_feed(rss_path.read_text(encoding="utf-8"))
        for item in items[:limit]:
            html_name = None
            if "123456-b2b-saas" in item.link:
                html_name = "post_saas.html"
            elif "minimal" in item.link:
                html_name = "post_minimal.html"
            if not html_name:
                continue
            html = (fixtures_dir / html_name).read_text(encoding="utf-8")
            post = parse_post_html(html, item.link)
            is_new = await upsert_vc_post(
                session,
                url=post.url,
                title=post.title or item.title,
                body_text=post.body_text,
                extra={"comments_count": len(post.comments)},
            )
            if is_new:
                inserted += 1
            else:
                skipped += 1
    await session.commit()
    return {"inserted": inserted, "skipped": skipped}


async def ingest_vc_from_rss(
    session: AsyncSession,
    *,
    limit: int = 10,
) -> dict[str, int]:
    inserted = 0
    skipped = 0
    async with VcFetcher() as fetcher:
        posts = await fetcher.fetch_posts_from_rss(limit=limit)
    for post in posts:
        is_new = await upsert_vc_post(
            session,
            url=post.url,
            title=post.title,
            body_text=post.body_text,
            extra={"comments_count": len(post.comments)},
        )
        if is_new:
            inserted += 1
        else:
            skipped += 1
    await session.commit()
    return {"inserted": inserted, "skipped": skipped}
