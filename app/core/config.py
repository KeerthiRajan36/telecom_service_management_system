from functools import lru_cache
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # General
    APP_NAME: str = "Telecom Service & Network Management System"
    ENV: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"

    # Database
    # Defaults to a local SQLite file so the project runs out-of-the-box
    # without external services. Point this at Postgres/MySQL in production,
    # e.g. postgresql+psycopg2://user:pass@host:5432/telecom
    DATABASE_URL: str = "sqlite:///./telecom.db"

    # JWT / Security
    SECRET_KEY: str = "CHANGE_ME_IN_PRODUCTION_super_secret_key"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 30

    # Rate limiting
    RATE_LIMIT_DEFAULT: str = "100/minute"

    # CORS
    CORS_ORIGINS: str = "*"

    # Pagination
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def _refuse_insecure_production_config(self):
        """Fail fast instead of silently running production with forgeable tokens."""
        if self.ENV.lower() == "production":
            if self.SECRET_KEY.startswith("CHANGE_ME") or len(self.SECRET_KEY) < 32:
                raise ValueError("SECRET_KEY must be set to a random value of at least 32 characters when ENV=production")
            if self.DEBUG:
                raise ValueError("DEBUG must be false when ENV=production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
