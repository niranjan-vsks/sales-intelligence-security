"""Manufacture a second delivery by perturbing the real one in known ways (cards/P6.md step 1).

The simulation, stated once: the second file is the first file's own raw lines with a seeded 7
percent or so of its banners changed, every timestamp moved forward `shift_days`, and
`_shodan.id` left unchanged on surviving banners (the provider mints a new id per observation;
the diff keys on entity and ip:port, so reusing ids changes nothing it reads). It exists to give
the diff a known answer. It is not a real second delivery and is never merged into current state.

Which banners are chosen is decided in DuckDB from the first file's Parquet (md5 order, so the
same seed gives the same choice and the counts are exact); the raw file is then streamed once,
line by line, applying the choices. Every choice is written to the truth file."""

import multiprocessing
import os
import sys
import threading
import time
import uuid
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import orjson
import zstandard
from pydantic import BaseModel

from sis import db, delta_config, paths
from sis.config import settings
from sis.delta.truth import PERTURBATIONS, read_truth, write_truth
from sis.ingest.file_id import compute_file_id
from sis.ingest.log import read_ingest_log
from sis.ingest.reader import BLOCK_BYTES, Block, stream_blocks
from sis.signals.catalogue import HTTP_BANNER, edge_predicate, load_mappings

# What the scorer can see, so the change is not a no-op: an expired cert only counts on a
# non-edge banner whose cert was not already expired; CVEs only on non-edge banners with a CPE.
ELIGIBLE: dict[str, str] = {
    "drop_banner": "true",
    "new_banner": "true",
    "expire_cert": "cert_expires IS NOT NULL AND NOT coalesce(cert_expired, false) "
                   "AND NOT is_edge",
    "remove_waf": "http_waf IS NOT NULL",
    "add_waf": f"{HTTP_BANNER} AND http_waf IS NULL",
    "add_vuln": "coalesce(len(cpe23), 0) > 0 AND NOT is_edge",
}
UUID_NS = uuid.UUID("6f2d6c1e-4b0a-5d38-9c57-0a1b2c3d4e5f")
CERT_TIME = "%Y%m%d%H%M%SZ"


class SynthResult(BaseModel):
    seed: int
    source_file_id: str
    synthetic_file_id: str
    path: str
    truth_path: str
    eligible: dict[str, int]
    selected: dict[str, int]
    applied: dict[str, int]
    lines_in: int
    lines_out: int
    wall_seconds: float


@dataclass(frozen=True)
class Action:
    ptype: str
    new_id: str | None = None
    new_port: int | None = None


# ---- choosing the banners ---------------------------------------------------------------


def new_banner_id(seed: int, banner_id: str) -> str:
    return str(uuid.uuid5(UUID_NS, f"{seed}:{banner_id}"))


def new_banner_port(seed: int, banner_id: str, port: int | None, ports: list[int]) -> int:
    """One of `ports`, picked by the seed and the id; the other one when it equals `port`."""
    pick = int(uuid.uuid5(UUID_NS, f"{seed}:port:{banner_id}").int % len(ports))
    chosen = ports[pick]
    return ports[(pick + 1) % len(ports)] if chosen == port else chosen


def select(file_id: str, seed: int, cfg: delta_config.Synth) -> tuple[
        dict[str, list[dict[str, Any]]], dict[str, int], dict[str, int]]:
    """(items, eligible, selected). `items[ptype]` has 1 row per (banner, entity), banners in
    md5 order of the seed. `eligible[ptype]` counts the banners left after the earlier types."""
    d = paths.file_dir(file_id)
    for name in ("banner_entity.parquet", "entities.parquet"):
        if not (d / name).exists():
            raise FileNotFoundError(f"no {name} for {file_id}; run `sis resolve` first")
    con = db.connect()
    db.register(con, "b", paths.banners_glob(file_id))
    db.register(con, "be", (d / "banner_entity.parquet").as_posix())
    db.register(con, "ent", (d / "entities.parquet").as_posix())
    edge = edge_predicate(load_mappings())
    con.execute("""
        CREATE TEMP TABLE be_active AS
        SELECT DISTINCT be.banner_id, be.entity_id, e.key_kind, e.key_value
        FROM be JOIN ent e USING (entity_id) WHERE e.status = 'active'""")
    con.execute(f"""
        CREATE TEMP TABLE cand AS
        SELECT b.id AS banner_id, coalesce(b.ip_str, b.ipv6) AS ip, b.port, b.module,
               b.http_status, b.http_waf, b.cert_expires, b.cert_expired, b.cpe23,
               ({edge}) AS is_edge
        FROM b WHERE b.id IN (SELECT banner_id FROM be_active)""")
    con.execute("CREATE TEMP TABLE chosen (ptype VARCHAR, banner_id VARCHAR)")
    eligible: dict[str, int] = {}
    selected: dict[str, int] = {}
    for ptype in PERTURBATIONS:
        pct: float = getattr(cfg.percent, ptype)
        where = (f"({ELIGIBLE[ptype]}) AND banner_id NOT IN (SELECT banner_id FROM chosen)")
        n = int(con.execute(f"SELECT count(*) FROM cand WHERE {where}").fetchall()[0][0])
        k = int(n * pct / 100.0 + 0.5)
        con.execute(f"""
            INSERT INTO chosen
            SELECT '{ptype}', banner_id FROM cand WHERE {where}
            ORDER BY md5(concat(?, ':{ptype}:', banner_id)), banner_id LIMIT {k}""", [str(seed)])
        eligible[ptype], selected[ptype] = n, k
    rows = con.execute("""
        SELECT c.ptype, c.banner_id, a.entity_id, a.key_kind, a.key_value, k.ip, k.port, k.module
        FROM chosen c JOIN cand k USING (banner_id) JOIN be_active a USING (banner_id)
        ORDER BY c.ptype, md5(concat(?, ':', c.ptype, ':', c.banner_id)), c.banner_id,
                 a.entity_id""", [str(seed)]).fetchall()
    con.close()
    items: dict[str, list[dict[str, Any]]] = {p: [] for p in PERTURBATIONS}
    for ptype, banner_id, entity_id, key_kind, key_value, ip, port, module in rows:
        item: dict[str, Any] = {"banner_id": banner_id, "entity_id": entity_id,
                                "key_kind": key_kind, "key_value": key_value, "ip": ip,
                                "port": port, "module": module}
        if ptype == "new_banner":
            item["new_id"] = new_banner_id(seed, banner_id)
            item["new_port"] = new_banner_port(seed, banner_id, port, cfg.new_ports)
        items[ptype].append(item)
    return items, eligible, selected


def actions_from(items: dict[str, list[dict[str, Any]]]) -> dict[str, Action]:
    """1 action per banner (a banner attributed to 2 entities appears twice in `items`)."""
    out: dict[str, Action] = {}
    for ptype, rows in items.items():
        for r in rows:
            out[r["banner_id"]] = Action(ptype, r.get("new_id"), r.get("new_port"))
    return out


# ---- changing one record ----------------------------------------------------------------


def shift_ts(ts: str, days: int) -> str:
    """`ts` moved forward `days`, in the same shape (with or without microseconds)."""
    moved = datetime.fromisoformat(ts) + timedelta(days=days)
    return moved.isoformat(timespec="microseconds" if "." in ts else "seconds")


def perturb_record(obj: dict[str, Any], action: Action | None,
                   cfg: delta_config.Synth) -> tuple[list[dict[str, Any]], str | None]:
    """(records to write, perturbation applied). The records are 0 for a dropped banner, 2 for
    a new one (the original and its copy), else 1. A timestamp that does not parse leaves the
    record unchanged and reports no perturbation, so the caller can count it (`shifted`)."""
    ptype = action.ptype if action else None
    if ptype == "drop_banner":
        return [], ptype
    ts = obj.get("timestamp")
    try:
        if not isinstance(ts, str):
            raise ValueError("no timestamp")
        new_ts = shift_ts(ts, cfg.shift_days)
    except ValueError:
        return [obj], None
    obj["timestamp"] = new_ts
    if action is None or ptype is None:
        return [obj], None
    if ptype == "new_banner":
        copy: dict[str, Any] = orjson.loads(orjson.dumps(obj))
        copy["_shodan"]["id"] = action.new_id
        copy["port"] = action.new_port
        return [obj, copy], ptype
    if ptype == "expire_cert":
        ssl = obj.get("ssl")
        cert = ssl.get("cert") if isinstance(ssl, dict) else None
        if not isinstance(cert, dict):
            return [obj], None
        cert["expires"] = (datetime.fromisoformat(new_ts)
                           - timedelta(days=cfg.expire_days_before)).strftime(CERT_TIME)
        cert["expired"] = True
    elif ptype in ("remove_waf", "add_waf"):
        http = obj.get("http")
        if not isinstance(http, dict):
            return [obj], None
        if ptype == "remove_waf":
            http.pop("waf", None)
        else:
            http["waf"] = cfg.waf_name
    elif ptype == "add_vuln":
        vulns = obj.get("vulns")
        if not isinstance(vulns, dict):
            vulns = {}
        vulns[cfg.cve.id] = {"cvss": cfg.cve.cvss, "verified": False, "references": [],
                             "summary": "Synthetic CVE injected by sis synth"}
        obj["vulns"] = vulns
    return [obj], ptype


# ---- the stream -------------------------------------------------------------------------

_ACTIONS: dict[str, Action] = {}
_CFG: delta_config.Synth | None = None


def _init(actions: dict[str, Action], cfg_json: str) -> None:
    global _ACTIONS, _CFG
    _ACTIONS = actions
    _CFG = delta_config.Synth.model_validate_json(cfg_json)


def perturb_block(data: bytes) -> tuple[bytes, dict[str, int]]:
    """A block of whole lines in, the perturbed block out, and plain-type stats."""
    assert _CFG is not None
    stats: Counter[str] = Counter()
    out: list[bytes] = []
    for line in data.split(b"\n")[:-1]:
        stats["lines_in"] += 1
        try:
            obj = orjson.loads(line)
        except orjson.JSONDecodeError:
            obj = None
        sh = obj.get("_shodan") if isinstance(obj, dict) else None
        rid = sh.get("id") if isinstance(sh, dict) else None
        if not isinstance(obj, dict):  # blank, malformed or not an object: pass through as is
            stats["passthrough"] += 1
            stats["lines_out"] += 1
            out.append(line + b"\n")
            continue
        action = _ACTIONS.get(rid) if isinstance(rid, str) else None
        before = obj.get("timestamp")
        recs, applied = perturb_record(obj, action, _CFG)
        if applied is not None:
            stats["applied_" + applied] += 1
        if recs and recs[0].get("timestamp") == before:  # not moved: no usable timestamp
            stats["unshifted"] += 1
        for r in recs:
            out.append(orjson.dumps(r) + b"\n")
            stats["lines_out"] += 1
    return b"".join(out), dict(stats)


def _gated(blocks: Iterator[Block], sem: threading.Semaphore,
           abort: threading.Event) -> Iterator[bytes]:
    for block in blocks:
        if not block.data:
            continue
        while not sem.acquire(timeout=0.5):
            if abort.is_set():
                return
        yield block.data


def find_raw(file_id: str, raw: Path | None = None) -> Path:
    """The raw delivery for `file_id`: `raw`, or the ingest log's original name under RAW_DIR.
    Its file_id must match, so a different file never passes for the source."""
    candidates: list[Path] = [raw] if raw else []
    if raw is None:
        for r in read_ingest_log().to_pylist():
            if r["file_id"] == file_id and r["status"] == "ok":
                candidates.append(settings.RAW_DIR / r["original_name"])
    for p in candidates:
        if p.is_file() and compute_file_id(p) == file_id:
            return p
    raise FileNotFoundError(
        f"cannot find the raw file for {file_id}; pass --raw PATH (RAW_DIR is {settings.RAW_DIR})")


def synth(file_id: str, seed: int | None = None, raw: Path | None = None,
          workers: int | None = None, force: bool = False,
          block_bytes: int = BLOCK_BYTES) -> SynthResult:
    """Write $SIS_DATA/synth/<seed>.jsonl.zst and <seed>_truth.json for the resolved `file_id`."""
    t0 = time.time()
    cfg = delta_config.load().synth
    seed = cfg.seed_default if seed is None else seed
    workers = workers or settings.INGEST_WORKERS
    truth_path, out_path = paths.synth_truth_path(seed), paths.synth_path(seed)
    if truth_path.exists() and out_path.exists() and not force:
        t = read_truth(truth_path)
        if t.get("source_file_id") == file_id:
            return SynthResult(
                seed=seed, source_file_id=file_id, synthetic_file_id=t["synthetic_file_id"],
                path=str(out_path), truth_path=str(truth_path), eligible=t["eligible"],
                selected=t["selected"], applied=t["applied"], lines_in=t["lines_in"],
                lines_out=t["lines_out"], wall_seconds=0.0)
    raw_path = find_raw(file_id, raw)
    items, eligible, selected = select(file_id, seed, cfg)
    actions = actions_from(items)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_name(out_path.name + ".tmp")
    totals: Counter[str] = Counter()
    blocks = stream_blocks(raw_path, block_bytes)
    sem = threading.BoundedSemaphore(workers * 2)  # bounds the bytes in flight
    abort = threading.Event()
    ctx = multiprocessing.get_context("spawn")
    t1 = time.time()
    n_blocks = 0
    try:
        with open(tmp, "wb") as f, \
                zstandard.ZstdCompressor(level=3, threads=-1).stream_writer(f) as w, \
                ctx.Pool(workers, initializer=_init,
                         initargs=(actions, cfg.model_dump_json())) as pool:
            # imap, not imap_unordered: the output order is the input order, so the same seed
            # gives the same bytes and the same file_id
            for data, stats in pool.imap(perturb_block, _gated(blocks, sem, abort)):
                sem.release()
                w.write(data)
                totals.update(stats)
                n_blocks += 1
                if n_blocks % 20 == 0:
                    print(f"{time.time() - t1:7.0f}s blocks={n_blocks} "
                          f"lines={totals['lines_in']}", file=sys.stderr, flush=True)
        os.replace(tmp, out_path)
    except BaseException:
        abort.set()
        tmp.unlink(missing_ok=True)
        raise
    finally:
        abort.set()

    applied = {p: totals[f"applied_{p}"] for p in PERTURBATIONS}
    planned = Counter(a.ptype for a in actions.values())
    bad = {p: (planned[p], applied[p]) for p in PERTURBATIONS if planned[p] != applied[p]}
    if bad:  # {ptype: (planned, applied)}
        out_path.unlink(missing_ok=True)
        raise RuntimeError(f"perturbations planned != applied: {bad}")
    synthetic_file_id = compute_file_id(out_path)
    truth = {
        "seed": seed, "source_file_id": file_id, "synthetic_file_id": synthetic_file_id,
        "created_at": datetime.now(UTC).isoformat(),
        "simulation": "second delivery manufactured by perturbing the first; not real data",
        "params": cfg.model_dump(), "eligible": eligible, "selected": selected,
        "applied": applied, "lines_in": totals["lines_in"], "lines_out": totals["lines_out"],
        "passthrough": totals["passthrough"], "unshifted": totals["unshifted"],
        "items": items,
    }
    write_truth(truth_path, truth)
    return SynthResult(
        seed=seed, source_file_id=file_id, synthetic_file_id=synthetic_file_id,
        path=str(out_path), truth_path=str(truth_path), eligible=eligible, selected=selected,
        applied=applied, lines_in=totals["lines_in"], lines_out=totals["lines_out"],
        wall_seconds=round(time.time() - t0, 1))
