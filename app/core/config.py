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

    # LLM citation enrichment + the distortion judge (one client, via build_llm).
    # Provider picks the backend: "vertex" (Google Gemini via Vertex AI + ADC,
    # needs a GCP project), "gemini" (Gemini Developer API — API key only, no
    # project), or "openrouter" (Nemotron via OpenAI-compatible API).
    llm_provider: str = "vertex"
    llm_temperature: float = 0.0

    # OpenRouter (OpenAI-compatible) — non-default fallback provider.
    openrouter_api_key: str | None = None
    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = "nvidia/nemotron-3-nano-30b-a3b:free"  # swap tier via .env

    # Google Vertex AI (uses Application Default Credentials).
    google_model: str = "gemini-2.5-flash"
    google_project: str | None = None  # GCP project id (required for vertex)
    google_location: str = "us-central1"
    google_thinking_budget: int = 0  # 0 disables Gemini 2.5 "thinking" (~40% faster)

    # Gemini Developer API (provider "gemini") — API key only, no GCP project.
    gemini_api_key: str | None = None  # GEMINI_API_KEY (AI Studio / express "AQ." key)

    # Citation resolution / semantic index (the fallback resolver).
    index_dir: str = "index"           # holds embeddings.npy / chunks.json / sources.json
    # Source corpus the (legacy) semantic resolver auto-builds its index from. MUST
    # point at the source judgments (pdfs/), NOT index/texts (that is the indexer's
    # extracted-text cache under index_dir). The runtime pipeline now resolves via the
    # metadata-match layer (sources_metadata_path), so this only matters if the semantic
    # resolver is used directly.
    corpus_dir: str = "pdfs"
    distortion_backend: str = "vertex"  # "vertex" (Gemini judge) | "mock" (offline)

    # Semantic-entropy uncertainty for Step 4 (Farquhar/Kuhn-style): sample the
    # support/contradict judgement N times, cluster by meaning, weight by sequence
    # probability (Gemini logprobs), and take entropy over clusters. Only runs with
    # the vertex (Gemini) judge; the N samples are issued concurrently.
    semantic_entropy_enabled: bool = True
    semantic_entropy_samples: int = 5            # N samples per (paragraph, citation)
    semantic_entropy_temperature: float = 1.0    # sampling temperature for diversity

    # One-off source-metadata builder (app.services.source_metadata_builder): a
    # preprocessing step, NOT part of the runtime pipeline. Vision-OCRs the first
    # pages of each source judgment, then extracts its citation metadata to JSON.
    # Vision OCR needs a multimodal model, so the builder forces its own provider
    # (default Gemini via Vertex) independent of the runtime ``llm_provider``, which
    # may be a text-only model like Nemotron.
    source_llm_provider: str = "vertex"                       # "vertex" | "openrouter"
    source_dir: str = "data"                                  # the source PDFs/judgments
    source_metadata_out: str = "data/source_metadata.json"    # the metadata "database"
    # Full-document vision-OCR transcripts (ALL pages), for later pipeline steps.
    source_texts_dir: str = "data/text_source"               # one <stem>.txt per source
    vision_dpi: int = 170                                     # page render DPI for OCR
    # A page with at least this many embedded-text chars is treated as digital (use
    # its text layer for free); below it the page is a scan and goes to vision OCR.
    text_layer_min_chars: int = 100
    vision_ocr_batch_pages: int = 3                           # pages per vision call (full OCR)
    # Files rendered/OCR'd at once. Kept small on purpose: PDF page rendering holds the
    # GIL, so too many files at once starves the progress bars and the vision calls.
    # Throughput comes from per-file batch parallelism + the global call cap, not from
    # rendering many files at once. (0 = all files — avoid for big scanned corpora.)
    vision_ocr_concurrency: int = 4
    vision_intra_concurrency: int = 10                        # page-batches per file in parallel
    vision_max_concurrent_calls: int = 16                     # global cap on simultaneous vision calls
    vision_max_pages: int = 3                                 # max leading pages for metadata
    source_request_sleep: float = 1.0                        # throttle between documents (s)

    # Source-metadata builder (app.services.source_metadata_builder): one-off step that
    # reads the vision-OCR transcripts in source_texts_dir and extracts each source's
    # Citation-shaped metadata to source_metadata_out via Gemini structured output.
    source_metadata_chars: int = 12000       # leading transcript chars fed per source
    source_metadata_concurrency: int = 8     # transcripts extracted at once (batch control)

    # Sources metadata database for the existence + metadata-equality check
    # (the metadata-match layer). This is the file the builder above writes
    # (source_metadata_out); keep them in sync. Keyed by source identifier; each
    # entry mirrors the EnrichedCitation field schema plus a `source` filename.
    sources_metadata_path: str = "data/source_metadata.json"

    # Step 5 report sink — the frontend (Vite) serves public/ at /, so it fetches
    # /report.json. Relative paths resolve against the repo root.
    report_output_path: str = "app/frontend/public/report.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
