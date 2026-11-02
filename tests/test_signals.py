import re
from datetime import datetime
from pathlib import Path

import pytest
from p3_build import build, signals_by_name, table

from sis import paths
from sis.config import settings
from sis.entities import resolve as resolve_mod
from sis.scoring import score as score_mod
from sis.signals.catalogue import SIGNALS, load_mappings


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(settings, "SIS_DATA", tmp_path / "sis_data")
    monkeypatch.setattr(resolve_mod, "REPORT_DIR", tmp_path / "docs")
    monkeypatch.setattr(score_mod, "REPORT_DIR", tmp_path / "docs")
    ops = tmp_path / "operators.txt"
    ops.write_text("bigcdn.net\n", encoding="utf-8")
    return ops


def data_model_signal_ids() -> list[str]:
    """signal_id column of the catalogue table in DATA_MODEL.md 3.1."""
    text = (paths.REPO_ROOT / "DATA_MODEL.md").read_text(encoding="utf-8")
    section = text.split("### 3.1")[1].split("### 3.2")[0]
    return re.findall(r"^\| ([ABCDX]_\w+) \|", section, flags=re.M)


def test_catalogue_matches_data_model() -> None:
    ids = data_model_signal_ids()
    # the card says 22; the DATA_MODEL table lists 23 (6 A, 4 B, 7 C, 5 D, 1 X)
    assert len(ids) == 23
    assert [s.signal_id for s in SIGNALS] == ids
    for s in SIGNALS:
        assert s.signal_id[0] == s.fact
    assert {s.signal_id for s in SIGNALS if s.edge_ok} == {"D_waf", "D_edge_substitute",
                                                           "C_live_web"}


def test_mapping_file_is_the_explorer_copy() -> None:
    shipped = (paths.config_dir() / "what_we_sell_map.csv").read_bytes()
    assert shipped == (paths.REPO_ROOT / "findings" / "07_what_we_sell_map.csv").read_bytes()
    assert {"W01", "W07", "P01", "P03", "B01", "B02"} <= set(load_mappings())


def vuln(banner: str, cve: str, cvss: float, kev: bool | None = None,
         verified: bool = False) -> dict[str, object]:
    return {"id": banner, "cve": cve, "cvss": cvss, "kev": kev, "verified": verified}


def test_heldout_excluded(isolated: Path) -> None:
    rows = [{"domains": ["kevonly.com"]}, {"domains": ["verified.com"]},
            {"domains": ["mixed.com"]}]
    vulns = [vuln("b0", "CVE-1", 9.8, kev=True), vuln("b0", "CVE-2", 7.5, kev=True),
             vuln("b1", "CVE-3", 9.0, verified=True),
             vuln("b2", "CVE-4", 10.0, kev=True), vuln("b2", "CVE-5", 5.0, kev=False),
             vuln("b2", "CVE-6", 4.0)]
    rows[0]["n_vulns"], rows[0]["max_cvss"] = 2, 9.8  # the banner row's own counts are ignored
    build(rows, isolated, vulns)
    s = signals_by_name()
    for name in ("kevonly.com", "verified.com"):
        assert "A_inferred_cves" not in s[name] and "A_max_cvss" not in s[name]
    assert s["mixed.com"]["A_inferred_cves"]["value"] == 2  # CVE-5, CVE-6
    assert s["mixed.com"]["A_max_cvss"]["value"] == 5.0  # not the kev 10.0
    ev = [e for e in table("evidence") if e["signal_id"] == "A_inferred_cves"]
    assert len(ev) == 1 and "CVE-4" not in ev[0]["value"] and "CVE-5" in ev[0]["value"]


@pytest.mark.parametrize("versions, ssl_version, fires", [
    (["-SSLv3", "TLSv1.2"], None, False),
    (["SSLv3"], None, True),
    (["-TLSv1", "TLSv1.1", "TLSv1.2"], None, False),
    (["TLSv1", "TLSv1.2"], None, True),
    (None, "TLSv1.0", True),
    (None, "TLSv1.3", False),
])
def test_legacy_tls_parsing(isolated: Path, versions: list[str] | None, ssl_version: str | None,
                            fires: bool) -> None:
    build([{"domains": ["t.com"], "ssl_versions": versions, "ssl_version": ssl_version,
            "module": "https", "port": 443}], isolated)
    assert ("B_legacy_tls" in signals_by_name()["t.com"]) is fires


def test_signal_values(isolated: Path) -> None:
    rows = [
        {"domains": ["v.com"], "module": "ssh", "port": 22, "data_len": 40,
         "tags": ["database", "devops"]},
        {"domains": ["v.com"], "module": "ssh", "port": 2222, "data_len": 40},
        {"domains": ["v.com"], "module": "ftp", "port": 21, "data_len": 0},  # no payload: no
        {"domains": ["v.com"], "module": "https", "port": 443, "http_status": 200,
         "cpe23": ["cpe:a", "cpe:b"], "http_header_names": ["a", "b", "c", "d"],
         "http_components": ["x", "y", "z"], "tags": ["iot"],
         "cert_issued": datetime(1995, 1, 1), "cert_expired": True},
        {"domains": ["v.com"], "module": "https", "port": 8443,
         "cert_issued": datetime(2027, 1, 1)},  # issued after the scan: clipped to 0
        {"domains": ["v.com"], "module": "smb", "port": 445, "data_len": 10,
         "blocks": ["ntlm"], "cloud_provider": "Vultr"},
    ]
    build(rows, isolated)
    s = {k: v["value"] for k, v in signals_by_name()["v.com"].items()}
    assert s["C_admin_services"] == 2  # ssh, smb
    assert s["C_asset_tags"] == 3  # database, devops, iot
    assert s["A_cpe_per_header"] == 0.5 and s["A_fingerprinted"] == 1
    assert s["C_components_vs_peers"] == 3
    assert s["B_cert_age_days"] == 7300  # 1995 -> 2026 is over 20 years: clipped
    assert s["B_expired"] == 1 and s["C_windows_internals"] == 1 and s["X_small_cloud"] == 1
    assert s["C_breadth_modules"] == 4 and s["C_breadth_ports"] == 6
    assert s["C_live_web"] == 1
    for absent in ("A_eol", "A_os_leak", "B_self_signed", "D_waf", "D_vpn"):
        assert absent not in s


def test_flags_have_no_pct_and_counts_do(isolated: Path) -> None:
    rows = [{"domains": [f"e{i}.com"], "os": "Linux", "port": 80 + i} for i in range(3)]
    build(rows, isolated)
    for sig in table("signals"):
        if sig["signal_id"] == "A_os_leak":
            assert sig["pct_in_peer"] is None
        if sig["signal_id"] == "C_breadth_ports":
            assert sig["pct_in_peer"] == 0.0  # all tied


def test_evidence_cap(isolated: Path) -> None:
    rows = [{"domains": ["big.com"], "os": "Linux", "port": 1000 + i, "data_len": i,
             "data": f"line one\r\nline {i}"} for i in range(20)]
    build(rows, isolated)
    ev = [e for e in table("evidence") if e["signal_id"] == "A_os_leak"]
    assert len(ev) == 5
    assert [e["port"] for e in ev] == [1019, 1018, 1017, 1016, 1015]  # largest data_len first
    assert ev[0]["snippet"] == "line one | line 19" and ev[0]["value"] == "Linux"
    assert ev[0]["field"] == "os" and ev[0]["ip"] is not None
    counts: dict[str, int] = {}
    for e in table("evidence"):
        counts[e["signal_id"]] = counts.get(e["signal_id"], 0) + 1
    assert max(counts.values()) == 5
    sig = {s["signal_id"]: s for s in table("signals")}
    assert sig["A_os_leak"]["n_banners"] == 20  # the count is uncapped, only evidence is capped


def test_edge_banners_feed_only_protection_and_live_web(isolated: Path) -> None:
    edge = {"domains": ["tenant.com"], "module": "https", "port": 443, "http_status": 200,
            "http_waf": "Incapsula (Imperva Inc.)", "cpe23": ["cpe:2.3:a:imperva:incapsula"],
            "os": "Linux", "cert_expired": True, "cert_self_signed": True,
            "product": "FortiGate", "tags": ["vpn"]}
    cdn = {"domains": ["tenant.com"], "module": "ssh", "port": 22, "data_len": 50,
           "tags": ["cdn", "eol-product"], "http_header_names": ["strict-transport-security"]}
    build([edge, cdn, {**edge, "port": 8443}], isolated)
    s = signals_by_name()["tenant.com"]
    assert set(s) == {"D_waf", "C_live_web", "C_breadth_modules", "C_breadth_ports"}
    assert s["C_breadth_modules"]["value"] == 0 and s["C_breadth_modules"]["n_banners"] == 0
