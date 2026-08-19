from functools import lru_cache

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

    # Яндекс.Директ / Wordstat API
    yandex_direct_oauth_token: str | None = None
    yandex_direct_client_login: str | None = None
    yandex_direct_api_url: str = "https://api.direct.yandex.com/json/v5"
    wordstat_cache_ttl_days: int = 7
    wordstat_max_rps: float = 5.0
    wordstat_max_keywords_per_report: int = 2000

    # YandexGPT (Foundation Models): Api-Key и каталог (folder)
    yandex_gpt_api_key: str | None = None
    yandex_gpt_folder_id: str | None = None
    yandex_gpt_api_url: str = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
    yandex_gpt_model_uri: str | None = None  # по умолчанию gpt://{folder}/yandexgpt/latest


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
