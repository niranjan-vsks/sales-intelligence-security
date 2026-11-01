"""Append-only ingest log (DATA_MODEL.md 1.3), rewritten atomically on each append."""

import os
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from sis import paths

S, INT, F, T = pa.string(), pa.int64(), pa.float64(), pa.timestamp("us")
SCHEMA = pa.schema([
    ("file_id", S), ("original_name", S), ("byte_length", INT), ("received_at", T),
    ("started_at", T), ("finished_at", T),
    # 'ok' | 'failed' | 'duplicate' | 'quarantined' | 'rejected' ('rejected' is added by P1:
    # a non-zstd file never reaches the quarantine check, but still deserves an audit row)
    ("status", S),
    ("lines_read", INT), ("rows_written", INT), ("rows_dropped", INT),
    ("vuln_rows_written", INT), ("dropped_reasons", S), ("wall_seconds", F),
    ("pipeline_version", S), ("error", S),
])


def read_ingest_log() -> pa.Table:
    path = paths.ingest_log_path()
    if not path.exists():
        return SCHEMA.empty_table()
    return pq.read_table(path, schema=SCHEMA)


def append_ingest_log(row: dict[str, Any]) -> None:
    """Add one row. Columns missing from `row` are null; unknown keys are rejected."""
    unknown = set(row) - set(SCHEMA.names)
    if unknown:
        raise KeyError(f"not ingest_log columns: {sorted(unknown)}")
    new = pa.Table.from_pylist([{name: row.get(name) for name in SCHEMA.names}], schema=SCHEMA)
    table = pa.concat_tables([read_ingest_log(), new])
    path = paths.ingest_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    pq.write_table(table, tmp, compression="zstd")
    os.replace(tmp, path)
