"""Synthetic files for the P3 tests: banners (+ vulns) -> resolve -> score, all under tmp."""

from datetime import datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from sis import paths
from sis.entities.resolve import resolve
from sis.ingest.flatten import SCHEMA, VSCHEMA
from sis.scoring.score import ScoreResult, score

FID = "p3file"
SCAN_TIME = datetime(2026, 10, 26, 12, 0, 0)


def write_file(rows: list[dict[str, Any]], vulns: list[dict[str, Any]] | None = None,
               file_id: str = FID) -> None:
    """Banner rows get a unique id b<i>, a unique IP, port 80, module http, country US and the
    scan time unless the row says otherwise. A vuln row names its banner by `id`."""
    full = [{"id": f"b{i}", "ip_str": f"10.{i // 65536}.{i // 256 % 256}.{i % 256}",
             "port": 80, "module": "http", "country_code": "US", "timestamp": SCAN_TIME, **r}
            for i, r in enumerate(rows)]
    d = paths.file_dir(file_id)
    (d / "banners").mkdir(parents=True, exist_ok=True)
    (d / "vulns").mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(full, schema=SCHEMA), d / "banners" / "part-0.parquet")
    pq.write_table(pa.Table.from_pylist(vulns or [], schema=VSCHEMA),
                   d / "vulns" / "part-0.parquet")


def build(rows: list[dict[str, Any]], ops: Path, vulns: list[dict[str, Any]] | None = None,
          file_id: str = FID, write_report: bool = False) -> ScoreResult:
    write_file(rows, vulns, file_id)
    resolve(file_id, operator_file=ops, write_back=False, write_report=False)
    return score(file_id, write_report=write_report)


def table(name: str, file_id: str = FID) -> list[dict[str, Any]]:
    return pq.read_table(paths.file_dir(file_id) / f"{name}.parquet").to_pylist()


def scores_by_name(file_id: str = FID) -> dict[str, dict[str, Any]]:
    names = {e["entity_id"]: e["key_value"] for e in table("entities", file_id)}
    return {names[s["entity_id"]]: s for s in table("scores", file_id)}


def signals_by_name(file_id: str = FID) -> dict[str, dict[str, dict[str, Any]]]:
    names = {e["entity_id"]: e["key_value"] for e in table("entities", file_id)}
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for s in table("signals", file_id):
        out.setdefault(names[s["entity_id"]], {})[s["signal_id"]] = s
    return out
