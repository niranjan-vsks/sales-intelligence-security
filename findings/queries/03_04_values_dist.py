"""Sections 3 and 4: value tables (values/), categorical tail shape, numeric quantiles + log histograms."""
import csv
import json

from common import TAG, connect, out

con = connect()
cols = list(csv.DictReader(open(out("02_columns.csv"), encoding="utf-8")))
N = int(cols[0]["rows"])
NUMERIC = {"BIGINT", "DOUBLE", "INTEGER"}
SKIP = {"id", "data", "extra_json", "http_headers", "hash", "http_html_hash", "http_headers_hash",
        "http_dom_hash", "http_title_hash", "http_components_hash", "http_favicon_hash"}
# hashes are identifiers, not quantities; they go to cardinality only
ID_NUMERIC = {"hash", "http_html_hash", "http_headers_hash", "http_dom_hash", "http_title_hash",
              "http_components_hash", "http_favicon_hash"}
LIMIT = 5000  # rows written per value file; files say if truncated

card, tails = [], []
con.execute("CREATE TEMP TABLE bb AS SELECT * EXCLUDE (data, extra_json, http_headers) FROM b")
for c in cols:
    name, t, au = c["column"], c["type_in_file"], int(c["approx_unique"])
    if name in SKIP and name not in ID_NUMERIC:
        continue
    is_list = t.endswith("[]")
    if t in NUMERIC and name not in ID_NUMERIC and not is_list:
        kind = "numeric"
    elif au >= 0.5 * N and not is_list:
        kind = "identifier"
    elif is_list:
        kind = "list"
    elif au <= 50:
        kind = "low"
    elif au <= 5000:
        kind = "mid"
    else:
        kind = "high"
    card.append({"column": name, "type": t, "approx_unique": au, "class": kind})
    if kind in ("numeric",):
        continue
    src = f"(SELECT unnest({name}) AS {name} FROM bb)" if is_list else "bb"
    fn = f"values/{name}{'_elements' if is_list else ''}.csv"
    con.execute(f"""CREATE OR REPLACE TEMP TABLE vt AS SELECT {name}::VARCHAR AS value, count(*) AS n
      FROM {src} GROUP BY 1""")
    tot, dist = con.execute("SELECT sum(n), count(*) FROM vt").fetchone()
    if kind != "identifier":
        con.execute(f"""COPY (SELECT value, n, round(100.0 * n / {tot or 1}, 4) AS pct FROM vt
          ORDER BY n DESC LIMIT {LIMIT}) TO '{out(fn).as_posix()}' (HEADER)""")
    r = con.execute("""WITH c AS (SELECT n, sum(n) OVER (ORDER BY n DESC ROWS UNBOUNDED PRECEDING)
        / sum(n) OVER () AS cum FROM vt)
      SELECT count(*) FILTER (WHERE cum <= 0.5) + 1, count(*) FILTER (WHERE cum <= 0.8) + 1,
             count(*) FILTER (WHERE cum <= 0.95) + 1, count(*) FILTER (WHERE n = 1), count(*),
             max(n) FROM c""").fetchone()
    tails.append({"column": name + ("[]" if is_list else ""), "class": kind,
                  "values_for_50pct": r[0], "values_for_80pct": r[1], "values_for_95pct": r[2],
                  "singletons": r[3], "distinct_values": r[4], "top_value_n": r[5],
                  "value_file": fn if kind != "identifier" else "", "truncated": dist > LIMIT,
                  "tag": TAG})

# numeric distributions, plus list lengths as derived numerics
num_exprs = [c["column"] for c in cols if c["type_in_file"] in NUMERIC and c["column"] not in ID_NUMERIC]
num_exprs += [f"len({c['column']})" for c in cols if c["type_in_file"].endswith("[]")]
nums = []
for e in num_exprs:
    r = con.execute(f"""SELECT count({e}),
      quantile_cont({e}, [0.01,0.05,0.1,0.25,0.5,0.75,0.9,0.95,0.99,0.999]),
      min({e}), max({e}), avg({e}), stddev({e}),
      count(*) FILTER (WHERE {e} = 0), count(*) FILTER (WHERE {e} < 0),
      mode({e}) FROM bb""").fetchone()
    hist = con.execute(f"""SELECT floor(log10(greatest({e}, 0) + 1))::INT AS bucket, count(*)
      FROM bb WHERE {e} IS NOT NULL GROUP BY 1 ORDER BY 1""").fetchall()
    top = con.execute(f"""SELECT {e}, count(*) FROM bb WHERE {e} IS NOT NULL GROUP BY 1
      ORDER BY 2 DESC LIMIT 5""").fetchall()
    nums.append({"expr": e, "non_null": r[0], "q": [round(x, 3) for x in (r[1] or [])],
                 "min": r[2], "max": r[3], "avg": r[4], "std": r[5], "zeros": r[6],
                 "negatives": r[7], "mode": r[8], "log10_hist": hist, "top5_values": top})

for name, rows in (("03_cardinality.csv", card), ("04_categorical_tails.csv", tails)):
    with open(out(name), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
out("04_numeric.json").write_text(json.dumps(nums, indent=1, default=str))
print(f"{TAG} card={len(card)} tails={len(tails)} numeric={len(nums)}")
