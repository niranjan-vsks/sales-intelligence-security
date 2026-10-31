"""Section 7.4 steps 3 to 5: count rows and customer-domain entities per mapping class, overlaps,
and the 'prerequisite without the thing' group. Mapping: findings/07_what_we_sell_map.csv."""
import csv
import json

from common import FINDINGS, TAG, connect, out

con = connect()
maps = list(csv.DictReader(open(FINDINGS / "07_what_we_sell_map.csv", encoding="utf-8")))
sel = ", ".join(f"coalesce(({m['predicate_sql']}), false) AS {m['mapping_id']}" for m in maps)
con.execute(f"CREATE TEMP TABLE m AS SELECT id, domains, coalesce(ip_str, ipv6) ip, tags, cloud_provider, {sel} FROM b")
classes = {}
for m in maps:
    classes.setdefault(m["class"], []).append(m["mapping_id"])
cls_expr = ", ".join(f"({' OR '.join(ids)}) AS {c}" for c, ids in classes.items())
con.execute(f"CREATE TEMP TABLE mc AS SELECT id, domains, ip, tags, cloud_provider, {cls_expr} FROM m")
con.execute("""CREATE TEMP TABLE cust AS SELECT d FROM (SELECT unnest(domains) d, ip FROM mc)
  GROUP BY d HAVING count(DISTINCT ip) <= 50""")
con.execute("""CREATE TEMP TABLE ec AS SELECT d, bool_or(is_what_we_sell) sell, bool_or(is_a_substitute) sub,
  bool_or(is_a_prerequisite) pre, bool_or(is_a_blocker) blk FROM
  (SELECT unnest(domains) d, * EXCLUDE (domains) FROM mc) JOIN cust USING (d) GROUP BY d""")
KEYS = ["n", "sell", "substitute", "prerequisite", "blocker", "sell_and_sub", "pre_without_sell",
        "pre_without_sell_or_sub", "pre_and_blocker"]
res = {"tag": TAG}
res["per_mapping_rows"] = dict(zip([m["mapping_id"] for m in maps], con.execute(
    "SELECT " + ", ".join(f"count(*) FILTER (WHERE {m['mapping_id']})" for m in maps) + " FROM m").fetchone()))
res["banner"] = dict(zip(KEYS, con.execute("""SELECT count(*), count(*) FILTER (WHERE is_what_we_sell),
  count(*) FILTER (WHERE is_a_substitute), count(*) FILTER (WHERE is_a_prerequisite),
  count(*) FILTER (WHERE is_a_blocker), count(*) FILTER (WHERE is_what_we_sell AND is_a_substitute),
  count(*) FILTER (WHERE is_a_prerequisite AND NOT is_what_we_sell),
  count(*) FILTER (WHERE is_a_prerequisite AND NOT is_what_we_sell AND NOT is_a_substitute),
  count(*) FILTER (WHERE is_a_prerequisite AND is_a_blocker) FROM mc""").fetchone()))
res["entity"] = dict(zip(KEYS, con.execute("""SELECT count(*), count(*) FILTER (WHERE sell),
  count(*) FILTER (WHERE sub), count(*) FILTER (WHERE pre), count(*) FILTER (WHERE blk),
  count(*) FILTER (WHERE sell AND sub), count(*) FILTER (WHERE pre AND NOT sell),
  count(*) FILTER (WHERE pre AND NOT sell AND NOT sub), count(*) FILTER (WHERE pre AND blk)
  FROM ec""").fetchone()))
con.execute("CREATE TEMP TABLE has_cust AS SELECT DISTINCT id FROM (SELECT id, unnest(domains) d FROM mc) JOIN cust USING (d)")
res["disqualifiers"] = dict(zip(
    ["rows_no_domain", "rows_with_domain_but_only_operator_domains", "rows_tag_cdn", "rows_cloud_provider"],
    con.execute("""SELECT count(*) FILTER (WHERE len(domains) = 0),
      count(*) FILTER (WHERE len(domains) > 0 AND id NOT IN (SELECT id FROM has_cust)),
      count(*) FILTER (WHERE list_contains(tags, 'cdn')),
      count(*) FILTER (WHERE cloud_provider IS NOT NULL) FROM mc""").fetchone()))
out("07_negative.json").write_text(json.dumps(res, indent=1, default=str))
print(json.dumps(res, indent=1, default=str))
