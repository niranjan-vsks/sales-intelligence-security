# 04_distributions.md

FULL. Source: queries/03_04_values_dist.py -> 04_numeric.json (quantiles
p1, p5, p10, p25, p50, p75, p90, p95, p99, p99.9, log10 histogram, top 5
values), 04_categorical_tails.csv.

## Numeric

| column | non-null | p50 | p90 | p99 | max | notes |
|---|---|---|---|---|---|---|
| port | 14,608,406 | 5,938 | 45,001 | 63,443 | 65,535 | 80 (2,158,982) and 443 (761,450) dominate; long flat tail across all 65k ports |
| uptime (minutes) | 5,763,517 | 34,725 | 65,111 | 131,364 | 70,766,721 | heavy tail; p99.9 517,518. Mode cluster 33,605-33,610 |
| n_vulns | 467,424 | 11 | 128 | 417 | 1,000 | 1,000 is a cap; spikes at 2 (101,328), 4, 44 = shared fingerprints |
| max_cvss | 467,424 | 9.3 | 10.0 | 10.0 | 10.0 | p25 already 7.5; 9.8 is the mode (192,638) |
| max_epss | 467,424 | 1.0 | 1.0 | 1.0 | 0.99999 | p50 at the cap: half of vulnerable banners carry a CVE with EPSS ~1 |
| http_status | 4,311,673 | 400 | 503 | 503 | 999 | 200 (1,112,010), 404, 503, 403; 2 populations: real sites vs edges answering errors |
| http_redirects | 4,311,673 | 0 | 0 | 1 | 10 | 10 (7,445) is a cap |
| http_html_len | 4,311,673 | 548 | 10,697 | 167,133 | 35,292,245 | 647,894 zeros; spikes at 707/708 (templated error pages) |
| data_len | 14,608,406 | 0 | 351 | 2,562 | 181,683 | 8,245,918 zeros (56.4 %) |
| record_bytes | 14,608,406 | 923 | 10,850 | 166,182 | 35,390,335 | heavy tailed; driven by html |
| ssl_cipher_bits | 990,516 | 256 | 256 | 256 | 256 | 2 values: 128, 256 |
| cert_pubkey_bits | 990,591 | 2,048 | 2,048 | 4,096 | 10,240 | 256 = EC keys (206,806); 1,024 on 8,121 |
| ssl_chain_len | 990,592 | 3 | 4 | 4 | 40 | 1 = 184,565 (single cert, often self-signed) |
| latitude / longitude | 14,606,286 | | | | | sentinel: 1.2954, 103.8584 on 4,172,913 rows (a single point, Singapore); 2nd point 39.09973, -94.57857 on 1,809,240 |

List lengths (derived numerics, section 7.3): hostnames p50 1, p99 3, max 824;
domains p50 1, p99 2, max 342; tags p50 1, max 5; cpe23 p50 1, p99 4, max 27;
http_components p50 1, p99 5, max 35 (1,586,871 zeros); http_header_names
p50 6, p99 22, max 52; cert_san p50 2, p99 66, max 1,001; ssl_versions is 0
(358,519) or 6 (631,948): bimodal, the list is either absent or complete.

Heavy-tailed: uptime, n_vulns, http_html_len, data_len, record_bytes,
cert_san length. Use ranks or log scale.

## Sentinels and unit mismatches

- Geolocation: 28.6 % of rows on 1 coordinate (1.2954, 103.8584). That is a
  provider default for an operator's whole range, not a location.
- cert_issued / cert_expires: 0001-01-01, 1970-01-01 (p0.1 of issued), and
  9999-12-31. Certificate validity of 3,650 days (29,496) and 7,305 days
  (19,538): device default certificates.
- n_vulns 1,000 and http_redirects 10: caps.
- data_len 0 and http_html_len 0: "no payload", a distinct population.
- http_status 999 (non-standard) present.

## Categorical tail shape (04_categorical_tails.csv)

| column | values for 50 / 80 / 95 % of rows | singletons | distinct |
|---|---|---|---|
| module | 1 / 4 / 25 | 1 | 246 |
| org | 2 / 53 / 1,964 | 30,706 | 83,118 |
| asn | 2 / 26 / 1,009 | 10,595 | 42,601 |
| country_code | 2 / 6 / 26 | 3 | 234 |
| domains[] | 2 / 157 / 59,149 | 319,061 | 488,241 |
| cpe23[] | 6 / 36 / 241 | 2,726 | 8,160 |
| http_header_names[] | 5 / 19 / 58 | 4,174 | 9,857 |
| http_components[] | 5 / 17 / 57 | 221 | 1,299 |
| vuln_ids[] | 119 / 444 / 1,311 | 1,985 | 11,064 |
| tags[] | 1 / 2 / 5 | 1 | 29 |

Head is tiny everywhere: 2 orgs (Incapsula, Google) cover half the file.
The tail is where the companies are.
