# 07_negative.md

FULL. Source: queries/07b_negative.py -> 07_negative.json, mapping
07_what_we_sell_map.csv (Stage 2 configuration). Entity = customer domain
(06_relationships.md roll-up, 485,089 entities, 1,074,635 rows).

## Counts (step 3)

| class | rows | entities |
|---|---|---|
| is_what_we_sell | 1,347,800 | 83,779 |
| is_a_substitute | 824,207 | 128,750 |
| is_a_prerequisite | 1,216,368 | 221,369 |
| is_a_blocker | 250,566 | 340 |
| sell AND substitute | 70,797 | 18,436 |
| prerequisite WITHOUT sell | 1,156,042 | 201,826 |
| prerequisite WITHOUT sell AND WITHOUT substitute | 945,673 | 131,104 |
| prerequisite AND blocker | 16,053 | 225 |

The target group ("has the prerequisite, not the thing") is 131,104
customer-domain entities, 27.0 % of all entities.

Caveat on rows: 519,798 of the is_what_we_sell rows are Incapsula edges
(the WAF vendor's own IPs answering for customers). At entity grain this
is what it should be: the customer domain is behind Imperva.

## Signal blocks

signal: already has a WAF / DDoS protection
source_column: http_waf
values_that_trigger: mapping W01 (60 values)
rows_triggered: 1,089,388
populated_pct_of_source: 10.721 (http_waf); inside module http 37.7 % of populated rows
absence_is_informative: yes, but only on rows with module in (http, https, *-simple-new); elsewhere the detector did not run
notes: entity-level negative; Stage 2 should not pitch a WAF to these.

signal: runs a network security appliance (firewall / VPN gateway)
source_column: product, cpe23
values_that_trigger: mappings W03, W04
rows_triggered: 28,342 (product), 586,078 (cpe23, includes Incapsula)
populated_pct_of_source: product 17.87, cpe23 20.91
absence_is_informative: unknown: product is fingerprinted only when the probe matched
notes: an appliance is also an attack surface (see 06 vulns: kev on Fortinet/SonicWall lines is not separately counted here).

signal: VPN / IPsec endpoint present
source_column: module, tags
values_that_trigger: W05 (ike, ike-nat-t, l2tp, openvpn, pptp, checkpoint-hostname), W06 (vpn)
rows_triggered: 232,028 (module), 127,896 (tag)
populated_pct_of_source: module 100, tags 70.987
absence_is_informative: no: VPN probes run on few ports
notes: substitute for some remote-access products, prerequisite for others; product choice is Stage 2's.

signal: CDN / edge platform without a WAF product
source_column: http_waf
values_that_trigger: W02 (15 values)
rows_triggered: 476,810
populated_pct_of_source: 10.721
absence_is_informative: no
notes: substitute: may bundle protection.

signal: self-managed hardening headers (HSTS, CSP)
source_column: http_header_names
values_that_trigger: W07
rows_triggered: 401,994
populated_pct_of_source: 28.362
absence_is_informative: yes within http rows (headers are always captured when the http block exists)
notes: substitute / maturity indicator; absence on a live site is the inverse (prerequisite without control).

## Disqualifiers that are not about product (step 5)

signal: decoy or scanner host
source_column: tags
values_that_trigger: honeypot, scanner (B01)
rows_triggered: 250,530
populated_pct_of_source: 70.987
absence_is_informative: no
notes: 103,305 + 50,906 honeypot rows are on the 2 Aliyun org spellings; at entity grain only 340 entities carry any blocker.

signal: attacker C2 / malware host
source_column: tags
values_that_trigger: c2, malware (B02)
rows_triggered: 36
populated_pct_of_source: 70.987
absence_is_informative: no
notes: too rare to matter as a disqualifier.

signal: no reverse DNS at all
source_column: domains
values_that_trigger: empty list
rows_triggered: 3,783,508
populated_pct_of_source: 74.1
absence_is_informative: yes: the row cannot be attributed to a company by name
notes: rows can still be attributed through cert_subject_cn or http_host (06 roll-up) where those exist.

signal: only operator (CDN / cloud / ISP) domains
source_column: domains
values_that_trigger: every domain on the row covers more than 50 IPs
rows_triggered: 9,750,263
populated_pct_of_source: 74.1
absence_is_informative: n/a
notes: the buyer is the operator, not a prospect; this is 66.7 % of all rows.

signal: CDN or cloud edge
source_column: tags, cloud_provider
values_that_trigger: tag cdn; cloud_provider not null
rows_triggered: 5,868,128 (cdn), 4,169,850 (cloud_provider)
populated_pct_of_source: tags 70.987, cloud_provider 28.544
absence_is_informative: no
notes: overlaps the operator-domain disqualifier.

Not checkable from the file: defunct, subsidiary-of, territory (no
company registry fields). Country is present (country_code 99.98 %) but
geolocation has a 28.6 % single-point sentinel (04_distributions.md).
