"""Section 5: list columns, JSON key trees (extra_json, http_headers, http_identifiers), prose profiles."""
import json

from common import TAG, connect, out

con = connect()
N = con.execute("SELECT count(*) FROM b").fetchone()[0]
res = {"tag": TAG, "rows": N}

# protocol blocks: fill over all rows, and over rows of the module that produces the block
con.execute("CREATE TEMP TABLE bl AS SELECT module, unnest(blocks) blk FROM b")
con.execute("CREATE TEMP TABLE mods AS SELECT module, count(*) n FROM b GROUP BY 1")
con.execute(f"""COPY (WITH t AS (SELECT blk, count(*) n FROM bl GROUP BY 1),
  bm AS (SELECT blk, module, count(*) n FROM bl GROUP BY 1, 2),
  top AS (SELECT blk, arg_max(module, n) top_module, max(n) top_n, count(*) n_modules FROM bm GROUP BY 1)
  SELECT t.blk AS block, t.n, round(100.0 * t.n / {N}, 4) AS pct_all_rows, top.n_modules,
    top.top_module, round(100.0 * top.top_n / t.n, 2) AS pct_from_top_module,
    round(100.0 * top.top_n / m.n, 2) AS fill_within_top_module
  FROM t JOIN top USING (blk) JOIN mods m ON m.module = top.top_module ORDER BY t.n DESC)
  TO '{out('values/blocks_fill.csv').as_posix()}' (HEADER)""")

# JSON key inventory of extra_json: level 1 (block) and level 2 (keys inside each block)
con.execute("""CREATE TEMP TABLE ej AS SELECT module, extra_json::JSON j FROM b
  WHERE extra_json IS NOT NULL""")
con.execute(f"""COPY (SELECT k1, k2, count(*) n, round(100.0*count(*)/{N}, 4) pct_all FROM (
    SELECT k1, unnest(CASE WHEN json_type(j -> k1) = 'OBJECT' THEN json_keys(j -> k1)
                           ELSE ['<' || json_type(j -> k1) || '>'] END) k2
    FROM (SELECT j, unnest(json_keys(j)) k1 FROM ej)) GROUP BY ALL ORDER BY k1, n DESC)
  TO '{out('values/extra_json_keys.csv').as_posix()}' (HEADER)""")
res["extra_json_rows"] = con.execute("SELECT count(*) FROM ej").fetchone()[0]

# http_identifiers keys
res["http_identifiers_keys"] = con.execute("""SELECT k, count(*) FROM (SELECT unnest(json_keys(
  http_identifiers::JSON)) k FROM b WHERE http_identifiers IS NOT NULL) GROUP BY 1 ORDER BY 2 DESC
  LIMIT 30""").fetchall()

# list columns: length quantiles (also in 04) and element counts are in values/*_elements.csv
res["list_lengths"] = {}
for c in ("hostnames", "domains", "tags", "cpe23", "vuln_ids", "http_components",
          "http_component_cats", "http_header_names", "ssl_versions", "ssl_alpn", "cert_san",
          "opts_vulns", "blocks"):
    res["list_lengths"][c] = con.execute(f"""SELECT count({c}), count(*) FILTER (WHERE len({c})>0),
      quantile_disc(len({c}), [0.5, 0.9, 0.99]), max(len({c})) FROM b""").fetchone()

# high-cardinality text detection (5)
res["text_detect"] = {}
for c in ("data", "http_title", "http_server", "org", "isp", "product", "version", "info",
          "http_location", "cert_subject_cn", "cert_issuer_o", "city", "http_host"):
    res["text_detect"][c] = con.execute(f"""SELECT avg(length({c})), quantile_cont(length({c}), 0.95),
      avg(({c} LIKE '[%' OR {c} LIKE '{{%')::INT), avg(({c} LIKE '%,%')::INT),
      avg(({c} LIKE '%|%')::INT), avg(({c} LIKE '%;%')::INT), avg(({c} LIKE 'http%')::INT),
      avg(length({c}) - length(replace({c}, ' ', ''))),
      count(DISTINCT {c}) / count({c}) FROM b WHERE {c} IS NOT NULL""").fetchone()

# prose profiles: data (banner text) and http_title
STOP = "('the','and','for','with','you','are','this','that','not','from','your','was','has','have','but','can','all','www','http','https','com','html')"
for c in ("data", "http_title"):
    res[f"{c}_dup_rate"] = con.execute(f"SELECT count(DISTINCT {c}) / count({c}) FROM b").fetchone()[0]
    res[f"{c}_len_q"] = con.execute(f"""SELECT quantile_disc(length({c}), [0.1,0.5,0.9,0.99]), max(length({c}))
      FROM b WHERE {c} IS NOT NULL""").fetchone()
    con.execute(f"""CREATE OR REPLACE TEMP TABLE toks AS SELECT rid, list_filter(string_split(
        regexp_replace(lower({c}), '[^a-z0-9 ]', ' ', 'g'), ' '), x -> length(x) > 2
        AND x NOT IN {STOP}) t FROM (SELECT row_number() OVER () rid, {c} FROM
        (SELECT {c} FROM b WHERE {c} IS NOT NULL USING SAMPLE 200000 ROWS (reservoir, 7)))""")
    con.execute(f"""COPY (SELECT tok, count(*) n FROM (SELECT unnest(t) tok FROM toks) GROUP BY 1
      ORDER BY 2 DESC LIMIT 500) TO '{out(f'values/{c}_tokens.csv').as_posix()}' (HEADER)""")
    con.execute(f"""COPY (SELECT bg, count(*) n FROM (SELECT unnest(list_transform(
        range(1, len(t)), i -> t[i] || ' ' || t[i+1])) bg FROM toks) GROUP BY 1
      ORDER BY 2 DESC LIMIT 500) TO '{out(f'values/{c}_bigrams.csv').as_posix()}' (HEADER)""")
    with open(out(f"values/{c}_random50.txt"), "w", encoding="utf-8") as f:
        for (x,) in con.execute(f"""SELECT left({c}, 400) FROM b WHERE {c} IS NOT NULL
            USING SAMPLE 50 ROWS (reservoir, 11)""").fetchall():
            f.write(repr(x) + "\n")
out("05_semistructured.json").write_text(json.dumps(res, indent=1, default=str))
print(json.dumps(res, indent=1, default=str)[:6000])
