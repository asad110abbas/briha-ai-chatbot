"""All settings come from the single `.env` file in the project root (see /.env.example)."""

from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    # App
    app_env: str = "development"
    app_timezone: str = "Asia/Karachi"
    app_base_url: str = "http://localhost:5173"
    cookie_secure: bool = False
    fixed_today: str | None = None  # YYYY-MM-DD, for tests/demos only

    # First admin (created on startup if the users table is empty)
    admin_username: str = ""
    admin_password: str = ""
    admin_full_name: str = "Administrator"
    # Recovery switch: when true, every startup resets the admin account to ADMIN_USERNAME /
    # ADMIN_PASSWORD and unlocks it. Turn it on only to recover a lost login, then turn it off.
    admin_reset_password: bool = False

    @field_validator("admin_username", "admin_password", "admin_full_name", mode="before")
    @classmethod
    def _strip(cls, v):
        return v.strip().strip('"').strip("'").strip() if isinstance(v, str) else v

    # BRIHA's own database (PostgreSQL)
    database_url: str = ""
    database_url_unpooled: str = ""  # set by the Vercel Neon integration; preferred (asyncpg + pgbouncer issues)
    postgres_host: str = "localhost"
    postgres_port: int = 5433
    postgres_db: str = "briha"
    postgres_user: str = "briha"
    postgres_password: str = "briha"

    # OpenAI
    llm_mode: str = "openai"  # openai | gemini (testing) | offline_demo (keyword rules, no key)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.1-flash-lite"  # 3.5-flash-lite measured 13-17 s per call
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    openai_api_key: str = ""
    openai_base_url: str | None = None
    https_proxy: str = ""  # only used for OpenAI calls, never for the internal data API
    openai_model_understanding: str = "gpt-5"
    openai_model_validator: str = "gpt-5"
    openai_model_responder: str = "gpt-5"
    openai_reasoning_effort: str = "low"
    openai_price_input_per_m: float = 1.25
    openai_price_output_per_m: float = 10.0
    validator_llm_enabled: bool = True

    # Company data source
    datasource_mode: str = "mock"  # mock | rest (rest reads /data_apis.yaml)
    data_api_verify_tls: bool = True
    mock_faults: str = ""  # comma list: down,timeout,wrong_dates,empty

    # Limits & rules
    ream_size_sheets: int = 500
    rate_limit_per_minute: int = 20
    rate_limit_per_day: int = 300
    max_message_chars: int = 1000
    sanity_max_sheets_per_day: int = 2_000_000
    retention_months: int = 12
    master_data_cache_hours: int = 6
    session_idle_hours: int = 12
    session_absolute_days: int = 7
    tool_timeout_seconds: float = 10.0
    run_timeout_seconds: float = 45.0
    prompt_version: str = "v2"

    @property
    def sqlalchemy_url(self) -> str:
        url = self.database_url_unpooled or self.database_url
        if url:
            return _asyncpg_url(url)
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.app_timezone)

    def today(self) -> date:
        if self.fixed_today:
            return date.fromisoformat(self.fixed_today)
        return datetime.now(self.tz).date()


def _asyncpg_url(url: str) -> str:
    """Accept provider URLs like postgres://...?sslmode=require (Neon) and adapt them for asyncpg."""
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    parts = urlsplit(url)
    scheme = "postgresql+asyncpg" if parts.scheme in ("postgres", "postgresql") else parts.scheme
    query = dict(parse_qsl(parts.query))
    if "sslmode" in query:
        mode = query.pop("sslmode")
        if mode in ("require", "verify-ca", "verify-full"):
            query["ssl"] = "require"
    query.pop("channel_binding", None)
    return urlunsplit((scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


@lru_cache
def get_settings() -> Settings:
    return Settings()
