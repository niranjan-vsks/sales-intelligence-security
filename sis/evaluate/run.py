"""`sis evaluate FILE_ID`: labels, metrics, baselines, ablations, report (cards/P4.md)."""

import time
from typing import Any

from pydantic import BaseModel

from sis import eval_config, paths
from sis.evaluate import report
from sis.evaluate.ablation import run_ablations
from sis.evaluate.baselines import run_baselines
from sis.evaluate.fixture import write_fixture
from sis.evaluate.labels import build_labels, open_file
from sis.evaluate.metrics import evaluate

REPORT_DIR = paths.REPO_ROOT / "docs"


class EvalResult(BaseModel):
    file_id: str
    n_labels: int
    out_dir: str
    report: str
    fixture: dict[str, Any] | None = None
    wall_seconds: float = 0.0


def run(file_id: str, fixture: bool = False) -> EvalResult:
    t0 = time.time()
    cfg = eval_config.load()
    con = open_file(file_id)
    n = build_labels(file_id, con)
    con.execute("""
        CREATE OR REPLACE TEMP TABLE ev AS
        SELECT sc.entity_id, sc.priority, sc.exposure, sc.segment,
               sc.fact_a, sc.fact_b, sc.fact_c, sc.fact_d,
               ent.n_modules, coalesce(cv.value, 0) AS cve_count,
               labels.* EXCLUDE (entity_id)
        FROM sc JOIN ent USING (entity_id) JOIN labels USING (entity_id)
        LEFT JOIN (SELECT entity_id, value FROM sig WHERE signal_id = 'A_inferred_cves') cv
            USING (entity_id)""")
    metrics = evaluate(file_id, con, cfg)
    baselines = run_baselines(file_id, con, cfg)
    ablations = run_ablations(file_id, con, cfg)
    fx = write_fixture(con, cfg) if fixture else None
    con.close()
    out = REPORT_DIR / f"EVAL_REPORT_{file_id}.md"
    report.write_report(metrics, baselines, ablations, out, cfg)
    return EvalResult(file_id=file_id, n_labels=n, out_dir=str(paths.eval_dir(file_id)),
                      report=str(out), fixture=fx, wall_seconds=round(time.time() - t0, 1))
