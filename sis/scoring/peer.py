"""Peer groups (DESIGN.md 5.1): country x breadth bucket, with fallbacks for small groups."""

from pathlib import Path

import duckdb
import pyarrow as pa
from pydantic import BaseModel

from sis import db, paths, scoring_config
from sis.config import settings
from sis.io import write_parquet
from sis.sqlfiles import run_sql

SQL_DIR = Path(__file__).resolve().parent / "sql"


class PeerResult(BaseModel):
    n_groups: int
    n_country_bucket: int
    n_bucket_only: int
    n_global: int


def bucket_label(lo: int, hi: int | None) -> str:
    if hi is None:
        return f"{lo}+"
    return str(lo) if lo == hi else f"{lo}-{hi}"


def register_buckets(con: duckdb.DuckDBPyConnection,
                     cfg: scoring_config.ScoringConfig | None = None) -> None:
    cfg = cfg or scoring_config.load()
    bk = cfg.peer.breadth_buckets
    con.register("buckets_arrow", pa.table({
        "lo": pa.array([lo for lo, _ in bk], pa.int64()),
        "hi": pa.array([hi for _, hi in bk], pa.int64()),
        "label": [bucket_label(lo, hi) for lo, hi in bk],
    }))
    con.execute("CREATE OR REPLACE TEMP TABLE buckets AS SELECT * FROM buckets_arrow")
    con.unregister("buckets_arrow")


def build_peer_table(con: duckdb.DuckDBPyConnection, min_size: int | None = None,
                     cfg: scoring_config.ScoringConfig | None = None) -> None:
    """Create temp table `peer(entity_id, country_code, bucket, peer_group)` from view `ent`."""
    register_buckets(con, cfg)
    run_sql(con, SQL_DIR / "01_peer.sql",
            min_size=settings.PEER_MIN_SIZE if min_size is None else min_size)


def peer_stats(con: duckdb.DuckDBPyConnection) -> PeerResult:
    row = con.execute("""
        SELECT count(DISTINCT peer_group),
               count(*) FILTER (WHERE peer_group NOT LIKE '*|%'),
               count(*) FILTER (WHERE peer_group LIKE '*|%' AND peer_group <> '*|*'),
               count(*) FILTER (WHERE peer_group = '*|*')
        FROM peer""").fetchall()[0]
    return PeerResult(n_groups=row[0], n_country_bucket=row[1], n_bucket_only=row[2],
                      n_global=row[3])


def assign_peer_groups(file_id: str, min_size: int | None = None) -> PeerResult:
    """Fill entities.peer_group for the file's active entities (blocked stay null) and rewrite
    $SIS_DATA/<file_id>/entities.parquet in place, same columns, same order."""
    path = paths.file_dir(file_id) / "entities.parquet"
    con = db.connect()
    con.execute("CREATE TEMP TABLE ent AS SELECT * FROM read_parquet(?)", [path.as_posix()])
    build_peer_table(con, min_size)
    stats = peer_stats(con)
    write_parquet(con, """
        SELECT e.* REPLACE (p.peer_group AS peer_group)
        FROM ent e LEFT JOIN peer p USING (entity_id) ORDER BY e.entity_id""", path)
    con.close()
    return stats
