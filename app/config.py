from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    APP_NAME : str = "Telecom And Network Management System" 
    API_V1_PREFIX : str = "/api/v1"
    ENVIRONMENT : str = "development"

    # postgresql+psycopg2://user:password@localhost:5432/electricity_db
    DATABASE_URL: str = "sqlite:///./telecom.db"

    # --- JWT / Auth ---
    SECRET_KEY: str = "APP_KEYSECRET_2026"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # --- CORS ---
    CORS_ORIGINS: str = "*"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()