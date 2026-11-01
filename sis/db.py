"""DuckDB connection factory with the settings every pipeline stage shares."""

import re
from pathlib import Path

import duckdb

from sis import paths
from sis.config import settings

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _lit(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def connect(
    read_only: bool = False, database: str | Path | None = None
) -> duckdb.DuckDBPyConnection:
    """Open a connection. In memory unless `database` is given.

    `read_only` only has meaning for a database file; an in-memory connection over
    Parquet views cannot write to the source files either way.
    """
    tmp = paths.duckdb_tmp_dir()
    tmp.mkdir(parents=True, exist_ok=True)  # lazily, so a bare machine works
    if database is None:
        con = duckdb.connect()
    else:
        con = duckdb.connect(str(database), read_only=read_only)
    con.execute(f"SET memory_limit = {_lit(settings.DUCKDB_MEMORY_LIMIT)}")
    con.execute(f"SET threads = {int(settings.DUCKDB_THREADS)}")
    con.execute(f"SET temp_directory = {_lit(tmp.as_posix())}")
    con.execute("SET preserve_insertion_order = false")
    return con


def register(con: duckdb.DuckDBPyConnection, name: str, path_glob: str) -> None:
    """Create or replace view `name` over the Parquet files matching `path_glob`."""
    if not _IDENT.match(name):
        raise ValueError(f"invalid view name: {name!r}")
    con.execute(f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM read_parquet({_lit(path_glob)})")
