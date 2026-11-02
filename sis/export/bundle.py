"""The serve bundle (DATA_MODEL.md 6, cards/P5.md step 1): the only artefact the app reads."""

import json
from datetime import UTC, datetime
from pathlib import Path

import duckdb
from pydantic import BaseModel

from sis import PIPELINE_VERSION, db, paths, scoring_config

MAX_BUNDLE_MB = 800  # cards/P5.md: above this the card stops and reports

EVENTS_SCHEMA = """
    event_id VARCHAR, entity_id VARCHAR, event_type VARCHAR, subject VARCHAR,
    from_file VARCHAR, to_file VARCHAR, from_value VARCHAR, to_value VARCHAR,
    detected_at TIMESTAMP, severity INTEGER"""
PROFILE_SCHEMA = """
    entity_id VARCHAR, is_business BOOLEAN, industry VARCHAR, description VARCHAR,
    confidence DOUBLE"""


class BundleResult(BaseModel):
    bundle_version: str
    path: str
    n_accounts: int
    n_evidence: int
    n_signals: int
    n_events: int
    size_mb: float


def _lit(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _optional(con: duckdb.DuckDBPyConnection, view: str, path: Path, schema: str) -> None:
    """A view over `path`, or an empty table with the right schema when it does not exist."""
    if path.exists():
        db.register(con, view, path.as_posix())
    else:
        con.execute(f"CREATE TEMP TABLE {view} ({schema})")


def _copy(con: duckdb.DuckDBPyConnection, sql: str, path: Path) -> int:
    n = int(con.execute(f"SELECT count(*) FROM ({sql})").fetchall()[0][0])
    con.execute(f"COPY ({sql}) TO {_lit(path.as_posix())} (FORMAT parquet, COMPRESSION zstd)")
    return n


def export(bundle_version: str | None = None) -> BundleResult:
    """Write $SIS_DATA/serve/<version>/{accounts,evidence,events,signals}.parquet + bundle.json.

    accounts = current entities JOIN current scores LEFT JOIN entity_profile, active only,
    ordered by rank_overall so the first row group is the first page. Evidence and signals
    come from the file each account's score was computed on."""
    cfg = scoring_config.load()
    version = bundle_version or (
        datetime.now(UTC).strftime("%Y%m%d-%H%M") + "-" + cfg.scoring_version)
    cur = paths.current_dir()
    for name in ("entities.parquet", "scores.parquet"):
        if not (cur / name).exists():
            raise FileNotFoundError(f"no current/{name}; run `sis resolve --merge` and "
                                    "`sis score --merge` first")
    out = paths.serve_dir(version)
    out.mkdir(parents=True, exist_ok=True)

    con = db.connect()
    db.register(con, "ent", (cur / "entities.parquet").as_posix())
    db.register(con, "sc", (cur / "scores.parquet").as_posix())
    _optional(con, "prof", cur / "entity_profile.parquet", PROFILE_SCHEMA)
    _optional(con, "ev", paths.history_dir() / "events.parquet", EVENTS_SCHEMA)
    file_ids = sorted(r[0] for r in con.execute("SELECT DISTINCT file_id FROM sc").fetchall())
    for view, name in (("evid", "evidence"), ("sig", "signals")):
        files = ", ".join(_lit((paths.file_dir(f) / f"{name}.parquet").as_posix())
                          for f in file_ids)
        con.execute(f"CREATE VIEW {view} AS SELECT * FROM read_parquet([{files}])")

    n_accounts = _copy(con, """
        SELECT e.entity_id, e.key_kind, e.key_value, e.display_name, e.n_banners, e.n_ips,
               e.n_ports, e.n_modules, e.country_code, e.country_codes, e.org_mode,
               e.cloud_providers, e.peer_group, e.first_seen_file, e.last_seen_file,
               s.fact_a, s.fact_b, s.fact_c, s.fact_d, s.exposure, s.segment, s.priority,
               s.rank_overall, s.rank_in_segment, s.rank_in_country, s.top_signals,
               s.scoring_version, s.file_id,
               p.is_business, p.industry, p.description, p.confidence AS industry_confidence
        FROM sc s JOIN ent e USING (entity_id)
        LEFT JOIN prof p USING (entity_id)
        WHERE e.status = 'active'
        ORDER BY s.rank_overall""", out / "accounts.parquet")
    # evidence and signals of the account's own scored file, active accounts only
    keep = ("SELECT sc.entity_id, sc.file_id FROM sc JOIN ent USING (entity_id) "
            "WHERE ent.status = 'active'")
    n_evidence = _copy(con, f"""
        SELECT x.* FROM evid x SEMI JOIN ({keep}) k USING (entity_id, file_id)
        ORDER BY x.entity_id, x.signal_id, x.banner_id""", out / "evidence.parquet")
    n_signals = _copy(con, f"""
        SELECT x.* FROM sig x SEMI JOIN ({keep}) k USING (entity_id, file_id)
        ORDER BY x.entity_id, x.signal_id""", out / "signals.parquet")
    # last 2 files only (DATA_MODEL.md 6)
    n_events = _copy(con, """
        SELECT * FROM ev
        WHERE to_file IN (SELECT to_file FROM ev GROUP BY 1 ORDER BY max(detected_at) DESC
                          LIMIT 1)
        ORDER BY entity_id, detected_at, event_id""", out / "events.parquet")
    con.close()

    meta = {
        "bundle_version": version, "built_at": datetime.now(UTC).isoformat(),
        "file_ids": file_ids, "scoring_version": cfg.scoring_version,
        "n_accounts": n_accounts, "n_evidence": n_evidence,
        "pipeline_version": PIPELINE_VERSION,
    }
    (out / "bundle.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    size = sum(f.stat().st_size for f in out.iterdir() if f.is_file()) / 1e6
    return BundleResult(bundle_version=version, path=str(out), n_accounts=n_accounts,
                        n_evidence=n_evidence, n_signals=n_signals, n_events=n_events,
                        size_mb=round(size, 1))
