# 07_ground_truth.md

FULL. Sources: queries/07c_ground_truth.py -> 07_ground_truth.json;
queries/06c_vulns.py -> 06_vulns.json; queries/07b_negative.py.

There is no buying outcome in the file (no deal, purchase, contact, or
churn field). What exists is provider-assigned labels that could validate
a "needs help" score, and existing-vendor presence that could validate a
"already bought" negative.

| candidate | coverage | measures | does not measure |
|---|---|---|---|
| vulns.kev = true | 282,801 banners (1.94 % of rows), 199 CVEs | a version-inferred CVE on the CISA known-exploited list | that the host is actually vulnerable (verified = true on only 4,808 banners) |
| vulns.ransomware_campaign = Known | 56,631 banners | CVE used by ransomware per the KEV catalogue | exploitation of this host |
| vulns.verified = true | 4,808 banners | provider tested and confirmed the CVE | anything about the 98.97 % unverified rest |
| opts_heartbleed | 926,405 rows tested: SAFE 532,759, ERROR 393,486, VULNERABLE 160 | an active test result (1 CVE) | other vulnerabilities |
| opts_vulns (non-empty) | 5,085 rows, 40 distinct ids (CVE-2018-18441 1,062, CVE-2020-0796 1,038, CVE-2015-0204 944, ... MS17-010 13; "~" prefix = likely) | provider-tested vulnerabilities | coverage beyond the few probes that test them |
| tags compromised / c2 / malware / doublepulsar | 77 / 31 / 5 / 1 rows | provider says the host is compromised or hostile | too rare to validate a ranking |
| tags eol-product / eol-os | 244,327 / 6,036 rows | end-of-life software observed | exploitability |
| tags honeypot | 250,439 rows | a decoy (negative: not a buyer) | |
| existing security vendor (07_what_we_sell_map.csv, is_what_we_sell) | 83,779 of 485,089 customer-domain entities | "already bought something in the category" | budget, satisfaction, or which product |

Rejected as ground truth: `module` values darktrack-rat (20,685 rows),
remcos-pro-rat (20,056), orcus-rat (12,088), ta14-353a (11,462). They are
probe names, not detections: on Google LLC IPs the 4 modules have 31,763
rows of which 16 carry a payload; on Aliyun IPs every row carries a payload
(07_ground_truth.json rat_module_by_org_payload); only 3,874 of 64,291 such
rows are honeypot-tagged. Tag c2 (31 rows) is the provider's actual C2 label.

Which case Stage 2 is in: no outcome label; 2 proxy families exist with
usable coverage at entity grain: (a) provider vulnerability labels (kev,
ransomware_campaign, verified, heartbleed), useful to validate "needs help
now"; (b) existing-vendor presence, useful to validate "already a
customer of someone". Both are partially circular if used as features too;
Stage 2 must hold one out.
