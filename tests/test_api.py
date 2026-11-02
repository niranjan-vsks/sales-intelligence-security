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


def test_pages(client: TestClient) -> None:
    home = client.get("/")
    assert home.status_code == 200 and "alpha.com" in home.text
    assert "walled.com" not in home.text  # default segment filter: untouched
    assert "test-1.1.0" in home.text and "ROLLUP_MAX_IPS 50" in home.text
    every = client.get("/?segment=&min_exposure=&q=")
    assert every.status_code == 200 and "walled.com" in every.text
    rows = client.get("/?segment=", headers={"HX-Request": "true"})
    assert "<table>" in rows.text and "<form" not in rows.text  # the partial only
    assert client.get("/?segment=nope").status_code == 422
    eid = client.get("/api/accounts?q=walled").json()["items"][0]["entity_id"]
    page = client.get(f"/accounts/{eid}")
    assert page.status_code == 200
    for section in ("Why", "Evidence", "Protection present", "Mark prospect", "Not a fit"):
        assert section in page.text
    assert "Cloudflare (Cloudflare Inc.)" in page.text
    about = client.get("/about")
    assert about.status_code == 200 and "How we know it works" in about.text
    assert "Hosting and cost" not in about.text  # section 9 is not on the About page
