"""Shared fixtures. `tiny_banners` flattens the committed 200-line sample (explorer's code)."""

import importlib.util
from dataclasses import dataclass
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "tiny_banners.jsonl"
# P1 moves the flattener into sis/ingest/flatten.py; until then the explorer's copy is reused.
EXPLORER_FLATTEN = REPO_ROOT / "findings" / "queries" / "01_flatten.py"


def _load_explorer_flatten():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("explorer_flatten", EXPLORER_FLATTEN)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True)
class TinyBanners:
    root: Path
    n_lines: int
    n_rows: int

    @property
    def banners_glob(self) -> str:
        return (self.root / "banners" / "*.parquet").as_posix()

    @property
    def vulns_glob(self) -> str:
        return (self.root / "vulns" / "*.parquet").as_posix()


@pytest.fixture
def tiny_banners(tmp_path: Path) -> TinyBanners:
    """A 200-row banners Parquet and a vulns Parquet under tmp_path."""
    flatten = _load_explorer_flatten()
    root = tmp_path / "tiny"
    (root / "banners").mkdir(parents=True)
    (root / "vulns").mkdir()
    buf = FIXTURE.read_bytes()
    stats = flatten.work((0, buf, str(root)))
    vulns_part = root / "vulns" / "part-00000.parquet"
    if not vulns_part.exists():  # the sample may hold no CVEs; keep the table present
        pq.write_table(pa.Table.from_pylist([], schema=flatten.VSCHEMA), vulns_part)
    return TinyBanners(root=root, n_lines=stats["lines"], n_rows=stats["rows"])
