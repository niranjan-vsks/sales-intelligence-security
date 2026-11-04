"""Score the diff against the truth file (cards/P6.md step 5).

For each perturbation type: recall = perturbed entities with at least 1 matching event over
perturbed entities; precision = matching events on perturbed entities over all matching events.
A perturbation is at banner grain and an event at entity grain, so some perturbations cannot map
1:1 to an event (a dropped banner whose ip:port another banner still answers; a removed WAF
while another banner still names one). Each miss is put in a named category by a query on the
2 files' own tables, not by lowering the bar; `unexplained` must stay 0."""

from typing import Any

import duckdb
import pyarrow as pa
from pydantic import BaseModel

from sis import db, delta_config, paths
from sis.delta.diff import _lit, load_side
from sis.delta.truth import PERTURBATIONS

# perturbation -> (event types that detect it, subject the event must have or None)
DETECTED_BY: dict[str, tuple[tuple[str, ...], str | None]] = {
    "drop_banner": (("service_gone", "entity_gone"), None),
    "new_banner": (("service_new",), None),
    "expire_cert": (("cert_expired_since",), None),
    "remove_waf": (("protection_removed",), None),
    "add_waf": (("protection_added",), None),
    "add_vuln": (("signal_appeared",), "A_inferred_cves"),
}

# Why a perturbed entity can have no matching event, in the order they are tried. Each is a
# predicate over `m` (the missed (ptype, entity_id) rows) and the temp tables of diff.load_side.
GONE = ("entity not active in the new file", "NOT EXISTS (SELECT 1 FROM act_b x "
        "WHERE x.entity_id = m.entity_id)")
MISS_CATEGORIES: dict[str, list[tuple[str, str]]] = {
    "drop_banner": [
        ("dropped ip:port still answered by another banner",
         "NOT EXISTS (SELECT 1 FROM t WHERE t.ptype = m.ptype AND t.entity_id = m.entity_id "
         "AND NOT EXISTS (SELECT 1 FROM svc_b s WHERE s.entity_id = t.entity_id "
         "AND s.skey = coalesce(t.ip, '') || ':' || coalesce(t.port::VARCHAR, '')))"),
    ],
    "new_banner": [
        GONE,
        ("new ip:port already a service of the entity",
         "NOT EXISTS (SELECT 1 FROM t WHERE t.ptype = m.ptype AND t.entity_id = m.entity_id "
         "AND NOT EXISTS (SELECT 1 FROM svc_a s WHERE s.entity_id = t.entity_id "
         "AND s.skey = coalesce(t.ip, '') || ':' || coalesce(t.new_port::VARCHAR, '')))"),
    ],
    "expire_cert": [
        GONE,
        ("entity already had an expired certificate",
         "EXISTS (SELECT 1 FROM sig_a s WHERE s.entity_id = m.entity_id "
         "AND s.signal_id = 'B_expired')"),
    ],
    "remove_waf": [
        GONE,
        ("another banner of the entity still names a WAF",
         "EXISTS (SELECT 1 FROM waf_b w WHERE w.entity_id = m.entity_id)"),
    ],
    "add_waf": [
        GONE,
        ("entity already had D_waf",
         "EXISTS (SELECT 1 FROM sig_a s WHERE s.entity_id = m.entity_id "
         "AND s.signal_id = 'D_waf')"),
    ],
    "add_vuln": [
        GONE,
        ("entity already had A_inferred_cves",
         "EXISTS (SELECT 1 FROM sig_a s WHERE s.entity_id = m.entity_id "
         "AND s.signal_id = 'A_inferred_cves')"),
    ],
}


class TypeStats(BaseModel):
    ptype: str
    eligible: int
    selected: int
    applied: int
    perturbed_entities: int
    detected_entities: int
    recall: float | None
    recall_min: float | None
    passed: bool | None
    events_of_type: int
    events_on_perturbed: int
    precision: float | None
    misses: dict[str, int]
    other_sources: dict[str, int]  # events outside this type's entities, by what perturbed them
    unexplained: int
    recall_detectable: float | None


def _ratio(n: int, d: int) -> float | None:
    return n / d if d else None


def _events_view(con: duckdb.DuckDBPyConnection, from_file: str, to_file: str) -> None:
    con.execute(f"""
        CREATE OR REPLACE TEMP VIEW evs AS
        SELECT * FROM read_parquet({_lit(paths.events_path().as_posix())})
        WHERE from_file = {_lit(from_file)} AND to_file = {_lit(to_file)}""")


def verify(from_file: str, to_file: str, truth: dict[str, Any]) -> list[TypeStats]:
    """Precision, recall and the miss categories per perturbation type."""
    recall_min = delta_config.load().verify.recall_min
    con = db.connect()
    con.execute("SET lambda_syntax = 'ENABLE_SINGLE_ARROW'")
    for side, fid in (("a", from_file), ("b", to_file)):
        load_side(con, side, fid)
    d_b = paths.file_dir(to_file)
    con.execute(f"""
        CREATE TEMP TABLE waf_b AS
        SELECT DISTINCT be.entity_id
        FROM read_parquet({_lit(paths.banners_glob(to_file))}) b
        JOIN read_parquet({_lit((d_b / 'banner_entity.parquet').as_posix())}) be
          ON be.banner_id = b.id
        WHERE b.http_waf IS NOT NULL""")
    rows = [{"ptype": p, "banner_id": r["banner_id"], "entity_id": r["entity_id"],
             "ip": r["ip"], "port": r["port"], "new_port": r.get("new_port")}
            for p in PERTURBATIONS for r in truth["items"][p]]
    schema = pa.schema([("ptype", pa.string()), ("banner_id", pa.string()),
                        ("entity_id", pa.string()), ("ip", pa.string()), ("port", pa.int64()),
                        ("new_port", pa.int64())])
    con.register("t_arrow", pa.Table.from_pylist(rows, schema=schema))
    con.execute("CREATE TEMP TABLE t AS SELECT * FROM t_arrow")
    _events_view(con, from_file, to_file)

    out: list[TypeStats] = []
    for ptype in PERTURBATIONS:
        types, subject = DETECTED_BY[ptype]
        match = f"event_type IN ({', '.join(_lit(x) for x in types)})"
        if subject:
            match += f" AND subject = {_lit(subject)}"
        con.execute(f"""
            CREATE OR REPLACE TEMP TABLE m_all AS
            SELECT DISTINCT ptype, entity_id FROM t WHERE ptype = {_lit(ptype)}""")
        n_pert = int(con.execute("SELECT count(*) FROM m_all").fetchall()[0][0])
        con.execute(f"""
            CREATE OR REPLACE TEMP TABLE m AS
            SELECT * FROM m_all a
            WHERE NOT EXISTS (SELECT 1 FROM evs e WHERE e.entity_id = a.entity_id AND {match})""")
        n_miss = int(con.execute("SELECT count(*) FROM m").fetchall()[0][0])
        misses: dict[str, int] = {}
        left = "true"  # rows not yet explained
        for name, pred in MISS_CATEGORIES[ptype]:
            n = int(con.execute(
                f"SELECT count(*) FROM m WHERE {left} AND ({pred})").fetchall()[0][0])
            misses[name] = n
            left = f"{left} AND NOT ({pred})"
        unexplained = int(con.execute(f"SELECT count(*) FROM m WHERE {left}").fetchall()[0][0])
        n_of_type = int(con.execute(
            f"SELECT count(*) FROM evs WHERE {match}").fetchall()[0][0])
        n_on = int(con.execute(
            f"SELECT count(*) FROM evs WHERE {match} "
            "AND entity_id IN (SELECT entity_id FROM m_all)").fetchall()[0][0])
        other_sources = dict(con.execute(f"""
            SELECT src, count(*) FROM (
                SELECT e.event_id,
                       coalesce(string_agg(DISTINCT t.ptype, '+' ORDER BY t.ptype),
                                'no perturbation') AS src
                FROM evs e LEFT JOIN t ON t.entity_id = e.entity_id
                WHERE {match} AND e.entity_id NOT IN (SELECT entity_id FROM m_all)
                GROUP BY e.event_id) GROUP BY src ORDER BY 2 DESC, 1""").fetchall())
        detected = n_pert - n_miss
        recall = _ratio(detected, n_pert)
        floor = recall_min.get(ptype)
        explained = sum(misses.values())
        out.append(TypeStats(
            ptype=ptype, eligible=truth["eligible"][ptype], selected=truth["selected"][ptype],
            applied=truth["applied"][ptype], perturbed_entities=n_pert,
            detected_entities=detected, recall=recall, recall_min=floor,
            passed=None if floor is None or recall is None else recall >= floor,
            events_of_type=n_of_type, events_on_perturbed=n_on,
            precision=_ratio(n_on, n_of_type), misses=misses,
            other_sources=other_sources, unexplained=unexplained,
            recall_detectable=_ratio(detected, n_pert - explained)))
    con.close()
    return out
