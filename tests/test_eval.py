"""phase P4 acceptance tests, marked `eval`: metric arithmetic by hand, then the committed
fixture against the committed thresholds (the CI step that blocks a degrading scoring change)."""

import json
import random

import duckdb
import pyarrow as pa
import pytest

from sis import eval_config, paths
from sis.evaluate.metrics import lift_at_k, precision_at_k, rank_biserial, wilson

pytestmark = pytest.mark.eval


def _table(scores: list[float], labels: list[bool]) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.register("t_arrow", pa.table({
        "entity_id": [f"e{i:06d}" for i in range(len(scores))],
        "s": scores, "y": labels}))
    con.execute("CREATE TABLE t AS SELECT * FROM t_arrow")
    return con


def test_precision_at_k_hand() -> None:
    con = _table([5, 4, 3, 2, 1], [True, False, True, True, False])
    assert [precision_at_k(con, "t", "s", "y", k) for k in (1, 2, 3, 4, 5)] == pytest.approx(
        [1.0, 0.5, 2 / 3, 0.75, 0.6])
    # k beyond the population: precision over the whole population
    assert precision_at_k(con, "t", "s", "y", 50) == pytest.approx(0.6)
    # base rate 0.6: lift@2 = 0.5 / 0.6
    assert lift_at_k(con, "t", "s", "y", 2) == pytest.approx(0.5 / 0.6)
    # ties are broken by entity_id ascending: e000000 (negative) comes first
    tied = _table([1, 1, 1, 1, 1], [False, True, True, True, True])
    assert precision_at_k(tied, "t", "s", "y", 1) == 0.0


def test_rank_biserial_hand() -> None:
    n = 1000
    labels = [i < 100 for i in range(n)]
    perfect = _table([float(n - i) for i in range(n)], labels)
    assert rank_biserial(perfect, "t", "s", "y") == pytest.approx(1.0)
    reversed_ = _table([float(i) for i in range(n)], labels)
    assert rank_biserial(reversed_, "t", "s", "y") == pytest.approx(-1.0)
    # all tied: AUC 0.5 exactly, because ties take their average rank
    tied = _table([0.0] * n, labels)
    assert rank_biserial(tied, "t", "s", "y") == pytest.approx(0.0)
    rng = random.Random(4)
    big = 20_000
    noise = _table([rng.random() for _ in range(big)], [rng.random() < 0.1 for _ in range(big)])
    assert abs(rank_biserial(noise, "t", "s", "y") or 0.0) < 0.05
    no_pos = _table([1.0, 2.0], [False, False])
    assert rank_biserial(no_pos, "t", "s", "y") is None


def test_wilson_interval() -> None:
    # Newcombe (1998), Statistics in Medicine 17:857-872, table I, method 3 (score, no c.c.)
    z = eval_config.load().z
    assert wilson(81, 263, z) == pytest.approx((0.2553, 0.3662), abs=1e-4)
    assert wilson(15, 148, z) == pytest.approx((0.0624, 0.1605), abs=1e-4)
    assert wilson(0, 20, z) == pytest.approx((0.0, 0.1611), abs=1e-4)
    assert wilson(1, 29, z) == pytest.approx((0.0061, 0.1718), abs=1e-4)
    assert wilson(0, 0, z) == (0.0, 1.0)


def test_fixture_threshold() -> None:
    cfg = eval_config.load().fixture
    thresholds = json.loads(paths.eval_thresholds_path().read_text(encoding="utf-8"))
    bundle = (paths.eval_fixture_dir() / "eval_bundle.parquet").as_posix()
    con = duckdb.connect()
    con.execute("CREATE TABLE ev AS SELECT * FROM read_parquet(?)", [bundle])
    assert con.execute("SELECT count(*) FROM ev").fetchall()[0][0] == cfg.n_entities
    for label in cfg.labels:
        key = f"precision_at_{cfg.k}/{label}"
        got = precision_at_k(con, "ev", "priority", label, cfg.k)
        assert got >= thresholds[key], f"{key}: {got} below the committed {thresholds[key]}"
