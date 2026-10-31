"""Section 6.2: functional dependencies between categorical columns with cardinality < 5,000."""
import csv
import itertools

from common import TAG, connect, out

con = connect()
cols = [r for r in csv.DictReader(open(out("02_columns.csv"), encoding="utf-8"))
        if int(r["approx_unique"]) < 5000 and not r["type_in_file"].endswith("[]")
        and r["type_in_file"] in ("VARCHAR", "BOOLEAN", "BIGINT")]
names = [c["column"] for c in cols]
con.execute(f"CREATE TEMP TABLE c AS SELECT {', '.join(names)} FROM b")
rows = []
for a, b_ in itertools.combinations(names, 2):
    da, db, dab = con.execute(f"""SELECT count(DISTINCT {a}), count(DISTINCT {b_}),
      count(DISTINCT ({a}, {b_})) FROM c WHERE {a} IS NOT NULL AND {b_} IS NOT NULL""").fetchone()
    if not dab or da < 2 or db < 2:
        continue
    near = "a->b" if dab <= 1.05 * da else ("b->a" if dab <= 1.05 * db else "")
    rows.append({"a": a, "b": b_, "da": da, "db": db, "dab": dab, "dependency": near, "tag": TAG})
with open(out("06_fd.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
for r in rows:
    if r["dependency"]:
        print(r)
