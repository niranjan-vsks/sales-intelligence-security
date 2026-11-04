"""Signals per (entity, signal), generated from the catalogue (DATA_MODEL.md 3.1, phase P3)."""

from pathlib import Path

import duckdb

from sis import db, paths
from sis.io import write_parquet
from sis.scoring.peer import build_peer_table
from sis.signals.catalogue import SIGNALS, edge_predicate, load_mappings, render
from sis.sqlfiles import run_sql

SQL_DIR = Path(__file__).resolve().parent / "sql"


def open_file(file_id: str) -> duckdb.DuckDBPyConnection:
    """A connection with views b, v, be and a materialised `ent` for the file."""
    out = paths.file_dir(file_id)
    for name in ("banner_entity.parquet", "entities.parquet"):
        if not (out / name).exists():
            raise FileNotFoundError(f"no {name} for {file_id}; run `sis resolve` first")
    con = db.connect()
    # mapping W04 in config/what_we_sell_map.csv (the explorer's file, copied unchanged) uses
    # the `x -> ...` lambda form, which DuckDB 2.0 only parses with this setting
    con.execute("SET lambda_syntax = 'ENABLE_SINGLE_ARROW'")
    db.register(con, "b", paths.banners_glob(file_id))
    db.register(con, "v", paths.vulns_glob(file_id))
    db.register(con, "be", (out / "banner_entity.parquet").as_posix())
    con.execute("CREATE TEMP TABLE ent AS SELECT * FROM read_parquet(?)",
                [(out / "entities.parquet").as_posix()])
    return con


def prepare(con: duckdb.DuckDBPyConnection) -> None:
    """Build be_active, vulns_clean, eb, and `ebf` = eb plus 1 boolean f_<signal_id> per signal."""
    mappings = load_mappings()
    run_sql(con, SQL_DIR / "01_vulns_clean.sql")
    run_sql(con, SQL_DIR / "02_eb.sql", fragments={"edge": edge_predicate(mappings)})
    flags = ",\n       ".join(f"{render(s, mappings)} AS f_{s.signal_id}" for s in SIGNALS)
    con.execute(f"CREATE OR REPLACE TEMP TABLE ebf AS SELECT *,\n       {flags}\nFROM eb")


def signals_sql() -> str:
    """1 SELECT per catalogue row, UNION ALL. Always-present signals get a row for every active
    entity (value 0 when no banner fires); the rest only where at least 1 banner fires."""
    parts = []
    for s in SIGNALS:
        fired = (f"SELECT entity_id, CAST({s.sql_expr} AS DOUBLE) AS value, "
                 f"count(*) AS n_banners FROM ebf WHERE f_{s.signal_id} GROUP BY entity_id")
        head = f"'{s.signal_id}' AS signal_id, '{s.fact}' AS fact, '{s.kind}' AS kind"
        if s.always:
            parts.append(f"SELECT p.entity_id, {head}, coalesce(x.value, 0) AS value, "
                         f"coalesce(x.n_banners, 0) AS n_banners "
                         f"FROM peer p LEFT JOIN ({fired}) x USING (entity_id)")
        else:
            parts.append(f"SELECT entity_id, {head}, value, n_banners FROM ({fired})")
    return "\nUNION ALL\n".join(parts)


def build_signals(con: duckdb.DuckDBPyConnection) -> None:
    """Temp table `sig` with pct_in_peer (step 5). Needs `ebf` and `peer`."""
    con.execute(f"CREATE OR REPLACE TEMP TABLE sig_raw AS {signals_sql()}")
    run_sql(con, SQL_DIR / "03_pct.sql")


def compute_signals(file_id: str, con: duckdb.DuckDBPyConnection | None = None) -> int:
    """Write $SIS_DATA/<file_id>/signals.parquet. Returns the row count."""
    own = con is None
    if con is None:
        con = open_file(file_id)
        build_peer_table(con)
        prepare(con)
    build_signals(con)
    n = write_parquet(con, f"""
        SELECT entity_id, signal_id, fact, value, n_banners, pct_in_peer,
               '{file_id}' AS file_id
        FROM sig ORDER BY entity_id, signal_id""", paths.file_dir(file_id) / "signals.parquet")
    if own:
        con.close()
    return n
