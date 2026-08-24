from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/niche_finder"
    redis_url: str = "redis://localhost:6379/0"

    # Static API token for the personal internal tool
    # Passed via header: X-Api-Token: <token>
    api_token: str = "change-me-please-generate-a-secret-token"

    # Telegram scraper credentials
    telegram_api_id: int | None = None
    telegram_api_hash: str | None = None
    telegram_phone: str = ""
    # Файл сессии или пусто, если используется TELEGRAM_SESSION_STRING
    telegram_session_path: str = ".data/telegram.session"
    telegram_session_string: str | None = None
    telegram_max_messages_per_minute: int = 30
    telegram_channels: str = "@startup_news,@vcru,@habr_com"
    telegram_ingest_limit_per_channel: int = 30
    telegram_flood_sleep_threshold: int = 60  # Telethon: пауза при flood-wait (сек)

    # RuBERT pain classifier (после ml/train_classifier.py)
    rubert_pain_model_path: str = "backend/ml/artifacts/rubert-pain-cls"
    embeddings_model_name: str = "DeepPavlov/rubert-base-cased"

    # Яндекс Wordstat (Yandex Search API v2, синхронный)
    # API-ключ сервисного аккаунта (роль search-api.webSearch.user)
    # или IAM-токен; передаётся в заголовке Authorization.
    wordstat_api_key: str | None = None
    wordstat_api_url: str = "https://searchapi.api.cloud.yandex.net/v2/wordstat"
    # Каталог (folderId). По умолчанию — тот же, что для YandexGPT.
    wordstat_folder_id: str | None = None
    wordstat_region: str = "213"  # 213 — Москва и область
    wordstat_period: str = "PERIOD_MONTHLY"
    wordstat_cache_ttl_days: int = 7
    wordstat_max_rps: float = 5.0
    wordstat_max_keywords_per_report: int = 2000
    # Окно динамики для тренда (дней). 400 → захватывает месяц год назад
    # от последней завершённой точки, чтобы считать YoY-тренд с учётом
    # сезонности (365 дней не хватает: выравнивание на 1-е число месяца).
    wordstat_trend_days: int = 400

    # YandexGPT (Foundation Models): Api-Key и каталог (folder)
    yandex_gpt_api_key: str | None = None
    yandex_gpt_folder_id: str | None = None
    yandex_gpt_api_url: str = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
    yandex_gpt_model_uri: str | None = None  # по умолчанию gpt://{folder}/yandexgpt/latest

    @field_validator("wordstat_api_url", mode="before")
    @classmethod
    def _empty_url_to_default(cls, v: object) -> object:
        """Пустая строка из env (${VAR:-} в compose) не должна перекрывать дефолт."""
        if v == "":
            return "https://searchapi.api.cloud.yandex.net/v2/wordstat"
        return v

    @field_validator("wordstat_trend_days", mode="before")
    @classmethod
    def _empty_int_to_default(cls, v: object) -> object:
        """Пустая строка из env (${VAR:-} в compose) не должна ломать int."""
        if v == "" or v is None:
            return 400
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
