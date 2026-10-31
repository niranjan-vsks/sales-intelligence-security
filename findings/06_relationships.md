# 06_relationships.md

All numbers FULL (14,608,406 rows) unless marked SAMPLE.
Sources: queries/06a_rollup.py -> 06_rollup.json, 06_rollup_examples.txt;
queries/06b_temporal.py -> 06_temporal.json; queries/06c_vulns.py -> 06_vulns.json;
queries/06d_fd.py -> 06_fd.csv.

## Grain

1 row = 1 service banner: 1 IP (v4 or v6), 1 port, 1 transport, 1 scan time.

| check | value |
|---|---|
| rows | 14,608,406 |
| distinct `_shodan.id` | 14,608,406 (unique, the row key) |
| distinct (ip, port, transport) | 13,209,079 |
| distinct (ip, port, transport, timestamp) | 14,608,406 |
| distinct `hash` (banner content hash) | 4,206,523 |

(ip, port, transport) is not unique: 495,392 groups hold 1,894,719 rows.
They are the same service observed more than once in the window, not
conflicting sources: 263,302 of those groups have 1 distinct `hash`
(identical content), 232,090 have more than 1. Time span inside a group:
p50 0.1 h, p90 0.58 h, p99 0.98 h, max 12.7 h. So: re-probes inside 1 scan
window, not history.

`hash` repeats massively (4.2 M distinct over 14.6 M rows): identical
banners across different IPs, mostly CDN/WAF edges answering on every port
(see roll-up).

## roll-up

Candidate keys (banners attributed = banners where the key is populated):

| key | distinct | banners populated | banners/key p50, p90, p99, p999 | max |
|---|---|---|---|---|
| ip | 4,992,440 | 100 % | 1, 4, 73, 94 | 4,081 |
| asn | 42,600 | 99.996 % | 4, 51, 1,206, 16,538 | 4,733,624 |
| org | 83,117 | 99.995 % | 2, 26, 596, 9,234 | 4,664,416 |
| domain (unnested) | 488,241 | 74.1 % | 1, 6, 63, 675 | 4,234,554 |
| hostname (unnested) | 3,767,910 | 74.1 % | 1, 4, 77, 126 | 100,155 |
| cert_subject_cn | 348,943 | 6.7 % | 1, 2, 15, 128 | 100,155 |
| http_host | 3,001,123 | 29.515 % | 1, 2, 10, 41 | 1,315 |

Functional dependencies between keys (pct = da/dab; 100 means A determines B):

- ip -> asn 100 %, ip -> org 100 %: org and asn are properties of the IP
  block, i.e. the network operator.
- asn -> org 42 %, org -> asn 83 %: neither is a clean hierarchy.
- domain -> org 85.6 %, domain -> asn 91.3 %: a domain usually sits in 1
  network, but 14 % span several.
- cn -> domain 91 %, domain -> cn 48 %.

What `org` actually names: the network operator, not the customer. Top 5
orgs hold 62.4 % of all rows (9,119,510): Incapsula Inc 4,664,416; Google LLC 3,175,021;
Cloudflare 561,455; Aliyun 376,839; Amazon.com 341,779.

What `domains` names: the registered domain of the reverse-DNS hostname.
Top domains are operator zones: incapdns.net 4,234,554 rows on 54,411 IPs;
googleusercontent.com 3,159,510 on 665,216 IPs; amazonaws.com 330,255;
cloudfront.net 283,908; akamaitechnologies.com 158,204.

Customer vs operator split, by how many IPs a domain covers:

| cutoff (IPs per domain) | domains at or under | domains over | rows on small domains | rows on big domains | rows with any small domain |
|---|---|---|---|---|---|
| 10 | 476,598 | 11,643 | 1,291,000 | 10,737,247 | 842,467 |
| 50 | 485,089 | 3,152 | 1,649,764 | 10,378,483 | 1,074,635 |
| 250 | 487,512 | 729 | 2,082,792 | 9,945,455 | 1,365,942 |

Chosen roll-up key for section 7: **customer domain** = an element of
`domains` whose domain covers 50 IPs or fewer in this file. Coverage:
1,074,635 rows (7.36 %) attach to at least 1 customer domain; 485,089
entities. Everything else (92.6 %) is unattributable to a buyer by this key:
it is CDN/WAF/cloud edge (Incapsula alone is 31.9 % of rows), consumer ISP
space, or IPs with no reverse DNS (25.9 % of rows have no domain at all).
The cutoff is a judgement on the distribution above, not a fitted value;
Stage 2 should treat it as a parameter.

`org` remains useful as the key for a different buyer: organisations that
run their own network (University of Iowa, Fujitsu Services, CERTH in
06_rollup_examples.txt). An org with 1 ASN and few IPs is a self-hosting
entity. That second roll-up is not quantified here.

Examples by eye: 06_rollup_examples.txt (20 org groups, 20 domain groups,
groups of 2 to 200 banners, reservoir sample seed 7).

## Child table: vulns

`vulns` flattened to 20,988,468 rows (banner id, CVE) over 467,424 banners
(3.2 % of rows), 11,064 distinct CVEs, 0 orphans on join to banners.
Keys inside each CVE object (all 20,988,468 unless noted): cvss,
cvss_version, cvss_v2, references, summary, verified, epss, ranking_epss;
kev on 373,900; ransomware_campaign on 373,110.

- `verified` is true on 6,111 rows (0.03 %). The rest are inferred from
  product and version, not tested.
- `kev` true on 370,460 rows, 282,801 banners, 199 CVEs.
- `ransomware_campaign`: Unknown 308,350, Known 61,320, null 3,440.
- CVEs per banner: p50 11, p90 128, p99 417, max 1,000 (a cap, likely).
- The single CVE on most rows: CVE-2025-23419 (173,669) and CVE-2023-44487
  (173,523, kev). 13 CVEs share exactly 131,415 rows: 1 product/version
  fingerprint fanned out to many CVEs.
- Malformed CVE ids: years "010" (13 rows) and "034" (579 rows).

## Functional dependencies (6.2)

06_fd.csv, all pairs of non-list columns with approx cardinality under
5,000. Real hierarchies (1 fact, not 2 features):

- country_code -> country_name (232 = 232 = 232)
- cloud_region -> cloud_provider (330 regions, 338 pairs); cloud_service ->
  cloud_provider
- ssl_cipher -> ssl_cipher_bits; ja3s -> ssl_version, ssl_cipher, bits
- cert_pubkey_bits -> cert_pubkey_type
- vendor -> devicetype (11 vendors, 11 pairs)

Spurious "dependencies" also flagged by the 5 % rule and to be ignored:
every pair involving http_identifiers, html_len, device, n_vulns on tiny
overlaps (the pair is defined on a few hundred rows only, so the higher
cardinality side trivially determines the other).

## Graph (6.3)

Identifier-like value sets that overlap: hostnames vs cert_subject_cn vs
http_host (all are DNS names). This is not a parent/child graph; it is the
same entity seen through 3 lenses (rDNS, TLS certificate, HTTP Host). ip ->
domain is many-to-many (domains per ip p99 4, max 11,948; ips per domain p99
31, max 665,216). No self-reference, no hierarchy, no cycles to test.

## Multiple entity types (6.4)

1 entity type (banner) but `_shodan.module` (246 values) decides which
protocol block a row carries. Sections 2 to 4 are reported per module in
values/blocks_fill.csv (fill rate inside the producing module).

## temporal

**Answer: the file is 1 scan window, not a time series.**

- `timestamp` (scan time) range: 2026-10-25 18:13:32 to 2026-10-26 13:06:06,
  18.9 hours.
- 95.7 % of rows (13,979,570) fall in 1 hour: 2026-10-26 12:00 to 13:00.
  99 % fall after 2026-10-26 11:12:50. The early tail (32 rows on 10-25,
  then doubling each hour) is a ramp, not separate scans.
- 1 timestamp per row. Repeat observations of the same service exist
  (above) but span p99 under 1 hour. Per IP across all its services the
  span is p50 0.52 h, p99 2.9 h.
- Consequence for "right now": inside 1 file, change-over-time is not
  computable. "Right now" can only mean "state observed in this scan", plus
  the 2 dates inside the record that describe the past: certificate issue
  and expiry. Freshness across files would come from the monthly stream of
  files (ASSIGNMENT.md), i.e. a Stage 2 ingestion design question.

Other temporal columns:

| column | non-null | range | meaning |
|---|---|---|---|
| cert_issued | 990,591 | 0001-01-01 to 2165-08-08 (sentinels both ends) | certificate notBefore |
| cert_expires | 990,591 | 0001-01-01 to 9999-12-31 | certificate notAfter |
| uptime | 5,763,517 | minutes, p50 34,725, max 70,766,721 | not a date; host uptime estimate |

Certificate age at scan time (days): p1 0, p10 8, p50 56, p90 720, p99 5,283.
Days to expiry: p1 -2,692, p5 -51, p10 32, p50 87, p90 775, p99 7,196.
53,847 certificates already expired at scan time (equals the provider's
`cert.expired` flag count). Validity periods: 90 days 374,389; 197 days
187,325; 365 days 63,342; 3,650 days 29,496; 7,305 days 19,538.
