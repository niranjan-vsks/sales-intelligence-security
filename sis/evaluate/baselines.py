"""Baselines the full model must beat (phase P4 step 4): random (5 seeded shuffles,
averaged; its expected precision is the base rate), breadth_only (n_modules desc) and
cve_count_only (A_inferred_cves desc, which already excludes the kev and verified rows)."""

import random
from typing import Any

import duckdb
import pyarrow as pa

from sis import eval_config, paths
from sis.evaluate.metrics import ALL_LABELS, label_metrics, wilson, write_json


def baseline_views(con: duckdb.DuckDBPyConnection, rel: str, score: str,
                   cfg: eval_config.EvalConfig) -> dict[str, Any]:
    return {
        "all": label_metrics(con, rel, score, ALL_LABELS, cfg.ks, cfg.z),
        "untouched_only": label_metrics(con, rel, score, ALL_LABELS, cfg.ks, cfg.z,
                                        where="segment = 'untouched'"),
    }


def mean_of_draws(draws: list[dict[str, Any]], z: float) -> dict[str, Any]:
    """Same shape as 1 draw: precision and rank-biserial averaged; the interval is Wilson on
    the hits pooled over all draws."""
    out: dict[str, Any] = {}
    for view in draws[0]:
        out[view] = {}
        for lab, first in draws[0][view].items():
            per = [d[view][lab] for d in draws]
            rbs = [p["rank_biserial"] for p in per if p["rank_biserial"] is not None]
            at_k: dict[str, Any] = {}
            for k, fk in first["at_k"].items():
                hits = sum(p["at_k"][k]["hits"] for p in per)
                trials = fk["k_eff"] * len(per)
                prec = sum(p["at_k"][k]["precision"] for p in per) / len(per)
                lo, hi = wilson(hits, trials, z)
                at_k[k] = {"k_eff": fk["k_eff"], "hits": hits / len(per), "precision": prec,
                           "ci95": [lo, hi],
                           "lift": prec / first["base_rate"] if first["base_rate"] else None}
            out[view][lab] = {"n": first["n"], "n_pos": first["n_pos"],
                              "base_rate": first["base_rate"],
                              "rank_biserial": sum(rbs) / len(rbs) if rbs else None,
                              "at_k": at_k}
    return out


def run_baselines(file_id: str, con: duckdb.DuckDBPyConnection,
                  cfg: eval_config.EvalConfig | None = None) -> dict[str, Any]:
    """baselines.json. `con` holds the `ev` table (sis.evaluate.run)."""
    cfg = cfg or eval_config.load()
    ids = [r[0] for r in con.execute("SELECT entity_id FROM ev ORDER BY entity_id").fetchall()]
    draws = []
    for seed in cfg.random_seeds:
        perm = list(range(len(ids)))
        random.Random(seed).shuffle(perm)
        con.register("_rnd_arrow", pa.table({"entity_id": ids, "rnd": perm}))
        con.execute("""CREATE OR REPLACE TEMP TABLE ev_rnd AS
                       SELECT ev.*, r.rnd FROM ev JOIN _rnd_arrow r USING (entity_id)""")
        draws.append(baseline_views(con, "ev_rnd", "rnd", cfg))
        con.unregister("_rnd_arrow")
    res: dict[str, Any] = {
        "file_id": file_id,
        "random": {"seeds": cfg.random_seeds, "mean": mean_of_draws(draws, cfg.z),
                   "draws": draws},
        "breadth_only": {"score": "entities.n_modules",
                         **baseline_views(con, "ev", "n_modules", cfg)},
        "cve_count_only": {"score": "signals A_inferred_cves (0 when absent)",
                           **baseline_views(con, "ev", "cve_count", cfg)},
    }
    write_json(res, paths.eval_dir(file_id) / "baselines.json")
    return res
