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

    # DaaS Rate limits (requests per minute)
    rate_limit_free: int = 10
    rate_limit_developer: int = 300
    rate_limit_enterprise: int = 3000

    # YooKassa (ЮKassa) billing
    yookassa_shop_id: str = ""
    yookassa_secret_key: str = ""

    # CORS — allow all in DaaS mode (clients call API directly)
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Dashboard URL for payment return URL
    dashboard_url: str = "http://localhost:5173"

    # Telegram scraper credentials
    telegram_api_id: int = 0
    telegram_api_hash: str = ""
    telegram_phone: str = ""

    # Яндекс.Директ / Wordstat API
    yandex_direct_token: str = ""
    yandex_direct_login: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
