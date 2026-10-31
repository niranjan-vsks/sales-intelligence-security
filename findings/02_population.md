# 02_population.md

FULL, 14,608,406 rows. Source: queries/02_profile.py -> 02_columns.csv,
02_summarize.csv, 02_sparse_skew.csv. "populated" = not NULL, not empty,
not in the placeholder list of EXPLORATION.md section 2; for lists, length > 0.

Correction to the placeholder rule: `shodan_region` shows 71.4 % placeholder
because its value `na` (North America, 9,986,822 rows) is on the placeholder
list. It is really 97.0 % populated (eu 4,178,517, na 9,986,822, empty
443,067). Treat it as dense.

## >= 90 pct, dense (20)

id, module, crawler, ptr (93.4), timestamp, port, transport, ip_str (97.9),
org, isp, asn, hash, country_code, country_name, city, region_code (98.9),
latitude, longitude, data_len, record_bytes. Plus shodan_region (see above).

Every dense column describes the network location and the scan, none
describes the company. The only company-ish dense fields (org, isp, asn)
name the network operator (06_relationships.md roll-up).

## 50 to 90, partial (5)

link 74.5, hostnames 74.1, domains 74.1, tags 71.0, blocks 55.2.

Absence of `domains` (25.9 %) means no reverse DNS, not "no company".

## 10 to 50, sparse (26)

data 43.6 (56.4 % of rows have an empty banner: `auto`-module port hits with
no payload), uptime 39.5, every http_* scalar 29.5, http_header_names 28.4,
cloud_provider 28.5, cloud_region 26.6, http_components_hash 25.7,
cpe23 20.9, http_server 19.3, http_components / cats 18.7, product 17.9,
http_title_hash 17.7, http_title 17.0, http_waf 10.7.

## < 10, rare (41)

TLS block (ssl_*, cert_*, jarm, ja3s, trust_revoked) 6.7 to 6.8;
opts_heartbleed 6.3; version 6.5; cloud_service 5.6; cert_san 5.6;
extra_json 4.6; ssl_versions 4.3; os 4.1; info 3.8; http_favicon_hash 3.4;
vuln_ids / n_vulns / max_cvss / max_epss 3.2; ipv6 2.1; cert_subject_o 1.4;
devicetype 0.51; trust_browser 0.39; ssl_alpn 0.34; vendor 0.14;
http_identifiers 0.07; opts_vulns 0.035; device 0.03; html_len 0.015.

## Who has the sparse fields filled (02_sparse_skew.csv, dense column = module)

Every sparse block is produced by 1 or 2 modules, so its fill pattern is
the module mix, not the company:

| field group | top producing module: share of populated rows (share of all rows, lift) |
|---|---|
| ssl_*, cert_*, jarm, ja3s | https 66.6 % (5.64 %, x11.8); https-simple-new 17.2 % (x3.6) |
| http_* scalars | http 48.1 % (15.0 %, x3.2); http-simple-new 16.1 % (x2.0) |
| vulns, max_cvss, max_epss | http 64.8 % (x4.3); https 11.4 % (x2.0) |
| product, version, cpe23 | http 52.4 / 56.7 / 46.4 % (x3.5 / x3.8 / x3.1) |
| devicetype, vendor | http-simple-new 78.8 % / 71.7 % (x9.8 / x8.9) |
| device | snmp_v3 75.1 % (x64); snmp_v2 18.2 % (x822) |
| uptime | auto 68.7 % (x1.32) |
| cloud_provider, cloud_region, shodan_region | auto 55 % (x1.05): not module-driven |
| ipv6 | https 52.2 % (x9.3) |
| extra_json | snmp_v3 25.5 % (x21.8), ssh 12.5 % (x21.8) |

Consequence: a missing TLS or HTTP field on an `auto` row means "that
module did not run", not "the company lacks TLS". Fill rate inside the
producing module is in values/blocks_fill.csv. Stage 2 must compute
absence only within rows of the module that can produce the field.

Skew on the other dense columns (transport, shodan_region, country_code,
link) is in 02_sparse_skew.csv.
