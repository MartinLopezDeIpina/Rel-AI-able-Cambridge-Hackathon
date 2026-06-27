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

    # LLM (OpenRouter, OpenAI-compatible). One client for the whole app: citation
    # enrichment AND the distortion judge stages reuse it.
    openrouter_api_key: str | None = None
    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = "google/gemini-3.5-flash"  # OpenRouter model id; override in .env
    llm_temperature: float = 0.0

    # Citation resolution / semantic index (the fallback resolver).
    index_dir: str = "index"           # holds embeddings.npy / chunks.json / sources.json
    corpus_dir: str = "index/texts"    # sources to build the index from if it's missing
    distortion_backend: str = "mock"   # "mock" (offline) | "openrouter" (LLM judge)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
