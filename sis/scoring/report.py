"""docs/SCORE_REPORT_<file_id>.md. Every number comes from a query on the run's own tables
(temp tables scores, sig, peer, ebf and the evidence written next to them)."""

from pathlib import Path
from typing import TYPE_CHECKING

import duckdb

from sis import paths
from sis.scoring.peer import peer_stats

if TYPE_CHECKING:
    from sis.scoring.score import ScoreResult

EYEBALL_SEED = 7
EYEBALL_N = 10
TOP_N = 20


def _rows(con: duckdb.DuckDBPyConnection, sql: str) -> list[tuple]:  # type: ignore[type-arg]
    return con.execute(sql).fetchall()


def _f(x: float | None, nd: int = 1) -> str:
    return "" if x is None else f"{x:.{nd}f}"


def write_report(con: duckdb.DuckDBPyConnection, r: "ScoreResult", path: Path) -> None:
    n = r.n_scored
    ev = (paths.file_dir(r.file_id) / "evidence.parquet").as_posix()
    target_diff = 100 * (r.stage1_target_group - 131_104) / 131_104
    L = [
        f"# Score report {r.file_id}",
        "",
        f"scoring_version {r.scoring_version}. Wall seconds {r.wall_seconds}. "
        f"Active entities scored {n:,}. Signal rows {r.n_signals:,}. "
        f"Evidence rows {r.n_evidence:,}.",
        "",
        "## Segments",
        "",
        "| segment | entities | share | exposure p50 | p90 | p99 | max |",
        "|---|---|---|---|---|---|---|",
    ]
    for seg, cnt, p50, p90, p99, mx in _rows(con, """
            SELECT segment, count(*), quantile_cont(exposure, 0.5), quantile_cont(exposure, 0.9),
                   quantile_cont(exposure, 0.99), max(exposure)
            FROM scores GROUP BY 1 ORDER BY 2 DESC"""):
        L.append(f"| {seg} | {cnt:,} | {100 * cnt / n:.2f}% | {_f(p50)} | {_f(p90)} | "
                 f"{_f(p99)} | {_f(mx)} |")
    L += [
        "",
        f"Stage 1 target group (prerequisite P01-P03, none of W01-W07, raw predicates on every "
        f"banner of the active entities): {r.stage1_target_group:,} vs 131,104 "
        f"({target_diff:+.2f}%). The `untouched` segment is "
        f"{r.segments.get('untouched', 0):,}: it applies the edge-banner rule and so differs.",
        "",
        "## Signal fire rates",
        "",
        "| signal | fact | entities | share of scored | banners firing |",
        "|---|---|---|---|---|",
    ]
    for sid, fact, ents, banners in _rows(con, """
            SELECT signal_id, fact, count(*) FILTER (WHERE n_banners > 0), sum(n_banners)
            FROM sig GROUP BY 1, 2 ORDER BY 3 DESC, 1"""):
        L.append(f"| {sid} | {fact} | {ents:,} | {100 * ents / n:.2f}% | {int(banners):,} |")
    L += ["", "## Facts", "", "| fact | mean | share > 0 | p90 |", "|---|---|---|---|"]
    for fact in ("fact_a", "fact_b", "fact_c", "fact_d"):
        mean, share, p90 = _rows(con, f"""SELECT avg({fact}), avg(({fact} > 0)::INT),
            quantile_cont({fact}, 0.9) FROM scores""")[0]
        L.append(f"| {fact} | {mean:.3f} | {100 * share:.2f}% | {p90:.3f} |")
    L += ["", f"## Top {TOP_N} by priority", "",
          "| rank | entity | segment | priority | exposure | A | B | C | D | top_signals |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for row in _rows(con, f"""
            SELECT s.rank_overall, e.key_value, s.segment, s.priority, s.exposure, s.fact_a,
                   s.fact_b, s.fact_c, s.fact_d, s.top_signals
            FROM scores s JOIN ent e USING (entity_id) ORDER BY s.rank_overall LIMIT {TOP_N}"""):
        L.append(f"| {row[0]} | {row[1]} | {row[2]} | {_f(row[3])} | {_f(row[4])} | "
                 f"{_f(row[5], 2)} | {_f(row[6], 2)} | {_f(row[7], 2)} | {_f(row[8], 2)} | "
                 f"{', '.join(row[9])} |")
    ps = peer_stats(con)
    L += [
        "", "## Peer groups", "",
        f"{ps.n_groups:,} groups. Entities in a country|bucket group {ps.n_country_bucket:,}; "
        f"fell back to bucket only {ps.n_bucket_only:,}; to global {ps.n_global:,}.",
        "", "| group size | groups | entities |", "|---|---|---|",
    ]
    for label, groups, ents in _rows(con, """
            SELECT CASE WHEN n < 100 THEN 'a: 30-99' WHEN n < 1000 THEN 'b: 100-999'
                        WHEN n < 10000 THEN 'c: 1,000-9,999' ELSE 'd: 10,000+' END,
                   count(*), sum(n)
            FROM (SELECT peer_group, count(*) AS n FROM peer GROUP BY 1) GROUP BY 1 ORDER BY 1"""):
        L.append(f"| {label[3:]} | {groups:,} | {int(ents):,} |")
    L += ["", "Largest groups: " + ", ".join(
        f"{g} {c:,}" for g, c in _rows(con, "SELECT peer_group, count(*) FROM peer "
                                            "GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 8"))]
    L += [
        "", f"## {EYEBALL_N} random untouched entities (seed {EYEBALL_SEED})", "",
        "Each with its signals and up to 3 evidence rows. The 1-line judgement under each is "
        "written by hand after reading the evidence.", "",
    ]
    con.execute("SELECT setseed(0.7)").fetchall()
    picks = _rows(con, f"""
        SELECT entity_id, key_value, exposure, priority, rank_overall, top_signals FROM (
            SELECT s.entity_id, e.key_value, s.exposure, s.priority, s.rank_overall,
                   s.top_signals
            FROM scores s JOIN ent e USING (entity_id) WHERE s.segment = 'untouched'
            ORDER BY s.entity_id)
        USING SAMPLE {EYEBALL_N} ROWS (reservoir, {EYEBALL_SEED}) ORDER BY rank_overall""")
    for eid, name, expo, prio, rank, top in picks:
        L.append(f"### {name} (rank {rank:,}, exposure {expo:.1f}, priority {prio:.1f})")
        sigs = _rows(con, f"""SELECT signal_id, value, pct_in_peer FROM sig
            WHERE entity_id = '{eid}' AND n_banners > 0 ORDER BY signal_id""")
        L.append("signals: " + ", ".join(
            f"{s}={v:g}" + (f" (pct {p:.2f})" if p is not None else "") for s, v, p in sigs))
        L.append(f"top_signals: {', '.join(top) or 'none'}")
        L.append("")
        for sid, ip, port, module, field, value, snip in _rows(con, f"""
                SELECT signal_id, ip, port, module, field, value, snippet
                FROM read_parquet('{ev}') WHERE entity_id = '{eid}'
                  AND signal_id NOT IN ('C_breadth_modules', 'C_breadth_ports')
                ORDER BY signal_id, port LIMIT 3"""):
            value, snip = ((x or "").replace("`", "'") for x in (value, snip))
            L.append(f"- {sid}: {ip}:{port} {module} {field}=`{value[:80]}` "
                     f"snippet `{snip[:100]}`")
        L += ["", "judgement: (to fill)", ""]
    path.write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")
