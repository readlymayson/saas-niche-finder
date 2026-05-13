from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.niche_idea import NicheIdea
from app.models.raw_post import RawPost
from app.services.scoring import score_from_payloads


def _safe_slug(seed: str, fallback_id: int) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", seed.lower()).strip("-")
    return base or f"niche-{fallback_id}"


async def refresh_niches_from_raw_posts(session: AsyncSession, *, limit: int = 20) -> int:
    rows = await session.execute(select(RawPost).order_by(RawPost.collected_at.desc()).limit(limit))
    posts = list(rows.scalars())
    updated = 0
    for post in posts:
        slug = _safe_slug(post.title or post.external_id, post.id)
        idea_q = await session.execute(select(NicheIdea).where(NicheIdea.slug == slug))
        idea = idea_q.scalar_one_or_none()
        payload = post.extra or {}
        if idea is None:
            idea = NicheIdea(
                slug=slug,
                title=post.title or slug,
                summary=(post.body_text or "")[:4000],
                yandex_gpt_json=payload if isinstance(payload, dict) else {},
                wordstat_snapshot={},
            )
            idea.score = score_from_payloads(idea.wordstat_snapshot, idea.yandex_gpt_json)
            session.add(idea)
        else:
            idea.title = post.title or idea.title
            idea.summary = (post.body_text or idea.summary or "")[:4000]
            if isinstance(payload, dict):
                idea.yandex_gpt_json = payload
            idea.score = score_from_payloads(idea.wordstat_snapshot, idea.yandex_gpt_json)
        updated += 1
    await session.commit()
    return updated


async def recompute_niche_scores(session: AsyncSession) -> int:
    rows = await session.execute(select(NicheIdea))
    niches = list(rows.scalars())
    for niche in niches:
        niche.score = score_from_payloads(niche.wordstat_snapshot, niche.yandex_gpt_json)
    await session.commit()
    return len(niches)
