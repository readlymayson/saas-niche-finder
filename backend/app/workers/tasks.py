"""Celery tasks for the DaaS data pipeline.

Pipeline:
  1. scrape_vcru       → Fetch RSS + HTML from VC.ru, save RawPost
  2. scrape_telegram    → Fetch messages from Telegram, save RawPost
  3. process_raw_posts  → ML: classify pain points, extract embeddings
  4. aggregate_niches   → Build NicheIdea from processed posts
  5. update_wordstat    → Fetch Яндекс.Вордстат data for niches
  6. score_niches       → Recalculate scores for all niches
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime

from celery import shared_task
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_maker
from app.models.niche import NicheIdea, RawPost

logger = logging.getLogger(__name__)


# ── Helpers ──


def _run_async(coro):
    """Run an async function in Celery's sync context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _get_unprocessed_posts(session: AsyncSession, limit: int = 50) -> list[RawPost]:
    """Fetch posts that haven't been ML-processed yet."""
    result = await session.execute(
        select(RawPost)
        .where(RawPost.is_processed == False)  # noqa: E712
        .limit(limit)
    )
    return list(result.scalars().all())


# ──────────────────────────────────────────
# Task 1: Scrape VC.ru
# ──────────────────────────────────────────


@shared_task(name="app.workers.tasks.scrape_vcru", max_retries=3, default_retry_delay=60)
def scrape_vcru() -> dict:
    """Scrape VC.ru RSS feed and save new posts to database."""
    from app.services.vc_parser import VcFetcher

    async def _run() -> dict:
        stats = {"posts_fetched": 0, "posts_saved": 0, "errors": 0}

        async with VcFetcher() as fetcher:
            try:
                posts = await fetcher.fetch_posts_from_rss(limit=20)
            except Exception as exc:
                logger.error("VC.ru RSS fetch failed: %s", exc)
                return {"error": str(exc), **stats}

            stats["posts_fetched"] = len(posts)

            async with async_session_maker() as session:
                for post in posts:
                    # Check for duplicate
                    existing = await session.execute(
                        select(RawPost).where(
                            RawPost.source == "vcru",
                            RawPost.url == post.url,
                        )
                    )
                    if existing.scalar_one_or_none() is not None:
                        continue

                    # Build comments JSON
                    comments_json = [
                        {"text": c.text, "author": c.author} for c in post.comments
                    ] if post.comments else None

                    raw = RawPost(
                        source="vcru",
                        url=post.url,
                        title=post.title,
                        body_text=post.body_text,
                        comments_json=comments_json,
                        is_processed=False,
                    )
                    session.add(raw)
                    stats["posts_saved"] += 1

                await session.commit()

        return stats

    return _run_async(_run())


# ──────────────────────────────────────────
# Task 2: Scrape Telegram
# ──────────────────────────────────────────


@shared_task(name="app.workers.tasks.scrape_telegram", max_retries=3, default_retry_delay=120)
def scrape_telegram() -> dict:
    """Scrape Telegram channels and save relevant messages."""
    from app.config import settings

    async def _run() -> dict:
        from app.services.tg_parser import TelegramParser

        parser = TelegramParser(
            api_id=settings.telegram_api_id,
            api_hash=settings.telegram_api_hash,
            phone=settings.telegram_phone,
        )
        stats = {"messages_fetched": 0, "messages_saved": 0, "errors": 0}

        try:
            messages = await parser.scrape_all_channels(hours_back=24, limit_per_channel=30)
            stats["messages_fetched"] = len(messages)

            async with async_session_maker() as session:
                for msg in messages:
                    existing = await session.execute(
                        select(RawPost).where(
                            RawPost.source == "telegram",
                            RawPost.source_id == msg["source_id"],
                        )
                    )
                    if existing.scalar_one_or_none() is not None:
                        continue

                    raw = RawPost(
                        source="telegram",
                        source_id=msg["source_id"],
                        title=None,
                        body_text=msg["text"],
                        author=msg["author"],
                        published_at=(
                            datetime.fromisoformat(msg["published_at"])
                            if msg.get("published_at") else None
                        ),
                        is_processed=False,
                    )
                    session.add(raw)
                    stats["messages_saved"] += 1

                await session.commit()

        except Exception as exc:
            logger.error("Telegram scrape failed: %s", exc)
            stats["errors"] += 1
        finally:
            await parser.close()

        return stats

    return _run_async(_run())


# ──────────────────────────────────────────
# Task 3: ML Processing
# ──────────────────────────────────────────


@shared_task(name="app.workers.tasks.process_raw_posts", max_retries=2, default_retry_delay=30)
def process_raw_posts(limit: int = 20) -> dict:
    """Run ML pipeline on unprocessed posts."""
    from app.ml.service import process_post_for_pain_points

    async def _run() -> dict:
        stats = {"processed": 0, "pain_points_found": 0, "errors": 0}

        async with async_session_maker() as session:
            posts = await _get_unprocessed_posts(session, limit=limit)

            for post in posts:
                try:
                    comments_list = post.comments_json if post.comments_json else []
                    result = process_post_for_pain_points(
                        title=post.title,
                        body_text=post.body_text,
                        comments_json=comments_list,
                    )

                    post.is_processed = True
                    post.is_pain_point = result["is_pain_point"]
                    post.pain_probability = result["pain_probability"]
                    post.embedding = result["embedding"]

                    if result["is_pain_point"]:
                        stats["pain_points_found"] += 1

                    stats["processed"] += 1

                except Exception as exc:
                    logger.error("ML processing failed for post %s: %s", post.id, exc)
                    post.is_processed = True  # mark as processed even on error
                    stats["errors"] += 1

            await session.commit()

        return stats

    return _run_async(_run())


# ──────────────────────────────────────────
# Task 4: Aggregate Niches
# ──────────────────────────────────────────


@shared_task(name="app.workers.tasks.aggregate_niches", max_retries=2, default_retry_delay=60)
def aggregate_niches() -> dict:
    """Aggregate processed pain posts into NicheIdea entries.

    Groups posts by keyword clusters into niche ideas.
    Calculates embeddings as mean of constituent post embeddings.
    """
    async def _run() -> dict:
        stats = {"niches_created": 0, "niches_updated": 0}

        async with async_session_maker() as session:
            # Get all pain posts that haven't been aggregated yet
            result = await session.execute(
                select(RawPost).where(
                    RawPost.is_pain_point == True,  # noqa: E712
                    RawPost.is_processed == True,  # noqa: E712
                )
            )
            pain_posts = list(result.scalars().all())

            if not pain_posts:
                return {"message": "No new pain posts to aggregate", **stats}

            # Simple grouping by keyword matching in body
            niche_keywords = {
                "логистик": "B2B SaaS для логистики",
                "доставк": "Логистика и доставка",
                "склад": "Складской учёт и WMS",
                "hr": "HR Tech",
                "кадр": "HR Tech / Кадровый учёт",
                "рекрутинг": "HR Tech / Рекрутинг",
                "бухгалтер": "Бухгалтерия и финансы",
                "финанс": "Финансы и отчётность",
                "1с": "1С и учётные системы",
                "crm": "CRM и управление продажами",
                "продаж": "CRM и управление продажами",
                "телефон": "Телефония и коммуникации",
                "edtech": "EdTech / Обучение",
                "образован": "EdTech / Образование",
                "медицин": "MedTech",
                "здравоохран": "MedTech",
                "еcommerce": "E-commerce",
                "интернет-магазин": "E-commerce",
                "маркетплейс": "Marketplace",
                "чат-бот": "Чат-боты и AI",
                "искусственн": "AI / Искусственный интеллект",
                "нейросет": "AI / Нейросети",
                "безопасност": "Infosec / Безопасность",
                "инфобез": "Infosec / Безопасность",
                "строител": "PropTech / Строительство",
                "недвижим": "PropTech / Недвижимость",
                "агро": "AgroTech",
                "сельск": "AgroTech",
            }

            niche_posts: dict[str, list[RawPost]] = {}
            for post in pain_posts:
                body = (post.title or "") + " " + post.body_text
                body_lower = body.lower()
                matched = False
                for keyword, niche_name in niche_keywords.items():
                    if keyword in body_lower:
                        if niche_name not in niche_posts:
                            niche_posts[niche_name] = []
                        niche_posts[niche_name].append(post)
                        matched = True
                        break
                if not matched:
                    # Uncategorized — create "Other" bucket
                    if "Другие B2B-ниши" not in niche_posts:
                        niche_posts["Другие B2B-ниши"] = []
                    niche_posts["Другие B2B-ниши"].append(post)

            # Upsert NicheIdea for each group
            for niche_name, posts in niche_posts.items():
                existing = await session.execute(
                    select(NicheIdea).where(NicheIdea.niche_name == niche_name)
                )
                niche = existing.scalar_one_or_none()

                # Calculate metrics
                wordstat_requests = 0  # filled later by wordstat task
                pain_points_data: list[dict] = []
                competitor_data: list[dict] = []
                embeddings: list[list[float]] = []
                vcru_mentions = 0

                for p in posts:
                    if p.source == "vcru":
                        vcru_mentions += 1

                    pain_points_data.append({
                        "text": p.body_text[:500],
                        "source_url": p.url or "",
                        "source_title": p.title or "",
                        "author": None,
                        "published_at": (
                            p.published_at.isoformat() if p.published_at else None
                        ),
                    })

                    if p.embedding and len(p.embedding) == 768:
                        embeddings.append(p.embedding)

                # Mean-pool embeddings
                mean_embedding = None
                if embeddings:
                    import numpy as np
                    mean_embedding = np.mean(embeddings, axis=0).tolist()

                if niche is None:
                    niche = NicheIdea(
                        niche_name=niche_name,
                        category="saas",
                        overall_score=0.0,
                        confidence=min(1.0, len(posts) * 0.1),
                        wordstat_requests=0,
                        wordstat_trend="stable",
                        vcru_mention_count=vcru_mentions,
                        pain_point_count=len(pain_points_data),
                        competitor_count=0,
                        summary_ru=f"Агрегированная ниша на основе {len(posts)} источников боли.",
                        pain_points_json=pain_points_data,
                        competitors_json=[],
                        embedding=mean_embedding,
                    )
                    session.add(niche)
                    stats["niches_created"] += 1
                else:
                    niche.vcru_mention_count += vcru_mentions
                    niche.pain_point_count += len(pain_points_data)
                    niche.confidence = min(1.0, niche.confidence + 0.05)
                    if mean_embedding:
                        niche.embedding = mean_embedding
                    # Update pain points (append new ones)
                    existing_pain = niche.pain_points_json or []
                    existing_pain.extend(pain_points_data)
                    niche.pain_points_json = existing_pain
                    stats["niches_updated"] += 1

            await session.commit()

        return stats

    return _run_async(_run())


# ──────────────────────────────────────────
# Task 5: Update Wordstat data
# ──────────────────────────────────────────


@shared_task(name="app.workers.tasks.update_wordstat", max_retries=2, default_retry_delay=120)
def update_wordstat() -> dict:
    """Fetch Яндекс.Вордстат data for all niches and update scores."""
    from app.services.wordstat import WordstatClient

    async def _run() -> dict:
        stats = {"niches_updated": 0, "errors": 0}

        client = WordstatClient()
        async with async_session_maker() as session:
            result = await session.execute(select(NicheIdea))
            niches = list(result.scalars().all())

            for niche in niches:
                try:
                    # Get keywords from niche name + related terms
                    keywords = [niche.niche_name]
                    wordstat = await client.get_keyword_stats(keywords)

                    if wordstat:
                        total = sum(wordstat.values())
                        niche.wordstat_requests = total

                        # Determine trend based on name patterns
                        if "раст" in niche.niche_name.lower():
                            niche.wordstat_trend = "growing"
                        elif "пад" in niche.niche_name.lower():
                            niche.wordstat_trend = "declining"
                        else:
                            niche.wordstat_trend = "stable"

                        stats["niches_updated"] += 1

                except Exception as exc:
                    logger.error("Wordstat update failed for niche %s: %s", niche.id, exc)
                    stats["errors"] += 1

            await session.commit()

        return stats

    return _run_async(_run())


# ──────────────────────────────────────────
# Task 6: Score Niches
# ──────────────────────────────────────────


@shared_task(name="app.workers.tasks.score_niches")
def score_niches() -> dict:
    """Recalculate overall_score for all niches based on available data."""
    async def _run() -> dict:
        stats = {"scored": 0}

        async with async_session_maker() as session:
            result = await session.execute(select(NicheIdea))
            niches = list(result.scalars().all())

            for niche in niches:
                score = _calculate_score(niche)
                niche.overall_score = score
                stats["scored"] += 1

            await session.commit()

        return stats

    return _run_async(_run())


def _calculate_score(niche: NicheIdea) -> float:
    """Calculate niche attractiveness score (0–100).

    Factors:
      - Wordstat request volume (0-40 pts)
      - Pain point count (0-25 pts)
      - VC.ru mentions (0-15 pts)
      - Wordstat trend (0-10 pts)
      - Competitor count (0-10 pts)
    """
    score = 0.0

    # 1. Wordstat volume (up to 40 pts)
    requests = niche.wordstat_requests or 0
    if requests >= 50000:
        score += 40
    elif requests >= 20000:
        score += 30
    elif requests >= 10000:
        score += 25
    elif requests >= 5000:
        score += 20
    elif requests >= 1000:
        score += 10
    elif requests > 0:
        score += 5

    # 2. Pain points (up to 25 pts)
    pain_count = niche.pain_point_count or 0
    score += min(25, pain_count * 3)

    # 3. VC.ru mentions (up to 15 pts)
    mentions = niche.vcru_mention_count or 0
    score += min(15, mentions * 0.5)

    # 4. Wordstat trend (up to 10 pts)
    trend = niche.wordstat_trend or "stable"
    if trend == "growing":
        score += 10
    elif trend == "stable":
        score += 5

    # 5. Competitor count (up to 10 pts)
    competitors = niche.competitor_count or 0
    # Moderate competition is good (validated market), too many is bad
    if 3 <= competitors <= 10:
        score += 10
    elif 1 <= competitors <= 2:
        score += 7
    elif competitors > 10:
        score += 3

    return round(min(100, max(0, score)), 1)

