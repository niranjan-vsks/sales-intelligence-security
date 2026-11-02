"""Ablations (cards/P4.md step 5): rescore through the P3 scoring SQL with an in-memory
override of config/scoring.yaml (the file is never edited), then the same metrics.

no_A, no_B, no_C: that fact's exposure weight set to 0, the other 2 renormalised to sum to 1.
no_D: every segment multiplier set to the `untouched` one, i.e. every entity ranked as if
untouched. Before any ablation the unmodified config is rescored and must reproduce
scores.parquet; otherwise the ablations would measure drift, not the fact."""

from typing import Any

import duckdb

from sis import eval_config, paths, scoring_config
from sis.evaluate.metrics import ALL_LABELS, views, write_json
from sis.scoring.score import build_scores

FACTS = ("a", "b", "c", "d")
IDENTITY_TOL = 1e-9


def override(cfg: scoring_config.ScoringConfig, drop: str) -> scoring_config.ScoringConfig:
    """A validated copy of `cfg` with fact `drop` ('a'..'d') removed as described above."""
    if drop not in FACTS:
        raise ValueError(f"unknown fact {drop!r}")
    data = cfg.model_dump()
    if drop == "d":
        m = data["segments"]["multipliers"]
        data["segments"]["multipliers"] = {k: m["untouched"] for k in m}
    else:
        w = data["exposure"]["weights"]
        w[drop] = 0.0
        total = sum(w.values())
        data["exposure"]["weights"] = {k: v / total for k, v in w.items()}
    data["scoring_version"] = f"{cfg.scoring_version}+no_{drop.upper()}"
    return scoring_config.ScoringConfig.model_validate(data)


def identity_check(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Compare the rescored temp table `scores` with the stored scores (view `sc`)."""
    n_sc, n_new, n_join, max_diff, seg_diff = con.execute("""
        SELECT (SELECT count(*) FROM sc), (SELECT count(*) FROM scores), count(*),
               max(greatest(abs(a.priority - b.priority), abs(a.exposure - b.exposure))),
               count(*) FILTER (WHERE a.segment <> b.segment)
        FROM sc a JOIN scores b USING (entity_id)""").fetchall()[0]
    return {"n_stored": int(n_sc), "n_rescored": int(n_new), "n_joined": int(n_join),
            "max_abs_diff": float(max_diff or 0.0), "segment_mismatches": int(seg_diff)}


def run_ablations(file_id: str, con: duckdb.DuckDBPyConnection,
                  cfg: eval_config.EvalConfig | None = None,
                  scfg: scoring_config.ScoringConfig | None = None) -> dict[str, Any]:
    """ablations.json. `con` holds `ev`, `labels`, views `sig`, `ent`, `sc` (sis.evaluate.run)."""
    cfg = cfg or eval_config.load()
    scfg = scfg or scoring_config.load()
    con.execute("""CREATE OR REPLACE TEMP TABLE peer AS
                   SELECT entity_id, country_code FROM ent JOIN act USING (entity_id)""")
    build_scores(con, scfg, file_id)  # temp table `scores` from `sig` and `peer`
    check = identity_check(con)
    if (check["n_rescored"] != check["n_stored"] or check["n_joined"] != check["n_stored"]
            or check["max_abs_diff"] > IDENTITY_TOL or check["segment_mismatches"]):
        raise RuntimeError(f"rescoring with the unmodified config does not reproduce "
                           f"scores.parquet: {check}")
    res: dict[str, Any] = {"file_id": file_id, "identity_check": check, "ablations": {}}
    for fact in FACTS:
        ocfg = override(scfg, fact)
        build_scores(con, ocfg, file_id)
        con.execute(f"""CREATE OR REPLACE TEMP TABLE ev_abl AS
                        SELECT s.entity_id, s.priority, s.exposure, s.segment,
                               {", ".join(f"l.{lab}" for lab in ALL_LABELS)}
                        FROM scores s JOIN labels l USING (entity_id)""")
        res["ablations"][f"no_{fact.upper()}"] = {
            "exposure_weights": ocfg.exposure.weights,
            "segment_multipliers": ocfg.segments.multipliers,
            **views(con, "ev_abl", cfg)}
    write_json(res, paths.eval_dir(file_id) / "ablations.json")
    return res
