"""Evidence: up to EVIDENCE_PER_SIGNAL banners per (entity, signal) (DATA_MODEL.md 3.2)."""

import duckdb

from sis import paths
from sis.io import write_parquet
from sis.scoring.peer import build_peer_table
from sis.signals.catalogue import SIGNALS
from sis.signals.compute import open_file, prepare

EVIDENCE_PER_SIGNAL = 5  # DATA_MODEL 3.2; a schema property, not a tunable
VALUE_CHARS = 300


def evidence_sql(file_id: str) -> str:
    """The 5 firing banners with the largest data_len, then lowest port, then banner_id."""
    parts = []
    for s in SIGNALS:
        parts.append(
            f"SELECT entity_id, '{s.signal_id}' AS signal_id, banner_id, ip, port, module, "
            f"'{s.source_field}' AS field, "
            f"left(CAST(({s.evidence_value_expr}) AS VARCHAR), {VALUE_CHARS}) AS value, "
            f"snippet, timestamp AS observed_at, "
            f"row_number() OVER (PARTITION BY entity_id ORDER BY data_len DESC NULLS LAST, "
            f"port, banner_id) AS rn "
            f"FROM ebf WHERE f_{s.signal_id}")
    union = "\nUNION ALL\n".join(parts)
    return (f"SELECT entity_id, signal_id, banner_id, ip, port, module, field, value, snippet, "
            f"observed_at, '{file_id}' AS file_id FROM ({union}) "
            f"WHERE rn <= {EVIDENCE_PER_SIGNAL} ORDER BY entity_id, signal_id, rn")


def compute_evidence(file_id: str, con: duckdb.DuckDBPyConnection | None = None) -> int:
    """Write $SIS_DATA/<file_id>/evidence.parquet. Returns the row count."""
    own = con is None
    if con is None:
        con = open_file(file_id)
        build_peer_table(con)
        prepare(con)
    n = write_parquet(con, evidence_sql(file_id), paths.file_dir(file_id) / "evidence.parquet")
    if own:
        con.close()
    return n
