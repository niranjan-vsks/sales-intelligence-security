"""Section 2: SUMMARIZE, per-column population, buckets, skew of sparse columns."""
import csv
import json

from common import TAG, connect, out

con = connect()
cols = con.execute("DESCRIBE SELECT * FROM b").fetchall()
con.execute("CREATE TEMP TABLE n AS SELECT count(*) AS n FROM b")
N = con.execute("SELECT n FROM n").fetchone()[0]

# raw SUMMARIZE (lists and big text excluded: SUMMARIZE on 2,000-char text is all noise)
skip = {"data", "extra_json", "http_headers"}
summ_cols = [c for c, t, *_ in cols if not t.endswith("[]") and c not in skip]
con.execute(f"CREATE TEMP TABLE summ AS SELECT * FROM (SUMMARIZE SELECT {', '.join(summ_cols)} FROM b)")
con.execute(f"COPY summ TO '{out('02_summarize.csv').as_posix()}' (HEADER)")
summ = {r[0]: r for r in con.execute("SELECT * FROM summ").fetchall()}

PH = "('null','none','n/a','na','nan','-','--','unknown','0','[]','{}')"
exprs = []
for c, t, *_ in cols:
    q = f'"{c}"'
    if t == "VARCHAR":
        exprs += [f"count({q})", f"count(*) FILTER (WHERE trim({q}) = '')",
                  f"count(*) FILTER (WHERE lower(trim({q})) IN {PH})",
                  f"count(*) FILTER (WHERE trim({q}) <> '' AND lower(trim({q})) NOT IN {PH})",
                  f"approx_count_distinct({q})"]
    elif t.endswith("[]"):
        exprs += [f"count({q})", f"count(*) FILTER (WHERE len({q}) = 0)", "0",
                  f"count(*) FILTER (WHERE len({q}) > 0)",
                  f"approx_count_distinct(array_to_string(list_sort({q}), '|'))"]
    else:
        exprs += [f"count({q})", "0", "0", f"count({q})", f"approx_count_distinct({q})"]
vals = con.execute(f"SELECT {', '.join(exprs)} FROM b").fetchone()

rows = []
for i, (c, t, *_) in enumerate(cols):
    nn, empty, ph, pop, au = vals[i * 5:(i + 1) * 5]
    s = summ.get(c)
    numeric = s is not None and t not in ("VARCHAR", "BOOLEAN")
    rows.append({
        "column": c, "type_in_file": t, "type_decided": t, "rows": N, "non_null": nn,
        "populated": pop, "populated_pct": round(100 * pop / N, 3),
        "placeholder_pct": round(100 * (ph + empty) / N, 3), "approx_unique": au,
        "min": (s[2] if s else "")[:60] if s else "", "max": (s[3] if s else "")[:60] if s else "",
        "median": s[8] if numeric else "", "notes": TAG,
    })
with open(out("02_columns.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)

# skew of sparse (<50 pct) columns on 5 dense low-cardinality columns
dense = ["module", "transport", "shodan_region", "country_code", "link"]
sparse = [r["column"] for r in rows if r["populated_pct"] < 50]
pop_expr = {}
for c, t, *_ in cols:
    if c in sparse:
        q = f'"{c}"'
        pop_expr[c] = (f"count(*) FILTER (WHERE len({q}) > 0)" if t.endswith("[]") else
                       f"count(*) FILTER (WHERE trim({q}) <> '')" if t == "VARCHAR" else
                       f"count({q})")
skew = []
for d in dense:
    res = con.execute(
        f"SELECT {d}, count(*), {', '.join(pop_expr[c] for c in sparse)} FROM b GROUP BY 1"
    ).fetchall()
    tot = [sum(r[i] for r in res) for i in range(1, 2 + len(sparse))]
    for j, c in enumerate(sparse):
        if tot[j + 1] == 0:
            continue
        top = sorted(res, key=lambda r: -r[2 + j])[:5]
        for r in top:
            sl, ov = r[2 + j] / tot[j + 1], r[1] / tot[0]
            skew.append({"column": c, "dense_col": d, "value": r[0],
                         "pct_of_populated": round(100 * sl, 2),
                         "pct_of_all": round(100 * ov, 2),
                         "lift": round(sl / ov, 2) if ov else None})
with open(out("02_sparse_skew.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(skew[0]))
    w.writeheader()
    w.writerows(skew)
print(json.dumps({"rows": N, "columns": len(cols), "sparse": len(sparse)}))
for r in rows:
    print(f"{r['column']:24} {r['type_in_file']:14} pop={r['populated_pct']:7.3f} ph={r['placeholder_pct']:6.3f} au={r['approx_unique']}")
