from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings

# NullPool: каждый таск Celery создаёт собственный event loop (см. _run_async),
# поэтому переиспользование соединений между loop'ами ломается
# ("Future attached to a different loop"). NullPool создаёт соединение заново
# в текущем loop — безопасно для Celery worker (solo) и FastAPI.
engine = create_async_engine(
    settings.database_url,
    echo=False,
    poolclass=NullPool,
)

async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session
