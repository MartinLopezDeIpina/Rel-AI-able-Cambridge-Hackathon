from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Absolute path to the project-root .env so settings load regardless of CWD.
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE, env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "FastAPI Template"
    environment: str = "development"
    debug: bool = True
    api_prefix: str = "/api"

    # LLM citation enrichment. Provider picks the backend: "openrouter" (Nemotron)
    # or "vertex" (Google Gemini via Vertex AI + ADC).
    llm_provider: str = "openrouter"
    llm_temperature: float = 0.0

    # OpenRouter (OpenAI-compatible).
    openrouter_api_key: str | None = None
    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = "nvidia/nemotron-3-nano-30b-a3b:free"  # swap tier via .env

    # Google Vertex AI (uses Application Default Credentials).
    google_model: str = "gemini-2.5-flash"
    google_project: str | None = None  # GCP project id (required for vertex)
    google_location: str = "us-central1"
    google_thinking_budget: int = 0  # 0 disables Gemini 2.5 "thinking" (~40% faster)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
