"""Held-out labels per active entity (cards/P4.md step 1, DATA_MODEL.md section 7)."""

from pathlib import Path

import duckdb

from sis import db, paths
from sis.io import write_parquet
from sis.signals.catalogue import edge_predicate, load_mappings
from sis.sqlfiles import run_sql

SQL_DIR = Path(__file__).resolve().parent / "sql"


def open_file(file_id: str) -> duckdb.DuckDBPyConnection:
    """Views b, v, be, sig, ent, sc over the file and table `act` (the active, scored entities)."""
    d = paths.file_dir(file_id)
    for name in ("banner_entity.parquet", "entities.parquet", "signals.parquet",
                 "scores.parquet"):
        if not (d / name).exists():
            raise FileNotFoundError(f"no {name} for {file_id}; run `sis score` first")
    con = db.connect()
    db.register(con, "b", paths.banners_glob(file_id))
    db.register(con, "v", paths.vulns_glob(file_id))
    for view, name in (("be", "banner_entity"), ("sig", "signals"), ("ent", "entities"),
                       ("sc", "scores")):
        db.register(con, view, (d / f"{name}.parquet").as_posix())
    con.execute("CREATE OR REPLACE TEMP TABLE act AS SELECT entity_id FROM sc")
    return con


def build_labels(file_id: str, con: duckdb.DuckDBPyConnection) -> int:
    """Temp table `labels` and $SIS_DATA/<file_id>/eval/labels.parquet. Returns the row count."""
    run_sql(con, SQL_DIR / "01_labels.sql", fragments={"edge": edge_predicate(load_mappings())})
    return write_parquet(con, "SELECT * FROM labels ORDER BY entity_id",
                         paths.eval_dir(file_id) / "labels.parquet")
