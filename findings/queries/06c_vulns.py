"""Section 1c / 6.4 / 7.5: the vulns child table, its join to banners, provider-assigned labels."""
import json

from common import TAG, connect, out

con = connect()
res = {"tag": TAG}
res["vuln_rows"], res["distinct_cve"], res["banners_with_vulns"] = con.execute(
    "SELECT count(*), count(DISTINCT cve), count(DISTINCT id) FROM v").fetchone()
res["orphans"] = con.execute("SELECT count(*) FROM v ANTI JOIN b USING (id)").fetchone()[0]
res["kev"] = con.execute("""SELECT count(*) FILTER (WHERE kev), count(kev), count(DISTINCT id) FILTER (WHERE kev),
  count(DISTINCT cve) FILTER (WHERE kev) FROM v""").fetchone()
res["verified"] = con.execute("SELECT verified, count(*) FROM v GROUP BY 1").fetchall()
res["other_keys"] = con.execute("""SELECT k, count(*) FROM (SELECT unnest(json_keys(other_keys::JSON)) k
  FROM v WHERE other_keys IS NOT NULL) GROUP BY 1""").fetchall()
res["ransomware_campaign"] = con.execute("""SELECT other_keys::JSON ->> 'ransomware_campaign' x, count(*)
  FROM v WHERE other_keys IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 10""").fetchall()
res["cvss_q"] = con.execute("SELECT quantile_cont(cvss, [0.1,0.5,0.9]), quantile_cont(epss,[0.5,0.9,0.99]) FROM v").fetchone()
res["cve_year"] = con.execute("""SELECT split_part(cve,'-',2) y, count(*) FROM v GROUP BY 1 ORDER BY 1""").fetchall()
res["vulns_per_banner_q"] = con.execute("""SELECT quantile_disc(n,[0.5,0.9,0.99]), max(n) FROM
  (SELECT id, count(*) n FROM v GROUP BY 1)""").fetchone()
res["vuln_by_module"] = con.execute("""SELECT b.module, count(DISTINCT v.id) FROM v JOIN b USING (id)
  GROUP BY 1 ORDER BY 2 DESC LIMIT 15""").fetchall()
res["kev_by_product"] = con.execute("""SELECT b.product, count(DISTINCT v.id) FROM v JOIN b USING (id)
  WHERE kev GROUP BY 1 ORDER BY 2 DESC LIMIT 15""").fetchall()
res["top_cves"] = con.execute("""SELECT cve, count(*), any_value(cvss), any_value(kev) FROM v GROUP BY 1
  ORDER BY 2 DESC LIMIT 15""").fetchall()
out("06_vulns.json").write_text(json.dumps(res, indent=1, default=str))
print(json.dumps(res, indent=1, default=str))
