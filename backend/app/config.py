from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

LlmProvider = Literal["local", "cursor"]


def normalize_llm_provider(value: str | None) -> LlmProvider:
    if value and value.strip().lower() == "cursor":
        return "cursor"
    return "local"


_BACKEND_DIR = Path(__file__).resolve().parent.parent
_ENV_FILE = _BACKEND_DIR / ".env"


class Settings(BaseSettings):
    app_name: str = "Local CV Analyzer"
    database_path: Path = Path("data/app.db")
    export_dir: Path = Path("data/exports")
    # Adresler git'e gönderilmemesi için .env'den okunur (bkz. .env.example).
    ollama_base_url: str = ""
    ollama_model: str = "qwen3.5:9b-q4_K_M"
    ollama_embedding_model: str = "nomic-embed-text"
    request_timeout_seconds: float = 30.0
    llm_timeout_seconds: float = 120.0
    llm_analysis_timeout_seconds: float = 360.0
    max_input_chars: int = 60_000
    max_llm_context_chars: int = 14_000
    ollama_enable_thinking: bool = True
    ollama_num_ctx: int = 8192
    llm_generate_num_predict: int = 900
    llm_summary_num_predict: int = 700
    cv_rewrite_num_predict: int = 1800
    job_title_num_predict: int = 4096
    job_title_cv_chars: int = 9000
    cv_edit_num_predict: int = 4096
    cv_edit_apply_num_predict: int = 2048
    cv_edit_cv_chars: int = 9000
    cv_edit_guidance_chars: int = 2000
    llm_analysis_num_predict: int = 4096
    llm_analysis_cv_chars: int = 9000
    llm_analysis_job_chars: int = 6000
    translation_num_predict: int = 4096
    cv_rewrite_cv_chars: int = 9000
    cv_rewrite_job_chars: int = 4500
    latex_rewrite_cv_chars: int = 12000
    latex_rewrite_job_chars: int = 4500
    auto_translate_llm_input_to_english: bool = True
    translation_chunk_chars: int = 3000
    translation_min_confidence: float = 0.80
    default_llm_provider: str = "local"
    # .env'den okunur (bkz. .env.example).
    cursor_api_base_url: str = ""
    cursor_api_key: str = ""
    cursor_model: str = "auto"
    apify_api_token: str = ""
    apify_enabled: bool = False
    apify_linkedin_search_actor_id: str = ""
    apify_linkedin_job_actor_id: str = ""
    apify_kariyer_search_actor_id: str = ""
    apify_kariyer_job_actor_id: str = ""
    apify_max_results_per_source: int = 10
    apify_timeout_seconds: float = 120.0
    # .env'den JSON listesi olarak okunur (bkz. .env.example).
    cors_origins: list[str] = []

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        env_prefix="",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
