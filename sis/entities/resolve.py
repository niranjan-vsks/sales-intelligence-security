"""Entity resolution: banners -> banner_entity -> entities (DESIGN.md 4, DATA_MODEL.md 2)."""

import json
import os
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import yaml
from pydantic import BaseModel, Field

from sis import PIPELINE_VERSION, db, paths
from sis.config import settings
from sis.delta.truth import synthetic_file_ids
from sis.entities import report
from sis.entities.normalise import host_registered_domain, normalise_name, registered_domain
from sis.ingest.log import read_ingest_log

SQL_DIR = Path(__file__).resolve().parent / "sql"
REPORT_DIR = paths.REPO_ROOT / "docs"
DERIVED_HEADER = "# derived from "


class ResolveConfig(BaseModel):
    """config/resolve.yaml: the operator rules of step 3 (phase P3.1 defect 1)."""

    template_zone_patterns: list[str]
    template_label_pattern: str
    template_min_ips: int = Field(ge=1)
    template_share: float = Field(gt=0.0, le=1.0)

    @property
    def zone_regex(self) -> str:
        return "|".join(f"(?:{p})" for p in self.template_zone_patterns)


def load_config(path: Path | None = None) -> ResolveConfig:
    path = path or paths.config_dir() / "resolve.yaml"
    return ResolveConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


class ResolveResult(BaseModel):
    file_id: str
    max_ips: int
    n_banners: int
    entities_by_kind: dict[str, int]
    n_active: int
    n_blocked: int
    blocked_by_reason: dict[str, int]
    banners_primary: int
    banners_fallback: int
    banners_none: int
    unattributed: dict[str, int]
    operators_seed: int
    operators_derived: int
    operators_derived_top: list[str] = Field(default_factory=list)
    # rule 1 and 2 matches, and how many of them each rule added beyond the seed, the cutoff
    # and (for rule 2) rule 1
    rule1_matched: int = 0
    rule1_added: int = 0
    rule2_matched: int = 0
    rule2_added: int = 0
    # (name, n_banners, n_ips, n_hostnames, n_templated), the 30 largest by n_banners
    rule2_top: list[tuple[str, int, int, int, int]] = Field(default_factory=list)
    wall_seconds: float = 0.0


class MergeResult(BaseModel):
    files: list[str]
    n_entities: int
    path: str


# ---- operator file ---------------------------------------------------------------------


def read_operator_file(path: Path) -> tuple[list[str], dict[str, list[str]]]:
    """(seed names, {file_id: derived names}). Seed = the lines before the first header.
    A `#` starts a comment, on its own line or after a name."""
    seed: list[str] = []
    derived: dict[str, list[str]] = {}
    current: list[str] | None = None
    if not path.exists():
        return seed, derived
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith(DERIVED_HEADER):
            current = derived.setdefault(line[len(DERIVED_HEADER):].strip(), [])
            continue
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        if current is None:
            seed.append(line.lower())
        else:
            current.append(line.lower())
    return seed, derived


def write_operator_file(
    path: Path, seed: list[str], derived: dict[str, list[str]], file_id: str, new: list[str]
) -> None:
    sections = {**derived, file_id: new}
    seen = set(seed)
    block = _seed_block(path)
    block_names = [n for ln in block if (n := ln.split("#", 1)[0].strip().lower())]
    lines = block if block_names == seed else list(dict.fromkeys(seed))
    for fid, names in sections.items():
        names = sorted(n for n in set(names) if n not in seen)
        if not names:
            continue
        seen.update(names)
        lines += [f"{DERIVED_HEADER}{fid}", *names]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def _seed_block(path: Path) -> list[str]:
    """The file's lines before the first derived header, verbatim, so hand comments survive."""
    if not path.exists():
        return []
    block: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.strip().startswith(DERIVED_HEADER):
            break
        if raw.strip():
            block.append(raw.rstrip())
    return block


# ---- helpers ---------------------------------------------------------------------------


def run_sql(con: duckdb.DuckDBPyConnection, name: str, **params: Any) -> None:
    """Run the statements of sql/<name>.sql, passing each only the parameters it mentions."""
    text = (SQL_DIR / name).read_text(encoding="utf-8")
    code = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("--"))
    for stmt in code.split(";"):  # statements hold no semicolons inside strings
        if not stmt.strip():
            continue
        used = {k: v for k, v in params.items() if re.search(rf"\${k}\b", stmt)}
        con.execute(stmt, used)


def _scalar(con: duckdb.DuckDBPyConnection, sql: str) -> Any:
    return con.execute(sql).fetchall()[0][0]


def _write(con: duckdb.DuckDBPyConnection, sql: str, path: Path) -> None:
    table: pa.Table = con.sql(sql).to_arrow_table()
    tmp = path.with_name(path.name + ".tmp")
    pq.write_table(table, tmp, compression="zstd")
    os.replace(tmp, path)


def _load_map(
    con: duckdb.DuckDBPyConnection, table: str, raw_sql: str, fn: Callable[[str], str | None]
) -> None:
    rows = [(r[0], fn(r[0])) for r in con.execute(raw_sql).fetchall() if r[0]]
    arrow = pa.table({
        "raw": [r for r, n in rows if n is not None],
        "name": [n for r, n in rows if n is not None],
    })
    con.register(f"{table}_arrow", arrow)
    con.execute(f"CREATE OR REPLACE TEMP TABLE {table} AS SELECT * FROM {table}_arrow")
    con.unregister(f"{table}_arrow")


# ---- the run ---------------------------------------------------------------------------


def resolve(
    file_id: str,
    max_ips: int | None = None,
    operator_file: Path | None = None,
    write_back: bool = True,
    write_report: bool = True,
) -> ResolveResult:
    t0 = time.time()
    cutoff = settings.ROLLUP_MAX_IPS if max_ips is None else max_ips
    out_dir = paths.file_dir(file_id)
    if not (out_dir / "banners").is_dir():
        raise FileNotFoundError(f"no ingested banners for {file_id}; run `sis ingest` first")
    op_path = operator_file or paths.config_dir() / "operator_domains.txt"
    seed, derived_all = read_operator_file(op_path)
    others = [n for fid, names in derived_all.items() if fid != file_id for n in names]
    rcfg = load_config()
    blocked_tags = yaml.safe_load(
        (paths.config_dir() / "blocked_tags.yaml").read_text(encoding="utf-8"))

    con = db.connect()
    db.register(con, "b", paths.banners_glob(file_id))
    n_banners = int(_scalar(con, "SELECT count(*) FROM b"))

    _load_map(con, "map_domain", "SELECT DISTINCT unnest(domains) FROM b", normalise_name)
    _load_map(con, "map_cert",
              "SELECT cert_subject_cn FROM b WHERE cert_subject_cn IS NOT NULL GROUP BY 1 "
              "UNION SELECT DISTINCT unnest(cert_san) FROM b WHERE cert_san IS NOT NULL",
              registered_domain)
    _load_map(con, "map_host", "SELECT DISTINCT http_host FROM b WHERE http_host IS NOT NULL",
              host_registered_domain)
    con.register("op_seed_arrow", pa.table({"name": sorted(set(seed) | set(others))},
                                           schema=pa.schema([("name", pa.string())])))
    con.execute("CREATE OR REPLACE TEMP TABLE op_seed AS SELECT * FROM op_seed_arrow")

    params = {
        "cutoff": cutoff, "file_id": file_id,
        "b01": blocked_tags["honeypot_or_scanner"], "b02": blocked_tags["c2_or_malware"],
        "zone_re": rcfg.zone_regex, "tpl_label_re": rcfg.template_label_pattern,
        "tpl_min_ips": rcfg.template_min_ips, "tpl_share": rcfg.template_share,
    }
    for step in ("01_names", "02_coverage", "03_operators", "04_primary", "05_fallback",
                 "06_banner_entity", "07_entities"):
        run_sql(con, f"{step}.sql", **params)

    derived = sorted(r[0] for r in con.execute("SELECT name FROM op_derived").fetchall())
    # a synthetic delivery (sis synth) must not add its derived names to the real operator list
    if write_back and file_id not in synthetic_file_ids():
        write_operator_file(op_path, seed, derived_all, file_id, derived)
    top_derived = [r[0] for r in con.execute(
        "SELECT o.name FROM op_derived o JOIN coverage c ON c.name = o.name "
        "GROUP BY o.name ORDER BY max(c.n_ips) DESC, o.name LIMIT 5").fetchall()]

    rule_counts = con.execute("""
        WITH base AS (
            SELECT name FROM op_seed
            UNION SELECT name FROM coverage WHERE kind = 'domain' AND n_ips > $cutoff)
        SELECT (SELECT count(*) FROM op_rule1),
               (SELECT count(*) FROM op_rule1 WHERE name NOT IN (SELECT name FROM base)),
               (SELECT count(*) FROM op_rule2),
               (SELECT count(*) FROM op_rule2 WHERE name NOT IN (SELECT name FROM base)
                                              AND name NOT IN (SELECT name FROM op_rule1))""",
        {"cutoff": cutoff}).fetchall()[0]
    rule2_top = [tuple(r) for r in con.execute("""
        SELECT r.name, count(DISTINCT n.banner_id), any_value(c.n_ips), any_value(t.n_hostnames),
               any_value(t.n_templated)
        FROM op_rule2 r JOIN host_template t USING (name)
        JOIN coverage c ON c.kind = 'domain' AND c.name = r.name
        JOIN names n ON n.kind = 'domain' AND n.name = r.name
        GROUP BY r.name ORDER BY 2 DESC, 1 LIMIT 30""").fetchall()]

    # unattributed banners, mutually exclusive reasons
    n_attr = int(_scalar(con, "SELECT count(DISTINCT banner_id) FROM banner_entity"))
    n_attr_active = int(_scalar(
        con, "SELECT count(DISTINCT banner_id) FROM banner_entity "
             "WHERE entity_id IN (SELECT entity_id FROM entities WHERE status = 'active')"))
    n_named = int(_scalar(con, "SELECT count(DISTINCT banner_id) FROM names"))
    n_nonop = int(_scalar(con, "SELECT count(DISTINCT banner_id) FROM names "
                               "WHERE name NOT IN (SELECT name FROM operators)"))
    unattributed = {
        "no_name": n_banners - n_named,
        "operator_only": n_named - n_nonop,
        "over_cutoff": n_nonop - n_attr,
        "blocked": n_attr - n_attr_active,
    }
    assert unattributed["over_cutoff"] == 0, f"over_cutoff must be 0, got {unattributed}"

    # outputs
    _write(con, "SELECT banner_id, entity_id, key_kind, key_value, attribution, "
                f"'{file_id}' AS file_id FROM banner_entity ORDER BY entity_id, banner_id",
           out_dir / "banner_entity.parquet")
    _write(con, "SELECT * FROM entities ORDER BY entity_id", out_dir / "entities.parquet")
    summary = [(reason, n, n / n_banners if n_banners else 0.0)
               for reason, n in unattributed.items()]
    pq.write_table(
        pa.table({"reason": [s[0] for s in summary], "n_banners": [s[1] for s in summary],
                  "pct": [s[2] for s in summary]},
                 schema=pa.schema([("reason", pa.string()), ("n_banners", pa.int64()),
                                   ("pct", pa.float64())])),
        out_dir / "unattributed_summary.parquet", compression="zstd")
    (out_dir / "resolve_meta.json").write_text(json.dumps({
        "built_at": datetime.now(UTC).isoformat(), "pipeline_version": PIPELINE_VERSION,
        "rollup_max_ips": cutoff,
        "tables": ["banner_entity", "entities", "unattributed_summary"],
    }, indent=1), encoding="utf-8")

    by_kind = dict(con.execute("SELECT key_kind, count(*) FROM entities WHERE status = 'active' "
                               "GROUP BY 1 ORDER BY 1").fetchall())
    blocked_by_reason = dict(con.execute(
        "SELECT blocked_reason, count(*) FROM entities WHERE status = 'blocked' "
        "GROUP BY 1 ORDER BY 1").fetchall())
    res = ResolveResult(
        file_id=file_id, max_ips=cutoff, n_banners=n_banners, entities_by_kind=by_kind,
        n_active=int(_scalar(con, "SELECT count(*) FROM entities WHERE status = 'active'")),
        n_blocked=int(_scalar(con, "SELECT count(*) FROM entities WHERE status = 'blocked'")),
        blocked_by_reason=blocked_by_reason,
        banners_primary=int(_scalar(con, "SELECT count(DISTINCT banner_id) FROM banner_entity "
                                         "WHERE attribution = 'primary'")),
        banners_fallback=int(_scalar(con, "SELECT count(DISTINCT banner_id) FROM banner_entity "
                                          "WHERE attribution = 'fallback'")),
        banners_none=n_banners - n_attr, unattributed=unattributed,
        operators_seed=len(set(seed) | set(others)), operators_derived=len(derived),
        operators_derived_top=top_derived,
        rule1_matched=rule_counts[0], rule1_added=rule_counts[1],
        rule2_matched=rule_counts[2], rule2_added=rule_counts[3], rule2_top=rule2_top,
        wall_seconds=round(time.time() - t0, 1),
    )
    if write_report:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        report.write_report(con, res, REPORT_DIR / f"RESOLVE_REPORT_{file_id}.md")
    con.close()
    return res


# ---- merge -----------------------------------------------------------------------------


def merge_current() -> MergeResult:
    """Rebuild $SIS_DATA/current/entities.parquet from every ok file's entities.parquet.

    Counts and modes come from the latest file that saw the entity; first_seen_file and
    last_seen_file are the earliest and latest by received_at. Nothing is deleted."""
    received: dict[str, datetime] = {}
    synthetic = synthetic_file_ids()  # a simulated delivery never becomes current state
    for r in read_ingest_log().to_pylist():
        if (r["status"] == "ok" and r["file_id"] not in synthetic
                and (paths.file_dir(r["file_id"]) / "entities.parquet").exists()):
            received[r["file_id"]] = r["received_at"]
    if not received:
        raise FileNotFoundError("no ingested file has entities.parquet; run `sis resolve` first")
    con = db.connect()
    con.register("files_arrow", pa.table({
        "file_id": list(received), "received_at": list(received.values())}))
    union = " UNION ALL ".join(
        f"SELECT * FROM read_parquet('{(paths.file_dir(f) / 'entities.parquet').as_posix()}')"
        for f in received)
    con.execute(f"CREATE TEMP TABLE allent AS SELECT e.*, f.received_at FROM ({union}) e "
                "JOIN files_arrow f USING (file_id)")
    out = paths.current_dir()
    out.mkdir(parents=True, exist_ok=True)
    _write(con, """
        SELECT * EXCLUDE (received_at, rn, fs)
               REPLACE (fs AS first_seen_file, file_id AS last_seen_file)
        FROM (
            SELECT *, row_number() OVER latest AS rn,
                   first(file_id) OVER earliest AS fs
            FROM allent
            WINDOW latest AS (PARTITION BY entity_id ORDER BY received_at DESC, file_id DESC),
                   earliest AS (PARTITION BY entity_id ORDER BY received_at, file_id
                                ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
        ) WHERE rn = 1 ORDER BY entity_id""", out / "entities.parquet")
    merged = (out / "entities.parquet").as_posix()
    n = int(_scalar(con, f"SELECT count(*) FROM read_parquet('{merged}')"))
    con.close()
    return MergeResult(files=sorted(received), n_entities=n, path=str(out / "entities.parquet"))
