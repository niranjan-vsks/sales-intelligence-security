"""P6: the diff, the synthetic second delivery, and the check of one against the other."""

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any

import orjson
import pyarrow.parquet as pq
import pytest
import zstandard
from p3_build import build

from sis import delta_config, paths
from sis.config import settings
from sis.delta import diff as diff_mod
from sis.delta import run as run_mod
from sis.delta import synth as synth_mod
from sis.delta.truth import PERTURBATIONS, synthetic_file_ids, write_truth
from sis.entities import resolve as resolve_mod
from sis.ingest import run as ingest_run
from sis.ingest.log import append_ingest_log
from sis.scoring import score as score_mod

FA, FB = "filea", "fileb"
WHEN = datetime(2026, 11, 3, 12, 0, 0)
WEB = {"module": "https", "port": 443, "http_status": 200}
WAF = "Cloudflare (Cloudflare Inc.)"


@pytest.fixture(autouse=True)
def data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "sis_data"
    monkeypatch.setattr(settings, "SIS_DATA", root)
    for mod in (resolve_mod, score_mod, ingest_run, run_mod):
        monkeypatch.setattr(mod, "REPORT_DIR", tmp_path / "docs")
    return root


@pytest.fixture
def ops(tmp_path: Path) -> Path:
    p = tmp_path / "operators.txt"
    p.write_text("bigcdn.net\n", encoding="utf-8")
    return p


def row(domain: str, n: int = 0, **kw: Any) -> dict[str, Any]:
    """A banner of `domain` with a fixed ip and id, so the same row in 2 files is 1 service."""
    port = kw.get("port", WEB["port"])
    return {**WEB, "id": f"{domain}-{n}-{port}", "ip_str": f"192.0.2.{abs(hash(domain)) % 200}",
            "domains": [domain], **kw}


def two_files(ops: Path, a: list[dict[str, Any]], b: list[dict[str, Any]]) -> None:
    build(a, ops, file_id=FA)
    build(b, ops, file_id=FB)


def events(file_a: str = FA, file_b: str = FB) -> list[dict[str, Any]]:
    return diff_mod.read_events(file_a, file_b)


def of_type(t: str) -> list[dict[str, Any]]:
    return [e for e in events() if e["event_type"] == t]


# ---- the diff ---------------------------------------------------------------------------


def test_diff_detects_removed_waf(ops: Path) -> None:
    a = [row("walled.com", http_waf=WAF), row("plain.com"), row("other.org")]
    b = [row("walled.com"), row("plain.com"), row("other.org")]
    two_files(ops, a, b)
    res = diff_mod.diff(FA, FB, detected_at=WHEN)
    assert res.by_type["protection_removed"] == 1
    (e,) = of_type("protection_removed")
    assert e["subject"] == "D_waf" and e["severity"] == 3 and e["from_value"] == WAF
    assert not of_type("protection_added")
    ent = {r["entity_id"]: r["key_value"] for r in
           pq.read_table(paths.file_dir(FA) / "entities.parquet").to_pylist()}
    assert ent[e["entity_id"]] == "walled.com"


def test_diff_idempotent(ops: Path) -> None:
    a = [row("walled.com", http_waf=WAF), row("plain.com")]
    b = [row("walled.com"), row("plain.com", cert_expired=True), row("fresh.net")]
    two_files(ops, a, b)
    diff_mod.diff(FA, FB, detected_at=WHEN)
    first = paths.events_path().read_bytes()
    diff_mod.diff(FA, FB, detected_at=WHEN)
    assert paths.events_path().read_bytes() == first
    n = diff_mod.append_history(FA)
    diff_mod.append_history(FB)
    h = paths.entity_history_path().read_bytes()
    assert diff_mod.append_history(FA) == n and diff_mod.append_history(FB) > 0
    assert paths.entity_history_path().read_bytes() == h


def test_event_id_stable(ops: Path) -> None:
    two_files(ops, [row("walled.com", http_waf=WAF)], [row("walled.com")])
    diff_mod.diff(FA, FB, detected_at=WHEN)
    evs = events()
    assert evs
    for e in evs:
        want = hashlib.sha1((e["entity_id"] + e["event_type"] + FA + FB + e["subject"]).encode()
                            ).hexdigest()
        assert e["event_id"] == want
    assert len({e["event_id"] for e in evs}) == len(evs)
    before = {e["event_id"] for e in evs}
    diff_mod.diff(FA, FB, detected_at=datetime(2030, 1, 1))  # the time does not enter the id
    assert {e["event_id"] for e in events()} == before


def test_history_and_other_pairs_survive(ops: Path) -> None:
    two_files(ops, [row("a.com"), row("b.com")], [row("a.com")])
    diff_mod.diff(FA, FB, detected_at=WHEN)
    build([row("a.com"), row("c.com")], ops, file_id="filec")
    diff_mod.diff(FB, "filec", detected_at=WHEN)
    pairs = {(e["from_file"], e["to_file"]) for e in diff_mod.read_events(FA, FB)}
    assert pairs == {(FA, FB)}
    assert {e["event_type"] for e in diff_mod.read_events(FB, "filec")} >= {"entity_new"}
    assert {e["event_type"] for e in events()} >= {"entity_gone"}
    diff_mod.append_history(FA)
    diff_mod.append_history(FB)
    h = pq.read_table(paths.entity_history_path()).to_pylist()
    assert {r["file_id"] for r in h} == {FA, FB}
    assert all("exposure" in r and "key_value" in r for r in h)


def test_event_types_and_severity(ops: Path) -> None:
    ssh = {"module": "ssh", "port": 22, "http_status": None, "data_len": 40}
    a = [row("grow.com"), row("gone.com"), row("cert.com"), row("eol.com"), row("seg.com"),
         row("same.org")]
    b = [row("grow.com"), row("grow.com", 1, **ssh), row("cert.com", cert_expired=True),
         row("eol.com", tags=["eol-product"]), row("seg.com", http_waf=WAF),
         row("same.org"), row("new.net")]
    two_files(ops, a, b)
    diff_mod.diff(FA, FB, detected_at=WHEN)
    by = {}
    for e in events():
        by.setdefault(e["event_type"], []).append(e)
    sev = {t: {e["severity"] for e in es} for t, es in by.items()}
    assert sev["entity_new"] == {2} and sev["entity_gone"] == {1}
    (svc,) = by["service_new"]
    assert svc["to_value"] == "ssh" and svc["severity"] == 3  # admin module
    assert svc["subject"].endswith(":22")
    (cert,) = by["cert_expired_since"]
    assert cert["severity"] == 3 and cert["subject"] == "B_expired"
    assert "signal_appeared" in by and {e["subject"] for e in by["signal_appeared"]} >= {"A_eol"}
    assert {e["severity"] for e in by["signal_appeared"] if e["subject"] == "A_eol"} == {3}
    assert "B_expired" not in {e["subject"] for e in by["signal_appeared"]}  # own event type
    assert sev["protection_added"] == {1}
    assert "segment_changed" in by  # seg.com: untouched -> displace
    assert all(e["severity"] in (1, 2, 3) for es in by.values() for e in es)


def test_severity_sql_follows_config() -> None:
    cfg = delta_config.load().diff.severity
    sql = diff_mod.severity_sql(cfg)
    assert "WHEN event_type = 'protection_removed' THEN 3" in sql
    assert sql.endswith(f"ELSE {cfg.default} END")
    assert "'ssh'" in sql and "'A_eol'" in sql


def test_exposure_threshold(ops: Path) -> None:
    a = [row("quiet.com"), row("loud.com")]
    b = [row("quiet.com"), row("loud.com", tags=["eol-product"], cert_expired=True,
                               os="Windows Server 2012")]
    two_files(ops, a, b)
    diff_mod.diff(FA, FB, detected_at=WHEN)
    ups = of_type("exposure_up")
    assert [float(e["to_value"]) - float(e["from_value"]) >= 10 for e in ups] == [True] * len(ups)
    assert not of_type("exposure_down")


def test_entities_gone_have_no_service_events(ops: Path) -> None:
    two_files(ops, [row("gone.com"), row("gone.com", 1, port=8443), row("stay.com")],
              [row("stay.com")])
    diff_mod.diff(FA, FB, detected_at=WHEN)
    assert len(of_type("entity_gone")) == 1
    assert not of_type("service_gone")


# ---- the synthetic delivery -------------------------------------------------------------


def banners(n_domains: int = 100) -> list[dict[str, Any]]:
    """n_domains domains, 3 banners each: https with a cert (some with a WAF, some with a CPE)
    and a plain http one."""
    out: list[dict[str, Any]] = []
    for i in range(n_domains):
        d = f"site{i}.com"
        out.append({**row(d, 0), "ip_str": f"10.1.{i // 250}.{i % 250}",
                    "cert_expires": datetime(2027, 1, 1), "cert_expired": False,
                    "http_waf": WAF if i % 3 == 0 else None,
                    "cpe23": ["cpe:2.3:a:x:y:1"] if i % 2 else None})
        out.append({**row(d, 1, port=80), "ip_str": f"10.2.{i // 250}.{i % 250}",
                    "module": "http"})
        out.append({**row(d, 2, port=8080), "ip_str": f"10.3.{i // 250}.{i % 250}",
                    "module": "http", "cpe23": ["cpe:2.3:a:z:w:2"]})
    return out


def test_synth_truth_counts(ops: Path) -> None:
    build(banners(), ops, file_id=FA)
    cfg = delta_config.load().synth
    sel = synth_mod.select(FA, 42, cfg)
    for p in PERTURBATIONS:
        want = getattr(cfg.percent, p) / 100 * sel.eligible[p]
        assert abs(sel.selected[p] - want) <= 1, (p, sel.selected[p], want)
        # the banners the stream will change; for entity-grain types that is more than `selected`
        assert len({r["banner_id"] for r in sel.items[p]}) == sel.selected_banners[p]
        if sel.unit[p] == "banners":
            assert sel.selected_banners[p] == sel.selected[p]
    assert sel.unit["remove_waf"] == sel.unit["add_vuln"] == "entities"
    assert sel.selected["drop_banner"] == round(0.02 * 300) == 6  # 2% of all 300 banners
    ids = [r["banner_id"] for p in PERTURBATIONS for r in sel.items[p]]
    assert len(ids) == len(set(ids))  # a banner takes part in 1 perturbation only
    again = synth_mod.select(FA, 42, cfg)
    assert again == sel  # the seed decides everything
    other = synth_mod.select(FA, 43, cfg)
    assert other.items != sel.items


def pcts(**kw: float) -> delta_config.Percent:
    base = {p: 0.0 for p in PERTURBATIONS}
    return delta_config.Percent(**{**base, **kw})


def test_synth_eligibility(ops: Path) -> None:
    build(banners(), ops, file_id=FA)
    cfg = delta_config.load().synth
    cfg = cfg.model_copy(update={"percent": pcts(
        expire_cert=100, remove_waf=100, add_waf=100, add_vuln=100)})
    sel = synth_mod.select(FA, 1, cfg)
    items = sel.items
    by_id = {r["id"]: r for r in banners()}
    # edge banners (a W01 WAF) never take expire_cert or add_vuln: the scorer ignores them
    assert all(not by_id[r["banner_id"]].get("http_waf") for r in items["expire_cert"])
    assert all(not by_id[r["banner_id"]].get("http_waf") for r in items["add_vuln"])
    assert all(by_id[r["banner_id"]].get("http_waf") for r in items["remove_waf"])
    assert all(not by_id[r["banner_id"]].get("http_waf") for r in items["add_waf"])
    assert sel.eligible["add_waf"] == sel.selected["add_waf"] > 0
    # add_waf never lands on an entity whose WAF remove_waf took away (it would put it back)
    stripped = {r["key_value"] for r in items["remove_waf"]}
    assert stripped and not stripped & {r["key_value"] for r in items["add_waf"]}


def test_entity_grain_takes_every_banner_of_the_entity(ops: Path) -> None:
    rows = [row("multi.com", n, port=p, http_waf=WAF, cpe23=["cpe:2.3:a:x:y:1"])
            for n, p in enumerate((443, 8443, 9443))]
    rows += [row("single.com", http_waf=WAF)]
    rows += [row(f"plain{i}.com", cpe23=["cpe:2.3:a:x:y:1"]) for i in range(4)]
    build(rows, ops, file_id=FA)
    cfg = delta_config.load().synth
    sel = synth_mod.select(FA, 3, cfg.model_copy(update={"percent": pcts(remove_waf=100)}))
    assert sel.selected["remove_waf"] == 2 and sel.eligible["remove_waf"] == 2
    assert sel.selected_banners["remove_waf"] == 4
    assert {r["banner_id"] for r in sel.items["remove_waf"]} == {
        r["id"] for r in rows if r.get("http_waf")}
    half = synth_mod.select(FA, 3, cfg.model_copy(update={"percent": pcts(remove_waf=50)}))
    assert half.selected["remove_waf"] == 1  # one entity, and all of its banners
    names = {r["key_value"] for r in half.items["remove_waf"]}
    assert len(names) == 1
    assert half.selected_banners["remove_waf"] == (3 if names == {"multi.com"} else 1)
    vuln = synth_mod.select(FA, 3, cfg.model_copy(update={"percent": pcts(add_vuln=100)}))
    assert vuln.selected["add_vuln"] == 4  # plain0..3: multi.com's CPE banners are edge
    # multi.com's CPE banners carry the WAF, so they are edge banners and not eligible
    assert not {r["banner_id"] for r in vuln.items["add_vuln"]} & {
        r["id"] for r in rows if r.get("http_waf")}


def test_remove_waf_skips_entities_whose_waf_a_copy_would_keep(ops: Path) -> None:
    rows = [row("keep.com", n, port=p, http_waf=WAF) for n, p in enumerate((443, 8443))]
    build(rows, ops, file_id=FA)
    cfg = delta_config.load().synth
    sel = synth_mod.select(FA, 3, cfg.model_copy(update={"percent": pcts(
        new_banner=50, remove_waf=100)}))
    assert sel.selected["new_banner"] == 1
    assert sel.eligible["remove_waf"] == 0  # the copy of a WAF banner would keep the WAF


def test_drop_prefers_banners_sole_on_their_ip_port(ops: Path) -> None:
    twin = {"ip_str": "203.0.113.5", "port": 443}
    rows = [row("dup.com", 0, **twin), row("dup.com", 1, module="http", **twin)]
    rows += [row(f"solo{i}.com") for i in range(6)]
    build(rows, ops, file_id=FA)
    cfg = delta_config.load().synth
    few = synth_mod.select(FA, 9, cfg.model_copy(update={"percent": pcts(drop_banner=50)}))
    assert few.selected["drop_banner"] == 4
    assert not {r["key_value"] for r in few.items["drop_banner"]} & {"dup.com"}
    assert few.drop_sole == {"selected": 4, "available": 6}
    every = synth_mod.select(FA, 9, cfg.model_copy(update={"percent": pcts(drop_banner=100)}))
    assert every.selected["drop_banner"] == 8  # sole banners first, then the rest
    assert every.drop_sole == {"selected": 6, "available": 6}


def test_new_banner_port_differs_and_is_stable() -> None:
    ports = [2222, 8443]
    for pid in ("a", "b", "c", "d"):
        p = synth_mod.new_banner_port(7, pid, 2222, ports)
        assert p == 8443
        assert synth_mod.new_banner_port(7, pid, 8443, ports) == 2222
        assert synth_mod.new_banner_port(7, pid, 80, ports) == synth_mod.new_banner_port(
            7, pid, 80, ports)
    assert synth_mod.new_banner_id(7, "x") == synth_mod.new_banner_id(7, "x")
    assert synth_mod.new_banner_id(7, "x") != synth_mod.new_banner_id(8, "x")


def rec(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "_shodan": {"id": "id1", "module": "https"}, "port": 443, "ip_str": "192.0.2.1",
        "timestamp": "2026-10-26T11:59:52.579107",
        "http": {"status": 200, "waf": WAF},
        "ssl": {"cert": {"expires": "20270101000000Z", "expired": False}},
        "cpe23": ["cpe:2.3:a:x:y:1"]}
    return {**base, **kw}


def test_shift_ts_keeps_shape() -> None:
    assert synth_mod.shift_ts("2026-10-26T11:59:52.579107", 30) == "2026-11-25T11:59:52.579107"
    assert synth_mod.shift_ts("2026-10-26T11:59:52", 30) == "2026-11-25T11:59:52"
    with pytest.raises(ValueError):
        synth_mod.shift_ts("yesterday", 30)


def test_perturb_record_each_type() -> None:
    cfg = delta_config.load().synth
    pr = synth_mod.perturb_record
    (plain,), applied = pr(rec(), None, cfg)
    assert applied is None and plain["timestamp"] == "2026-11-25T11:59:52.579107"
    assert pr(rec(), synth_mod.Action("drop_banner"), cfg) == ([], "drop_banner")
    orig, copy = pr(rec(), synth_mod.Action("new_banner", "id2", 8443), cfg)[0]
    assert orig["_shodan"]["id"] == "id1" and orig["port"] == 443
    assert copy["_shodan"]["id"] == "id2" and copy["port"] == 8443
    assert copy["timestamp"] == orig["timestamp"] == "2026-11-25T11:59:52.579107"
    (e,), _ = pr(rec(), synth_mod.Action("expire_cert"), cfg)
    assert e["ssl"]["cert"]["expired"] is True
    assert e["ssl"]["cert"]["expires"] == "20261115115952Z"  # 10 days before the new timestamp
    (r,), _ = pr(rec(), synth_mod.Action("remove_waf"), cfg)
    assert "waf" not in r["http"]
    (w,), _ = pr(rec(http={"status": 200}), synth_mod.Action("add_waf"), cfg)
    assert w["http"]["waf"] == WAF
    (v,), _ = pr(rec(), synth_mod.Action("add_vuln"), cfg)
    assert v["vulns"] == {"CVE-2099-00001": {"cvss": 9.8, "verified": False, "references": [],
                                             "summary": "Synthetic CVE injected by sis synth"}}
    assert "kev" not in v["vulns"]["CVE-2099-00001"]
    (bad,), applied = pr(rec(timestamp="garbage"), synth_mod.Action("add_vuln"), cfg)
    assert applied is None and bad["timestamp"] == "garbage" and "vulns" not in bad
    (keep,), _ = pr(rec(vulns={"CVE-1": {"cvss": 5}}), synth_mod.Action("add_vuln"), cfg)
    assert set(keep["vulns"]) == {"CVE-1", "CVE-2099-00001"}


def test_synthetic_files_stay_out_of_current_state(tmp_path: Path, ops: Path) -> None:
    for fid in (FA, FB):
        build(banners(5), ops, file_id=fid)
        append_ingest_log({"file_id": fid, "original_name": fid, "byte_length": 1,
                           "received_at": WHEN, "status": "ok"})
    assert resolve_mod.merge_current().files == sorted([FA, FB])
    assert score_mod.merge_current().files == sorted([FA, FB])
    write_truth(paths.synth_truth_path(42), {"seed": 42, "synthetic_file_id": FB})
    assert synthetic_file_ids() == {FB}
    assert resolve_mod.merge_current().files == [FA]
    assert score_mod.merge_current().files == [FA]
    op = tmp_path / "ops.txt"
    op.write_text("bigcdn.net\n", encoding="utf-8")
    resolve_mod.resolve(FB, operator_file=op, write_report=False)
    assert op.read_text(encoding="utf-8") == "bigcdn.net\n"  # no derived section for FB


# ---- end to end -------------------------------------------------------------------------


def raw_line(i: int, domain: str, port: int, module: str, waf: str | None, cert: bool,
             cpe: bool) -> dict[str, Any]:
    http: dict[str, Any] = {"status": 200, "host": domain, "title": "t"}
    if waf:
        http["waf"] = waf
    out: dict[str, Any] = {
        "_shodan": {"id": f"raw-{i}", "module": module}, "ip_str": f"10.9.{i // 250}.{i % 250}",
        "port": port, "timestamp": "2026-10-26T12:00:00.000000", "domains": [domain],
        "hostnames": [domain], "http": http, "data": "x" * 20,
        "location": {"country_code": "US"}}
    if cert:
        out["ssl"] = {"cert": {"issued": "20250101000000Z", "expires": "20270101000000Z",
                               "expired": False, "subject": {"CN": domain},
                               "issuer": {"CN": "CA"}}}
    if cpe:
        out["cpe23"] = ["cpe:2.3:a:x:y:1"]
    return out


def test_end_to_end_small(tmp_path: Path, ops: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lines: list[dict[str, Any]] = []
    for d in range(60):
        dom = f"corp{d}.com"
        lines.append(raw_line(len(lines), dom, 443, "https", WAF if d % 3 == 0 else None, True,
                              d % 2 == 1))
        lines.append(raw_line(len(lines), dom, 80, "http", None, False, d % 2 == 0))
    raw = tmp_path / "delivery"
    raw.write_bytes(zstandard.ZstdCompressor().compress(
        b"\n".join(orjson.dumps(x) for x in lines) + b"\n"))
    a = ingest_run.ingest(raw, workers=1)
    assert a.status == "ok"
    resolve_mod.resolve(a.file_id, operator_file=ops, write_back=False, write_report=False)

    cfg = delta_config.load().synth
    big = cfg.model_copy(update={"percent": delta_config.Percent(
        drop_banner=10, new_banner=10, expire_cert=20, remove_waf=30, add_waf=20, add_vuln=20)})
    orig_load = delta_config.load
    monkeypatch.setattr(delta_config, "load", lambda path=None: orig_load(path).model_copy(
        update={"synth": big}))
    sm = synth_mod
    res = sm.synth(a.file_id, seed=5, raw=raw, workers=1, block_bytes=4096)
    assert res.applied == res.selected_banners
    assert res.lines_out == res.lines_in - res.selected["drop_banner"] + res.selected["new_banner"]
    assert res.selected["drop_banner"] == 12 and res.selected["new_banner"] == 11
    # same seed, same bytes (so the same file_id); a rerun without --force reuses the file
    again = sm.synth(a.file_id, seed=5, raw=raw, workers=1)
    assert again.synthetic_file_id == res.synthetic_file_id
    assert synthetic_file_ids() == {res.synthetic_file_id}

    b = ingest_run.ingest(paths.synth_path(5), workers=1)
    assert b.status == "ok" and b.file_id == res.synthetic_file_id
    assert b.rows_written == a.rows_written - 12 + 11
    resolve_mod.resolve(b.file_id, operator_file=ops, write_back=False, write_report=False)
    for fid in (a.file_id, b.file_id):
        score_mod.score(fid, write_report=False)
    out = run_mod.run(a.file_id, b.file_id, report_dir=tmp_path / "reports")
    assert out.stats is not None
    by = {s.ptype: s for s in out.stats}
    for p in PERTURBATIONS:
        assert by[p].applied == res.applied[p]
        assert by[p].unexplained == 0, by[p]
    # entity-grain remove_waf and sole-preferring drops leave nothing to miss on this data
    assert by["remove_waf"].recall == 1.0 and by["drop_banner"].recall == 1.0
    text = Path(out.report).read_text(encoding="utf-8")
    assert "simulated second delivery" in text and "Diff wall time" in text
    assert text.count("**unexplained**") == 6


# ---- the bundle and the app -------------------------------------------------------------


def test_bundle_events_and_recent_change(tmp_path: Path, ops: Path) -> None:
    import json
    import shutil

    from fastapi.testclient import TestClient

    from sis.api.app import create_app
    from sis.export.bundle import export

    a = [row("walled.com", http_waf=WAF), row("plain.com"), row("other.org")]
    b = [row("walled.com"), row("plain.com", cert_expired=True), row("other.org")]
    two_files(ops, a, b)
    diff_mod.diff(FA, FB, detected_at=WHEN)
    write_truth(paths.synth_truth_path(1), {"seed": 1, "synthetic_file_id": FB})
    cur = paths.current_dir()
    cur.mkdir(parents=True)
    for name in ("entities.parquet", "scores.parquet"):  # current state = the first file
        shutil.copy(paths.file_dir(FA) / name, cur / name)
    res = export("t-1")
    assert res.n_events == len(events()) > 0
    meta = json.loads((Path(res.path) / "bundle.json").read_text(encoding="utf-8"))
    assert meta["delta"] == {"from_file": FA, "to_file": FB, "n_events": res.n_events,
                             "simulated": True}
    with TestClient(create_app(Path(res.path))) as c:
        items = c.get("/api/accounts?sort=recent_change").json()["items"]
        sev = [i["max_event_severity"] for i in items]
        assert sev[:2] == [3, 3] and sev[2] is None  # walled.com and plain.com changed
        assert {i["display_name"] for i in items[:2]} == {"walled.com", "plain.com"}
        by = {i["display_name"]: i for i in items}
        page = c.get(f"/accounts/{by['walled.com']['entity_id']}")
        assert "Changes (simulated second delivery)" in page.text
        assert "protection_removed" in page.text
        quiet = c.get(f"/accounts/{by['other.org']['entity_id']}")
        assert "Changes" not in quiet.text
        home = c.get("/?segment=&sort=recent_change")
        assert home.status_code == 200 and "severity 3" in home.text


# ---- guards found by mutation testing ---------------------------------------------------


def test_added_protection_is_not_also_a_signal(ops: Path) -> None:
    two_files(ops, [row("a.com"), row("b.com")], [row("a.com", http_waf=WAF), row("b.com")])
    diff_mod.diff(FA, FB, detected_at=WHEN)
    assert len(of_type("protection_added")) == 1
    assert "D_waf" not in {e["subject"] for e in of_type("signal_appeared")}


def test_exposure_threshold_is_inclusive() -> None:
    from sis import db
    from sis.sqlfiles import run_sql

    con = db.connect()
    for s, exp in (("a", (50.0, 50.0, 50.0)), ("b", (60.0, 59.9, 40.0))):
        con.execute(f"""CREATE TEMP TABLE act_{s} AS SELECT * FROM (VALUES
            ('e1', 'domain', 'one.com', {exp[0]}, 'untouched'),
            ('e2', 'domain', 'two.com', {exp[1]}, 'untouched'),
            ('e3', 'domain', 'three.com', {exp[2]}, 'untouched')
            ) t(entity_id, key_kind, key_value, exposure, segment)""")
        con.execute(f"CREATE TEMP TABLE sig_{s} (entity_id VARCHAR, signal_id VARCHAR, "
                    "fact VARCHAR, value DOUBLE)")
        con.execute(f"CREATE TEMP TABLE svc_{s} (entity_id VARCHAR, skey VARCHAR, "
                    "module VARCHAR)")
        con.execute(f"CREATE TEMP TABLE evd_{s} (entity_id VARCHAR, signal_id VARCHAR, "
                    "v VARCHAR)")
    run_sql(con, diff_mod.SQL_DIR / "01_events.sql",
            fragments={"severity": diff_mod.severity_sql(delta_config.load().diff.severity)},
            threshold=10.0, from_file="x", to_file="y", detected_at="2026-11-03 12:00:00")
    got = dict(con.execute("SELECT entity_id, event_type FROM events").fetchall())
    assert got == {"e1": "exposure_up", "e3": "exposure_down"}  # +10.0 counts, +9.9 does not


def test_synthetic_file_does_not_write_operators(ops: Path, monkeypatch: pytest.MonkeyPatch,
                                                 tmp_path: Path) -> None:
    for fid in (FA, FB):
        build(banners(5), ops, file_id=fid)
    written: list[str] = []
    monkeypatch.setattr(resolve_mod, "write_operator_file",
                        lambda path, seed, derived, file_id, new: written.append(file_id))
    write_truth(paths.synth_truth_path(1), {"seed": 1, "synthetic_file_id": FB})
    resolve_mod.resolve(FB, operator_file=ops, write_report=False)
    assert written == []
    resolve_mod.resolve(FA, operator_file=ops, write_report=False)
    assert written == [FA]


def test_bundle_holds_the_latest_pair_only(ops: Path) -> None:
    import shutil

    from sis.export.bundle import export

    a = [row("walled.com", http_waf=WAF), row("plain.com")]
    two_files(ops, a, [row("walled.com"), row("plain.com")])
    build([row("walled.com", http_waf=WAF), row("plain.com", cert_expired=True)], ops,
          file_id="filec")
    diff_mod.diff(FA, "filec", detected_at=datetime(2026, 11, 1))  # the older pair
    diff_mod.diff(FA, FB, detected_at=WHEN)
    cur = paths.current_dir()
    cur.mkdir(parents=True)
    for name in ("entities.parquet", "scores.parquet"):
        shutil.copy(paths.file_dir(FA) / name, cur / name)
    res = export("t-2")
    assert res.n_events == len(events(FA, FB)) > 0
    assert len(diff_mod.read_events(FA, "filec")) > 0
    ev = pq.read_table(Path(res.path) / "events.parquet").to_pylist()
    assert {e["to_file"] for e in ev} == {FB}
