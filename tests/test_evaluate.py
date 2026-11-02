"""P4 pipeline tests on a synthetic file: labels, the ablation override, the rescoring
identity guard and the artefacts `sis evaluate` writes."""

import json
from pathlib import Path

import pyarrow.parquet as pq
import pytest
from p3_build import FID, build

from sis import paths, scoring_config
from sis.config import settings
from sis.entities import resolve as resolve_mod
from sis.evaluate import ablation
from sis.evaluate import run as run_mod
from sis.evaluate.ablation import override
from sis.evaluate.metrics import ALL_LABELS
from sis.evaluate.run import run
from sis.scoring import score as score_mod

WEB = {"module": "https", "port": 443, "http_status": 200}
ROWS = [
    {**WEB, "domains": ["kev.com"], "cpe23": ["cpe:2.3:a:x:y:1"]},          # b0
    {**WEB, "domains": ["ver.com"]},                                         # b1
    {**WEB, "domains": ["hb.com"], "opts_heartbleed": "2026/10/26 - VULNERABLE"},  # b2
    {**WEB, "domains": ["safe.com"], "opts_heartbleed": "2026/10/26 - SAFE"},      # b3
    {**WEB, "domains": ["ov.com"], "opts_vulns": ["CVE-2020-0796"]},         # b4
    {**WEB, "domains": ["waf.com"], "http_waf": "Cloudflare (Cloudflare Inc.)"},  # b5
    {**WEB, "domains": ["plain.com"]},                                       # b6
    {**WEB, "opts_vulns": ["MS17-010"]},                                     # b7: no entity
    {**WEB, "domains": ["trap.com"], "tags": ["honeypot"],
     "opts_vulns": ["MS17-010"]},                                            # b8: blocked
]
VULNS = [
    {"id": "b0", "cve": "CVE-K", "cvss": 9.8, "kev": True,
     "other_keys": json.dumps({"ransomware_campaign": "Known"})},
    {"id": "b0", "cve": "CVE-C", "cvss": 5.0},
    {"id": "b1", "cve": "CVE-V", "cvss": 7.5, "verified": True},
    {"id": "b6", "cve": "CVE-U", "cvss": 6.0, "kev": True,
     "other_keys": json.dumps({"ransomware_campaign": "Unknown"})},
    {"id": "b7", "cve": "CVE-N", "cvss": 9.0, "kev": True, "verified": True},
]


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(settings, "SIS_DATA", tmp_path / "sis_data")
    for mod in (resolve_mod, score_mod, run_mod):
        monkeypatch.setattr(mod, "REPORT_DIR", tmp_path / "docs")
    ops = tmp_path / "operators.txt"
    ops.write_text("bigcdn.net\n", encoding="utf-8")
    build(ROWS, ops, VULNS)
    return tmp_path


def _labels_by_name() -> dict[str, dict[str, bool]]:
    d = paths.file_dir(FID)
    names = {e["entity_id"]: e["key_value"]
             for e in pq.read_table(d / "entities.parquet").to_pylist()}
    return {names[r.pop("entity_id")]: r
            for r in pq.read_table(paths.eval_dir(FID) / "labels.parquet").to_pylist()}


def test_labels() -> None:
    run(FID)
    lab = _labels_by_name()
    assert set(lab) == {"kev.com", "ver.com", "hb.com", "safe.com", "ov.com", "waf.com",
                        "plain.com"}  # active entities only: trap.com is blocked
    on = {name: {k for k, v in row.items() if v} for name, row in lab.items()}
    assert on == {
        "kev.com": {"label_kev", "label_ransomware"},
        "ver.com": {"label_verified", "label_any_tested"},
        "hb.com": {"label_heartbleed", "label_any_tested"},
        "safe.com": set(),
        "ov.com": {"label_opts_vulns", "label_any_tested"},
        "waf.com": {"label_has_vendor"},
        "plain.com": {"label_kev"},  # ransomware 'Unknown' is not a ransomware label
    }


def test_override_leaves_yaml_alone() -> None:
    cfg = scoring_config.load()
    no_a = override(cfg, "a")
    assert no_a.exposure.weights == pytest.approx({"a": 0.0, "b": 0.20 / 0.55, "c": 0.35 / 0.55})
    assert no_a.segments.multipliers == cfg.segments.multipliers
    no_d = override(cfg, "d")
    assert set(no_d.segments.multipliers.values()) == {cfg.segments.multipliers["untouched"]}
    assert no_d.exposure.weights == cfg.exposure.weights
    assert no_a.scoring_version == f"{cfg.scoring_version}+no_A"
    assert scoring_config.load() == cfg
    with pytest.raises(ValueError):
        override(cfg, "x")


def test_run_writes_artefacts(isolated: Path) -> None:
    res = run(FID)
    out = paths.eval_dir(FID)
    metrics = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
    assert {"labels", "by_priority", "by_exposure", "untouched_only"} <= set(metrics)
    assert metrics["n_active"] == 7 and set(metrics["by_priority"]) == set(ALL_LABELS)
    assert metrics["labels"]["label_any_tested"]["n_pos"] == 3
    assert metrics["sanity"]["displace_has_vendor_is_1"] is True
    abl = json.loads((out / "ablations.json").read_text(encoding="utf-8"))
    assert set(abl["ablations"]) == {"no_A", "no_B", "no_C", "no_D"}
    assert abl["identity_check"]["max_abs_diff"] == 0.0
    base = json.loads((out / "baselines.json").read_text(encoding="utf-8"))
    # with k above the population every ranking's precision is the base rate
    rnd = base["random"]["mean"]["all"]["label_any_tested"]["at_k"]["100"]
    assert rnd["precision"] == pytest.approx(3 / 7) and len(base["random"]["draws"]) == 5
    text = Path(res.report).read_text(encoding="utf-8")
    for lab in ALL_LABELS:
        assert f"### {lab}" in text
    assert res.fixture is None and not (isolated / "tests").exists()


def test_ablation_refuses_a_drifted_rescore(monkeypatch: pytest.MonkeyPatch) -> None:
    drifted = override(scoring_config.load(), "a")  # kev.com has fact_a > 0
    monkeypatch.setattr(ablation.scoring_config, "load", lambda: drifted)
    with pytest.raises(RuntimeError, match="does not reproduce"):
        run(FID)
