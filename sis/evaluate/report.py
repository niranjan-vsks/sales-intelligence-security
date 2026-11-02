"""docs/EVAL_REPORT_<file_id>.md, rendered only from metrics.json, baselines.json and
ablations.json, so every number in it traces to a file under $SIS_DATA/<file_id>/eval/."""

from pathlib import Path
from typing import Any

from sis import eval_config
from sis.evaluate.metrics import ALL_LABELS

TESTED = ("label_verified", "label_heartbleed", "label_opts_vulns", "label_any_tested")
SEGMENTS = ("untouched", "partially_covered", "displace", "low_surface")


def _pct(x: float | None, nd: int = 2) -> str:
    return "n/a" if x is None else f"{100 * x:.{nd}f}%"


def _num(x: float | None, nd: int = 2) -> str:
    return "n/a" if x is None else f"{x:.{nd}f}"


def _p_ci(m: dict[str, Any], k: int) -> str:
    a = m["at_k"][str(k)]
    lo, hi = a["ci95"]
    return f"{_pct(a['precision'])} [{100 * lo:.2f}, {100 * hi:.2f}]"


def _row(name: str, m: dict[str, Any], ks: list[int]) -> str:
    cells = [_p_ci(m, k) for k in ks]
    cells += [_num(m["at_k"][str(k)]["lift"]) for k in ks]
    cells.append(_num(m["rank_biserial"], 3))
    return f"| {name} | " + " | ".join(cells) + " |"


def _expected_row(m: dict[str, Any], ks: list[int]) -> str:
    base = _pct(m["base_rate"])
    return ("| random (expected = base rate) | " + " | ".join([base] * len(ks))
            + " | " + " | ".join(["1.00"] * len(ks)) + " | 0.000 |")


def _p(m: dict[str, Any], k: int) -> float:
    return float(m["at_k"][str(k)]["precision"])


def _overlap(a: dict[str, Any], b: dict[str, Any], k: int) -> bool:
    (alo, ahi), (blo, bhi) = a["at_k"][str(k)]["ci95"], b["at_k"][str(k)]["ci95"]
    return bool(alo <= bhi and blo <= ahi)


def rankings(metrics: dict[str, Any], baselines: dict[str, Any], ablations: dict[str, Any],
             view: str = "by_priority") -> dict[str, dict[str, Any]]:
    """name -> {label -> metrics} for every ranking the per-label tables compare."""
    bview = "untouched_only" if view == "untouched_only" else "all"
    out = {"full model": metrics[view],
           "random (mean of 5 draws)": baselines["random"]["mean"][bview],
           "breadth_only": baselines["breadth_only"][bview],
           "cve_count_only": baselines["cve_count_only"][bview]}
    out.update({name: a[view] for name, a in ablations["ablations"].items()})
    return out


def statements(metrics: dict[str, Any], baselines: dict[str, Any], ablations: dict[str, Any],
               k: int) -> list[str]:
    """Plain sentences derived from the numbers: does the full model beat cve_count_only on
    the tested labels, and does removing a fact raise precision (that fact hurts here)."""
    full, cve = metrics["by_priority"], baselines["cve_count_only"]["all"]
    out = []
    for lab in TESTED:
        f, c = full[lab], cve[lab]
        verdict = "beats" if _p(f, k) > _p(c, k) else "does NOT beat"
        note = ", but the 95% intervals overlap" if _overlap(f, c, k) else ""
        out.append(f"- {lab}: the full model {verdict} cve_count_only at k={k:,} "
                   f"({_pct(_p(f, k))} vs {_pct(_p(c, k))}){note}. Rank-biserial "
                   f"{_num(f['rank_biserial'], 3)} vs {_num(c['rank_biserial'], 3)}.")
    for lab in ("label_any_tested", "label_kev"):
        base_p, base_rb = _p(full[lab], k), full[lab]["rank_biserial"]
        for name, a in ablations["ablations"].items():
            m = a["by_priority"][lab]
            better = []
            if _p(m, k) > base_p:
                better.append(f"p@{k:,} {_pct(_p(m, k))} vs {_pct(base_p)}")
            if (m["rank_biserial"] or 0) > (base_rb or 0):
                better.append(f"rank-biserial {_num(m['rank_biserial'], 3)} vs "
                              f"{_num(base_rb, 3)}")
            if better:
                out.append(f"- {lab}: {name} beats the full model on {' and '.join(better)}: "
                           f"by that measure the removed part does not earn its weight on "
                           f"this label.")
    return out


def write_report(metrics: dict[str, Any], baselines: dict[str, Any], ablations: dict[str, Any],
                 path: Path, cfg: eval_config.EvalConfig | None = None) -> None:
    cfg = cfg or eval_config.load()
    ks = cfg.ks
    k_mid = ks[len(ks) // 2]
    n = metrics["n_active"]
    labels = metrics["labels"]
    chk = ablations["identity_check"]
    L = [
        f"# Eval report {metrics['file_id']}",
        "",
        f"scoring_version {metrics['scoring_version']}. Active entities {n:,}. Rankings are "
        f"by `priority` unless stated, ties by entity_id. Intervals are Wilson 95%. "
        f"Rank-biserial is 2 x AUC - 1 (Mann-Whitney, tied scores at their average rank). "
        f"Rescoring with the unmodified config reproduced scores.parquet "
        f"({chk['n_rescored']:,} rows, max abs diff {chk['max_abs_diff']:.1e}, "
        f"{chk['segment_mismatches']} segment mismatches) before any ablation ran.",
        "",
        "## Labels",
        "",
        "Base rate = share of active entities with the label. Per-segment columns are the "
        "rate inside that segment. label_ransomware is informational, never a target.",
        "",
        "| label | entities | base rate | " + " | ".join(SEGMENTS) + " |",
        "|---|---|---|" + "---|" * len(SEGMENTS),
    ]
    for lab in ALL_LABELS:
        d = labels[lab]
        segs = [_pct(d["by_segment"].get(s, {}).get("rate")) for s in SEGMENTS]
        L.append(f"| {lab} | {d['n_pos']:,} | {_pct(d['base_rate'])} | " + " | ".join(segs)
                 + " |")
    ov = metrics["tested_overlap"]
    L += ["", f"The tested labels overlap: {ov['verified_and_opts_vulns']:,} entities have both "
          f"label_verified and label_opts_vulns, {ov['verified_only']:,} only verified, "
          f"{ov['opts_vulns_only']:,} only opts_vulns. label_any_tested is close to 1 label of "
          f"{labels['label_any_tested']['n_pos']:,} entities, not 3 independent ones."]
    head = ("| ranking | " + " | ".join(f"p@{k:,} [95% CI]" for k in ks) + " | "
            + " | ".join(f"lift@{k:,}" for k in ks) + " | rank-biserial |")
    sep = "|---|" + "---|" * (2 * len(ks) + 1)
    L += ["", "## Per label, ranking by priority", "",
          "Rows: the full model, 3 baselines, 4 ablations (no_A/B/C: that exposure weight "
          "0, the others renormalised; no_D: every segment multiplier = untouched's).", ""]
    rk = rankings(metrics, baselines, ablations)
    for lab in ALL_LABELS:
        m = metrics["by_priority"][lab]
        L += [f"### {lab}", "",
              f"{m['n_pos']:,} positives of {m['n']:,}, base rate {_pct(m['base_rate'], 3)}.",
              "", head, sep, _row("full model", m, ks), _expected_row(m, ks)]
        L += [_row(name, r[lab], ks) for name, r in rk.items() if name != "full model"]
        L.append("")
    L += ["## Ranking by exposure (no segment multiplier)", "",
          "no_D is identical to the full model here, because D only enters through the "
          "segment multiplier.", "",
          "| label | full p@" + " | full p@".join(f"{k:,}" for k in ks)
          + f" | rank-biserial | no_A p@{k_mid:,} | no_B p@{k_mid:,} | no_C p@{k_mid:,} |",
          "|---|" + "---|" * (len(ks) + 4)]
    for lab in ALL_LABELS:
        m = metrics["by_exposure"][lab]
        abl = [_pct(_p(ablations["ablations"][a]["by_exposure"][lab], k_mid))
               for a in ("no_A", "no_B", "no_C")]
        L.append(f"| {lab} | " + " | ".join(_p_ci(m, k) for k in ks)
                 + f" | {_num(m['rank_biserial'], 3)} | " + " | ".join(abl) + " |")
    L += ["", "## Untouched segment only", "",
          "The list sales will actually call. Base rates are recomputed inside the segment.", "",
          f"| label | entities | positives | base rate | full p@{k_mid:,} [95% CI] | "
          f"lift@{k_mid:,} | rank-biserial | random p@{k_mid:,} | breadth_only p@{k_mid:,} | "
          f"cve_count_only p@{k_mid:,} |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    urk = rankings(metrics, baselines, ablations, "untouched_only")
    for lab in ALL_LABELS:
        m = metrics["untouched_only"][lab]
        L.append(f"| {lab} | {m['n']:,} | {m['n_pos']:,} | {_pct(m['base_rate'], 3)} | "
                 f"{_p_ci(m, k_mid)} | {_num(m['at_k'][str(k_mid)]['lift'])} | "
                 f"{_num(m['rank_biserial'], 3)} | "
                 + " | ".join(_pct(_p(urk[b][lab], k_mid)) for b in
                              ("random (mean of 5 draws)", "breadth_only", "cve_count_only"))
                 + " |")
    s = metrics["sanity"]
    L += ["", "## Sanity: label_has_vendor and exposure by segment", "",
          "label_has_vendor is `D_waf` or `D_security_appliance`, which is exactly the "
          "`displace` rule, so its rate there is 1.0 by construction. Displace = 1.0: "
          f"{s['displace_has_vendor_is_1']}.", "",
          "| segment | label_has_vendor rate |", "|---|---|"]
    L += [f"| {seg} | {_pct(s['has_vendor_rate_by_segment'].get(seg))} |" for seg in SEGMENTS]
    L += ["", "| segment | entities | exposure p10 | p50 | p90 | p99 | mean |",
          "|---|---|---|---|---|---|---|"]
    for seg, q in s["exposure_displace_vs_untouched"].items():
        L.append(f"| {seg} | {q['n']:,} | {_num(q['p10'], 1)} | {_num(q['p50'], 1)} | "
                 f"{_num(q['p90'], 1)} | {_num(q['p99'], 1)} | {_num(q['mean'], 1)} |")
    L += ["", f"## Read from the numbers (k = {k_mid:,})", "",
          "cve_count_only is almost fact A alone (it ranks by the count of version-inferred "
          "CVEs), so it is the baseline the full model most needs to beat on the tested "
          "labels.", ""]
    L += statements(metrics, baselines, ablations, k_mid)
    L += ["", "## What this does and does not show", "",
          "There is no purchase, contact or churn field in the file, so these labels are "
          "proxies held out from scoring. label_kev is downstream of the same version strings "
          "fact A reads, so a high score there partly proves we can read a version string. "
          "The tested labels (verified, heartbleed, opts_vulns, and their union "
          "label_any_tested) are independent of the scoring inputs but number in the low "
          "thousands of entities, so their intervals are wide. label_has_vendor is a sanity "
          "check, not a target. Neither family says anyone bought anything. The only true "
          "test is the sales team's reply rate after a month of use; evals/README.md "
          "describes where that 7th label goes.", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L), encoding="utf-8")
