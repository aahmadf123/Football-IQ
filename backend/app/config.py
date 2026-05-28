"""Application configuration loaded from environment variables."""

from functools import lru_cache
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Core ──────────────────────────────────────────────────────────────
    environment: str = "development"
    secret_key: str
    log_level: str = "INFO"

    # ── Database ──────────────────────────────────────────────────────────
    database_url: str  # asyncpg URL for the app
    database_sync_url: str = ""  # psycopg2 URL for Alembic (derived if empty)

    # ── Cloudflare R2 ─────────────────────────────────────────────────────
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_endpoint_url: str = ""
    r2_bucket_raw: str = "raw-video"
    r2_bucket_clips: str = "clips"
    r2_bucket_overlays: str = "overlays"
    r2_bucket_artifacts: str = "artifacts"
    r2_presign_ttl: int = 3600

    # ── JWT ───────────────────────────────────────────────────────────────
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 30

    # ── CORS ──────────────────────────────────────────────────────────────
    cors_origins: str = "http://localhost:3000"

    # ── College Football Data (CFBD) — backend-only (Issues #160/#161/#162) ─
    # Vendor integration for Toledo/MAC analytics. The key is read by the
    # backend ONLY and must never reach frontend code, browser bundles, logs,
    # or coach-visible errors. ``cfbd_api_key`` defaults to empty so the app
    # boots without it; the client fails safely with a backend-only error when
    # a CFBD call is attempted without a key (see app.cfbd.client).
    cfbd_api_key: str = ""
    cfbd_base_url: str = "https://api.collegefootballdata.com"
    # Cached CFBD rows older than this are flagged ``stale`` to the UI. College
    # football data refreshes roughly weekly, so the default is 7 days.
    cfbd_cache_stale_after_hours: int = 168

    @field_validator("database_sync_url", mode="before")
    @classmethod
    def derive_sync_url(cls, v: str, info: Any) -> str:
        if v:
            return v
        # Derive from async URL by stripping driver suffix
        async_url: str = ""
        if hasattr(info, "data"):
            async_url = str(info.data.get("database_url", ""))
        return async_url.replace("+asyncpg", "")

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()  # type: ignore[call-arg]
