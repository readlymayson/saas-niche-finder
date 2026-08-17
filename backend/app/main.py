from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.api import niches, v1
from app.db.base import Base
from app.db.session import engine
from app.db.vector import enable_vector_extension


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await enable_vector_extension(conn)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(
    title="NicheFinder Internal API",
    description=(
        "Личный инструмент поиска B2B-ниш: парсинг VC.ru и Telegram, "
        "ML-скоринг (RuBERT + pgvector), Яндекс.Вордстат и YandexGPT.\n\n"
        "## Аутентификация\n"
        "Единственный статический токен в заголовке: `X-Api-Token: <token>`\n"
        "(либо `Authorization: Bearer <token>`)."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(v1.router, prefix="/v1", tags=["v1"])
app.include_router(niches.router, prefix="/internal", tags=["internal"])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
async def ready() -> dict[str, str]:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception:
        return {"status": "degraded"}
