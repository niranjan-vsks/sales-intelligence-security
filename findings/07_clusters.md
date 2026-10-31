# 07_clusters.md

FULL. Source: queries/07_signals.py -> 07_corr_numeric.csv (Spearman, 2,000,000-row
reservoir sample, seed 3), 07_corr_categorical.csv (Cramer's V, top 30 levels + other +
null, 2,000,000-row sample, seed 5), 07_num_vs_cat.csv; queries/06d_fd.py -> 06_fd.csv.
Rule: |rho| > 0.7, or V > 0.5, or a functional dependency.

Representative indicators ("reps") used in 7.2 and 7.3 are 0/1 per banner:
r_vuln (n_vulns > 0), r_cvss7 (max_cvss >= 7), r_http, r_ssl, r_selfsigned,
r_certexpired, r_cloud, r_waf, r_cpe, r_banner_text (data_len > 0), r_eol (tag
eol-product). Population rates (banner / entity): r_vuln 0.032 / 0.163,
r_selfsigned 0.0094 / 0.037, r_certexpired 0.0037 / 0.061, r_waf 0.107 / 0.208,
r_eol 0.0167 / 0.091, r_ssl 0.068 / 0.667, r_cloud 0.285 / 0.181 (07_summary.json).

| cluster_id | columns | representative | fact_it_encodes | strength | notes |
|---|---|---|---|---|---|
| K1 | n_vulns, vuln_ids, max_cvss, max_epss, r_vuln, r_cvss7 | r_vuln | known-vulnerable software version | rho n_vulns~r_vuln 1.00, ~r_cvss7 0.96, ~max_cvss 0.79 | vulns are inferred from product+version (verified on 1 % of vulnerable banners), so K1 is downstream of K2 |
| K2 | product, version, cpe23, http_server, os, tags eol-product | cpe23 (vendor:product:version) | fingerprinted software and version | product/cpe populated lifts r_vuln 5.2 / 4.8, r_eol 5.5 / 4.8 (07_rare_values.csv `<populated>`) | eol-product tag is a 2nd view of version age |
| K3 | module, transport, port, blocks | module | which probe ran (decides which blocks exist) | V module~transport 0.93, transport~port 0.87, module~port 0.62 | every sparse field's fill is driven by K3 (02_population.md) |
| K4 | data_len, record_bytes, n_headers, r_http, r_banner_text, http_html_len | data_len | payload size: a real service answered vs an empty port hit | rho data_len~r_banner_text 0.95, ~n_headers 0.89, ~record_bytes 0.82, r_http~r_banner_text 0.74 | |
| K5 | hostnames, domains, cert_san, cert_subject_cn, http_host | domains (customer domain) | the name of the entity | rho n_hostnames~n_domains 0.98; cn -> domain 91 % FD | the roll-up key, not a feature |
| K6 | ip, org, isp, asn, cloud_provider, cloud_region, latitude/longitude, country | org | network operator | ip -> org 100 %, ip -> asn 100 %; V cloud_provider~org 0.60; cloud_region -> cloud_provider FD | describes the host network, not the company |
| K7 | ssl_version, ssl_cipher, ssl_cipher_bits, ja3s, jarm, cert_issuer_o, cert_pubkey_*, cert_sig_alg | cert_issuer_o | TLS stack and certificate source | FDs ja3s -> ssl_version, ssl_cipher -> bits, pubkey_bits -> type; V cert_issuer_o~ssl_version 0.52 | |
| K8 | cert_self_signed, tags self-signed, cert_expired, cert_days_to_expiry, cert_age_days | r_selfsigned (with r_certexpired) | certificate hygiene | tag self-signed lifts r_selfsigned 104, r_certexpired 36.4 (banner) | r_selfsigned and r_certexpired are not merged: rho under 0.7 |
| K9 | http_waf, http_components (CDN/WAF names), tags cdn | r_waf | an edge protection product is in front | waf populated lifts r_waf 9.3, r_vuln 0.18, r_eol 0.09 | negative cluster |
| K10 | country_code, country_name, region_code, city | country_code | geography | country_code -> country_name FD (232 = 232 = 232) | 28.6 % single-point geolocation sentinel |
| K11 | uptime | uptime | host uptime | no |rho| > 0.7 with anything | standalone |

Numeric vs categorical (median spread larger than overall IQR, 07_num_vs_cat.csv):
module, country_code, cloud_provider, product, link and org all split
data_len, record_bytes, cert_age_days and cert_days_to_expiry; product also
splits n_vulns (median 0 to 61). Peer group for 7.3 chosen from these: the
2 lowest-cardinality splitters that are not K6 duplicates, module x
country_code (3,266 groups of 30 or more rows; 0.41 % of rows in undersized
groups).
