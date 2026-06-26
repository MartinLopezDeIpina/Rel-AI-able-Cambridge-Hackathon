from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "FastAPI Template"
    environment: str = "development"
    debug: bool = True
    api_prefix: str = "/api"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
