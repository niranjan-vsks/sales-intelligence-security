# REPORT.md: Stage 1 exploration, read this first

All numbers FULL (14,608,406 rows) unless marked. Every number traces to a
file in findings/ produced by a script in findings/queries/.

## The 6 facts

1. **Grain**: 1 row = 1 service banner (1 IP, 1 port, 1 transport, 1 scan
   time) from a Shodan export. Key `_shodan.id`, unique. The buyer is not a
   row: roll-up key = customer domain (an element of `domains` that covers
   50 IPs or fewer). `org`/`asn` are the network operator (ip -> org 100 %).
2. **Counts**: 14,608,407 lines, 14,608,406 rows (1 line unparseable).
   4,992,440 IPs. 485,089 customer-domain entities on 1,074,635 rows (7.36 %).
3. **Snapshot**: 1 scan window, 2026-10-25 18:13 to 2026-10-26 13:06, and
   95.7 % of rows inside 1 hour (2026-10-26 12:00-13:00). Not a delta, not
   history. Repeat probes of a service span < 1 h at p99.
4. **Representative columns**: r_vuln (K1 vulnerable version), cpe23 (K2
   software fingerprint), module (K3 probe), data_len (K4 payload), domains
   (K5 entity key), org (K6 operator), cert_issuer_o (K7 TLS stack),
   r_selfsigned / r_certexpired (K8 cert hygiene), r_waf (K9 protection),
   country_code (K10), uptime (K11).
5. **Coverage > 50 %**: only C-13 (entity breadth, 100 % of entities) and
   the disqualifiers D-18 / D-20. Every positive raw signal is sparse at row
   grain; at entity grain C-01 reaches 70.2 %.
6. **Ground truth**: no buying outcome. Proxies: vulns.kev 282,801 banners
   (1.94 %), ransomware_campaign Known 56,631, verified CVE 4,808,
   heartbleed VULNERABLE 160, existing security vendor on 83,779 entities.

**"Right now" (6.5, answered explicitly)**: timestamps do not vary in any
useful way: the whole file is 1 scan, 18.9 hours end to end, 95.7 % in 1
hour. Inside 1 file nothing can be "new" or "changed". "Right now" can only
mean "observed in this scan", plus 2 dates in the record that describe the
past (certificate issued / expires: 53,847 certificates already expired at
scan time). Change over time needs a 2nd file; that is the Stage 2
ingestion design (the brief says files arrive monthly).

## Candidates (08_candidates.md)

- C-01 versioned software fingerprint (cpe23/product): r_vuln x4.8, r_eol x4.8; 20.9 % rows, 70 % entities.
- C-02 known-vulnerable version (vulns): r_eol x25.8, r_waf x0.18; 3.2 % rows, 16.3 % entities.
- C-03 end-of-life tag: r_vuln x25.8, r_waf x0.09; 1.7 % rows, 9.1 % entities.
- C-04 self-signed / device-default certificate: r_selfsigned x104, r_certexpired x36; 3.7 % entities.
- C-05 legacy TLS negotiated (SSLv3/TLSv1.0): r_certexpired x98 (banner); 6,707 rows only.
- C-06 exposed remote-admin/data service on the entity: r_vuln x1.4-3.7, r_selfsigned up to x24 (entity).
- C-07 Windows internals exposed (NTLM/RDP): r_selfsigned x19.6 (entity); also leaks AD domain names.
- C-08 provider tags database / iot: r_eol x4.4, r_selfsigned x4.8-6.4 (entity); small.
- C-09 OS fingerprinted: r_eol x12.7, r_vuln x8.0; 4.1 % rows.
- C-10 WAF already in front (negative): r_vuln x0.18; 17.3 % of entities have some security vendor.
- C-11 firewall/VPN appliance on perimeter (negative and surface): SonicWall entity r_selfsigned x12.9.
- C-12 HSTS/CSP headers (substitute): weak, r_vuln still x1.6-2.1. Low confidence.
- C-13 entity service breadth: top decile r_selfsigned x3.2, r_vuln x1.3, r_waf x2.4; 100 % entities.
- C-14 more web components than peers (module x country): r_vuln x9.2, r_waf x0.47; 29.5 % rows.
- C-15 n_cpe / n_headers: r_vuln x13.0, r_waf x0.03; 18.9 % rows.
- C-16 old certificate for its peers: r_certexpired x88, r_vuln x2.2; 6.8 % rows.
- C-17 DigitalOcean / Vultr / Linode hosting: r_vuln x2.5-9.3 (banner); low confidence.
- D-18 only operator domains (CDN/cloud/ISP): 66.7 % of rows. Disqualifier.
- D-19 honeypot or scanner: 250,530 rows, 154,211 on Aliyun. Disqualifier.
- D-20 no reverse DNS: 25.9 % of rows. Disqualifier for name-based roll-up.

Target group from 7.4 ("prerequisite without the thing"): 131,104 entities
(27.0 %) have a live web service or exposed admin service and no security
product or substitute (07_negative.md).

## 10 most surprising things

1. 2 network operators are half the file: Incapsula 4,664,416 rows (31.9 %)
   and Google 3,175,021. Top 5 orgs = 62.4 %. Most rows are CDN/WAF edges,
   not companies.
2. Incapsula and similar edges answer on every port: 3,744,039 Incapsula
   rows are module `auto` and they also produce x11, dahua-dvr, teamviewer
   and weblogic "services" (07_ground_truth.json incapsula_modules).
3. `module` is the probe that was tried, not what was found. The
   darktrack-rat / remcos-pro-rat / orcus-rat / ta14-353a modules (64,291
   rows) look like malware detections; on Google IPs 16 of 31,763 such rows
   have any payload. The real C2 tag fires on 31 rows.
4. 56.4 % of rows have an empty banner (data_len 0); `auto` is 52.2 % of
   rows and 6,813,284 of its 7,631,835 rows are empty.
5. Vulnerabilities are inferred, not tested: verified = true on 6,111 of
   20,988,468 vuln rows. Any server version string predicts r_vuln at the
   ceiling (entity lift 6.14 = every member vulnerable).
6. 13 CVEs share exactly 131,415 rows each: 1 fingerprint fans out to many
   CVEs. n_vulns is capped at 1,000.
7. 28.6 % of rows geolocate to 1 point (1.2954, 103.8584).
8. shodan_region value `na` (North America) collides with the "n/a"
   placeholder rule; naive profiling marks 71 % of a dense column as missing.
9. Only 7.36 % of rows attach to a customer domain; reverse-DNS `domains`
   is dominated by operator zones (incapdns.net 4,234,554 rows).
10. 2,206 rows carry a whole top-level `html` page and http_html_len
    reaches 35,292,245 bytes in 1 record; ssl_versions is either empty or
    complete (0 or 6 entries, nothing between except 125 rows of 5).

## Deviations from EXPLORATION.md, and why

- **Data location**: Parquet and samples live in
  C:/Users/NIRANJAN VSKS/sis_data, not repo `data/`. The repo is inside
  OneDrive; 2.5 GB of Parquet plus a 7.5 GB sample JSONL would sync.
  `SIS_DATA` env var overrides (queries/common.py). `data/` is in .gitignore.
- **1a skipped**: no decompress-to-disk. Streamed `zstd -dc | 01_flatten.py`
  (11 workers). Line count by a separate in-process zstd pass
  (01_linecount.py) instead of `wc -l`; `zstd | wc -l` failed in Git Bash
  with "Write error: Invalid argument" after 1,221,316 lines.
- **1b partitioning**: not partitioned by module (246 modules x 1,220
  chunks = too many tiny files). Instead 1,220 files, each sorted by module.
- **1b `has_<block>` booleans**: replaced by 1 list column `blocks`
  (list_contains gives the same boolean).
- **1b dropped**: 1 record with a lone UTF-16 surrogate failed orjson and
  was dropped (logged in stats.json).
- **1c**: vuln keys inventoried over all records, not the first 10,000.
- **Sample**: the 1,000,000-row sample is the first 1 M lines, used only to
  develop queries. All findings files are FULL; sample outputs stayed outside
  the repo.
- **2**: SUMMARIZE excluded list columns and the 3 big text columns
  (data, extra_json, http_headers); their population came from the custom
  pass. Placeholder rule kept as written, with the `na` correction noted.
- **3**: value files capped at 5,000 rows each (04_categorical_tails.csv
  flags truncation). Identifier columns get no value file.
- **6.2**: FD run on all non-list columns under 5,000 approx distinct, not
  only "categorical" ones; spurious tiny-overlap hits listed as such.
- **7.1**: Cramer's V on top-30 levels + other + null, on a 2 M sample;
  Spearman on a 2 M sample (both as the plan allows).
- **7.2**: lift is a ratio of rates of 0/1 reps, not of medians;
  `max_abs_log2_lift` saturates at 5 when a slice has 0 positives against an
  expectation of 5 or more. Ceiling 2 % and floor 50 as written. Banner-grain
  lifts are distorted by module (which reps can exist); entity-grain lifts
  are the ones quoted for C-06, C-07, C-08.
- **7.3**: peer group = module x country_code (from 07_num_vs_cat.csv).
  Change over time not computed: 6.5 found 1 scan window.
- **7.4**: values/http_component_category_pairs.csv is a component x
  row-category co-occurrence table, not the provider's component -> category
  map (the flattener did not keep that mapping). Not used for mapping.
- **Bug found and fixed**: the first full 7.x run had r_cpe and r_eol NULL
  on rows without cpe23/tags, inflating their base rates (r_cpe 0.99995).
  Fixed with coalesce and rerun; the files in findings/ are from the rerun.
