from __future__ import annotations

import os
from functools import lru_cache
from ipaddress import ip_network
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _postgres_async(url: str) -> str:
    if url.startswith("postgres://"):
        url = "postgresql://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url.removeprefix("postgresql://")
    return url


def _postgres_sync(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql://" + url.removeprefix("postgres://")
    if url.startswith("postgresql+asyncpg://"):
        return "postgresql://" + url.removeprefix("postgresql+asyncpg://")
    return url


def _redis_db(url: str, db: int) -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in {"redis", "rediss"}:
        return url
    return urlunsplit((parsed.scheme, parsed.netloc, f"/{db}", parsed.query, parsed.fragment))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = Field(default="production")
    app_name: str = Field(default="PRIME NICK")
    app_base_url: str = Field(default="http://localhost:8080")
    railway_public_domain: str | None = None
    railway_static_url: str | None = None
    log_level: str = Field(default="INFO")

    bot_token: str = Field(min_length=20)
    bot_webhook_secret: str = Field(min_length=24)

    database_url: str | None = None
    postgres_url: str | None = None
    sync_database_url: str | None = None
    redis_url: str = Field(default="redis://localhost:6379/0")
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None

    internal_hmac_secret: str = Field(min_length=32)
    jwt_active_kid: str = Field(default="2026-05")
    jwt_secret_2026_05: str = Field(min_length=32)

    trusted_proxies: str = Field(default="127.0.0.1/32,10.0.0.0/8,172.16.0.0/12,100.64.0.0/10,fc00::/7")
    cloudflare_ip_ranges: str | None = None
    turnstile_secret: str | None = None

    robokassa_merchant_login: str
    robokassa_password1: str = Field(min_length=8)
    robokassa_password2: str = Field(min_length=8)
    robokassa_hash_algorithm: str = Field(default="sha256")
    robokassa_is_test: bool = Field(default=False)
    robokassa_payment_url: str = Field(default="https://auth.robokassa.ru/Merchant/Index.aspx")

    telegram_api_id: int
    telegram_api_hash: str
    pyrogram_session_name: str = "prime_nick_checker"

    sentry_dsn: str | None = None

    free_generation_limit: int = 2
    free_generation_window_seconds: int = 12 * 60 * 60
    free_min_username_len: int = 8
    free_reservation_limit: int = 15
    vip_reservation_limit: int = 100

    @model_validator(mode="after")
    def normalize_railway_urls(self):
        if self.app_base_url == "http://localhost:8080":
            domain = self.railway_public_domain or self.railway_static_url or os.getenv("RAILWAY_PUBLIC_DOMAIN")
            if domain:
                domain = domain.removeprefix("https://").removeprefix("http://").rstrip("/")
                self.app_base_url = f"https://{domain}"

        raw_db = self.database_url or self.postgres_url or os.getenv("DATABASE_PRIVATE_URL") or os.getenv("POSTGRES_URL")
        if not raw_db:
            raise ValueError("DATABASE_URL or POSTGRES_URL is required")
        self.sync_database_url = self.sync_database_url or _postgres_sync(raw_db)
        self.database_url = _postgres_async(raw_db)

        self.redis_url = str(self.redis_url)
        self.celery_broker_url = self.celery_broker_url or _redis_db(self.redis_url, 1)
        self.celery_result_backend = self.celery_result_backend or _redis_db(self.redis_url, 2)
        return self

    @property
    def trusted_proxy_networks(self):
        return [ip_network(item.strip(), strict=False) for item in self.trusted_proxies.split(",") if item.strip()]

    @property
    def telegram_webhook_path(self) -> str:
        return "/telegram/webhook"

    @property
    def telegram_webhook_url(self) -> str:
        return str(self.app_base_url).rstrip("/") + self.telegram_webhook_path

    @property
    def robokassa_result_path(self) -> str:
        return "/payments/robokassa/result"

    @property
    def robokassa_success_path(self) -> str:
        return "/payments/robokassa/success"

    @property
    def robokassa_fail_path(self) -> str:
        return "/payments/robokassa/fail"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
