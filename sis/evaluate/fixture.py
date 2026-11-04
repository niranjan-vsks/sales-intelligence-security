"""The committed eval bundle and its thresholds (phase P4 step 7). Written only on
`sis evaluate FILE_ID --fixture`, so a normal run never moves the CI bar."""

import json
import random
from typing import Any

import duckdb
import pyarrow as pa

from sis import eval_config, paths
from sis.evaluate.metrics import ALL_LABELS, precision_at_k
from sis.io import write_parquet

COLUMNS = ("entity_id", "priority", "exposure", "segment", "fact_a", "fact_b", "fact_c", "fact_d")


def write_fixture(con: duckdb.DuckDBPyConnection,
                  cfg: eval_config.EvalConfig | None = None) -> dict[str, Any]:
    """Sample cfg.fixture.n_entities rows of `ev` with cfg.fixture.seed, write
    tests/fixtures/eval_bundle/eval_bundle.parquet and tests/eval_thresholds.json."""
    fx = (cfg or eval_config.load()).fixture
    ids = [r[0] for r in con.execute("SELECT entity_id FROM ev ORDER BY entity_id").fetchall()]
    picked = random.Random(fx.seed).sample(ids, fx.n_entities)
    con.register("_pick", pa.table({"entity_id": picked}))
    cols = ", ".join(COLUMNS + ALL_LABELS)
    con.execute(f"""CREATE OR REPLACE TEMP TABLE bundle AS
                    SELECT {cols} FROM ev JOIN _pick USING (entity_id)""")
    out = paths.eval_fixture_dir() / "eval_bundle.parquet"
    con.unregister("_pick")
    n = write_parquet(con, "SELECT * FROM bundle ORDER BY entity_id", out)
    measured = {f"precision_at_{fx.k}/{lab}": precision_at_k(con, "bundle", "priority", lab, fx.k)
                for lab in fx.labels}
    thresholds = {k: v * fx.threshold_factor for k, v in measured.items()}
    paths.eval_thresholds_path().write_text(json.dumps(thresholds, indent=1) + "\n",
                                            encoding="utf-8")
    return {"rows": n, "bytes": out.stat().st_size, "measured": measured,
            "thresholds": thresholds}
