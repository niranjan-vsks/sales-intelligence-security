"""Runtime settings. Every tunable that is not a scoring constant lives here."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Never inside the repo: the repo is synced by OneDrive and the data is 100+ GB.
    SIS_DATA: Path = Path("C:/Users/NIRANJAN VSKS/sis_data")

    ROLLUP_MAX_IPS: int = 50
    PEER_MIN_SIZE: int = 30
    CLASSIFY_TOP_N: int = 5000

    OPENROUTER_API_KEY: str | None = None
    LLM_BASE_URL: str = "https://openrouter.ai/api/v1"
    LLM_BUDGET_USD_TOTAL: float = 12.0
    LOGFIRE_TOKEN: str | None = None

    DUCKDB_MEMORY_LIMIT: str = "10GB"
    DUCKDB_THREADS: int = 12
    INGEST_WORKERS: int = 11


settings = Settings()
