"""Section 7.2 reading aid: top 25 rare values per rep at entity grain (rows >= 300) and at banner
grain (rows >= 1000), from 07_rare_values.csv. Written to 07_rare_top_by_rep.csv."""
import pandas as pd

from common import out

r = pd.read_csv(out("07_rare_values.csv"))
REPS = ["r_vuln", "r_cvss7", "r_selfsigned", "r_certexpired", "r_eol", "r_waf", "r_ssl", "r_cloud"]
parts = []
for grain, floor in (("entity", 300), ("banner", 1000)):
    x = r[(r.grain == grain) & (r.rows >= floor) & (r.value != "<populated>")]
    for rep in REPS:
        t = x.sort_values(f"lift_{rep}", ascending=False).head(25).copy()
        t.insert(0, "ranked_by", rep)
        parts.append(t)
pd.concat(parts).to_csv(out("07_rare_top_by_rep.csv"), index=False)
print("ok")
