from __future__ import annotations

from pathlib import Path

import pytest

from app.services.pain_classifier import PainClassifier
from app.services.telegram_ingest import _tg_external_id


def test_tg_external_id_stable() -> None:
    assert _tg_external_id("@vcru", 42) == "vcru:42"


def test_pain_classifier_heuristic() -> None:
    clf = PainClassifier()
    assert clf.predict_label("Ищу CRM срочно, боль в Excel") == 1
    assert clf.predict_label("Новость дня без запроса") == 0
    assert clf.pain_frequency("нужна автоматизация") >= 5.0


@pytest.mark.asyncio
async def test_ingest_telegram_fixtures_sqlite(tmp_path: Path) -> None:
    pytest.importorskip("aiosqlite")
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.db.base import Base
    from app.services.telegram_ingest import ingest_telegram_from_fixtures

    fixtures_src = Path(__file__).resolve().parent / "fixtures" / "telegram"
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        stats = await ingest_telegram_from_fixtures(session, fixtures_src, limit=10)
    assert stats["inserted"] >= 3
    await engine.dispose()
