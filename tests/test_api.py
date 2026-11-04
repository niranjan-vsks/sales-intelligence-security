"""P5: the JSON API and pages over a bundle exported from a synthetic scored file."""

import json
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from p3_build import FID, build

from sis import paths
from sis.api.app import create_app
from sis.config import settings
from sis.entities import resolve as resolve_mod
from sis.export.bundle import export
from sis.scoring import score as score_mod
from sis.signals.catalogue import BY_ID

WEB = {"module": "https", "port": 443, "http_status": 200}
ROWS = [
    {**WEB, "domains": ["alpha.com"], "tags": ["eol-product"], "cert_expired": True},
    {**WEB, "domains": ["alpha.com"], "module": "ssh", "port": 22, "data_len": 40},
    {**WEB, "domains": ["bravo.com"], "cpe23": ["cpe:2.3:a:x:y:1"]},
    {**WEB, "domains": ["charlie.org"]},
    {**WEB, "domains": ["walled.com"], "http_waf": "Cloudflare (Cloudflare Inc.)"},
    {**WEB, "domains": ["fronted.com"], "http_waf": "Fastly (Fastly CDN)"},
    {"domains": ["quiet.net"], "module": "auto", "data_len": 0, "country_code": "DE"},
    {**WEB, "domains": ["deutsch.de"], "country_code": "DE", "os": "Windows Server 2012"},
]


@pytest.fixture
def bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(settings, "SIS_DATA", tmp_path / "sis_data")
    for mod in (resolve_mod, score_mod):
        monkeypatch.setattr(mod, "REPORT_DIR", tmp_path / "docs")
    ops = tmp_path / "operators.txt"
    ops.write_text("bigcdn.net\n", encoding="utf-8")
    build(ROWS, ops)
    cur = paths.current_dir()
    cur.mkdir(parents=True)
    for name in ("entities.parquet", "scores.parquet"):  # what `--merge` gives for 1 file
        shutil.copy(paths.file_dir(FID) / name, cur / name)
    res = export("test-1.1.0")
    return Path(res.path)


@pytest.fixture
def client(bundle: Path) -> Iterator[TestClient]:
    with TestClient(create_app(bundle)) as c:
        yield c


def test_export_bundle(bundle: Path) -> None:
    meta = json.loads((bundle / "bundle.json").read_text(encoding="utf-8"))
    assert meta["bundle_version"] == "test-1.1.0" and meta["n_accounts"] == len(ROWS) - 1
    assert meta["file_ids"] == [FID]
    assert {p.name for p in bundle.iterdir()} == {
        "accounts.parquet", "evidence.parquet", "events.parquet", "signals.parquet",
        "bundle.json"}


def test_health(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "bundle_version": "test-1.1.0", "n_accounts": 7}


def test_accounts_default_sort(client: TestClient) -> None:
    items = client.get("/api/accounts").json()["items"]
    assert len(items) == 7
    prio = [a["priority"] for a in items]
    assert prio == sorted(prio, reverse=True)
    assert [a["rank_overall"] for a in items] == sorted(a["rank_overall"] for a in items)
    meta = client.get("/api/accounts?page_size=2&page=2").json()["meta"]
    assert meta == {"page": 2, "page_size": 2, "total": 7, "sort": "priority"}


def test_accounts_filters_and_422(client: TestClient) -> None:
    def names(qs: str) -> set[str]:
        r = client.get(f"/api/accounts?{qs}")
        assert r.status_code == 200, r.text
        return {a["display_name"] for a in r.json()["items"]}

    assert names("segment=displace") == {"walled.com"}
    assert names("segment=partially_covered") == {"fronted.com"}
    assert names("segment=low_surface") == {"quiet.net"}
    assert names("country=DE") == {"quiet.net", "deutsch.de"}
    assert names("country=DE&segment=untouched") == {"deutsch.de"}  # filters AND
    assert names("q=ALP") == {"alpha.com"}  # contains, case insensitive
    assert names("q=.org") == {"charlie.org"}
    assert names("q=%25") == set()  # a literal %, not a wildcard
    top = client.get("/api/accounts?sort=exposure").json()["items"]
    assert [a["exposure"] for a in top] == sorted((a["exposure"] for a in top), reverse=True)
    for bad in ("sort=name", "segment=nope", "page_size=201", "page=0", "min_exposure=101"):
        assert client.get(f"/api/accounts?{bad}").status_code == 422, bad


def test_q_is_parameterised(client: TestClient) -> None:
    r = client.get("/api/accounts", params={"q": "'; drop table x; --"})
    assert r.status_code == 200 and r.json()["items"] == []
    assert client.get("/api/health").json()["n_accounts"] == 7


def test_account_detail_shape(client: TestClient) -> None:
    first = client.get("/api/accounts?q=alpha").json()["items"][0]
    d = client.get(f"/api/accounts/{first['entity_id']}").json()
    assert d["display_name"] == "alpha.com" and d["segment"] == "untouched"
    assert {s["signal_id"] for s in d["signals"]} >= {"A_eol", "B_expired", "C_admin_services",
                                                      "C_any_service"}
    assert all(s["label"] for s in d["signals"])
    by_id = {s["signal_id"]: s for s in d["signals"]}
    assert by_id["A_eol"]["contribution"] > 0 and by_id["C_any_service"]["contribution"] is None
    assert d["evidence"]["C_admin_services"][0]["port"] == 22
    assert set(d["evidence"]) <= set(by_id)
    assert d["events"] == [] and d["profile"] is None
    assert client.get("/api/accounts/nope").status_code == 404


def test_feedback_appends(client: TestClient, bundle: Path) -> None:
    eid = client.get("/api/accounts").json()["items"][0]["entity_id"]
    r = client.post("/api/feedback", json={"entity_id": eid, "verdict": "prospect"})
    assert r.status_code == 200 and r.json()["n_feedback"] == 1
    r = client.post("/api/feedback", json={"entity_id": eid, "verdict": "not_fit", "note": "isp"})
    assert r.json()["n_feedback"] == 2
    lines = (bundle / "feedback.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(x)["verdict"] for x in lines] == ["prospect", "not_fit"]
    assert json.loads(lines[1])["bundle_version"] == "test-1.1.0"
    assert client.post("/api/feedback", json={"entity_id": eid, "verdict": "maybe"}
                       ).status_code == 422
    assert client.post("/api/feedback", json={"entity_id": "nope", "verdict": "prospect"}
                       ).status_code == 404
    r = client.post("/ui/feedback", data={"entity_id": eid, "verdict": "not_fit"})
    assert r.status_code == 200 and "not a fit" in r.text
    assert len((bundle / "feedback.jsonl").read_text(encoding="utf-8").splitlines()) == 3


def test_stats(client: TestClient) -> None:
    s = client.get("/api/stats").json()
    assert sum(s["segments"].values()) == 7 and s["countries_top20"]["DE"] == 2
    assert s["bundle"]["bundle_version"] == "test-1.1.0"
    hist = s["exposure_hist"]
    assert len(hist) == 10 and sum(hist) == 7 and all(isinstance(n, int) for n in hist)
    items = client.get("/api/accounts?page_size=200").json()["items"]
    assert hist[9] == sum(a["exposure"] >= 90 for a in items)
    assert hist[0] == sum(a["exposure"] < 10 for a in items)
    fires = s["signal_fire_counts"]
    assert fires and set(fires) <= set(BY_ID)
    assert all(1 <= n <= 7 for n in fires.values())
    assert list(fires.values()) == sorted(fires.values(), reverse=True)
    assert fires["C_admin_services"] == 1  # alpha.com's ssh
    assert client.get("/api/stats").json() == s  # cached aggregates give the same answer


def test_pages(client: TestClient) -> None:
    home = client.get("/")
    assert home.status_code == 200
    for tile in ("Active accounts", "Untouched", "Has a vendor", "Changes",
                 "No earlier delivery to compare"):  # the test bundle has no delta
        assert tile in home.text
    assert "alpha.com" in home.text  # "Start here": untouched accounts only
    assert "walled.com" not in home.text
    assert "test-1.1.0" in home.text and "ROLLUP_MAX_IPS 50" in home.text
    listing = client.get("/accounts")
    assert listing.status_code == 200 and "alpha.com" in listing.text
    assert "walled.com" not in listing.text  # default segment filter: untouched
    every = client.get("/accounts?segment=&min_exposure=&q=")
    assert every.status_code == 200 and "walled.com" in every.text
    two = client.get("/accounts?segment=&segment=displace&segment=partially_covered")
    assert "walled.com" in two.text and "fronted.com" in two.text
    assert "alpha.com" not in two.text  # chips: segments compose with OR
    rows = client.get("/accounts?segment=", headers={"HX-Request": "true"})
    assert "<table" in rows.text and "<form" not in rows.text  # the partial only
    assert client.get("/accounts?segment=nope").status_code == 422
    assert client.get("/accounts?min_exposure=101").status_code == 422
    eid = client.get("/api/accounts?q=walled").json()["items"][0]["entity_id"]
    page = client.get(f"/accounts/{eid}")
    assert page.status_code == 200
    for section in ("Why it ranks here", "The 4 facts", "Protection", "Mark as prospect",
                    "Not a fit", "Technical details"):
        assert section in page.text
    assert "Behind Cloudflare (Cloudflare Inc.)" in page.text
    alpha = client.get("/api/accounts?q=alpha").json()["items"][0]["entity_id"]
    text = client.get(f"/accounts/{alpha}").text
    assert "Show evidence" in text and "A TLS certificate has expired" in text
    readable, _, tech = text.partition("Technical details")
    assert not any(sid in readable for sid in BY_ID)  # signal ids only in the collapsed block
    assert "B_expired" in tech
    about = client.get("/about")
    assert about.status_code == 200 and "About this tool" in about.text
    assert "The 4 segments" in about.text and "Hosting and cost" not in about.text  # docs/ABOUT.md
    assert "github.com/niranjan-vsks/sales-intelligence-security" in about.text
