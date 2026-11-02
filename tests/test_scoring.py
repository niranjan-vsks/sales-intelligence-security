import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import pytest
from p3_build import FID, build, scores_by_name, signals_by_name, table, write_file

from sis import paths, scoring_config
from sis.config import settings
from sis.entities import resolve as resolve_mod
from sis.entities.resolve import resolve
from sis.ingest.log import append_ingest_log, read_ingest_log
from sis.scoring import score as score_mod
from sis.scoring.explain import contributions
from sis.scoring.peer import bucket_label
from sis.scoring.score import merge_current, score


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(settings, "SIS_DATA", tmp_path / "sis_data")
    monkeypatch.setattr(resolve_mod, "REPORT_DIR", tmp_path / "docs")
    monkeypatch.setattr(score_mod, "REPORT_DIR", tmp_path / "docs")
    ops = tmp_path / "operators.txt"
    ops.write_text("bigcdn.net\n", encoding="utf-8")
    return ops


# ---- 3 hand-computed entities ----------------------------------------------------------
# PEER_MIN_SIZE is set above the population so every entity is in '*|*' and the percent
# ranks are over these 3 entities only.

E1 = [{"domains": ["e1.com"], "module": "https", "port": 443, "http_status": 200,
       "cpe23": ["cpe:2.3:a:x:y:1"], "http_header_names": ["a", "b"],
       "http_components": ["c1", "c2", "c3"], "ssl_versions": ["SSLv3", "TLSv1.2"],
       "cert_issued": datetime(2020, 1, 1)}]
E2 = [{"domains": ["e2.com"], "module": "ssh", "port": 22, "data_len": 100,
       "tags": ["database"], "cert_expired": True},
      {"domains": ["e2.com"], "module": "rdp", "port": 3389, "data_len": 50,
       "os": "Windows Server 2019"}]
E3 = [{"domains": ["e3.com"], "module": "https", "port": 443, "http_status": 200,
       "product": "FortiGate", "cpe23": ["cpe:2.3:h:fortinet:fortigate"],
       "http_header_names": ["strict-transport-security", "x", "y", "z"],
       "http_components": ["c1"], "cert_issued": datetime(2025, 10, 26)}]
# b0 is E1's banner: 2 clean CVEs and 1 kev CVE that must not count
VULNS = [{"id": "b0", "cve": "CVE-A", "cvss": 5.0}, {"id": "b0", "cve": "CVE-B", "cvss": 3.0},
         {"id": "b0", "cve": "CVE-K", "cvss": 10.0, "kev": True}]


def test_fact_formulas(isolated: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "PEER_MIN_SIZE", 1000)
    build(E1 + E2 + E3, isolated, VULNS)
    s = scores_by_name()
    # E1: A = cves (0.4 + 0.6 * 5.0 / 10) + 0.20 * pct(cpe/header 0.5 vs E3 0.25 -> 1)
    #     B = 0.4 legacy + 0.3 * pct(age, E1 oldest -> 1); C = 0.15 * pct(components 3 vs 1 -> 1)
    #     + 0.25 * pct(breadth 1 module, tied lowest -> 0); D = 0
    expect = {
        "e1.com": (0.7 + 0.2, 0.4 + 0.3, 0.15, 0.0, "untouched"),
        # E2: A = 0.15 os; B = 0.6 expired; C = 0.4 * 2/3 admin + 0.25 windows + 0.2 * 1/2 tags
        #     + 0.25 * pct(2 modules, highest -> 1)
        "e2.com": (0.15, 0.6, 0.4 * 2 / 3 + 0.25 + 0.1 + 0.25, 0.0, "untouched"),
        # E3: A = 0.25 fingerprinted + 0.20 * pct(0.25, lowest -> 0); B = 0.3 * pct(age, newest
        #     -> 0); C = 0; D = max(0.8 appliance, 0.3 headers)
        "e3.com": (0.25, 0.0, 0.0, 0.8, "displace"),
    }
    mult = {"untouched": 1.0, "displace": 0.6}
    for name, (a, b, c, d, seg) in expect.items():
        r = s[name]
        assert r["fact_a"] == pytest.approx(a, abs=1e-9), name
        assert r["fact_b"] == pytest.approx(b, abs=1e-9), name
        assert r["fact_c"] == pytest.approx(c, abs=1e-9), name
        assert r["fact_d"] == pytest.approx(d, abs=1e-9), name
        assert r["segment"] == seg
        exposure = 100 * (0.45 * a + 0.20 * b + 0.35 * c)
        assert r["exposure"] == pytest.approx(exposure, abs=1e-9), name
        assert r["priority"] == pytest.approx(exposure * mult[seg], abs=1e-9), name
    assert [s[n]["rank_overall"] for n in ("e1.com", "e2.com", "e3.com")] == [1, 2, 3]
    # contributions 31.5, 9, 8, 6, 5.25; A_fingerprinted (0.25) loses the max() to the CVEs
    assert s["e1.com"]["top_signals"] == ["A_inferred_cves", "A_cpe_per_header", "B_legacy_tls",
                                          "B_cert_age_days", "C_components_vs_peers"]
    assert s["e1.com"]["scoring_version"] == scoring_config.load().scoring_version


def test_contributions_explain_top_signals(isolated: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "PEER_MIN_SIZE", 1000)
    build(E1 + E2 + E3, isolated, VULNS)
    for row in table("scores"):
        c = contributions(row["entity_id"], FID)
        assert [sid for sid, _ in c][:5] == row["top_signals"]
        if row["segment"] != "displace":
            # with no clip active, contributions add up to exposure
            assert sum(v for _, v in c) == pytest.approx(row["exposure"], abs=1e-9)
    e2 = next(r for r in table("entities") if r["key_value"] == "e2.com")
    c2 = dict(contributions(e2["entity_id"], FID))
    assert c2["C_admin_services"] == pytest.approx(100 * 0.35 * 0.4 * 2 / 3)
    assert not any(sid.startswith("D_") for sid in c2)


def test_segments(isolated: Path) -> None:
    rows = [
        {"domains": ["untouched.com"], "module": "https", "http_status": 200},
        {"domains": ["partial.com"], "module": "https", "http_status": 200,
         "http_waf": "Fastly (Fastly CDN)"},
        {"domains": ["displace.com"], "module": "https", "http_status": 200,
         "http_waf": "Cloudflare (Cloudflare Inc.)"},
        {"domains": ["low.com"], "module": "snmp", "port": 161},
        {"domains": ["trap.com"], "tags": ["honeypot"], "http_status": 200},
    ]
    build(rows, isolated)
    s = scores_by_name()
    assert {n: r["segment"] for n, r in s.items()} == {
        "untouched.com": "untouched", "partial.com": "partially_covered",
        "displace.com": "displace", "low.com": "low_surface"}  # blocked trap.com not scored
    assert s["partial.com"]["fact_d"] == 0.5 and s["displace.com"]["fact_d"] == 1.0


def test_edge_only_entity(isolated: Path) -> None:
    """cards/P3.md: an entity whose banners are all edge banners gets fact_a = fact_b = 0,
    fact_c = 0 (C_live_web fires but has no weight in fact_c), fact_d = 1, segment displace."""
    edge = {"domains": ["tenant.com"], "module": "https", "port": 443, "http_status": 200,
            "http_waf": "Incapsula (Imperva Inc.)", "cpe23": ["cpe:2.3:a:imperva:x"],
            "os": "Linux", "tags": ["eol-product"], "cert_expired": True,
            "cert_issued": datetime(2001, 1, 1)}
    cdn = {"domains": ["tenant.com"], "module": "rdp", "port": 3389, "data_len": 10,
           "tags": ["cdn", "database"], "blocks": ["ntlm"]}
    other = [{"domains": [f"o{i}.com"], "module": "ssh", "port": 22 + i, "data_len": 5}
             for i in range(3)]
    build([edge, {**edge, "port": 8443}, cdn] + other, isolated)
    r = scores_by_name()["tenant.com"]
    assert (r["fact_a"], r["fact_b"], r["fact_c"], r["fact_d"]) == (0, 0, 0, 1)
    assert r["segment"] == "displace" and r["exposure"] == 0
    assert "C_live_web" in signals_by_name()["tenant.com"]


def test_peer_fallback(isolated: Path) -> None:
    us = [{"domains": [f"us{i}.com"], "country_code": "US"} for i in range(30)]
    de = [{"domains": [f"de{i}.de"], "country_code": "DE"} for i in range(5)]
    nocc = [{"domains": ["none.com"], "country_code": None}]
    wide = [{"domains": ["wide.com"], "module": m, "port": p}
            for m, p in (("http", 80), ("ssh", 22), ("ftp", 21), ("smtp", 25))]
    build(us + de + nocc + wide, isolated)
    groups = {e["key_value"]: e["peer_group"] for e in table("entities")}
    assert groups["us0.com"] == "US|1"
    assert groups["de0.de"] == "*|1"  # 5 DE entities < PEER_MIN_SIZE 30
    assert groups["none.com"] == "*|1"
    assert groups["wide.com"] == "*|*"  # bucket 4-9 holds 1 entity
    assert bucket_label(4, 9) == "4-9" and bucket_label(10, None) == "10+"


def test_peer_pct_uses_the_whole_bucket_for_fallbacks(isolated: Path,
                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "PEER_MIN_SIZE", 3)
    rows = [{"domains": [f"us{i}.com"], "country_code": "US", "port": 80 + p}
            for i in range(3) for p in range(i + 1)]  # 1, 2, 3 ports
    rows += [{"domains": ["de.de"], "country_code": "DE", "port": 80 + p} for p in range(4)]
    build(rows, isolated)
    s = signals_by_name()
    assert s["us2.com"]["C_breadth_ports"]["pct_in_peer"] == 1.0  # top of US|1 (3 entities)
    # de.de alone in DE falls back to *|1 and is ranked against all 4 bucket-1 entities
    assert s["de.de"]["C_breadth_ports"]["pct_in_peer"] == 1.0
    assert s["us2.com"]["C_breadth_ports"]["value"] == 3


def test_rank_deterministic(isolated: Path) -> None:
    rows = [{"domains": [f"d{i % 9}.com"], "module": ["http", "ssh", "ftp"][i % 3],
             "port": 20 + i % 5, "data_len": i, "os": "Linux" if i % 2 else None}
            for i in range(60)]
    write_file(rows)
    resolve(FID, operator_file=isolated, write_back=False, write_report=False)
    out = paths.file_dir(FID)
    blobs = []
    for _ in range(2):
        score(FID, write_report=False)
        blobs.append({n: (out / n).read_bytes() for n in (
            "scores.parquet", "signals.parquet", "evidence.parquet", "entities.parquet")})
    assert blobs[0] == blobs[1]
    ranks = sorted(r["rank_overall"] for r in table("scores"))
    assert ranks == list(range(1, len(ranks) + 1))


def test_score_report_and_meta(isolated: Path) -> None:
    rows = [{"domains": [f"r{i}.com"], "module": "https", "http_status": 200, "port": 443}
            for i in range(12)]
    res = build(rows, isolated, write_report=True)
    report = score_mod.REPORT_DIR / f"SCORE_REPORT_{FID}.md"
    text = report.read_text(encoding="utf-8")
    assert "## Segments" in text and "random untouched entities" in text
    meta = json.loads((paths.file_dir(FID) / "score_meta.json").read_text(encoding="utf-8"))
    assert meta["stage1_target_group"] == res.stage1_target_group == 12
    assert res.segments == {"untouched": 12}


def log_ok(file_id: str, received: datetime) -> None:
    append_ingest_log({"file_id": file_id, "status": "ok", "received_at": received})


def test_merge_current(isolated: Path) -> None:
    build([{"domains": ["a.com"]}, {"domains": ["old.com"], "os": "Linux"}], isolated,
          file_id="f1")
    build([{"domains": ["a.com"], "os": "Linux", "http_status": 200}, {"domains": ["new.com"]}],
          isolated, file_id="f2")
    log_ok("f1", datetime(2026, 1, 1))
    log_ok("f2", datetime(2026, 2, 1))
    assert read_ingest_log().num_rows == 2
    m = merge_current()
    assert m.files == ["f1", "f2"] and m.n_scores == 3
    rows: dict[str, Any] = {}
    names = {**{e["entity_id"]: e["key_value"] for e in table("entities", "f1")},
             **{e["entity_id"]: e["key_value"] for e in table("entities", "f2")}}
    for r in pq.read_table(m.path).to_pylist():
        rows[names[r["entity_id"]]] = r
    assert rows["a.com"]["file_id"] == "f2"  # the latest file's score
    assert rows["old.com"]["file_id"] == "f1"  # kept, not deleted
    assert sorted(r["rank_overall"] for r in rows.values()) == [1, 2, 3]
    assert rows["a.com"]["rank_overall"] == 1  # untouched with os leak beats the rest


# ---- sanity assertions on the real output (cards/P3.md step 13) ------------------------

def _real() -> Path | None:
    from sis.config import Settings

    root = Settings().SIS_DATA
    for d in sorted(root.glob("*-*")) if root.exists() else []:
        if (d / "scores.parquet").exists() and (d / "score_meta.json").exists():
            return d
    return None


REAL = _real()
real_only = pytest.mark.skipif(REAL is None, reason="no scored real file under SIS_DATA")


@real_only
def test_real_output_sanity() -> None:
    import duckdb

    assert REAL is not None
    con = duckdb.connect()
    sc, sg = (REAL / "scores.parquet").as_posix(), (REAL / "signals.parquet").as_posix()
    ent = (REAL / "entities.parquet").as_posix()
    bad = con.execute(f"""SELECT
        count(*) FILTER (WHERE exposure < 0 OR exposure > 100),
        count(*) FILTER (WHERE least(fact_a, fact_b, fact_c, fact_d) < 0
                            OR greatest(fact_a, fact_b, fact_c, fact_d) > 1),
        count(*) - (SELECT count(*) FROM read_parquet('{ent}') WHERE status = 'active')
        FROM read_parquet('{sc}')""").fetchall()[0]
    assert bad == (0, 0, 0)
    # displace: 100 % have D_waf or D_security_appliance; untouched: 0 % have any D signal
    rates = con.execute(f"""
        WITH d AS (
            SELECT entity_id, bool_or(signal_id IN ('D_waf', 'D_security_appliance')) AS main,
                   bool_or(fact = 'D') AS any_d
            FROM read_parquet('{sg}') GROUP BY 1)
        SELECT avg(coalesce(main, false)::INT) FILTER (WHERE segment = 'displace'),
               avg(coalesce(any_d, false)::INT) FILTER (WHERE segment = 'untouched')
        FROM read_parquet('{sc}') LEFT JOIN d USING (entity_id)""").fetchall()[0]
    assert rates == (1.0, 0.0)
    meta = json.loads((REAL / "score_meta.json").read_text(encoding="utf-8"))
    target = meta["stage1_target_group"]
    assert abs(target - 131_104) / 131_104 <= 0.05, target
