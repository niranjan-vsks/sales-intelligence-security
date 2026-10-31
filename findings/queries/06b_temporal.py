"""Section 6.5: temporal columns. Range, mode, spread of scan timestamps, repeat observations."""
import json

from common import TAG, connect, out

con = connect()
res = {"tag": TAG}
for c in ("timestamp", "cert_issued", "cert_expires"):
    r = con.execute(f"""SELECT count({c}), min({c}), max({c}),
      quantile_disc({c}, [0.001, 0.01, 0.5, 0.99, 0.999]), mode(date_trunc('day', {c}))
      FROM b""").fetchone()
    res[c] = {"non_null": r[0], "min": r[1], "max": r[2], "q001_01_50_99_999": r[3], "mode_day": r[4]}
res["timestamp_by_day"] = con.execute("""SELECT date_trunc('day', timestamp) d, count(*) FROM b
  GROUP BY 1 ORDER BY 1""").fetchall()
res["timestamp_by_hour"] = con.execute("""SELECT date_trunc('hour', timestamp) h, count(*) FROM b
  GROUP BY 1 ORDER BY 1""").fetchall()
# do banners appear in file order of time? (monotonicity is a property of the export, not needed)
# repeat observations of the same service: same (ip, port, transport) at different times
res["repeat_service"] = con.execute("""SELECT count(*) AS n_groups, sum(n) AS n_rows,
  quantile_disc(span_h, [0.5, 0.9, 0.99]) span_hours, max(span_h)
  FROM (SELECT coalesce(ip_str, ipv6) ip, port, transport, count(*) n,
        date_diff('minute', min(timestamp), max(timestamp)) / 60.0 span_h
        FROM b GROUP BY ALL HAVING n > 1)""").fetchone()
res["repeat_service_same_hash"] = con.execute("""SELECT count(*) FILTER (WHERE nh = 1),
  count(*) FILTER (WHERE nh > 1) FROM (SELECT coalesce(ip_str, ipv6) ip, port, transport,
  count(*) n, count(DISTINCT hash) nh FROM b GROUP BY ALL HAVING n > 1)""").fetchone()
# per-IP time span across all its services
res["ip_span_hours_q"] = con.execute("""SELECT quantile_disc(s, [0.5, 0.9, 0.99]), max(s) FROM
  (SELECT date_diff('minute', min(timestamp), max(timestamp)) / 60.0 s FROM b
   GROUP BY coalesce(ip_str, ipv6) HAVING count(*) > 1)""").fetchone()
# uptime: minutes since last reboot per Shodan docs field name; record quantiles only
res["uptime"] = con.execute("""SELECT count(uptime), quantile_disc(uptime, [0.1,0.5,0.9,0.99]),
  max(uptime) FROM b""").fetchone()
# certificate age and time to expiry, relative to the scan timestamp
res["cert_age_days_q"] = con.execute("""SELECT quantile_disc(date_diff('day', cert_issued, timestamp),
  [0.01,0.1,0.5,0.9,0.99]) FROM b WHERE cert_issued IS NOT NULL""").fetchone()
res["cert_days_to_expiry_q"] = con.execute("""SELECT quantile_disc(date_diff('day', timestamp, cert_expires),
  [0.01,0.05,0.1,0.5,0.9,0.99]), count(*) FILTER (WHERE cert_expires < timestamp),
  count(*) FILTER (WHERE cert_expired) FROM b WHERE cert_expires IS NOT NULL""").fetchone()
res["cert_validity_days_top"] = con.execute("""SELECT date_diff('day', cert_issued, cert_expires) d,
  count(*) FROM b WHERE cert_issued IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 10""").fetchall()
# dates embedded in vulns? (none expected; checked as a column list)
out("06_temporal.json").write_text(json.dumps(res, indent=1, default=str))
print(json.dumps({k: v for k, v in res.items() if k != "timestamp_by_hour"}, indent=1, default=str))
