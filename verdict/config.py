import os
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_database_url() -> str:
    """Falls back across the env var names Postgres marketplace integrations
    commonly inject (Neon via Vercel's own integration exposes several) when
    DATABASE_URL itself isn't set — pydantic-settings' own env override for
    the `database_url` field still wins whenever DATABASE_URL is present."""
    for name in ("DATABASE_URL", "POSTGRES_URL", "POSTGRES_PRISMA_URL", "POSTGRES_URL_NON_POOLING"):
        value = os.environ.get(name)
        if value:
            return value
    return "postgresql+psycopg://verdict:verdict@localhost:5432/verdict"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = Field(default_factory=_default_database_url)
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5-20251001"
    admin_token: str = "change-me"
    evidence_floor: int = 4
    turnstile_secret_key: str = ""
    turnstile_site_key: str = ""
    rate_limit_per_hour: int = 20
    daily_spend_cap_usd: float = 5.0
    estimated_cost_per_lead_usd: float = 0.01
    n8n_outbound_webhook_url: str = ""
    # Serverless platforms (Vercel and similar) can't run a persistent
    # `verdict-worker` process, so the pipeline runs inline inside the
    # request instead — same approach the original Next.js app uses.
    # Auto-enabled when the Vercel runtime's own VERCEL env var is present;
    # can also be set explicitly for other serverless hosts.
    inline_processing: bool = bool(os.environ.get("VERCEL"))

    @property
    def sqlalchemy_database_url(self) -> str:
        """Accept provider URLs while selecting the installed psycopg driver."""
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        return self.database_url


@lru_cache
def settings() -> Settings:
    return Settings()
