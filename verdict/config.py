from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://verdict:verdict@localhost:5432/verdict"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-haiku-latest"
    admin_token: str = "change-me"
    evidence_floor: int = 4

    @property
    def sqlalchemy_database_url(self) -> str:
        """Accept provider URLs while selecting the installed psycopg driver."""
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        return self.database_url


@lru_cache
def settings() -> Settings:
    return Settings()
