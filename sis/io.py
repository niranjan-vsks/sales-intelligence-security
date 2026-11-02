"""Atomic Parquet writes from a DuckDB query."""

import os
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq


def write_parquet(con: duckdb.DuckDBPyConnection, sql: str, path: Path) -> int:
    """Materialise `sql`, write it to `path` via a .tmp sibling and an atomic rename.
    Returns the row count. The caller orders the query, so the bytes are deterministic."""
    table: pa.Table = con.sql(sql).to_arrow_table()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    pq.write_table(table, tmp, compression="zstd")
    os.replace(tmp, path)
    return int(table.num_rows)
