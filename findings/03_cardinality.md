# 03_cardinality.md

FULL. Source: queries/03_04_values_dist.py -> 03_cardinality.csv (class per
column), 04_categorical_tails.csv, values/*.csv (1 file per categorical and
per exploded list; top 5,000 values each, `truncated` flag in the tails file).

Thresholds used: as in EXPLORATION.md (low <= 50, mid <= 5,000, high > 5,000),
plus "identifier" when approx_unique >= 50 % of rows. Hash columns are
classified as identifiers regardless of type.

## Classification

- identifier / row key: id, timestamp (not a key: 14,579,978 distinct
  values, 3 rows max per value).
- identifier-like, high: ip_str, ipv6, hash, http_host, http_html_hash,
  cert_sha256, cert_subject_cn, hostnames[], cert_san[], opts_heartbleed
  (contains the IP and time, 919,228 distinct).
- low categorical: shodan_region (3), transport (2), link (12), devicetype
  (25), device (17), ssl_version (5), ssl_cipher (34), cert_sig_alg (14),
  cert_pubkey_type (3 incl. null), trust_browser (6), cloud_provider (14),
  booleans.
- mid categorical: module (246), crawler (93), country_code (234), region_code
  (915), os (2,488), vendor (52), http_waf (76), ja3s (847), cloud_region
  (331), cloud_service (63), http_identifiers (2,908).
- high categorical (names): org (83,118), isp (40,770), asn (42,601), product
  (4,743), version (7,154), info (6,044), city (41,939), http_title
  (194,304), http_server (21,018), cert_issuer_o (10,097), jarm (8,437).
- list columns, element vocabularies: tags 29, ssl_versions 12, ssl_alpn 14,
  http_component_cats 94, http_components 1,299, http_header_names 9,857,
  blocks 173, cpe23 8,160, vuln_ids 11,064, domains 488,241.

## Same fact, 2 spellings (normalise in Stage 2)

- org: "Incapsula Inc" (4,664,416) and "Incapsula Inc." (79,724); "Aliyun
  Computing Co., LTD" (376,839) and "Aliyun Computing Co.LTD" (133,625);
  "Meteverse Limited." (82,211) and "METEVERSE LIMITED" (53,765);
  "Amazon.com, Inc." and "Amazon Technologies Inc." (different legal
  entities, same operator). values/org.csv.
- country_code (234 values) vs country_name (233): 1:1 (06_fd.csv).
- `version` holds escaped control characters (`7.4\r\n`), so the same
  version appears under several spellings.

## Controlled vocabularies (fixed by the data provider)

module, tags, link, devicetype, device, cloud_provider, cloud_service,
http_waf ("Name (Vendor)" pattern), http_component_cats, ssl_version,
ssl_versions (with a leading "-" meaning "not supported", e.g. "-TLSv1"),
trust_browser, shodan_region (eu, na, empty).

Free entry: org, isp, http_title, http_server, product, version, info,
cert_subject_o, cert_issuer_o, city.

## Codes looked up

- `module`: the scanner probe that produced the banner (http, https, ssh,
  snmp_v3, ike, rdp, ...). `auto` = 52.2 % of rows: a generic probe, mostly
  empty payload (data_len = 0 on 8,245,918 rows overall).
- module names that are detections, not protocols: darktrack-rat (20,685),
  remcos-pro-rat (20,056), orcus-rat (12,088), ta14-353a (11,462). See
  values/module.csv.
- `tags`: provider labels. cdn 5,868,128; cloud 4,168,884; pqc 350,916;
  honeypot 250,439; eol-product 244,327; self-signed 132,202; vpn 127,896;
  proxy 64,415; starttls 41,401; iot 29,599; database 15,455; eol-os 6,036;
  open-dir 5,335; devops 4,913; ai 1,998; ics 577; mcp 428; medical 359;
  scanner 94; ssh-bad-key 80; compromised 77; tor 64; c2 31; malware 5;
  doublepulsar 1. (values/tags_elements.csv; counts are element counts.)
- `asn`: "AS" + number. `crawler`: 40-hex id of the scanning node (93).
- `ja3s`, `jarm`: TLS server fingerprints (hashes).
- `link`: MTU-derived link type (Ethernet or modem, DSL, generic tunnel or
  VPN, IPSec or GRE, ...).
