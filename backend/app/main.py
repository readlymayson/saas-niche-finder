from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_keys, auth, billing, v1
from app.config import settings
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
    title="NicheFinder DaaS API",
    description=(
        "Data-as-a-Service API для B2B-скоринга ниш. "
        "Анализ Яндекс.Вордстат, VC.ru и патентов РФ.\n\n"
        "## Аутентификация\n"
        "Используйте API-ключ в заголовке: `Authorization: Bearer nf_<prefix>_<secret>`\n"
        "Ключи можно создать в Developer Portal.\n\n"
        "## Тарифы\n"
        "- **Free** (песочница): 10 запросов/мин\n"
        "- **Developer**: 300 запросов/мин\n"
        "- **Enterprise**: 3000 запросов/мин"
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(api_keys.router, prefix="/api-keys", tags=["api-keys"])
app.include_router(billing.router, prefix="/billing", tags=["billing"])
app.include_router(v1.router, prefix="/v1", tags=["v1"])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
