"""Ranking metrics against held-out labels (cards/P4.md steps 2 and 3, DESIGN.md section 6).

A ranking is a relation with `entity_id`, 1 numeric score column and boolean label columns.
Rank order is score descending, ties by entity_id ascending, so precision@k is deterministic.
Rank-biserial is 2 * AUC - 1, AUC from the Mann-Whitney rank sum of the positives with tied
scores taking their average rank, all in DuckDB (no sklearn)."""

import json
import math
from pathlib import Path
from typing import Any

import duckdb

from sis import eval_config, paths

LABELS = ("label_kev", "label_verified", "label_heartbleed", "label_opts_vulns",
          "label_any_tested", "label_has_vendor")
INFO_LABELS = ("label_ransomware",)  # reported, never a target (cards/P4.md step 1)
ALL_LABELS = LABELS + INFO_LABELS


def wilson(hits: int, n: int, z: float) -> tuple[float, float]:
    """Wilson score interval for hits / n. (0, 1) when n is 0."""
    if n == 0:
        return (0.0, 1.0)
    p = hits / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z / (1 + z * z / n) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, centre - half), min(1.0, centre + half))


def label_metrics(con: duckdb.DuckDBPyConnection, rel: str, score: str,
                  labels: tuple[str, ...] | list[str], ks: list[int], z: float,
                  where: str | None = None) -> dict[str, dict[str, Any]]:
    """Per label: n, n_pos, base_rate, rank_biserial, and per k: k_eff, hits, precision,
    ci95 (Wilson), lift. `where` restricts the population before ranking."""
    cond = f"WHERE {where}" if where else ""
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE _ranked AS
        SELECT row_number() OVER (ORDER BY {score} DESC, entity_id) AS rn,
               rank() OVER (ORDER BY {score}) + (count(*) OVER (PARTITION BY {score}) - 1) / 2.0
                   AS arank,
               {", ".join(labels)}
        FROM {rel} {cond}""")
    cols = ["count(*)"]
    for lab in labels:
        cols += [f"count(*) FILTER (WHERE {lab})", f"sum(arank) FILTER (WHERE {lab})"]
        cols += [f"count(*) FILTER (WHERE {lab} AND rn <= {int(k)})" for k in ks]
    row = con.execute(f"SELECT {', '.join(cols)} FROM _ranked").fetchall()[0]
    n = int(row[0])
    out: dict[str, dict[str, Any]] = {}
    width = 2 + len(ks)
    for i, lab in enumerate(labels):
        n_pos, rank_sum, *hits = row[1 + i * width: 1 + (i + 1) * width]
        n_pos = int(n_pos)
        base = n_pos / n if n else 0.0
        n_neg = n - n_pos
        rb = None
        if n_pos and n_neg:
            auc = (float(rank_sum) - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)
            rb = 2 * auc - 1
        at_k: dict[str, Any] = {}
        for k, h in zip(ks, hits, strict=True):
            k_eff = min(k, n)
            prec = h / k_eff if k_eff else 0.0
            lo, hi = wilson(int(h), k_eff, z)
            at_k[str(k)] = {"k_eff": k_eff, "hits": int(h), "precision": prec,
                            "ci95": [lo, hi], "lift": prec / base if base else None}
        out[lab] = {"n": n, "n_pos": n_pos, "base_rate": base, "rank_biserial": rb,
                    "at_k": at_k}
    return out


def precision_at_k(con: duckdb.DuckDBPyConnection, rel: str, score: str, label: str,
                   k: int) -> float:
    return float(label_metrics(con, rel, score, [label], [k], 1.96)[label]["at_k"][str(k)]
                 ["precision"])


def lift_at_k(con: duckdb.DuckDBPyConnection, rel: str, score: str, label: str,
              k: int) -> float | None:
    lift = label_metrics(con, rel, score, [label], [k], 1.96)[label]["at_k"][str(k)]["lift"]
    return None if lift is None else float(lift)


def rank_biserial(con: duckdb.DuckDBPyConnection, rel: str, score: str,
                  label: str) -> float | None:
    rb = label_metrics(con, rel, score, [label], [], 1.96)[label]["rank_biserial"]
    return None if rb is None else float(rb)


def views(con: duckdb.DuckDBPyConnection, rel: str, cfg: eval_config.EvalConfig,
          by_exposure: bool = True) -> dict[str, Any]:
    """The 3 views of 1 scored relation: by priority, by exposure, untouched segment only
    (by priority, which equals exposure there because the multiplier is 1.0)."""
    res = {"by_priority": label_metrics(con, rel, "priority", ALL_LABELS, cfg.ks, cfg.z)}
    if by_exposure:
        res["by_exposure"] = label_metrics(con, rel, "exposure", ALL_LABELS, cfg.ks, cfg.z)
    res["untouched_only"] = label_metrics(con, rel, "priority", ALL_LABELS, cfg.ks, cfg.z,
                                          where="segment = 'untouched'")
    return res


def label_counts(con: duckdb.DuckDBPyConnection, rel: str = "ev") -> dict[str, Any]:
    """Entities with each label and base rate over all active entities and within each segment."""
    n = int(con.execute(f"SELECT count(*) FROM {rel}").fetchall()[0][0])
    out: dict[str, Any] = {}
    for lab in ALL_LABELS:
        k = int(con.execute(f"SELECT count(*) FILTER (WHERE {lab}) FROM {rel}").fetchall()[0][0])
        seg = {s: {"n": int(a), "n_pos": int(b), "rate": b / a if a else None}
               for s, a, b in con.execute(f"""
                   SELECT segment, count(*), count(*) FILTER (WHERE {lab})
                   FROM {rel} GROUP BY 1 ORDER BY 1""").fetchall()}
        out[lab] = {"n_pos": k, "base_rate": k / n if n else 0.0, "by_segment": seg}
    return {"n_active": n, "labels": out}


def sanity(con: duckdb.DuckDBPyConnection, rel: str = "ev") -> dict[str, Any]:
    """cards/P4.md step 6: label_has_vendor per segment (displace must be 1.0 by construction)
    and the exposure quantiles of displace vs untouched."""
    rates = dict(con.execute(f"""
        SELECT segment, avg(label_has_vendor::INT) FROM {rel} GROUP BY 1 ORDER BY 1""").fetchall())
    q = {seg: {"n": int(n), "p10": p10, "p50": p50, "p90": p90, "p99": p99, "mean": mean}
         for seg, n, p10, p50, p90, p99, mean in con.execute(f"""
             SELECT segment, count(*), quantile_cont(exposure, 0.1),
                    quantile_cont(exposure, 0.5), quantile_cont(exposure, 0.9),
                    quantile_cont(exposure, 0.99), avg(exposure)
             FROM {rel} WHERE segment IN ('displace', 'untouched') GROUP BY 1 ORDER BY 1""")
         .fetchall()}
    return {"has_vendor_rate_by_segment": rates, "exposure_displace_vs_untouched": q,
            "displace_has_vendor_is_1": rates.get("displace") == 1.0}


def evaluate(file_id: str, con: duckdb.DuckDBPyConnection,
             cfg: eval_config.EvalConfig | None = None) -> dict[str, Any]:
    """metrics.json for the full model. `con` holds the `ev` table (sis.evaluate.run)."""
    cfg = cfg or eval_config.load()
    counts = label_counts(con)
    version = con.execute("SELECT min(scoring_version) FROM sc").fetchall()[0][0]
    res: dict[str, Any] = {"file_id": file_id, "scoring_version": version, "ks": cfg.ks,
                           "n_active": counts["n_active"], "labels": counts["labels"]}
    both, v_only, o_only = con.execute("""
        SELECT count(*) FILTER (WHERE label_verified AND label_opts_vulns),
               count(*) FILTER (WHERE label_verified AND NOT label_opts_vulns),
               count(*) FILTER (WHERE label_opts_vulns AND NOT label_verified) FROM ev""")\
        .fetchall()[0]
    res["tested_overlap"] = {"verified_and_opts_vulns": int(both), "verified_only": int(v_only),
                             "opts_vulns_only": int(o_only)}
    res.update(views(con, "ev", cfg))
    res["sanity"] = sanity(con)
    write_json(res, paths.eval_dir(file_id) / "metrics.json")
    return res


def write_json(obj: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1), encoding="utf-8")
    tmp.replace(path)
