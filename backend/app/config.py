from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/niche_finder"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret_key: str = "change-me-in-production-use-openssl-rand-hex-32"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Telegram (Telethon, user session): API id/hash из my.telegram.org
    telegram_api_id: int | None = None
    telegram_api_hash: str | None = None
    # Файл сессии или пусто, если используется TELEGRAM_SESSION_STRING
    telegram_session_path: str = ".data/telegram.session"
    telegram_session_string: str | None = None
    # Не более 30 сообщений в минуту (консервативно для user-аккаунта)
    telegram_max_messages_per_minute: int = 30
    telethon_flood_sleep_threshold: int = 60
    # Список каналов через запятую: @startup_news,@vcru
    telegram_channels: str = "@startup_news,@vcru,@habr_com"
    telegram_ingest_limit_per_channel: int = 30

    # RuBERT pain classifier (после ml/train_classifier.py)
    rubert_pain_model_path: str = "backend/ml/artifacts/rubert-pain-cls"
    embeddings_model_name: str = "DeepPavlov/rubert-base-cased"

    # Яндекс.Директ API v5 — Вордстат (OAuth-токен пользователя с доступом к Директу)
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

    free_niche_views_per_day: int = 5
    # ЮKassa (prod только после human-gate / SYNGATE_ALLOW_YOOKASSA_PROD)
    yookassa_amount_rub: str = "990.00"
    yookassa_shop_id: str | None = None
    yookassa_secret_key: str | None = None
    yookassa_return_url: str = "http://localhost:5173/billing/success"
    yookassa_webhook_allow_unverified: bool = False


def parse_telegram_channels(raw: str) -> list[str]:
    return [c.strip() for c in raw.split(",") if c.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
