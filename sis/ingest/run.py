"""Ingest one raw delivery into $SIS_DATA/<file_id>/{banners,vulns}, atomically (DESIGN.md 3)."""

import itertools
import json
import multiprocessing
import os
import shutil
import sys
import threading
import time
from collections import Counter
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import orjson
import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import BaseModel, Field

from sis import PIPELINE_VERSION, db, paths
from sis.config import settings
from sis.ingest import report
from sis.ingest.file_id import compute_file_id
from sis.ingest.flatten import (
    SCHEMA,
    VSCHEMA,
    MissingIdError,
    NotAnObjectError,
    flatten_record,
)
from sis.ingest.log import append_ingest_log, read_ingest_log
from sis.ingest.reader import BLOCK_BYTES, Block, is_zstd, stream_blocks, stream_lines

PREFLIGHT_LINES = 1000
QUARANTINE_SAMPLE = 50
ROW_GROUP = 100_000
REPORT_DIR = paths.REPO_ROOT / "docs"

Status = Literal["ok", "failed", "duplicate", "quarantined", "rejected"]


class IngestResult(BaseModel):
    file_id: str
    status: Status
    original_name: str
    byte_length: int
    received_at: datetime
    started_at: datetime
    finished_at: datetime | None = None
    lines_read: int = 0
    rows_written: int = 0
    rows_dropped: int = 0
    vuln_rows_written: int = 0
    dropped_reasons: dict[str, int] = Field(default_factory=dict)
    wall_seconds: float = 0.0
    workers: int = 1
    parquet_bytes_banners: int = 0
    parquet_bytes_vulns: int = 0
    top_keys: dict[str, int] = Field(default_factory=dict)
    new_keys: dict[str, int] = Field(default_factory=dict)
    pipeline_version: str = PIPELINE_VERSION
    error: str | None = None


class ReconciliationError(RuntimeError):
    pass


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


# ---- block processing (runs in worker processes) ---------------------------------------


def write_part(table: pa.Table, path: Path) -> None:
    pq.write_table(table, path, compression="zstd", row_group_size=ROW_GROUP)


def rows_to_table(rows: list[dict[str, Any]]) -> pa.Table:
    """The explorer's trick: timestamps travel as strings and are cast, so a malformed one raises
    here rather than silently becoming null."""
    table = pa.Table.from_pylist([{**r, "timestamp": None} for r in rows], schema=SCHEMA)
    ts = pa.array([r["timestamp"] for r in rows], pa.string()).cast(pa.timestamp("us"))
    return table.set_column(SCHEMA.get_field_index("timestamp"), "timestamp", ts)


def process_block(args: tuple[int, bytes, str, str]) -> dict[str, Any]:
    """Parse one block of lines and write its Parquet parts. Returns plain-type stats."""
    idx, buf, out, file_id = args
    rows: list[dict[str, Any]] = []
    vrows: list[dict[str, Any]] = []
    dropped: Counter[str] = Counter()
    top_keys: Counter[str] = Counter()
    vuln_keys: Counter[str] = Counter()
    lines = buf.split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    for line in lines:
        if not line.strip():
            dropped["blank"] += 1
            continue
        try:
            obj = orjson.loads(line)
            row, vs = flatten_record(obj, file_id)
        except MissingIdError:
            dropped["missing_id"] += 1
            continue
        except (orjson.JSONDecodeError, NotAnObjectError):
            dropped["json_parse"] += 1
            continue
        except Exception:  # an unexpected shape inside a valid record; counted, never silent
            dropped["flatten_error"] += 1
            continue
        row["record_bytes"] = len(line)
        top_keys.update(obj.keys())
        for v in obj.get("vulns", {}).values() if isinstance(obj.get("vulns"), dict) else ():
            if isinstance(v, dict):
                vuln_keys.update(v.keys())
        rows.append(row)
        vrows.extend(vs)
    rows.sort(key=lambda x: x["module"] or "")

    try:
        table = rows_to_table(rows)
    except (pa.ArrowInvalid, pa.ArrowTypeError):
        # one row has a value the schema cannot hold; keep the rest, count the culprits
        good, good_v = [], []
        by_id: dict[str, list[dict[str, Any]]] = {}
        for v in vrows:
            by_id.setdefault(v["id"], []).append(v)
        for r in rows:
            try:
                rows_to_table([r])
                pa.Table.from_pylist(by_id.get(r["id"], []), schema=VSCHEMA)
            except (pa.ArrowInvalid, pa.ArrowTypeError):
                dropped["type_error"] += 1
            else:
                good.append(r)
                good_v.extend(by_id.get(r["id"], []))
        rows, vrows = good, good_v
        table = rows_to_table(rows)

    if rows:
        write_part(table, Path(out) / "banners" / f"part-{idx:05d}.parquet")
    if vrows:
        write_part(pa.Table.from_pylist(vrows, schema=VSCHEMA),
                   Path(out) / "vulns" / f"part-{idx:05d}.parquet")
    return {
        "lines": len(lines), "rows": len(rows), "vuln_rows": len(vrows),
        "dropped": dict(dropped), "top_keys": dict(top_keys), "vuln_keys": dict(vuln_keys),
    }


# ---- orchestration ---------------------------------------------------------------------


def _is_good_line(line: bytes) -> bool:
    try:
        obj = orjson.loads(line)
    except orjson.JSONDecodeError:
        return False
    sid = obj.get("_shodan") if isinstance(obj, dict) else None
    rid = sid.get("id") if isinstance(sid, dict) else None
    return isinstance(rid, str) and bool(rid)


def _preflight(path: Path) -> tuple[int, list[bytes]]:
    """(lines checked, bad lines) over the first PREFLIGHT_LINES lines."""
    lines = stream_lines(path)
    try:
        head = list(itertools.islice(lines, PREFLIGHT_LINES))
    finally:
        lines.close()  # type: ignore[attr-defined]
    return len(head), [ln for ln in head if not _is_good_line(ln)]


def _gated(blocks: Iterator[Block], sem: threading.Semaphore, abort: threading.Event,
           out: str, file_id: str, oversize: Counter[str]) -> Iterator[tuple[int, bytes, str, str]]:
    """Feed blocks to the pool, never more than the semaphore allows in flight."""
    for idx, block in enumerate(blocks):
        oversize["n"] += block.oversize
        if not block.data:
            continue
        while not sem.acquire(timeout=0.5):
            if abort.is_set():
                return
        yield idx, block.data, out, file_id


def _run_blocks(
    path: Path, out: Path, file_id: str, workers: int, block_bytes: int
) -> dict[str, Any]:
    total: dict[str, Any] = {
        "lines": 0, "rows": 0, "vuln_rows": 0, "oversize": 0, "blocks": 0,
        "dropped": Counter(), "top_keys": Counter(), "vuln_keys": Counter(),
    }
    oversize: Counter[str] = Counter()
    t0 = time.time()

    def absorb(st: dict[str, Any]) -> None:
        total["blocks"] += 1
        for k in ("lines", "rows", "vuln_rows"):
            total[k] += st[k]
        for k in ("dropped", "top_keys", "vuln_keys"):
            total[k].update(st[k])
        if total["blocks"] % 20 == 0:
            print(f"{time.time() - t0:7.0f}s blocks={total['blocks']} rows={total['rows']}",
                  file=sys.stderr, flush=True)

    blocks = stream_blocks(path, block_bytes)
    if workers <= 1:
        for idx, block in enumerate(blocks):
            oversize["n"] += block.oversize
            if block.data:
                absorb(process_block((idx, block.data, str(out), file_id)))
    else:
        sem = threading.BoundedSemaphore(workers * 2)  # bounds the bytes in flight
        abort = threading.Event()
        ctx = multiprocessing.get_context("spawn")
        try:
            with ctx.Pool(workers) as pool:
                gated = _gated(blocks, sem, abort, str(out), file_id, oversize)
                for st in pool.imap_unordered(process_block, gated):
                    sem.release()
                    absorb(st)
        finally:
            abort.set()
    if oversize["n"]:
        total["dropped"]["oversize"] += oversize["n"]
        total["lines"] += oversize["n"]
    return total


def _count_parquet(glob: str) -> int:
    con = db.connect()
    try:
        row = con.execute("SELECT count(*) FROM read_parquet(?)", [glob]).fetchone()
    finally:
        con.close()
    assert row is not None
    return int(row[0])


def _dir_bytes(d: Path) -> int:
    return sum(p.stat().st_size for p in d.glob("*.parquet"))


def _known_keys() -> set[str]:
    text = (paths.config_dir() / "known_top_keys.txt").read_text(encoding="utf-8")
    return {ln for ln in text.splitlines() if ln}


def _earlier_ok(file_id: str) -> dict[str, Any] | None:
    rows = [r for r in read_ingest_log().to_pylist()
            if r["file_id"] == file_id and r["status"] == "ok"]
    return rows[-1] if rows else None


def ingest(path: str | Path, workers: int | None = None, force: bool = False,
           block_bytes: int = BLOCK_BYTES) -> IngestResult:
    path = Path(path)
    workers = workers or settings.INGEST_WORKERS
    t0 = time.time()
    stat = path.stat()
    res = IngestResult(
        file_id=compute_file_id(path), status="failed", original_name=path.name,
        byte_length=stat.st_size,
        received_at=datetime.fromtimestamp(stat.st_mtime, UTC).replace(tzinfo=None),
        started_at=_utcnow(), workers=workers,
    )

    def finish(status: Status, error: str | None = None) -> IngestResult:
        res.status, res.error = status, error
        res.finished_at = _utcnow()
        res.wall_seconds = round(time.time() - t0, 3)
        res.rows_dropped = sum(res.dropped_reasons.values())
        append_ingest_log({
            "file_id": res.file_id, "original_name": res.original_name,
            "byte_length": res.byte_length, "received_at": res.received_at,
            "started_at": res.started_at, "finished_at": res.finished_at, "status": status,
            "lines_read": res.lines_read, "rows_written": res.rows_written,
            "rows_dropped": res.rows_dropped, "vuln_rows_written": res.vuln_rows_written,
            "dropped_reasons": json.dumps(res.dropped_reasons, sort_keys=True),
            "wall_seconds": res.wall_seconds, "pipeline_version": PIPELINE_VERSION,
            "error": error,
        })
        return res

    if not is_zstd(path):
        return finish("rejected", "not a zstd file (magic bytes 28 b5 2f fd missing)")

    final, tmp = paths.file_dir(res.file_id), paths.tmp_dir(res.file_id)
    earlier = _earlier_ok(res.file_id)
    if earlier and final.is_dir() and not force:
        res.lines_read, res.rows_written = earlier["lines_read"], earlier["rows_written"]
        res.vuln_rows_written = earlier["vuln_rows_written"]
        res.rows_dropped = earlier["rows_dropped"]
        res.dropped_reasons = json.loads(earlier["dropped_reasons"] or "{}")
        res.wall_seconds = earlier["wall_seconds"]
        res.finished_at, res.status = _utcnow(), "duplicate"
        append_ingest_log({
            "file_id": res.file_id, "original_name": res.original_name,
            "byte_length": res.byte_length, "received_at": res.received_at,
            "started_at": res.started_at, "finished_at": res.finished_at,
            "status": "duplicate", "pipeline_version": PIPELINE_VERSION,
        })
        return res

    checked, bad = _preflight(path)
    if checked == 0 or len(bad) * 100 > checked:
        q = paths.quarantine_dir()
        q.mkdir(parents=True, exist_ok=True)
        (q / f"{res.file_id}.txt").write_text(
            "\n".join(ln[:2000].decode("utf-8", "replace") for ln in bad[:QUARANTINE_SAMPLE]),
            encoding="utf-8")
        return finish("quarantined",
                      f"{len(bad)} of the first {checked} lines are not valid banner records")

    if tmp.exists():
        shutil.rmtree(tmp)  # debris from a crashed earlier run
    (tmp / "banners").mkdir(parents=True)
    (tmp / "vulns").mkdir()
    try:
        total = _run_blocks(path, tmp, res.file_id, workers, block_bytes)
        res.lines_read, res.rows_written = total["lines"], total["rows"]
        res.vuln_rows_written = total["vuln_rows"]
        res.dropped_reasons = dict(total["dropped"])
        res.rows_dropped = sum(res.dropped_reasons.values())

        if res.lines_read != res.rows_written + res.rows_dropped:
            raise ReconciliationError(
                f"reconciliation failed: {res.lines_read} lines read != "
                f"{res.rows_written} written + {res.rows_dropped} dropped")
        if not any((tmp / "vulns").glob("*.parquet")):  # keep the table readable when empty
            write_part(pa.Table.from_pylist([], schema=VSCHEMA),
                       tmp / "vulns" / "part-00000.parquet")
        on_disk = _count_parquet((tmp / "banners" / "*.parquet").as_posix())
        v_on_disk = _count_parquet((tmp / "vulns" / "*.parquet").as_posix())
        if on_disk != res.rows_written or v_on_disk != res.vuln_rows_written:
            raise ReconciliationError(
                f"reconciliation failed: parquet holds {on_disk} banner and {v_on_disk} vuln "
                f"rows, workers reported {res.rows_written} and {res.vuln_rows_written}")

        res.top_keys = dict(total["top_keys"].most_common())
        known = _known_keys()
        res.new_keys = {k: n for k, n in res.top_keys.items() if k not in known}
        (tmp / "key_inventory.json").write_text(json.dumps({
            "top_keys": res.top_keys, "vuln_keys": dict(total["vuln_keys"].most_common()),
            "new_keys": res.new_keys,
        }, indent=1), encoding="utf-8")
        res.parquet_bytes_banners = _dir_bytes(tmp / "banners")
        res.parquet_bytes_vulns = _dir_bytes(tmp / "vulns")

        old = final.with_name(final.name + ".old")
        if final.exists():  # only reachable with --force
            os.replace(final, old)
        os.replace(tmp, final)
        shutil.rmtree(old, ignore_errors=True)
    except Exception as e:
        shutil.rmtree(tmp, ignore_errors=True)
        return finish("failed", f"{type(e).__name__}: {e}")
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise

    out = finish("ok")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report.write_report(out, REPORT_DIR / f"INGEST_REPORT_{out.file_id}.md")
    return out
