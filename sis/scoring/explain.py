"""Why an entity scored what it did: per-signal contributions to exposure (cards/P3.md step 9).

The same SQL that produces scores.top_signals (sql/02_facts.sql) runs over 1 entity's stored
signals, so the explanation can never drift from the score."""

from pathlib import Path

import duckdb

from sis import db, paths, scoring_config
from sis.scoring.score import SQL_DIR, params, wide_sql
from sis.sqlfiles import run_sql


def contributions(entity_id: str, file_id: str,
                  cfg: scoring_config.ScoringConfig | None = None,
                  signals_path: Path | None = None,
                  con: duckdb.DuckDBPyConnection | None = None) -> list[tuple[str, float]]:
    """(signal_id, contribution) ordered by contribution desc, then signal_id. Only signals
    that add to exposure appear; fact D signals never do. `signals_path` defaults to the file's
    signals.parquet (the app passes the bundle's); `con` defaults to a new connection, and when
    given gets temp tables sig, one, wide, terms, facts, contrib replaced."""
    cfg = cfg or scoring_config.load()
    path: Path = signals_path or paths.file_dir(file_id) / "signals.parquet"
    own = con is None
    if con is None:
        con = db.connect()
    con.execute("CREATE OR REPLACE TEMP TABLE sig AS SELECT * FROM read_parquet(?) "
                "WHERE entity_id = ?", [path.as_posix(), entity_id])
    con.execute("CREATE OR REPLACE TEMP TABLE one AS SELECT ?::VARCHAR AS entity_id, "
                "NULL::VARCHAR AS country_code", [entity_id])
    con.execute(f"CREATE OR REPLACE TEMP TABLE wide AS {wide_sql(base='one')}")
    run_sql(con, SQL_DIR / "02_facts.sql", fragments={"prerequisite": cfg.prerequisite_sql},
            **params(cfg))
    rows = con.execute("SELECT signal_id, contribution FROM contrib "
                       "ORDER BY contribution DESC, signal_id").fetchall()
    if own:
        con.close()
    return [(str(s), float(c)) for s, c in rows]
