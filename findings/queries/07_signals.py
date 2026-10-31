"""Section 7: correlation clusters (7.1), rare values with lift (7.2), derived signals (7.3),
at 2 grains: banner and rolled-up entity (customer domain, see 06_relationships.md roll-up).

Representative indicators (reps) are 0/1 per banner. Lift = rate of the rep in a slice / rate in
the population. max_abs_log2_lift is the largest |log2 lift| across reps with >= 5 positives.
"""
import csv
import itertools
import json
import math

import numpy as np
import pandas as pd

from common import TAG, connect, out

con = connect()
DOMAIN_IP_CUTOFF = 50  # from 06_rollup.json domain_ip_cutoffs; domains on > 50 IPs are operator rDNS zones
FLOOR, CEIL = 50, 0.02

con.execute(f"""CREATE TEMP TABLE dstat AS SELECT d, count(DISTINCT coalesce(ip_str, ipv6)) ips
  FROM (SELECT unnest(domains) d, ip_str, ipv6 FROM b) GROUP BY 1""")
con.execute(f"CREATE TEMP TABLE cust AS SELECT d FROM dstat WHERE ips <= {DOMAIN_IP_CUTOFF}")

con.execute("""CREATE TEMP TABLE f AS SELECT
  id, module, port, transport, coalesce(ip_str, ipv6) ip, org, asn, country_code, link, product, os,
  devicetype, cloud_provider, http_waf, http_server, cert_issuer_o, ssl_version, http_status::VARCHAR http_status_s,
  tags, http_components, http_component_cats, http_header_names, blocks, cpe23, ssl_versions,
  list_transform(cpe23, x -> split_part(x, ':', 4)) cpe_vendor,
  domains,
  uptime, coalesce(n_vulns, 0) n_vulns, max_cvss, max_epss, http_status, http_redirects, http_html_len,
  ssl_cipher_bits, cert_pubkey_bits, ssl_chain_len, data_len, record_bytes,
  len(tags) n_tags, len(hostnames) n_hostnames, len(domains) n_domains, len(cpe23) n_cpe,
  len(http_components) n_components, len(http_header_names) n_headers,
  date_diff('day', cert_issued, timestamp) cert_age_days,
  date_diff('day', timestamp, cert_expires) cert_days_to_expiry,
  -- reps (0/1)
  (coalesce(n_vulns, 0) > 0)::INT r_vuln,
  (coalesce(max_cvss, 0) >= 7)::INT r_cvss7,
  (http_status IS NOT NULL)::INT r_http,
  (ssl_version IS NOT NULL)::INT r_ssl,
  coalesce(cert_self_signed, false)::INT r_selfsigned,
  coalesce(cert_expired, false)::INT r_certexpired,
  (cloud_provider IS NOT NULL)::INT r_cloud,
  (http_waf IS NOT NULL)::INT r_waf,
  coalesce(len(cpe23) > 0, false)::INT r_cpe,
  (data_len > 0)::INT r_banner_text,
  coalesce(list_contains(tags, 'eol-product'), false)::INT r_eol
FROM b""")
REPS = ["r_vuln", "r_cvss7", "r_http", "r_ssl", "r_selfsigned", "r_certexpired", "r_cloud",
        "r_waf", "r_cpe", "r_banner_text", "r_eol"]
# banner -> customer domain (a banner can belong to several)
con.execute("""CREATE TEMP TABLE bd AS SELECT DISTINCT id, d FROM
  (SELECT id, unnest(domains) d FROM f) JOIN cust USING (d)""")
# entity-level reps = any() over the entity's banners
con.execute(f"""CREATE TEMP TABLE er AS SELECT d, {', '.join(f'max({r}) {r}' for r in REPS)},
  count(*) n_banners, count(DISTINCT ip) n_ips, count(DISTINCT port) n_ports,
  count(DISTINCT module) n_modules, count(DISTINCT org) n_orgs, sum(n_vulns) sum_vulns,
  max(max_cvss) max_cvss, avg(r_vuln) share_vuln, count(DISTINCT country_code) n_countries
  FROM bd JOIN f USING (id) GROUP BY d""")
N = con.execute("SELECT count(*) FROM f").fetchone()[0]
NE = con.execute("SELECT count(*) FROM er").fetchone()[0]
pop = con.execute(f"SELECT {', '.join(f'avg({r})' for r in REPS)} FROM f").fetchone()
epop = con.execute(f"SELECT {', '.join(f'avg({r})' for r in REPS)} FROM er").fetchone()
summary = {"tag": TAG, "rows": N, "entities": NE, "banners_attributed":
           con.execute("SELECT count(DISTINCT id) FROM bd").fetchone()[0],
           "pop_rates": dict(zip(REPS, pop)), "entity_pop_rates": dict(zip(REPS, epop))}

# ---------------- 7.1 numeric Spearman ----------------
NUM = ["port", "uptime", "n_vulns", "max_cvss", "max_epss", "http_status", "http_redirects",
       "http_html_len", "ssl_cipher_bits", "cert_pubkey_bits", "ssl_chain_len", "data_len",
       "record_bytes", "n_tags", "n_hostnames", "n_domains", "n_cpe", "n_components", "n_headers",
       "cert_age_days", "cert_days_to_expiry"] + REPS
df = con.execute(f"SELECT {', '.join(NUM)} FROM f USING SAMPLE 2000000 ROWS (reservoir, 3)").df()
df = df.astype("float64")
sp = df.corr(method="spearman", min_periods=500)
sp.round(4).to_csv(out("07_corr_numeric.csv"))

# ---------------- 7.1 categorical Cramer's V ----------------
CAT = ["module", "transport", "country_code", "link", "cloud_provider", "http_waf", "product", "os",
       "devicetype", "cert_issuer_o", "ssl_version", "http_status_s", "org", "port_s"]
con.execute("CREATE TEMP TABLE fc AS SELECT *, port::VARCHAR port_s FROM f USING SAMPLE 2000000 ROWS (reservoir, 5)")
for c in CAT:  # top 30 values + other, NULL as its own level
    con.execute(f"""CREATE OR REPLACE TEMP TABLE top_{c} AS SELECT {c} v FROM fc WHERE {c} IS NOT NULL
      GROUP BY 1 ORDER BY count(*) DESC LIMIT 30""")
lvl = {c: f"CASE WHEN {c} IS NULL THEN '<null>' WHEN {c} IN (SELECT v FROM top_{c}) THEN {c} ELSE '<other>' END"
       for c in CAT}
cv = []
for a, b_ in itertools.combinations(CAT, 2):
    ct = con.execute(f"SELECT {lvl[a]} a, {lvl[b_]} b, count(*) n FROM fc GROUP BY 1, 2").df()
    t = ct.pivot_table(index="a", columns="b", values="n", fill_value=0).to_numpy(dtype=float)
    n = t.sum()
    e = np.outer(t.sum(1), t.sum(0)) / n
    chi2 = ((t - e) ** 2 / np.where(e == 0, 1, e)).sum()
    k = min(t.shape) - 1
    cv.append({"a": a, "b": b_, "cramers_v": round(math.sqrt(chi2 / (n * k)), 4) if k > 0 else None})
pd.DataFrame(cv).sort_values("cramers_v", ascending=False).to_csv(out("07_corr_categorical.csv"), index=False)

# numeric vs categorical: median per level vs overall IQR
nvc = []
NUM_NVC = ["uptime", "n_vulns", "data_len", "http_html_len", "n_headers", "n_components",
           "cert_age_days", "cert_days_to_expiry", "record_bytes"]
for c in ["module", "country_code", "cloud_provider", "product", "link", "org"]:
    for m in NUM_NVC:
        q1, q3 = con.execute(f"SELECT quantile_cont({m}, 0.25), quantile_cont({m}, 0.75) FROM fc").fetchone()
        if q1 is None:
            continue
        rows = con.execute(f"""SELECT {lvl[c]} lv, median({m}) med, count({m}) n FROM fc
          GROUP BY 1 HAVING count({m}) >= 200""").fetchall()
        meds = [r[1] for r in rows if r[1] is not None]
        if len(meds) > 1 and (max(meds) - min(meds)) > (q3 - q1):
            nvc.append({"categorical": c, "numeric": m, "iqr": q3 - q1, "min_median": min(meds),
                        "max_median": max(meds), "levels": len(meds)})
pd.DataFrame(nvc).to_csv(out("07_num_vs_cat.csv"), index=False)

# ---------------- 7.2 rare values, banner and entity grain ----------------
SCALAR = ["module", "port", "product", "os", "devicetype", "country_code", "link", "cloud_provider",
          "http_waf", "http_server", "cert_issuer_o", "ssl_version", "http_status_s", "org", "asn"]
LISTS = ["tags", "http_components", "http_component_cats", "http_header_names", "blocks",
         "cpe_vendor", "ssl_versions"]
rare = []
rep_sum = ", ".join(f"sum({r}) s_{r}" for r in REPS)
erep_sum = ", ".join(f"sum(er.{r}) s_{r}" for r in REPS)


def lifts(row, base, n):
    out_ = {}
    best = 0.0
    for r, p in zip(REPS, base):
        s = row[f"s_{r}"]
        rate = s / n if n else 0
        lift = rate / p if p else None
        out_[f"lift_{r}"] = round(lift, 3) if lift is not None else None
        if lift and s >= 5:
            best = max(best, abs(math.log2(lift)))
        elif lift == 0 and p * n >= 5:  # expected >= 5 positives, saw none
            best = max(best, 5.0)
    out_["max_abs_log2_lift"] = round(best, 3)
    return out_


for col in SCALAR + LISTS:
    is_list = col in LISTS
    expr = f"unnest({col})" if is_list else f"{col}::VARCHAR"
    q = f"""SELECT v, count(*) n, {rep_sum} FROM (SELECT DISTINCT id, {expr} v, {', '.join(REPS)} FROM f)
      WHERE v IS NOT NULL GROUP BY v HAVING count(*) >= {FLOOR} AND count(*) <= {CEIL * N}"""
    for row in con.execute(q).df().to_dict("records"):
        rare.append({"grain": "banner", "column": col, "value": row["v"], "rows": row["n"],
                     "pct": round(100 * row["n"] / N, 4), **lifts(row, pop, row["n"])})
    qe = f"""SELECT v, count(*) n, {erep_sum} FROM (SELECT DISTINCT bd.d, {expr.replace(col, 'f.' + col)} v
        FROM bd JOIN f USING (id)) x JOIN er ON er.d = x.d
      WHERE v IS NOT NULL GROUP BY v HAVING count(*) >= {FLOOR} AND count(*) <= {CEIL * NE}"""
    for row in con.execute(qe).df().to_dict("records"):
        rare.append({"grain": "entity", "column": col, "value": row["v"], "rows": row["n"],
                     "pct": round(100 * row["n"] / NE, 4), **lifts(row, epop, row["n"])})
# sparse columns: populated slice as the value
SPARSE = {"uptime": "uptime IS NOT NULL", "os": "os IS NOT NULL", "product": "product IS NOT NULL",
          "cpe23": "len(cpe23) > 0", "http_waf": "http_waf IS NOT NULL",
          "cloud_provider": "cloud_provider IS NOT NULL", "domains": "len(domains) > 0",
          "max_cvss": "max_cvss IS NOT NULL", "ssl_version": "ssl_version IS NOT NULL",
          "http_status": "http_status IS NOT NULL", "devicetype": "devicetype IS NOT NULL"}
for col, cond in SPARSE.items():
    row = con.execute(f"SELECT count(*) n, {rep_sum} FROM f WHERE {cond}").df().to_dict("records")[0]
    rare.append({"grain": "banner", "column": col, "value": "<populated>", "rows": row["n"],
                 "pct": round(100 * row["n"] / N, 4), **lifts(row, pop, row["n"]),
                 })
rare_df = pd.DataFrame(rare).sort_values(["grain", "max_abs_log2_lift", "rows"], ascending=[True, False, False])
rare_df["notes"] = TAG
rare_df.to_csv(out("07_rare_values.csv"), index=False)

# ---------------- 7.3 derived ----------------
derived = []
COUNTS = ["n_vulns", "n_cpe", "n_components", "n_headers", "n_hostnames", "n_tags", "data_len",
          "http_html_len", "record_bytes"]
dfx = con.execute(f"SELECT {', '.join(COUNTS)}, {', '.join(REPS)} FROM f USING SAMPLE 2000000 ROWS (reservoir, 9)").df().astype("float64")


def decile_lift(series, frame, base_reps):
    s = series.dropna()
    if s.nunique() < 3:
        return None, None
    lo, hi = s.quantile(0.1), s.quantile(0.9)
    top, bot = frame.loc[s[s >= hi].index], frame.loc[s[s <= lo].index]
    res = {}
    for r in base_reps:
        a, b_ = top[r].mean(), bot[r].mean()
        res[r] = round(a / b_, 3) if b_ else (None if a == 0 else float("inf"))
    return res, round(100 * len(s) / len(frame), 3)


cid = 0
for a, b_ in itertools.combinations(COUNTS, 2):
    ratio = dfx[a] / dfx[b_].replace(0, np.nan)
    if ratio.notna().sum() < 1000:
        continue
    ra, rb = ratio.corr(dfx[a], method="spearman"), ratio.corr(dfx[b_], method="spearman")
    if abs(ra) >= 0.9 or abs(rb) >= 0.9:
        continue
    lift, cov = decile_lift(ratio, dfx, REPS)
    if lift is None:
        continue
    cid += 1
    derived.append({"candidate_id": f"D-R{cid:02d}", "family": "ratio", "formula": f"{a} / {b_}",
                    "inputs": f"{a},{b_}", "coverage_pct": cov,
                    "top_vs_bottom_decile_lift": json.dumps(lift),
                    "notes": f"{TAG}; spearman vs inputs {ra:.2f},{rb:.2f}"})

# entity-level derived (counts per rolled-up entity)
edf = con.execute("SELECT * FROM er").df()
for i, c in enumerate(["n_banners", "n_ips", "n_ports", "n_modules", "n_orgs", "sum_vulns",
                       "share_vuln", "n_countries"]):
    lift, cov = decile_lift(edf[c].astype(float), edf.astype({r: float for r in REPS}), REPS)
    derived.append({"candidate_id": f"D-E{i+1:02d}", "family": "entity_count", "formula": c,
                    "inputs": "bd x f grouped by customer domain", "coverage_pct": cov,
                    "top_vs_bottom_decile_lift": json.dumps(lift) if lift else "",
                    "notes": f"{TAG}; entity grain; quantiles {edf[c].quantile([.5,.9,.99]).round(2).tolist()}"})

# peer gaps: peer = module x country_code (lowest-cardinality reps that split numerics, 07_num_vs_cat)
peer = con.execute("""WITH g AS (SELECT module, country_code, count(*) n FROM f GROUP BY 1, 2)
  SELECT sum(n) FILTER (WHERE n < 30) / sum(n), count(*) FILTER (WHERE n >= 30) FROM g""").fetchone()
summary["peer_module_country_rows_in_undersized_groups"] = peer[0]
summary["peer_groups_ge30"] = peer[1]
spread = []
for m in ["uptime", "n_vulns", "n_headers", "n_components", "data_len", "cert_age_days", "cert_days_to_expiry"]:
    r = con.execute(f"""WITH g AS (SELECT module, country_code, quantile_cont({m}, 0.25) q1,
        quantile_cont({m}, 0.75) q3, count({m}) n FROM f GROUP BY 1, 2 HAVING count({m}) >= 30)
      SELECT median(q3 - q1), (SELECT quantile_cont({m}, 0.75) - quantile_cont({m}, 0.25) FROM f),
             count(*) FROM g""").fetchone()
    spread.append({"feature": m, "median_within_peer_iqr": r[0], "overall_iqr": r[1], "peer_groups": r[2]})
    lift_rows = con.execute(f"""SELECT pr >= 0.9 AS hi, {', '.join(f'avg({x})' for x in REPS)} FROM (
        SELECT *, percent_rank() OVER (PARTITION BY module, country_code ORDER BY {m}) pr FROM f
        WHERE {m} IS NOT NULL) WHERE pr <= 0.1 OR pr >= 0.9 GROUP BY 1""").fetchall()
    if len(lift_rows) == 2:
        lo = [x for x in lift_rows if not x[0]][0][1:]
        hi = [x for x in lift_rows if x[0]][0][1:]
        cid += 1
        derived.append({"candidate_id": f"D-P{cid:02d}", "family": "peer_gap",
                        "formula": f"percent_rank({m}) within module x country_code",
                        "inputs": m, "coverage_pct": round(100 * con.execute(
                            f"SELECT avg(({m} IS NOT NULL)::INT) FROM f").fetchone()[0], 3),
                        "top_vs_bottom_decile_lift": json.dumps({x: (round(h / l, 3) if l else None)
                                                                 for x, h, l in zip(REPS, hi, lo)}),
                        "notes": f"{TAG}; within-peer IQR {r[0]} vs overall {r[1]}"})
summary["peer_spread"] = spread
with open(out("07_derived.csv"), "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(derived[0]))
    w.writeheader()
    w.writerows(derived)
out("07_summary.json").write_text(json.dumps(summary, indent=1, default=str))
print(json.dumps(summary, indent=1, default=str))
