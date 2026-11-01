import hashlib
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import zstandard
from conftest import FIXTURE

from sis import db, paths
from sis.config import settings
from sis.entities import resolve as resolve_mod
from sis.entities.normalise import host_registered_domain, normalise_name, registered_domain
from sis.entities.resolve import (
    merge_current,
    read_operator_file,
    resolve,
    write_operator_file,
)
from sis.ingest import run as ingest_mod
from sis.ingest.flatten import SCHEMA
from sis.ingest.log import append_ingest_log

FID = "testfile"


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(settings, "SIS_DATA", tmp_path / "sis_data")
    monkeypatch.setattr(resolve_mod, "REPORT_DIR", tmp_path / "docs")
    ops = tmp_path / "operators.txt"
    ops.write_text("bigcdn.net\n", encoding="utf-8")
    return ops


def make_file(rows: list[dict[str, Any]], file_id: str = FID) -> str:
    """Write a banners table for `file_id`; rows give only the columns a test cares about."""
    full = []
    for i, r in enumerate(rows):
        full.append({"id": f"b{i}", "ip_str": f"10.0.0.{i}", "port": 80, "module": "http",
                     "country_code": "US", **r})
    d = paths.file_dir(file_id) / "banners"
    d.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(full, schema=SCHEMA), d / "part-00000.parquet")
    return file_id


def run(rows: list[dict[str, Any]], ops: Path, **kw: Any) -> tuple[Any, dict[str, list[Any]]]:
    make_file(rows)
    res = resolve(FID, operator_file=ops, write_back=False, write_report=False, **kw)
    out = paths.file_dir(FID)
    tables = {n: pq.read_table(out / f"{n}.parquet").to_pydict()
              for n in ("banner_entity", "entities", "unattributed_summary")}
    return res, tables


def keys(tables: dict[str, Any]) -> set[tuple[str, str]]:
    e = tables["entities"]
    return set(zip(e["key_kind"], e["key_value"], strict=True))


# ---- pure functions --------------------------------------------------------------------


def test_normalise() -> None:
    assert normalise_name("WWW.Example.COM.") == "example.com"
    assert normalise_name("1.2.3.4") is None
    assert normalise_name("localhost") is None
    assert normalise_name("2001:db8::1") is None
    assert normalise_name("a b.com") is None
    assert normalise_name("a..com") is None
    assert normalise_name(None) is None and normalise_name("") is None
    assert normalise_name("mail.example.com") == "mail.example.com"  # subdomains are kept


def test_registered_domain() -> None:
    assert registered_domain("a.b.example.co.uk") == "example.co.uk"
    assert registered_domain("*.example.com") == "example.com"
    assert registered_domain("example.com") == "example.com"
    assert registered_domain("com") is None and registered_domain("1.2.3.4") is None
    assert registered_domain(None) is None


def test_host_registered_domain_strips_ports_and_ips() -> None:
    assert host_registered_domain("shop.example.com:8080") == "example.com"
    assert host_registered_domain("10.1.1.1:80") is None
    assert host_registered_domain("[2001:db8::1]:443") is None
    assert host_registered_domain(None) is None


# ---- attribution rules -----------------------------------------------------------------


def test_cutoff_param(isolated: Path) -> None:
    rows = [{"domains": ["spread.com"], "ip_str": f"10.0.1.{i}"} for i in range(3)]
    rows += [{"domains": ["tight.com"], "ip_str": "10.0.2.1"}]
    low, t_low = run(rows, isolated, max_ips=2)
    high, t_high = run(rows, isolated, max_ips=3)
    assert keys(t_low) == {("domain", "tight.com")}  # spread.com covers 3 IPs > 2
    assert keys(t_high) == {("domain", "tight.com"), ("domain", "spread.com")}
    assert high.n_active > low.n_active
    assert low.unattributed["operator_only"] == 3 and low.operators_derived == 1


def test_cutoff_boundary_is_inclusive(isolated: Path) -> None:
    rows = [{"domains": ["edge.com"], "ip_str": f"10.0.1.{i}"} for i in range(50)]
    _, t = run(rows, isolated, max_ips=50)
    assert ("domain", "edge.com") in keys(t)
    _, t = run(rows + [{"domains": ["edge.com"], "ip_str": "10.0.9.9"}], isolated, max_ips=50)
    assert ("domain", "edge.com") not in keys(t)  # 51 IPs


def test_operator_excluded(isolated: Path) -> None:
    rows = [
        {"domains": ["bigcdn.net"]},
        {"domains": ["x.com", "bigcdn.net"]},
        {"cert_subject_cn": "edge.bigcdn.net"},
        {"http_host": "h.bigcdn.net"},
    ]
    res, t = run(rows, isolated)
    assert all(v != "bigcdn.net" for _, v in keys(t))
    assert keys(t) == {("domain", "x.com")}
    assert res.unattributed["operator_only"] == 3  # the 3 banners with nothing but bigcdn.net
    assert res.unattributed["over_cutoff"] == 0


def test_fallback_only_when_no_primary(isolated: Path) -> None:
    rows = [
        {"domains": ["acme.com"], "cert_subject_cn": "www.other.org"},  # primary wins
        {"cert_subject_cn": "www.foo.org"},  # no primary: certificate
        {"http_host": "shop.bar.net:8080"},  # no primary, no cert: http_host
        {"cert_subject_cn": "c.cert.org", "http_host": "h.host.org"},  # cert before host
        {"domains": ["bigcdn.net"], "cert_subject_cn": "x.customer.io"},  # operator rdns: cert
    ]
    _, t = run(rows, isolated)
    assert keys(t) == {("domain", "acme.com"), ("cert_cn", "foo.org"), ("http_host", "bar.net"),
                       ("cert_cn", "cert.org"), ("cert_cn", "customer.io")}
    attr = dict(zip(t["banner_entity"]["banner_id"], t["banner_entity"]["attribution"],
                    strict=True))
    assert attr == {"b0": "primary", "b1": "fallback", "b2": "fallback", "b3": "fallback",
                    "b4": "fallback"}
    assert len(t["banner_entity"]["banner_id"]) == 5  # one row each, none for other.org


def test_rekey_fallback_to_domain(isolated: Path) -> None:
    rows = [{"domains": ["x.com"]}, {"cert_subject_cn": "mail.x.com"}, {"http_host": "x.com"}]
    _, t = run(rows, isolated)
    assert keys(t) == {("domain", "x.com")}  # one entity, one id
    be = t["banner_entity"]
    assert sorted(be["attribution"]) == ["fallback", "fallback", "primary"]
    assert len(set(be["entity_id"])) == 1
    assert t["entities"]["n_banners"] == [3]


def test_wide_certificate_name_still_joins_its_domain_entity(isolated: Path) -> None:
    rows = [{"domains": ["acme.com"], "ip_str": "10.0.0.1"}]
    rows += [{"cert_subject_cn": "vpn.acme.com", "ip_str": f"10.0.1.{i}"} for i in range(4)]
    res, t = run(rows, isolated, max_ips=2)  # the certificate name covers 4 IPs, above 2
    assert keys(t) == {("domain", "acme.com")} and t["entities"]["n_banners"] == [5]
    assert res.unattributed["over_cutoff"] == 0 and res.operators_derived == 0


def test_banner_with_two_domains_feeds_two_entities(isolated: Path) -> None:
    _, t = run([{"domains": ["a.com", "b.com"]}], isolated)
    assert keys(t) == {("domain", "a.com"), ("domain", "b.com")}
    assert len(t["banner_entity"]["banner_id"]) == 2


def test_blocked(isolated: Path) -> None:
    rows = [
        {"domains": ["trap.com"], "tags": ["honeypot"]},
        {"domains": ["scan.com"], "tags": ["scanner", "cloud"]},
        {"domains": ["evil.com"], "tags": ["scanner", "c2"]},  # c2 wins
        {"domains": ["fine.com"], "tags": ["cloud"]},
        {"domains": ["mixed.com"], "tags": ["honeypot"]},
        {"domains": ["mixed.com"], "tags": None},  # one bad banner blocks the entity
    ]
    res, t = run(rows, isolated)
    status = dict(zip(t["entities"]["key_value"],
                      zip(t["entities"]["status"], t["entities"]["blocked_reason"], strict=True),
                      strict=True))
    assert status == {
        "trap.com": ("blocked", "honeypot_or_scanner"),
        "scan.com": ("blocked", "honeypot_or_scanner"),
        "evil.com": ("blocked", "c2_or_malware"),
        "fine.com": ("active", None),
        "mixed.com": ("blocked", "honeypot_or_scanner"),
    }
    assert res.n_active == 1 and res.n_blocked == 4
    assert res.unattributed["blocked"] == 5  # every banner but fine.com's


def test_entity_columns(isolated: Path) -> None:
    rows = [
        {"domains": ["acme.com"], "country_code": "US", "org": "Host A", "port": 80,
         "ip_str": "1.1.1.1"},
        {"domains": ["acme.com"], "country_code": "DE", "org": "Host A", "port": 443,
         "ip_str": "1.1.1.1", "module": "https", "cloud_provider": "AWS"},
        {"domains": ["acme.com"], "country_code": "DE", "org": "Host B", "port": 443,
         "ip_str": "1.1.1.2", "module": "https"},
        {"domains": ["acme.com"], "country_code": "FR", "org": "Host B", "port": 22,
         "ip_str": "1.1.1.3", "module": "ssh"},
    ]
    _, t = run(rows, isolated)
    e = {k: v[0] for k, v in t["entities"].items()}
    assert e["entity_id"] == hashlib.sha1(b"domain:acme.com").hexdigest()
    assert (e["n_banners"], e["n_ips"], e["n_ports"], e["n_modules"]) == (4, 3, 3, 3)
    assert e["country_code"] == "DE" and e["country_codes"] == ["DE", "FR", "US"]
    assert e["org_mode"] == "Host A"  # 2 vs 2: ties broken alphabetically
    assert e["cloud_providers"] == ["AWS"]
    assert e["display_name"] == "acme.com" and e["status"] == "active"
    assert e["blocked_reason"] is None and e["peer_group"] is None
    assert e["first_seen_file"] == e["last_seen_file"] == e["file_id"] == FID


def test_unattributed_summary_partitions_the_banners(isolated: Path) -> None:
    rows = [
        {"domains": ["ok.com"]},  # attributed
        {"domains": ["bigcdn.net"]},  # operator only
        {"domains": None},  # no name
        {"domains": ["1.2.3.4"]},  # a name that fails normalisation counts as no name
        {"domains": ["trap.com"], "tags": ["honeypot"]},  # blocked
    ]
    res, t = run(rows, isolated)
    assert res.unattributed == {"no_name": 2, "operator_only": 1, "over_cutoff": 0, "blocked": 1}
    s = t["unattributed_summary"]
    assert dict(zip(s["reason"], s["n_banners"], strict=True)) == res.unattributed
    assert s["pct"][s["reason"].index("no_name")] == pytest.approx(2 / 5)
    assert res.banners_primary == 2 and res.banners_fallback == 0 and res.banners_none == 3
    assert res.n_banners == res.banners_primary + res.banners_fallback + res.banners_none


def test_entity_id_deterministic(isolated: Path) -> None:
    rows = [{"domains": [f"d{i % 7}.com"], "ip_str": f"10.0.0.{i}"} for i in range(40)]
    rows += [{"cert_subject_cn": f"c{i}.org"} for i in range(5)]
    make_file(rows)
    out = paths.file_dir(FID)
    blobs = []
    for _ in range(2):
        resolve(FID, operator_file=isolated, write_back=False, write_report=False)
        names = ("entities.parquet", "banner_entity.parquet", "unattributed_summary.parquet")
        blobs.append({n: (out / n).read_bytes() for n in names})
    assert blobs[0] == blobs[1]


# ---- operator file ---------------------------------------------------------------------


def test_operator_file_roundtrip_and_idempotent_rerun(isolated: Path) -> None:
    rows = [{"domains": ["spread.com"], "ip_str": f"10.0.1.{i}"} for i in range(3)]
    make_file(rows)
    for _ in range(2):  # the second run must not duplicate or change anything
        resolve(FID, max_ips=2, operator_file=isolated, write_report=False)
        assert isolated.read_text(encoding="utf-8") == (
            f"bigcdn.net\n# derived from {FID}\nspread.com\n")
    seed, derived = read_operator_file(isolated)
    assert seed == ["bigcdn.net"] and derived == {FID: ["spread.com"]}


def test_other_files_derived_sections_are_kept(isolated: Path) -> None:
    write_operator_file(isolated, ["bigcdn.net"], {"older": ["x.com", "bigcdn.net"]}, "newer",
                        ["y.com", "x.com"])
    assert isolated.read_text(encoding="utf-8") == (
        "bigcdn.net\n# derived from older\nx.com\n# derived from newer\ny.com\n")


def test_shipped_operator_seed_is_intact() -> None:
    seed, _ = read_operator_file(paths.config_dir() / "operator_domains.txt")
    assert seed[:12] == ["incapdns.net", "googleusercontent.com", "amazonaws.com", "cloudfront.net",
                         "akamaitechnologies.com", "cloudflare.com", "linode.com", "vultr.com",
                         "digitalocean.com", "hetzner.com", "ovh.net", "aliyuncs.com"]


# ---- on the real fixture, through the real ingest --------------------------------------


@pytest.fixture
def ingested(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    z = tmp_path / "delivery"
    z.write_bytes(zstandard.ZstdCompressor().compress(FIXTURE.read_bytes()))
    monkeypatch.setattr(ingest_mod, "REPORT_DIR", tmp_path / "ingest_docs")
    res = ingest_mod.ingest(z, workers=1)
    assert res.status == "ok"
    return res.file_id


def test_resolve_fixture_end_to_end(ingested: str, isolated: Path) -> None:
    res = resolve(ingested, operator_file=isolated, write_back=False)
    out = paths.file_dir(ingested)
    for name in ("banner_entity", "entities", "unattributed_summary"):
        assert (out / f"{name}.parquet").exists()
    assert (resolve_mod.REPORT_DIR / f"RESOLVE_REPORT_{ingested}.md").exists()
    assert res.n_banners == 200 and res.unattributed["over_cutoff"] == 0
    assert res.n_banners == res.banners_primary + res.banners_fallback + res.banners_none
    con = db.connect()
    db.register(con, "e", (out / "entities.parquet").as_posix())
    assert con.execute("SELECT count(*) = count(DISTINCT entity_id) FROM e").fetchone() == (True,)
    assert con.execute("SELECT count(*) FROM e WHERE length(entity_id) <> 40").fetchone() == (0,)


def test_cutoff_changes_entity_count_on_the_fixture(ingested: str, isolated: Path) -> None:
    loose = resolve(ingested, max_ips=1000, operator_file=isolated, write_back=False,
                    write_report=False)
    tight = resolve(ingested, max_ips=1, operator_file=isolated, write_back=False,
                    write_report=False)
    assert loose.n_active + loose.n_blocked >= tight.n_active + tight.n_blocked
    assert loose.banners_none <= tight.banners_none


# ---- merge -----------------------------------------------------------------------------


def log_ok(file_id: str, received: datetime) -> None:
    append_ingest_log({"file_id": file_id, "status": "ok", "received_at": received})


def test_merge_current(isolated: Path) -> None:
    make_file([{"domains": ["a.com"]}, {"domains": ["only-old.com"]}], "f1")
    make_file([{"domains": ["a.com"]}, {"domains": ["a.com"]}, {"domains": ["new.com"]}], "f2")
    log_ok("f1", datetime(2026, 1, 1))
    log_ok("f2", datetime(2026, 2, 1))
    for f in ("f1", "f2"):
        resolve(f, operator_file=isolated, write_back=False, write_report=False)
    m = merge_current()
    assert m.files == ["f1", "f2"] and m.n_entities == 3  # a.com, only-old.com, new.com
    rows = {r["key_value"]: r for r in pq.read_table(m.path).to_pylist()}
    assert rows["a.com"]["first_seen_file"] == "f1" and rows["a.com"]["last_seen_file"] == "f2"
    assert rows["a.com"]["n_banners"] == 2  # counts come from the latest file only
    assert rows["only-old.com"]["last_seen_file"] == "f1"  # not deleted, just not seen again
    assert rows["new.com"]["first_seen_file"] == "f2"


def test_merge_single_file_matches_the_file(isolated: Path) -> None:
    make_file([{"domains": ["a.com"]}, {"domains": ["b.com"], "tags": ["honeypot"]}])
    log_ok(FID, datetime(2026, 1, 1))
    resolve(FID, operator_file=isolated, write_back=False, write_report=False)
    m = merge_current()
    per_file = pq.read_table(paths.file_dir(FID) / "entities.parquet")
    merged = pq.read_table(m.path)
    assert m.n_entities == per_file.num_rows == 2
    assert merged.to_pylist() == per_file.to_pylist()


def test_merge_ignores_files_not_logged_ok(isolated: Path) -> None:
    make_file([{"domains": ["a.com"]}], "f1")
    make_file([{"domains": ["z.com"]}], "f2")
    log_ok("f1", datetime(2026, 1, 1))  # f2 was never logged ok
    for f in ("f1", "f2"):
        resolve(f, operator_file=isolated, write_back=False, write_report=False)
    assert merge_current().n_entities == 1
    shutil.rmtree(paths.file_dir("f1"))
    with pytest.raises(FileNotFoundError):
        merge_current()
