"""Shared DuckDB setup. Every analysis script takes SRC = sample | full as argv[1].

Data lives outside the OneDrive-synced repo, in DATA_DIR (default below), so the
100+ GB of Parquet is never synced or committed.
"""
import os
import sys
from pathlib import Path

import duckdb

DATA_DIR = Path(os.environ.get("SIS_DATA", r"C:/Users/NIRANJAN VSKS/sis_data"))
FINDINGS = Path(__file__).resolve().parent.parent
SRC = sys.argv[1] if len(sys.argv) > 1 else "sample"
TAG = "SAMPLE" if SRC == "sample" else "FULL"


def connect():
    con = duckdb.connect()
    con.execute("SET memory_limit = '10GB'")
    tmp = DATA_DIR / "duckdb_tmp"
    tmp.mkdir(exist_ok=True)
    con.execute(f"SET temp_directory = '{tmp.as_posix()}'")
    con.execute("SET preserve_insertion_order = false")
    con.execute("SET threads = 12")
    root = (DATA_DIR / SRC).as_posix()
    con.execute(f"CREATE VIEW b AS SELECT * FROM read_parquet('{root}/banners/*.parquet')")
    con.execute(f"CREATE VIEW v AS SELECT * FROM read_parquet('{root}/vulns/*.parquet')")
    return con


def out(name):
    """findings/<name> for the full run; a scratch copy outside the repo for the sample."""
    base = FINDINGS if SRC == "full" else DATA_DIR / "findings_sample"
    p = base / name
    p.parent.mkdir(parents=True, exist_ok=True)
    return p
