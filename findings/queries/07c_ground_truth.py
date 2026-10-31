"""Section 7.5: provider-assigned outcome-like fields and their coverage."""
import json

from common import TAG, connect, out

con = connect()
res = {"tag": TAG}
res["heartbleed_result"] = con.execute("""SELECT regexp_extract(opts_heartbleed, ' - ([A-Z]+)', 1) r, count(*)
  FROM b WHERE opts_heartbleed IS NOT NULL GROUP BY 1 ORDER BY 2 DESC""").fetchall()
res["opts_vulns_nonempty"] = con.execute("SELECT count(*) FROM b WHERE len(opts_vulns) > 0").fetchone()[0]
res["tags_outcome_like"] = con.execute("""SELECT t, count(*) FROM (SELECT unnest(tags) t FROM b)
  WHERE t IN ('compromised','c2','malware','doublepulsar','eol-product','eol-os','honeypot','ssh-bad-key')
  GROUP BY 1 ORDER BY 2 DESC""").fetchall()
res["rat_modules"] = con.execute("""SELECT module, count(*), count(DISTINCT coalesce(ip_str, ipv6))
  FROM b WHERE module IN ('darktrack-rat','remcos-pro-rat','orcus-rat','ta14-353a') GROUP BY 1""").fetchall()
res["kev_banners"] = con.execute("SELECT count(DISTINCT id) FROM v WHERE kev").fetchone()[0]
res["ransomware_known_banners"] = con.execute("""SELECT count(DISTINCT id) FROM v
  WHERE other_keys::JSON ->> 'ransomware_campaign' = 'Known'""").fetchone()[0]
res["verified_vuln_banners"] = con.execute("SELECT count(DISTINCT id) FROM v WHERE verified").fetchone()[0]
# compromise indicators on rows that also attach to a customer domain (are they on buyer hosts?)
res["compromise_rows_with_any_domain"] = con.execute("""SELECT count(*) FROM b WHERE (module IN
  ('darktrack-rat','remcos-pro-rat','orcus-rat','ta14-353a') OR list_contains(tags,'compromised')
  OR list_contains(tags,'c2') OR list_contains(tags,'malware')) AND len(domains) > 0""").fetchone()[0]
res["rat_module_by_org_payload"] = con.execute("""SELECT module, org, count(*), count(*) FILTER (WHERE data_len > 0)
  FROM b WHERE module IN ('darktrack-rat','remcos-pro-rat','orcus-rat','ta14-353a') GROUP BY ALL
  ORDER BY 3 DESC LIMIT 10""").fetchall()
res["rat_module_honeypot_tagged"] = con.execute("""SELECT module, count(*) FILTER (WHERE list_contains(tags,'honeypot')),
  count(*) FROM b WHERE module IN ('darktrack-rat','remcos-pro-rat','orcus-rat','ta14-353a') GROUP BY 1""").fetchall()
res["honeypot_by_org"] = con.execute("""SELECT org, count(*) FROM b WHERE list_contains(tags,'honeypot')
  GROUP BY 1 ORDER BY 2 DESC LIMIT 5""").fetchall()
res["incapsula_modules"] = con.execute("""SELECT module, count(*) FROM b WHERE org = 'Incapsula Inc'
  GROUP BY 1 ORDER BY 2 DESC LIMIT 8""").fetchall()
res["empty_payload_by_module"] = con.execute("""SELECT module, count(*), count(*) FILTER (WHERE data_len = 0)
  FROM b GROUP BY 1 ORDER BY 2 DESC LIMIT 5""").fetchall()
out("07_ground_truth.json").write_text(json.dumps(res, indent=1, default=str))
print(json.dumps(res, indent=1, default=str))
