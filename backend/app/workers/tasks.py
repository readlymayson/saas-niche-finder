import asyncio
from pathlib import Path

from celery import shared_task

from app.config import get_settings, parse_telegram_channels
from app.db.session import async_session_maker
from app.services.niche_pipeline import recompute_niche_scores, refresh_niches_from_raw_posts
from app.services.telegram_ingest import ingest_telegram_channels, ingest_telegram_from_fixtures
from app.services.vc_ingest import ingest_vc_from_fixtures, ingest_vc_from_rss


@shared_task(name="app.workers.tasks.ping")
def ping() -> str:
    return "pong"


@shared_task(name="app.workers.tasks.refresh_niches_pipeline")
def refresh_niches_pipeline(limit: int = 20) -> dict[str, int]:
    async def _run() -> int:
        async with async_session_maker() as session:
            return await refresh_niches_from_raw_posts(session, limit=limit)

    updated = asyncio.run(_run())
    return {"updated": updated}


@shared_task(name="app.workers.tasks.recompute_niche_scores")
def recompute_scores_task() -> dict[str, int]:
    async def _run() -> int:
        async with async_session_maker() as session:
            return await recompute_niche_scores(session)

    recalculated = asyncio.run(_run())
    return {"recalculated": recalculated}


@shared_task(name="app.workers.tasks.ingest_vc_rss")
def ingest_vc_rss(limit: int = 10, *, use_fixtures: bool = False) -> dict[str, int]:
    fixtures = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "vc"

    async def _run() -> dict[str, int]:
        async with async_session_maker() as session:
            if use_fixtures and fixtures.is_dir():
                return await ingest_vc_from_fixtures(session, fixtures, limit=limit)
            return await ingest_vc_from_rss(session, limit=limit)

    return asyncio.run(_run())


@shared_task(name="app.workers.tasks.ingest_telegram")
def ingest_telegram(
    *,
    use_fixtures: bool = False,
    limit_per_channel: int = 30,
) -> dict[str, int]:
    fixtures = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "telegram"
    cfg = get_settings()

    async def _run() -> dict[str, int]:
        async with async_session_maker() as session:
            if use_fixtures and fixtures.is_dir():
                return await ingest_telegram_from_fixtures(
                    session, fixtures, limit=limit_per_channel
                )
            channels = parse_telegram_channels(cfg.telegram_channels)
            return await ingest_telegram_channels(
                session,
                channels,
                limit_per_channel=limit_per_channel,
                settings=cfg,
            )

    return asyncio.run(_run())
