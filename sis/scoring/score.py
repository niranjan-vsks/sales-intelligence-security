"""Scores per active entity (DESIGN.md 5.2, 5.3; DATA_MODEL.md 3.3) and the merge to current."""

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa
from pydantic import BaseModel

from sis import PIPELINE_VERSION, db, paths, scoring_config
from sis.ingest.log import read_ingest_log
from sis.io import write_parquet
from sis.scoring import report
from sis.scoring.peer import PeerResult, assign_peer_groups, build_peer_table, peer_stats
from sis.signals.catalogue import SIGNALS, load_mappings
from sis.signals.compute import compute_signals, open_file, prepare
from sis.signals.evidence import compute_evidence
from sis.sqlfiles import run_sql

SQL_DIR = Path(__file__).resolve().parent / "sql"
REPORT_DIR = paths.REPO_ROOT / "docs"
STAGE1_TARGET_GROUP = 131_104  # findings/07_negative.md: prerequisite, no sell, no substitute


class ScoreResult(BaseModel):
    file_id: str
    scoring_version: str
    n_scored: int
    segments: dict[str, int]
    n_signals: int
    n_evidence: int
    peer: PeerResult
    stage1_target_group: int
    wall_seconds: float = 0.0


class MergeResult(BaseModel):
    files: list[str]
    n_scores: int
    path: str


def params(cfg: scoring_config.ScoringConfig) -> dict[str, Any]:
    """Every constant the scoring SQL binds, named <fact>_<weight>, cap_*, x_*, m_*."""
    f = cfg.facts
    p: dict[str, Any] = {}
    for fact, weights in (("a", f.a.weights), ("b", f.b.weights), ("c", f.c.weights),
                          ("d", f.d.weights)):
        p.update({f"{fact}_{k}": v for k, v in weights.items()})
    p["cap_admin_services"] = f.c.caps.admin_services
    p["cap_asset_tags"] = f.c.caps.asset_tags
    p.update({f"x_{k}": v for k, v in cfg.exposure.weights.items()})
    p.update({f"m_{k}": v for k, v in cfg.segments.multipliers.items()})
    return p


def wide_sql(sig: str = "sig", base: str = "peer") -> str:
    """1 row per entity of `base`, v_<id> and p_<id> per catalogue signal, 0 when absent."""
    cols = ",\n       ".join(
        f"coalesce(max(s.value) FILTER (WHERE s.signal_id = '{s.signal_id}'), 0) "
        f"AS v_{s.signal_id}, "
        f"coalesce(max(s.pct_in_peer) FILTER (WHERE s.signal_id = '{s.signal_id}'), 0) "
        f"AS p_{s.signal_id}"
        for s in SIGNALS)
    return (f"SELECT p.entity_id, p.country_code,\n       {cols}\n"
            f"FROM {base} p LEFT JOIN {sig} s USING (entity_id) "
            f"GROUP BY p.entity_id, p.country_code")


def build_scores(con: duckdb.DuckDBPyConnection, cfg: scoring_config.ScoringConfig,
                 file_id: str) -> None:
    """Temp tables wide, terms, facts, contrib, scored, scores from `sig` and `peer`."""
    con.execute(f"CREATE OR REPLACE TEMP TABLE wide AS {wide_sql()}")
    run_sql(con, SQL_DIR / "02_facts.sql", **params(cfg))
    con.execute("""
        CREATE OR REPLACE TEMP TABLE scored AS
        SELECT f.entity_id, f.fact_a, f.fact_b, f.fact_c, f.fact_d, f.exposure, f.segment,
               f.priority, coalesce(t.top_signals, []::VARCHAR[]) AS top_signals,
               $v::VARCHAR AS scoring_version, $f::VARCHAR AS file_id, w.country_code
        FROM facts f JOIN wide w USING (entity_id)
        LEFT JOIN (SELECT entity_id,
                          list(signal_id ORDER BY contribution DESC, signal_id)[1:5] AS top_signals
                   FROM contrib GROUP BY entity_id) t USING (entity_id)""",
                {"v": cfg.scoring_version, "f": file_id})
    run_sql(con, SQL_DIR / "03_rank.sql")


def stage1_target_group(con: duckdb.DuckDBPyConnection) -> int:
    """The Stage 1 target group recomputed with its own predicates on every banner of the
    active entities (edge banners included, as Stage 1 had no edge rule): any P01-P03 and no
    W01-W07 (findings/07_negative.md)."""
    m = load_mappings()
    pre = " OR ".join(f"coalesce(({m[k]}), false)" for k in ("P01", "P02", "P03"))
    sell = " OR ".join(f"coalesce(({m[k]}), false)"
                       for k in ("W01", "W02", "W03", "W04", "W05", "W06", "W07"))
    return int(con.execute(f"""
        SELECT count(*) FILTER (WHERE pre AND NOT sell) FROM (
            SELECT entity_id, bool_or({pre}) AS pre, bool_or({sell}) AS sell
            FROM eb GROUP BY entity_id)""").fetchall()[0][0])


def score(file_id: str, write_report: bool = True) -> ScoreResult:
    """Peer groups, signals, evidence and scores for 1 file, all written under
    $SIS_DATA/<file_id>/; the report goes to docs/SCORE_REPORT_<file_id>.md."""
    t0 = time.time()
    cfg = scoring_config.load()
    out = paths.file_dir(file_id)
    assign_peer_groups(file_id)
    con = open_file(file_id)
    build_peer_table(con, cfg=cfg)
    peer = peer_stats(con)
    prepare(con)
    n_signals = compute_signals(file_id, con)
    n_evidence = compute_evidence(file_id, con)
    build_scores(con, cfg, file_id)
    n = write_parquet(con, "SELECT * FROM scores ORDER BY entity_id", out / "scores.parquet")
    segments = dict(con.execute(
        "SELECT segment, count(*) FROM scores GROUP BY 1 ORDER BY 1").fetchall())
    target = stage1_target_group(con)
    (out / "score_meta.json").write_text(json.dumps({
        "built_at": datetime.now(UTC).isoformat(), "pipeline_version": PIPELINE_VERSION,
        "scoring_version": cfg.scoring_version,
        "tables": ["signals", "evidence", "scores"],
        "stage1_target_group": target, "stage1_target_group_reference": STAGE1_TARGET_GROUP,
    }, indent=1), encoding="utf-8")
    res = ScoreResult(file_id=file_id, scoring_version=cfg.scoring_version, n_scored=n,
                      segments=segments, n_signals=n_signals, n_evidence=n_evidence, peer=peer,
                      stage1_target_group=target, wall_seconds=round(time.time() - t0, 1))
    if write_report:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        report.write_report(con, res, REPORT_DIR / f"SCORE_REPORT_{file_id}.md")
    con.close()
    return res


def merge_current() -> MergeResult:
    """Rebuild $SIS_DATA/current/scores.parquet: the latest file's scores per entity (by
    received_at), ranks recomputed over the merged set."""
    received: dict[str, datetime] = {}
    for r in read_ingest_log().to_pylist():
        if r["status"] == "ok" and (paths.file_dir(r["file_id"]) / "scores.parquet").exists():
            received[r["file_id"]] = r["received_at"]
    if not received:
        raise FileNotFoundError("no ingested file has scores.parquet; run `sis score` first")
    con = db.connect()
    con.register("files_arrow", pa.table({
        "file_id": list(received), "received_at": list(received.values())}))

    def part(f: str) -> str:
        d = paths.file_dir(f)
        return (f"SELECT s.*, e.country_code "
                f"FROM read_parquet('{(d / 'scores.parquet').as_posix()}') s "
                f"JOIN read_parquet('{(d / 'entities.parquet').as_posix()}') e USING (entity_id)")

    union = " UNION ALL ".join(part(f) for f in received)
    con.execute(f"""
        CREATE TEMP TABLE scored AS
        SELECT * EXCLUDE (received_at, rn) FROM (
            SELECT a.*, f.received_at, row_number() OVER (
                PARTITION BY a.entity_id ORDER BY f.received_at DESC, a.file_id DESC) AS rn
            FROM ({union}) a JOIN files_arrow f USING (file_id)
        ) WHERE rn = 1""")
    run_sql(con, SQL_DIR / "03_rank.sql")
    out = paths.current_dir() / "scores.parquet"
    n = write_parquet(con, "SELECT * FROM scores ORDER BY entity_id", out)
    con.close()
    return MergeResult(files=sorted(received), n_scores=n, path=str(out))
