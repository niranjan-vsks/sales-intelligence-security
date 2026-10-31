"""Section 1d / 6.1: grain, uniqueness, and candidate roll-up keys from banner to organisation."""
import json

from common import TAG, connect, out

con = connect()
con.execute("""CREATE TEMP TABLE k AS SELECT
  id, coalesce(ip_str, ipv6) AS ip, asn, org, domains, hostnames, cert_subject_cn,
  http_host, port, transport, module, timestamp, hash FROM b""")
res = {"tag": TAG}
res["rows"], res["distinct_id"], res["distinct_ip_port_transport"], res["distinct_ip_port_ts"], \
    res["distinct_hash"] = con.execute("""SELECT count(*), count(DISTINCT id),
  count(DISTINCT (ip, port, transport)), count(DISTINCT (ip, port, transport, timestamp)),
  count(DISTINCT hash) FROM k""").fetchone()
res["ip_port_groups_with_dupes"], res["rows_in_dupe_groups"] = con.execute("""
  SELECT count(*), sum(n) FROM (SELECT ip, port, transport, count(*) n FROM k
  GROUP BY ALL HAVING n > 1)""").fetchone()

keys = {
    "ip": "SELECT id, ip AS key FROM k",
    "asn": "SELECT id, asn AS key FROM k",
    "org": "SELECT id, org AS key FROM k",
    "domain": "SELECT id, unnest(domains) AS key FROM k",
    "hostname": "SELECT id, unnest(hostnames) AS key FROM k",
    "cert_subject_cn": "SELECT id, cert_subject_cn AS key FROM k",
    "http_host": "SELECT id, http_host AS key FROM k",
}
res["keys"] = {}
for name, sql in keys.items():
    r = con.execute(f"""WITH x AS ({sql}), x2 AS (SELECT * FROM x WHERE key IS NOT NULL AND key <> ''),
      g AS (SELECT key, count(DISTINCT id) n FROM x2 GROUP BY key)
      SELECT (SELECT count(DISTINCT key) FROM x2),
             (SELECT count(DISTINCT id) FROM x2),
             (SELECT quantile_disc(n, [0.5, 0.9, 0.99, 0.999]) FROM g),
             (SELECT max(n) FROM g),
             (SELECT count(*) FILTER (WHERE n = 1) FROM g)""").fetchone()
    res["keys"][name] = {"distinct": r[0], "banners_populated": r[1],
                         "populated_pct": round(100 * r[1] / res["rows"], 3),
                         "banners_per_key_p50_p90_p99_p999": r[2], "max": r[3],
                         "singleton_keys": r[4]}
# banners with more than 1 domain: is domain a clean key?
res["domains_len_dist"] = con.execute("""SELECT len(domains) l, count(*) FROM k GROUP BY 1
  ORDER BY 1 LIMIT 12""").fetchall()

# functional dependencies between the keys (scalar ones + first domain)
fd_cols = {"ip": "ip", "asn": "asn", "org": "org", "domain1": "domains[1]",
           "cn": "cert_subject_cn"}
res["fd"] = []
names = list(fd_cols)
for i, a in enumerate(names):
    for b_ in names[i + 1:]:
        ea, eb = fd_cols[a], fd_cols[b_]
        da, db, dab = con.execute(f"""SELECT count(DISTINCT {ea}), count(DISTINCT {eb}),
          count(DISTINCT ({ea}, {eb})) FROM k WHERE {ea} IS NOT NULL AND {eb} IS NOT NULL""").fetchone()
        res["fd"].append({"a": a, "b": b_, "da": da, "db": db, "dab": dab,
                          "a_determines_b_pct": round(100 * da / dab, 2) if dab else None,
                          "b_determines_a_pct": round(100 * db / dab, 2) if dab else None})
# how many orgs per ip / per domain
res["orgs_per_domain_q"] = con.execute("""SELECT quantile_disc(n,[0.5,0.9,0.99]), max(n) FROM
  (SELECT d, count(DISTINCT org) n FROM (SELECT unnest(domains) d, org FROM k) GROUP BY d)""").fetchone()
res["domains_per_org_q"] = con.execute("""SELECT quantile_disc(n,[0.5,0.9,0.99]), max(n) FROM
  (SELECT org, count(DISTINCT d) n FROM (SELECT unnest(domains) d, org FROM k) GROUP BY org)""").fetchone()
res["ips_per_domain_q"] = con.execute("""SELECT quantile_disc(n,[0.5,0.9,0.99]), max(n) FROM
  (SELECT d, count(DISTINCT ip) n FROM (SELECT unnest(domains) d, ip FROM k) GROUP BY d)""").fetchone()
res["domains_per_ip_q"] = con.execute("""SELECT quantile_disc(n,[0.5,0.9,0.99]), max(n) FROM
  (SELECT ip, count(DISTINCT d) n FROM (SELECT unnest(domains) d, ip FROM k) GROUP BY ip)""").fetchone()

# share of banners in the top orgs / domains: is the key the customer or the host?
res["top_orgs"] = con.execute("""SELECT org, count(*) n, count(DISTINCT ip) ips,
  count(DISTINCT domains[1]) first_domains FROM k GROUP BY 1 ORDER BY 2 DESC LIMIT 25""").fetchall()
res["top_domains"] = con.execute("""SELECT d, count(*) n, count(DISTINCT ip) ips,
  count(DISTINCT org) orgs FROM (SELECT unnest(domains) d, ip, org FROM k) GROUP BY 1
  ORDER BY 2 DESC LIMIT 25""").fetchall()
# customer-vs-infrastructure split of domains: a domain spread across many IPs is a
# reverse-DNS zone of a network operator, not a customer. Distribution recorded for 3 cutoffs.
con.execute("""CREATE TEMP TABLE dstat AS SELECT d, count(DISTINCT ip) ips, count(DISTINCT org) orgs,
  count(*) n FROM (SELECT unnest(domains) d, ip, org FROM k) GROUP BY 1""")
res["domain_ip_cutoffs"] = {}
for cut in (10, 50, 250):
    res["domain_ip_cutoffs"][cut] = con.execute(f"""SELECT count(*) FILTER (WHERE ips <= {cut}),
      count(*) FILTER (WHERE ips > {cut}), sum(n) FILTER (WHERE ips <= {cut}),
      sum(n) FILTER (WHERE ips > {cut}) FROM dstat""").fetchone()
    res["domain_ip_cutoffs"][f"{cut}_banners_with_any_small_domain"] = con.execute(f"""
      SELECT count(DISTINCT id) FROM (SELECT id, unnest(domains) d FROM k) JOIN dstat USING (d)
      WHERE ips <= {cut}""").fetchone()[0]
res["top_ports_share"] = con.execute("""SELECT port, count(*) FROM k GROUP BY 1 ORDER BY 2 DESC LIMIT 15""").fetchall()
# 20 example groups by eye, for org and for domain
with open(out("06_rollup_examples.txt"), "w", encoding="utf-8") as f:
    for key, sql in (("org", "org"), ("domain", "d")):
        f.write(f"===== 20 random {key} groups ({TAG})\n")
        src = "(SELECT unnest(domains) d, * FROM k)" if key == "domain" else "k"
        groups = con.execute(f"""SELECT g FROM (SELECT {sql} g FROM {src} WHERE {sql} IS NOT NULL
          GROUP BY 1 HAVING count(*) BETWEEN 2 AND 200) USING SAMPLE 20 ROWS (reservoir, 7)""").fetchall()
        for (g,) in groups:
            rs = con.execute(f"""SELECT ip, port, module, org, asn, domains[1:3], cert_subject_cn
              FROM {src} WHERE {sql} = ? LIMIT 6""", [g]).fetchall()
            n = con.execute(f"SELECT count(*), count(DISTINCT ip), count(DISTINCT org), "
                            f"count(DISTINCT domains[1]) FROM {src} WHERE {sql} = ?", [g]).fetchone()
            f.write(f"\n--- {key}={g!r} banners={n[0]} ips={n[1]} orgs={n[2]} first_domains={n[3]}\n")
            for r in rs:
                f.write(f"  {r}\n")
out("06_rollup.json").write_text(json.dumps(res, indent=1, default=str))
print(json.dumps(res, indent=1, default=str))
