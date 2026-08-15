from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://verdict:verdict@localhost:5432/verdict"
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

    @property
    def sqlalchemy_database_url(self) -> str:
        """Accept provider URLs while selecting the installed psycopg driver."""
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        return self.database_url


@lru_cache
def settings() -> Settings:
    return Settings()
