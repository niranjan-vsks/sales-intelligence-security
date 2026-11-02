"""docs/RESOLVE_REPORT_<file_id>.md. Every number comes from a query on the run's own tables."""

from pathlib import Path
from typing import TYPE_CHECKING

import duckdb

if TYPE_CHECKING:
    from sis.entities.resolve import ResolveResult

EYEBALL_SEED = 7
EYEBALL_N = 20
EYEBALL_BANNERS = 4


def _pct(n: int, total: int) -> str:
    return f"{100 * n / total:.2f}%" if total else "n/a"


def write_report(con: duckdb.DuckDBPyConnection, r: "ResolveResult", path: Path) -> None:
    n = r.n_banners
    L = [
        f"# Resolve report {r.file_id}",
        "",
        f"ROLLUP_MAX_IPS = {r.max_ips}. Wall seconds {r.wall_seconds}. Banners {n:,}.",
        "",
        "## Entities",
        "",
        "| key_kind | active entities |",
        "|---|---|",
        *[f"| {k} | {v:,} |" for k, v in r.entities_by_kind.items()],
        f"| **active total** | **{r.n_active:,}** |",
        f"| blocked | {r.n_blocked:,} |",
        "",
        "Blocked by reason: "
        + (", ".join(f"{k} {v:,}" for k, v in r.blocked_by_reason.items()) or "none"),
        "",
        "## Banners by attribution",
        "",
        "| attribution | banners | share |",
        "|---|---|---|",
        f"| primary (customer domain from reverse DNS) | {r.banners_primary:,} | "
        f"{_pct(r.banners_primary, n)} |",
        f"| fallback (certificate or http_host, no primary) | {r.banners_fallback:,} | "
        f"{_pct(r.banners_fallback, n)} |",
        f"| none | {r.banners_none:,} | {_pct(r.banners_none, n)} |",
        "",
        "## Unattributed banners by reason",
        "",
        "Mutually exclusive. A banner attributed only to blocked entities counts as `blocked`.",
        "",
        "| reason | banners | share |",
        "|---|---|---|",
        *[f"| {k} | {v:,} | {_pct(v, n)} |" for k, v in r.unattributed.items()],
        "",
        "## Operator domains",
        "",
        f"Seed (file lines before the first derived header, plus other files' sections): "
        f"{r.operators_seed:,}. Derived from this file: {r.operators_derived:,}. "
        f"Largest 5 by IP coverage: {', '.join(r.operators_derived_top) or 'none'}.",
        "",
        "Hosting-zone rules (config/resolve.yaml), matched and added beyond the seed and the "
        f"cutoff: rule 1 template zone {r.rule1_matched:,} matched, {r.rule1_added:,} added; "
        f"rule 2 templated hostnames {r.rule2_matched:,} matched, {r.rule2_added:,} added "
        "(not counting rule 1).",
        "",
        "Rule 2, the 30 largest by banners:",
        "",
        "| name | banners | ips | hostnames | templated |",
        "|---|---|---|---|---|",
        *[f"| {n} | {nb:,} | {ips:,} | {nh:,} | {nt:,} |" for n, nb, ips, nh, nt in r.rule2_top],
        "",
    ]
    q = con.execute("SELECT quantile_disc(n_banners, [0.5, 0.9, 0.99]), max(n_banners) "
                    "FROM entities WHERE status = 'active'").fetchall()[0]
    L += [
        "## Banners per active entity", "",
        f"p50 {q[0][0]}, p90 {q[0][1]}, p99 {q[0][2]}, max {q[1]:,}", "",
        "## Top 20 active entities by n_banners", "",
        "Eyeball for hosting providers that slipped through; add them to the seed part of "
        "`config/operator_domains.txt` and rerun.", "",
        "| entity | kind | banners | ips | org_mode |", "|---|---|---|---|---|",
    ]
    for key, kind, nb, ips, org in con.execute(
        "SELECT key_value, key_kind, n_banners, n_ips, org_mode FROM entities "
        "WHERE status = 'active' ORDER BY n_banners DESC, key_value LIMIT 20"
    ).fetchall():
        L.append(f"| {key} | {kind} | {nb:,} | {ips:,} | {org} |")
    L += ["", f"## Eyeball sample: {EYEBALL_N} active entities, reservoir seed {EYEBALL_SEED}", ""]
    sample = con.execute(
        f"SELECT entity_id, key_kind, key_value, n_banners, n_ips FROM entities "
        f"WHERE status = 'active' USING SAMPLE {EYEBALL_N} ROWS (reservoir, {EYEBALL_SEED}) "
        f"ORDER BY key_value").fetchall()
    for eid, kind, key, nb, ips in sample:
        L += [f"### {key} ({kind}) banners={nb} ips={ips}", ""]
        rows = con.execute(
            f"SELECT a.ip, a.port, a.module, a.org, b.domains[1:2], b.cert_subject_cn, "
            f"b.http_host, e.attribution FROM be_attr a JOIN b ON b.id = a.banner_id "
            f"JOIN banner_entity e ON e.banner_id = a.banner_id AND e.entity_id = a.entity_id "
            f"WHERE a.entity_id = ? ORDER BY a.ip, a.port LIMIT {EYEBALL_BANNERS}", [eid]
        ).fetchall()
        L += [f"- {x}" for x in rows] + [""]
    path.write_text("\n".join(L) + "\n", encoding="utf-8")
