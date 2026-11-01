import csv
import gzip
import json
from pathlib import Path

import pyarrow.parquet as pq
import pytest
import zstandard
from conftest import FIXTURE, REPO_ROOT, _load_explorer_flatten

from sis import db, paths
from sis.config import settings
from sis.ingest import file_id as file_id_mod
from sis.ingest import run as run_mod
from sis.ingest.flatten import SCHEMA, VSCHEMA, MissingIdError, flatten_record
from sis.ingest.log import append_ingest_log, read_ingest_log
from sis.ingest.reader import is_zstd, stream_blocks, stream_lines

SMALL_BLOCK = 256 * 1024  # several blocks from the 1.1 MB fixture; above its largest line (151 KB)


@pytest.fixture(autouse=True)
def data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "sis_data"
    monkeypatch.setattr(settings, "SIS_DATA", root)
    # keep the report out of the repo's docs/ while testing
    monkeypatch.setattr(run_mod, "REPORT_DIR", tmp_path / "docs")
    return root


def make_zst(tmp_path: Path, payload: bytes, name: str = "delivery") -> Path:
    p = tmp_path / name
    p.write_bytes(zstandard.ZstdCompressor(level=3).compress(payload))
    return p


@pytest.fixture
def fixture_zst(tmp_path: Path) -> Path:
    return make_zst(tmp_path, FIXTURE.read_bytes())


def fixture_lines() -> list[bytes]:
    return FIXTURE.read_bytes().splitlines()


# ---- file_id ---------------------------------------------------------------------------


def test_file_id_stable(tmp_path: Path) -> None:
    data = bytes(range(256)) * 1000
    a = tmp_path / "a"
    a.write_bytes(data)
    assert file_id_mod.compute_file_id(a) == file_id_mod.compute_file_id(a)
    b = tmp_path / "b"
    b.write_bytes(data[:100] + b"\x00" + data[101:])  # 1 byte changed, same length
    assert file_id_mod.compute_file_id(b) != file_id_mod.compute_file_id(a)
    c = tmp_path / "c"
    c.write_bytes(data + b"x")  # same prefix, different length
    assert file_id_mod.compute_file_id(c) != file_id_mod.compute_file_id(a)


def test_file_id_only_reads_the_first_64_mib(tmp_path: Path) -> None:
    head = b"a" * file_id_mod.HEAD_BYTES
    one, two = tmp_path / "one", tmp_path / "two"
    one.write_bytes(head + b"X" + b"tail")
    two.write_bytes(head + b"Y" + b"tail")  # differs after 64 MiB, same length
    assert file_id_mod.compute_file_id(one) == file_id_mod.compute_file_id(two)


def test_file_id_is_a_valid_windows_name(tmp_path: Path) -> None:
    p = tmp_path / "f"
    p.write_bytes(b"x")
    fid = file_id_mod.compute_file_id(p)
    assert not set(fid) & set('<>:"/\\|?*')
    assert fid.endswith("-1")


# ---- reader ----------------------------------------------------------------------------


def test_is_zstd(tmp_path: Path) -> None:
    z = make_zst(tmp_path, b"{}\n")
    g = tmp_path / "g.gz"
    g.write_bytes(gzip.compress(b"{}\n"))
    assert is_zstd(z) and not is_zstd(g)


def test_stream_lines_roundtrip(fixture_zst: Path) -> None:
    assert list(stream_lines(fixture_zst)) == fixture_lines()


def test_stream_blocks_are_newline_aligned_and_bounded(fixture_zst: Path) -> None:
    blocks = list(stream_blocks(fixture_zst, block_bytes=SMALL_BLOCK))
    assert len(blocks) > 3
    joined = b"".join(b.data for b in blocks)
    assert joined == FIXTURE.read_bytes()
    assert all(b.data.endswith(b"\n") for b in blocks)
    # a block overshoots the target by at most one read chunk (a quarter block here)
    assert max(len(b.data) for b in blocks) <= SMALL_BLOCK + SMALL_BLOCK // 4


def test_stream_blocks_adds_trailing_newline(tmp_path: Path) -> None:
    z = make_zst(tmp_path, b'{"a":1}\n{"a":2}')
    assert b"".join(b.data for b in stream_blocks(z)) == b'{"a":1}\n{"a":2}\n'


def test_stream_blocks_drops_a_line_larger_than_the_buffer(tmp_path: Path) -> None:
    payload = b'{"a":1}\n' + b"x" * 5000 + b'\n{"a":2}\n'
    z = make_zst(tmp_path, payload)
    blocks = list(stream_blocks(z, block_bytes=1000))
    assert sum(b.oversize for b in blocks) == 1
    assert b"".join(b.data for b in blocks) == b'{"a":1}\n{"a":2}\n'


# ---- flatten ---------------------------------------------------------------------------


def test_flatten_matches_fixture() -> None:
    fid = "f" * 8
    explorer = _load_explorer_flatten()
    expected_cols = [r["column"] for r in csv.DictReader(
        open(REPO_ROOT / "findings" / "02_columns.csv", encoding="utf-8"))]
    rows = []
    for line in fixture_lines():
        row, _ = flatten_record(json.loads(line), fid)
        rows.append(row)
    assert len(rows) == 200
    assert list(rows[0]) == expected_cols + ["file_id"]  # 93 columns in the file, not 96
    assert SCHEMA.names == expected_cols + ["file_id"]
    assert {r["file_id"] for r in rows} == {fid}
    # identical to the explorer's flattener on every column it produces
    for line, row in zip(fixture_lines(), rows, strict=True):
        vrows: list[dict] = []  # type: ignore[type-arg]
        ref = explorer.flatten(json.loads(line), vrows, __import__("collections").Counter())
        for col in expected_cols:
            if col == "record_bytes":
                continue  # set by the caller in both implementations
            assert row[col] == ref[col], col


def test_flatten_emits_vuln_children() -> None:
    obj = {
        "_shodan": {"id": "x1", "module": "http"},
        "vulns": {"CVE-2020-1": {"cvss": 7.5, "verified": False, "kev": True,
                                 "ransomware_campaign": "Known", "references": ["a", "b"]}},
    }
    row, vrows = flatten_record(obj, "fid")
    assert row["n_vulns"] == 1 and row["max_cvss"] == 7.5
    assert len(vrows) == 1 and vrows[0]["cve"] == "CVE-2020-1" and vrows[0]["file_id"] == "fid"
    assert vrows[0]["n_references"] == 2 and "Known" in vrows[0]["other_keys"]
    assert list(vrows[0]) == VSCHEMA.names


def test_flatten_stashes_unknown_blocks_in_extra_json() -> None:
    row, _ = flatten_record({"_shodan": {"id": "x"}, "brand_new_protocol": {"k": 1}}, "fid")
    assert json.loads(row["extra_json"]) == {"brand_new_protocol": {"k": 1}}


@pytest.mark.parametrize("obj", [{}, {"_shodan": {}}, {"_shodan": {"id": None}},
                                 {"_shodan": {"id": 7}}, {"_shodan": {"id": ""}}])
def test_flatten_requires_a_string_id(obj: dict) -> None:  # type: ignore[type-arg]
    with pytest.raises(MissingIdError):
        flatten_record(obj, "fid")


# ---- the run ---------------------------------------------------------------------------


def banner_count(fid: str) -> int:
    con = db.connect()
    db.register(con, "b", paths.banners_glob(fid))
    row = con.execute("SELECT count(*) FROM b").fetchone()
    assert row is not None
    return int(row[0])


def test_ingest_fixture_end_to_end(fixture_zst: Path, tiny_banners) -> None:  # type: ignore[no-untyped-def]
    res = run_mod.ingest(fixture_zst, workers=1, block_bytes=SMALL_BLOCK)
    assert res.status == "ok", res.error
    assert (res.lines_read, res.rows_written, res.rows_dropped) == (200, 200, 0)
    assert res.lines_read == res.rows_written + res.rows_dropped
    final = paths.file_dir(res.file_id)
    assert final.is_dir() and not paths.tmp_dir(res.file_id).exists()
    assert len(list((final / "banners").glob("*.parquet"))) > 1
    assert banner_count(res.file_id) == 200
    inv = json.loads((final / "key_inventory.json").read_text(encoding="utf-8"))
    assert inv["top_keys"]["_shodan"] == 200 and inv["new_keys"] == {}
    assert (run_mod.REPORT_DIR / f"INGEST_REPORT_{res.file_id}.md").exists()
    log = read_ingest_log().to_pylist()
    assert [r["status"] for r in log] == ["ok"] and log[0]["rows_written"] == 200

    # same bytes out as the explorer's flattener (minus the file_id column)
    con = db.connect()
    db.register(con, "new", paths.banners_glob(res.file_id))
    db.register(con, "ref", tiny_banners.banners_glob)
    diff = con.execute(
        "SELECT count(*) FROM (SELECT * EXCLUDE (file_id) FROM new EXCEPT SELECT * FROM ref)"
    ).fetchone()
    assert diff == (0,)
    assert con.execute("SELECT DISTINCT file_id FROM new").fetchall() == [(res.file_id,)]


def test_rejects_non_zstd(tmp_path: Path) -> None:
    g = tmp_path / "delivery.gz"
    g.write_bytes(gzip.compress(FIXTURE.read_bytes()))
    res = run_mod.ingest(g, workers=1)
    assert res.status == "rejected"
    assert not paths.file_dir(res.file_id).exists()
    assert not paths.tmp_dir(res.file_id).exists()


def test_quarantines_garbage(tmp_path: Path) -> None:
    z = make_zst(tmp_path, b"xx\n" * 1500)
    res = run_mod.ingest(z, workers=1)
    assert res.status == "quarantined"
    assert not paths.file_dir(res.file_id).exists()
    q = paths.quarantine_dir() / f"{res.file_id}.txt"
    assert q.exists() and len(q.read_text(encoding="utf-8").splitlines()) == 50
    assert read_ingest_log().to_pylist()[0]["status"] == "quarantined"


def test_tolerates_a_few_bad_lines_in_the_first_thousand(tmp_path: Path) -> None:
    lines = fixture_lines() * 6  # 1,200 lines; ids repeat, which ingest does not police
    bad = [b"not json", b'{"no_shodan": 1}', b"[1,2]"]  # 3 of the first 1,000 is under 1 percent
    payload = b"\n".join(lines[:100] + bad + lines[100:]) + b"\n"
    res = run_mod.ingest(make_zst(tmp_path, payload), workers=1, block_bytes=SMALL_BLOCK)
    assert res.status == "ok", res.error
    assert res.lines_read == 1203 and res.rows_written == 1200 and res.rows_dropped == 3
    assert res.dropped_reasons == {"json_parse": 2, "missing_id": 1}


def test_duplicate_skipped(fixture_zst: Path) -> None:
    first = run_mod.ingest(fixture_zst, workers=1)
    assert first.status == "ok"
    second = run_mod.ingest(fixture_zst, workers=1)
    assert second.status == "duplicate"
    assert second.rows_written == 200  # the earlier run's numbers
    dirs = {p.name for p in settings.SIS_DATA.iterdir() if p.is_dir()}
    assert dirs <= {first.file_id, "duckdb_tmp"}
    assert [r["status"] for r in read_ingest_log().to_pylist()] == ["ok", "duplicate"]


def test_force_reruns_a_known_file(fixture_zst: Path) -> None:
    run_mod.ingest(fixture_zst, workers=1)
    again = run_mod.ingest(fixture_zst, workers=1, force=True)
    assert again.status == "ok" and again.rows_written == 200
    assert banner_count(again.file_id) == 200  # replaced, not doubled


def test_atomic_on_crash(fixture_zst: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real = run_mod.write_part
    calls = {"n": 0}

    def boom(table, path):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("disk full")
        real(table, path)

    monkeypatch.setattr(run_mod, "write_part", boom)
    res = run_mod.ingest(fixture_zst, workers=1, block_bytes=SMALL_BLOCK)
    assert res.status == "failed" and "disk full" in (res.error or "")
    assert not paths.file_dir(res.file_id).exists()
    assert not paths.tmp_dir(res.file_id).exists()
    assert read_ingest_log().to_pylist()[-1]["status"] == "failed"


def test_reconciliation_failure_fails_the_run(
    fixture_zst: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = run_mod.write_part

    def lose_rows(table, path):  # type: ignore[no-untyped-def]
        real(table.slice(0, max(table.num_rows - 1, 0)), path)  # silently writes one row fewer

    monkeypatch.setattr(run_mod, "write_part", lose_rows)
    res = run_mod.ingest(fixture_zst, workers=1, block_bytes=SMALL_BLOCK)
    assert res.status == "failed" and "reconcil" in (res.error or "").lower()
    assert not paths.file_dir(res.file_id).exists()


def test_new_provider_field_is_reported(tmp_path: Path) -> None:
    lines = fixture_lines()
    extra = json.loads(lines[0])
    extra["_shodan"]["id"] = "extra-1"
    extra["quantum_scanner"] = {"x": 1}
    payload = b"\n".join(lines + [json.dumps(extra).encode()]) + b"\n"
    res = run_mod.ingest(make_zst(tmp_path, payload), workers=1)
    assert res.status == "ok" and res.new_keys == {"quantum_scanner": 1}


def test_parallel_workers_match_serial(fixture_zst: Path) -> None:
    """Real process pool (spawn), same output as the in-process path."""
    serial = run_mod.ingest(fixture_zst, workers=1, block_bytes=SMALL_BLOCK)
    par = run_mod.ingest(fixture_zst, workers=2, block_bytes=SMALL_BLOCK, force=True)
    assert par.status == "ok", par.error
    assert (par.lines_read, par.rows_written, par.vuln_rows_written) == (
        serial.lines_read, serial.rows_written, serial.vuln_rows_written)
    n = sum(pq.ParquetFile(p).metadata.num_rows
            for p in (paths.file_dir(par.file_id) / "banners").glob("*.parquet"))
    assert n == 200


# ---- ingest log ------------------------------------------------------------------------


def test_ingest_log_appends_atomically(data_root: Path) -> None:
    assert read_ingest_log().num_rows == 0
    base = {"file_id": "a", "status": "ok", "lines_read": 5}
    append_ingest_log(base)
    append_ingest_log({**base, "file_id": "b", "status": "failed", "error": "x"})
    rows = read_ingest_log().to_pylist()
    assert [r["file_id"] for r in rows] == ["a", "b"]
    assert rows[1]["error"] == "x" and rows[0]["error"] is None
    assert not list(data_root.glob("*.tmp"))
