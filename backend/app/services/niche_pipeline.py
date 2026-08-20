from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.models.niche_idea import NicheIdea
from app.models.raw_post import RawPost
from app.services.niche_draft import build_niche_draft
from app.services.scoring import score_from_payloads


def _safe_slug(seed: str, fallback_id: int) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", seed.lower()).strip("-")
    return base or f"niche-{fallback_id}"


def _keyword_from_post(post: RawPost) -> str:
    title = (post.title or "").strip()
    if title:
        return title[:120]
    body = (post.body_text or "").strip()
    return body[:120] if body else post.external_id


def _yandex_integrations_enabled(cfg: Settings) -> bool:
    return bool(cfg.wordstat_api_key and cfg.yandex_gpt_api_key)


def _wordstat_snapshot_from_draft(draft: dict[str, Any]) -> dict[str, Any]:
    ws = draft.get("wordstat") or {}
    payload = ws.get("payload") if isinstance(ws, dict) else {}
    if not isinstance(payload, dict):
        payload = {}
    extra = payload.get("growth")
    if extra is None and isinstance(ws, dict):
        extra = ws.get("growth")
    return {"growth": extra, "payload": payload}


def _gpt_json_from_post_and_draft(
    post: RawPost,
    draft: dict[str, Any] | None,
) -> dict[str, Any]:
    base: dict[str, Any] = {}
    if isinstance(post.extra, dict):
        for key in ("pain_frequency", "competitors_count", "budget_signal"):
            if key in post.extra:
                base[key] = post.extra[key]
    if draft and isinstance(draft.get("yandex_gpt"), dict):
        base.setdefault("yandex_gpt_raw", draft["yandex_gpt"])
    return base


def _try_embed_text(text: str, *, settings: Settings) -> list[float] | None:
    model = getattr(settings, "embeddings_model_name", "DeepPavlov/rubert-base-cased")
    try:
        from ml.embeddings import embed_texts, load_encoder_for_embeddings
    except ImportError:
        return None
    try:
        tokenizer, encoder = load_encoder_for_embeddings(model)
        vec = embed_texts([text], tokenizer, encoder)
        return vec[0].tolist()
    except Exception:
        return None


async def _enrich_idea_from_post(
    session: AsyncSession,
    post: RawPost,
    idea: NicheIdea,
    *,
    settings: Settings,
    use_yandex: bool,
) -> None:
    draft: dict[str, Any] | None = None
    if use_yandex and _yandex_integrations_enabled(settings):
        keyword = _keyword_from_post(post)
        try:
            draft = await build_niche_draft(session, keyword, settings=settings)
            idea.wordstat_snapshot = _wordstat_snapshot_from_draft(draft)
            idea.yandex_gpt_json = _gpt_json_from_post_and_draft(post, draft)
        except Exception:
            idea.yandex_gpt_json = _gpt_json_from_post_and_draft(post, None)
    else:
        idea.yandex_gpt_json = _gpt_json_from_post_and_draft(post, None)
        if isinstance(post.extra, dict) and "wordstat" in post.extra:
            idea.wordstat_snapshot = post.extra.get("wordstat") or {}

    embed_source = f"{idea.title}\n{idea.summary or ''}"
    vector = _try_embed_text(embed_source, settings=settings)
    if vector is not None:
        idea.embedding = vector

    idea.score = score_from_payloads(idea.wordstat_snapshot, idea.yandex_gpt_json)


async def refresh_niches_from_raw_posts(
    session: AsyncSession,
    *,
    limit: int = 20,
    settings: Settings | None = None,
    enrich_yandex: bool | None = None,
) -> int:
    cfg = settings or get_settings()
    use_yandex = enrich_yandex if enrich_yandex is not None else True
    rows = await session.execute(select(RawPost).order_by(RawPost.collected_at.desc()).limit(limit))
    posts = list(rows.scalars())
    updated = 0
    for post in posts:
        slug = _safe_slug(post.title or post.external_id, post.id)
        idea_q = await session.execute(select(NicheIdea).where(NicheIdea.slug == slug))
        idea = idea_q.scalar_one_or_none()
        if idea is None:
            idea = NicheIdea(
                slug=slug,
                title=post.title or slug,
                summary=(post.body_text or "")[:4000],
                yandex_gpt_json={},
                wordstat_snapshot={},
            )
            session.add(idea)
        else:
            idea.title = post.title or idea.title
            idea.summary = (post.body_text or idea.summary or "")[:4000]

        await _enrich_idea_from_post(session, post, idea, settings=cfg, use_yandex=use_yandex)
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
