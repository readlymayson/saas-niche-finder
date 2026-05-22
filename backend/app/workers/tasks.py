import asyncio
from pathlib import Path

from celery import shared_task

from app.db.session import async_session_maker
from app.services.niche_pipeline import recompute_niche_scores, refresh_niches_from_raw_posts
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
