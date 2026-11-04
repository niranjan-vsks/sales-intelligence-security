"""Events between 2 consecutive files, and the entity history (DATA_MODEL.md 4, phase P6).

The grain is the entity: an event says what changed for 1 account between the 2 deliveries.
Everything is a function of the 2 per-file table sets, so a rerun gives the same bytes: the
event id is a hash, `detected_at` is the arrival time of the newer delivery, and the output is
sorted."""

import time
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
from pydantic import BaseModel

from sis import db, delta_config, paths
from sis.ingest.log import read_ingest_log
from sis.io import write_parquet
from sis.signals.catalogue import ADMIN_MODULES
from sis.sqlfiles import run_sql

SQL_DIR = Path(__file__).resolve().parent / "sql"
EVENT_TYPES = (
    "entity_new", "entity_gone", "service_new", "service_gone", "signal_appeared",
    "signal_cleared", "cert_expired_since", "protection_removed", "protection_added",
    "exposure_up", "exposure_down", "segment_changed")


class DiffResult(BaseModel):
    from_file: str
    to_file: str
    n_events: int
    by_type: dict[str, int]
    by_severity: dict[int, int]
    n_active_from: int
    n_active_to: int
    detected_at: datetime
    wall_seconds: float
    path: str


def _lit(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def severity_sql(cfg: delta_config.Severity) -> str:
    """The CASE expression of config/delta.yaml's severity rules (phase P6 step 3)."""
    admin = ", ".join(_lit(m) for m in ADMIN_MODULES)
    high = ", ".join(_lit(s) for s in cfg.high_signals)
    whens = [
        f"WHEN event_type = 'service_new' AND to_value IN ({admin}) "
        f"THEN {cfg.admin_service_new}",
        f"WHEN event_type = 'signal_appeared' AND subject IN ({high}) "
        f"THEN {cfg.high_signal_severity}",
        *(f"WHEN event_type = {_lit(t)} THEN {n}" for t, n in sorted(cfg.by_type.items())),
    ]
    return "CASE " + " ".join(whens) + f" ELSE {cfg.default} END"


def received_at(file_id: str) -> datetime | None:
    for r in reversed(read_ingest_log().to_pylist()):
        if r["file_id"] == file_id and r["status"] == "ok":
            got: datetime = r["received_at"]
            return got
    return None


def _need(file_id: str, names: tuple[str, ...]) -> Path:
    d = paths.file_dir(file_id)
    for n in names:
        if not (d / n).exists():
            raise FileNotFoundError(f"no {n} for {file_id}; run resolve and score first")
    return d


def load_side(con: duckdb.DuckDBPyConnection, side: str, file_id: str) -> None:
    """Temp tables act_<side>, sig_<side>, svc_<side>, evd_<side> for 1 file."""
    d = _need(file_id, ("entities.parquet", "scores.parquet", "signals.parquet",
                        "evidence.parquet", "banner_entity.parquet"))

    def q(name: str) -> str:
        return _lit((d / name).as_posix())

    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE act_{side} AS
        SELECT e.entity_id, e.key_kind, e.key_value, s.exposure, s.segment
        FROM read_parquet({q('entities.parquet')}) e
        JOIN read_parquet({q('scores.parquet')}) s USING (entity_id)
        WHERE e.status = 'active'""")
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE sig_{side} AS
        SELECT entity_id, signal_id, fact, value
        FROM read_parquet({q('signals.parquet')}) WHERE value > 0""")
    # a service is an (ip, port) of the entity; 2 banners on 1 ip:port are 1 service
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE svc_{side} AS
        SELECT be.entity_id, coalesce(b.ip_str, b.ipv6, '') || ':' || coalesce(b.port::VARCHAR, '')
                   AS skey, min(b.module) AS module
        FROM read_parquet({_lit(paths.banners_glob(file_id))}) b
        JOIN (SELECT DISTINCT banner_id, entity_id FROM read_parquet({q('banner_entity.parquet')})
              WHERE entity_id IN (SELECT entity_id FROM act_{side})) be ON be.banner_id = b.id
        GROUP BY 1, 2""")
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE evd_{side} AS
        SELECT entity_id, signal_id, left(string_agg(DISTINCT value, ', ' ORDER BY value), 200) AS v
        FROM read_parquet({q('evidence.parquet')}) WHERE value IS NOT NULL
          AND entity_id IN (SELECT entity_id FROM act_{side})
        GROUP BY 1, 2""")


def diff(from_file: str, to_file: str, detected_at: datetime | None = None,
         write: bool = True) -> DiffResult:
    """Compute the events from `from_file` to `to_file` and, with `write`, replace that pair's
    rows in $SIS_DATA/history/events.parquet."""
    t0 = time.time()
    cfg = delta_config.load().diff
    when = detected_at or received_at(to_file)
    if when is None:
        raise ValueError(f"{to_file} is not in the ingest log; pass detected_at")
    con = db.connect()
    for side, fid in (("a", from_file), ("b", to_file)):
        load_side(con, side, fid)
    run_sql(con, SQL_DIR / "01_events.sql", fragments={"severity": severity_sql(cfg.severity)},
            threshold=cfg.exposure_threshold, from_file=from_file, to_file=to_file,
            detected_at=when.isoformat(sep=" "))
    dup = con.execute("SELECT count(*) - count(DISTINCT event_id) FROM events").fetchall()[0][0]
    if dup:
        raise RuntimeError(f"{dup} duplicate event ids: (entity, type, subject) is not unique")
    by_type = dict(con.execute(
        "SELECT event_type, count(*) FROM events GROUP BY 1 ORDER BY 1").fetchall())
    by_sev = {int(k): int(v) for k, v in con.execute(
        "SELECT severity, count(*) FROM events GROUP BY 1 ORDER BY 1").fetchall()}
    n_a = int(con.execute("SELECT count(*) FROM act_a").fetchall()[0][0])
    n_b = int(con.execute("SELECT count(*) FROM act_b").fetchall()[0][0])
    out = paths.events_path()
    if write:
        # the table keeps every other pair as it was; this pair is replaced (idempotent)
        keep = ""
        if out.exists():
            keep = (f"SELECT * FROM read_parquet({_lit(out.as_posix())}) "
                    f"WHERE NOT (from_file = {_lit(from_file)} AND to_file = {_lit(to_file)}) "
                    "UNION ALL ")
        write_parquet(con, f"SELECT * FROM ({keep}SELECT * FROM events) "
                           "ORDER BY from_file, to_file, event_id", out)
    n_events = int(con.execute("SELECT count(*) FROM events").fetchall()[0][0])
    res = DiffResult(
        from_file=from_file, to_file=to_file, n_events=n_events, by_type=by_type,
        by_severity=by_sev, n_active_from=n_a, n_active_to=n_b, detected_at=when,
        wall_seconds=round(time.time() - t0, 2), path=str(out))
    con.close()
    return res


def append_history(file_id: str) -> int:
    """Add the file's entity + score rows to entity_history.parquet, replacing any earlier rows
    of the same file_id. Returns the file's row count."""
    d = _need(file_id, ("entities.parquet", "scores.parquet"))
    con = db.connect()
    ent = _lit((d / "entities.parquet").as_posix())
    sc = _lit((d / "scores.parquet").as_posix())
    ecols = {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet({ent})").fetchall()}
    extra = ", ".join(f"s.{c}" for (c, *_) in con.execute(
        f"DESCRIBE SELECT * FROM read_parquet({sc})").fetchall() if c not in ecols)
    new = (f"SELECT e.*, {extra} FROM read_parquet({ent}) e "
           f"LEFT JOIN read_parquet({sc}) s USING (entity_id)")
    out = paths.entity_history_path()
    keep = ""
    if out.exists():
        keep = (f"SELECT * FROM read_parquet({_lit(out.as_posix())}) "
                f"WHERE file_id <> {_lit(file_id)} UNION ALL BY NAME ")
    write_parquet(con, f"SELECT * FROM ({keep}{new}) ORDER BY file_id, entity_id", out)
    n_file = int(con.execute(f"SELECT count(*) FROM read_parquet({ent})").fetchall()[0][0])
    con.close()
    return n_file


def read_events(from_file: str, to_file: str) -> list[dict[str, Any]]:
    con = db.connect()
    cur = con.execute(
        f"SELECT * FROM read_parquet({_lit(paths.events_path().as_posix())}) "
        "WHERE from_file = ? AND to_file = ? ORDER BY event_id", [from_file, to_file])
    cols = [c[0] for c in cur.description or []]
    rows = [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]
    con.close()
    return rows
