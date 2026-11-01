import copy
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError
from typer.testing import CliRunner

import sis
from sis import db, paths, scoring_config
from sis.cli import app
from sis.config import Settings, settings
from sis.llm import tiers_config

COMMANDS = [
    "ingest", "resolve", "score", "evaluate", "delta", "classify", "export", "serve",
    "reportcard", "mcp",
]
CONFIG = paths.config_dir()


@pytest.fixture
def data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "sis_data"  # deliberately not created
    monkeypatch.setattr(settings, "SIS_DATA", root)
    return root


def test_version_strings() -> None:
    assert sis.__version__ == "0.1.0"
    assert sis.PIPELINE_VERSION  # git short sha, or "dev"


def test_settings_defaults() -> None:
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.ROLLUP_MAX_IPS == 50
    assert s.PEER_MIN_SIZE == 30
    assert s.CLASSIFY_TOP_N == 5000
    assert s.LLM_BASE_URL == "https://openrouter.ai/api/v1"
    assert s.LLM_BUDGET_USD_TOTAL == 12.0
    assert s.DUCKDB_MEMORY_LIMIT == "10GB"
    assert s.DUCKDB_THREADS == 12
    assert s.INGEST_WORKERS == 11
    assert s.OPENROUTER_API_KEY is None and s.LOGFIRE_TOKEN is None


def test_settings_read_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROLLUP_MAX_IPS", "250")
    monkeypatch.setenv("SIS_DATA", "/somewhere/else")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.ROLLUP_MAX_IPS == 250
    assert s.SIS_DATA == Path("/somewhere/else")


def test_paths_resolve(data_root: Path) -> None:
    assert paths.file_dir("abc") == data_root / "abc"
    assert paths.tmp_dir("abc") == data_root / "abc.tmp"
    assert paths.banners_glob("abc") == (data_root / "abc" / "banners" / "*.parquet").as_posix()
    assert paths.vulns_glob("abc") == (data_root / "abc" / "vulns" / "*.parquet").as_posix()
    assert paths.current_dir() == data_root / "current"
    assert paths.serve_dir("v1") == data_root / "serve" / "v1"
    assert paths.history_dir() == data_root / "history"
    assert paths.ingest_log_path() == data_root / "ingest_log.parquet"
    assert paths.llm_calls_path() == data_root / "llm_calls.parquet"
    assert paths.quarantine_dir() == data_root / "quarantine"


def test_default_data_root_is_outside_the_repo() -> None:
    assert not Settings(_env_file=None).SIS_DATA.is_relative_to(paths.REPO_ROOT)  # type: ignore[call-arg]


def test_cli_lists_every_command() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    for name in COMMANDS:
        assert name in result.output


IMPLEMENTED = {"ingest", "resolve"}  # a card that builds a command removes it from the stub list


@pytest.mark.parametrize("name", [c for c in COMMANDS if c not in IMPLEMENTED])
def test_cli_stub_exits_2(name: str) -> None:
    result = CliRunner().invoke(app, [name])
    assert result.exit_code == 2
    assert f"not implemented: {name}" in result.output


def test_connect_without_data_dir(data_root: Path) -> None:
    assert not data_root.exists()
    con = db.connect()
    assert con.execute("SELECT 42").fetchone() == (42,)
    assert con.execute("SELECT current_setting('threads')").fetchone() == (settings.DUCKDB_THREADS,)
    assert (data_root / "duckdb_tmp").is_dir()


def test_register_and_reject_bad_name(data_root: Path, tiny_banners) -> None:  # type: ignore[no-untyped-def]
    con = db.connect()
    db.register(con, "b", tiny_banners.banners_glob)
    db.register(con, "v", tiny_banners.vulns_glob)
    n = con.execute("SELECT count(*) FROM b").fetchone()
    assert n == (tiny_banners.n_rows,)
    con.execute("SELECT count(*) FROM v")  # the view exists even with no CVE rows
    with pytest.raises(ValueError):
        db.register(con, "b; DROP TABLE x", tiny_banners.banners_glob)


def test_tiny_banners_fixture(tiny_banners) -> None:  # type: ignore[no-untyped-def]
    assert tiny_banners.n_lines == 200
    assert tiny_banners.n_rows == 200
    con = db.connect()
    db.register(con, "b", tiny_banners.banners_glob)
    ids = con.execute("SELECT count(DISTINCT id) FROM b").fetchone()
    assert ids == (200,)


def test_fixture_file_size() -> None:
    p = Path(__file__).parent / "fixtures" / "tiny_banners.jsonl"
    assert p.exists() and p.stat().st_size < 2 * 1024 * 1024


# ---- config files ----------------------------------------------------------------------


def test_scoring_yaml_loads() -> None:
    c = scoring_config.load()
    assert c.scoring_version == "1.0.0"
    assert c.exposure.weights == {"a": 0.45, "b": 0.20, "c": 0.35}
    assert c.facts.a.weights["eol"] == 1.0
    assert c.peer.breadth_buckets == [(1, 1), (2, 3), (4, 9), (10, None)]
    assert c.segments.multipliers["displace"] == 0.6


def _scoring_raw() -> dict:  # type: ignore[type-arg]
    return yaml.safe_load((CONFIG / "scoring.yaml").read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def test_scoring_rejects_weight_out_of_range() -> None:
    raw = copy.deepcopy(_scoring_raw())
    raw["facts"]["a"]["weights"]["eol"] = 2.5
    with pytest.raises(ValidationError):
        scoring_config.ScoringConfig.model_validate(raw)


def test_scoring_rejects_exposure_not_summing_to_one() -> None:
    raw = copy.deepcopy(_scoring_raw())
    raw["exposure"]["weights"]["a"] = 0.46
    with pytest.raises(ValidationError, match="sum to 1.0"):
        scoring_config.ScoringConfig.model_validate(raw)


def test_scoring_rejects_unknown_and_missing_keys() -> None:
    raw = copy.deepcopy(_scoring_raw())
    del raw["facts"]["d"]["weights"]["vpn"]
    with pytest.raises(ValidationError):
        scoring_config.ScoringConfig.model_validate(raw)


def test_scoring_rejects_gap_in_breadth_buckets() -> None:
    raw = copy.deepcopy(_scoring_raw())
    raw["peer"]["breadth_buckets"] = [[1, 1], [3, 9], [10, None]]
    with pytest.raises(ValidationError):
        scoring_config.ScoringConfig.model_validate(raw)


def test_operator_domains_seed() -> None:
    # P2 appends data-derived names under "# derived from <file_id>" headers; the seed stays first.
    lines = (CONFIG / "operator_domains.txt").read_text(encoding="utf-8").split()
    assert lines[:12] == [
        "incapdns.net", "googleusercontent.com", "amazonaws.com", "cloudfront.net",
        "akamaitechnologies.com", "cloudflare.com", "linode.com", "vultr.com",
        "digitalocean.com", "hetzner.com", "ovh.net", "aliyuncs.com",
    ]
    assert len(set(lines)) == len(lines)


def test_industry_taxonomy() -> None:
    raw = yaml.safe_load((CONFIG / "industry_taxonomy.yaml").read_text(encoding="utf-8"))
    assert len(raw["industries"]) == 20
    assert raw["fallbacks"] == ["other", "not_a_business"]
    assert len(set(raw["industries"]) | set(raw["fallbacks"])) == 22


def test_llm_tiers_yaml_loads() -> None:
    c = tiers_config.load()
    assert set(c.tiers) == {"reasoning", "mid", "errand"}
    assert c.tasks == {
        "classify": "errand", "reportcard": "mid", "judge": "reasoning", "mcp_agent": "mid",
    }
    spent = sum(t.budget_usd for t in c.tiers.values()) + c.reserve_usd
    assert spent <= settings.LLM_BUDGET_USD_TOTAL


def _tiers_raw() -> dict:  # type: ignore[type-arg]
    return yaml.safe_load((CONFIG / "llm_tiers.yaml").read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def test_tiers_reject_over_budget() -> None:
    c = tiers_config.TiersConfig.model_validate(_tiers_raw())
    with pytest.raises(ValueError, match="exceed total"):
        c.check_budget(11.0)


def test_tiers_reject_one_model_in_a_tier() -> None:
    raw = copy.deepcopy(_tiers_raw())
    raw["tiers"]["mid"]["models"] = ["deepseek/deepseek-v4-flash"]
    with pytest.raises(ValidationError):
        tiers_config.TiersConfig.model_validate(raw)


def test_tiers_reject_task_without_tier() -> None:
    raw = copy.deepcopy(_tiers_raw())
    del raw["tasks"]["judge"]
    with pytest.raises(ValidationError, match="tasks without a tier"):
        tiers_config.TiersConfig.model_validate(raw)


def test_tiers_reject_task_mapped_to_unknown_tier() -> None:
    raw = copy.deepcopy(_tiers_raw())
    raw["tasks"]["classify"] = "premium"
    with pytest.raises(ValidationError):
        tiers_config.TiersConfig.model_validate(raw)
