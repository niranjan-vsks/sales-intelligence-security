"""Every filesystem path the pipeline reads or writes. No path is built anywhere else.

Layout follows DATA_MODEL.md. SIS_DATA is read at call time so tests can point it at a tmp dir.
"""

from pathlib import Path

from sis.config import settings

REPO_ROOT = Path(__file__).resolve().parent.parent


def data_root() -> Path:
    return settings.SIS_DATA


def config_dir() -> Path:
    return REPO_ROOT / "config"


def file_dir(file_id: str) -> Path:
    return data_root() / file_id


def tmp_dir(file_id: str) -> Path:
    """Where a run writes before the atomic rename to file_dir (DESIGN.md section 3)."""
    return data_root() / f"{file_id}.tmp"


def banners_glob(file_id: str) -> str:
    return (file_dir(file_id) / "banners" / "*.parquet").as_posix()


def vulns_glob(file_id: str) -> str:
    return (file_dir(file_id) / "vulns" / "*.parquet").as_posix()


def eval_dir(file_id: str) -> Path:
    return file_dir(file_id) / "eval"


def eval_fixture_dir() -> Path:
    """The committed 50,000-entity bundle the CI eval step recomputes metrics on."""
    return REPO_ROOT / "tests" / "fixtures" / "eval_bundle"


def eval_thresholds_path() -> Path:
    return REPO_ROOT / "tests" / "eval_thresholds.json"


def quarantine_dir() -> Path:
    return data_root() / "quarantine"


def current_dir() -> Path:
    return data_root() / "current"


def serve_dir(version: str) -> Path:
    return data_root() / "serve" / version


def history_dir() -> Path:
    return data_root() / "history"


def ingest_log_path() -> Path:
    return data_root() / "ingest_log.parquet"


def llm_calls_path() -> Path:
    return data_root() / "llm_calls.parquet"


def duckdb_tmp_dir() -> Path:
    return data_root() / "duckdb_tmp"
