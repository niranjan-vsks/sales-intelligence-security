# 08_candidates.md

FULL (14,608,406 banners; 485,089 customer-domain entities) unless marked.
Lift = rate of a rep in the slice / rate in the population (07_rare_values.csv,
grain banner or entity), or top-decile / bottom-decile rate (07_derived.csv).
Reps and clusters: 07_clusters.md. Lifts of exactly 6.139 at entity grain on
r_vuln mean "every entity in the slice has a vuln" (ceiling = 1 / 0.163).

## The 6 facts

1. **grain**: 1 row = 1 service banner (1 IP, 1 port, 1 transport, 1 scan
   time), key `_shodan.id` (unique). Roll-up to a buyer: customer domain =
   an element of `domains` covering 50 IPs or fewer (06_relationships.md
   roll-up). `org`/`asn` name the network operator, not the buyer.
2. **counts**: 14,608,406 rows (14,608,407 lines, 1 unparseable). 4,992,440
   distinct IPs. 485,089 customer-domain entities covering 1,074,635 rows
   (7.36 %); 92.6 % of rows are unattributable by that key (CDN/WAF edges,
   cloud, ISP space, no reverse DNS).
3. **snapshot, not history**: 1 scan window, 2026-10-25 18:13 to
   2026-10-26 13:06; 95.7 % of rows in 1 hour (2026-10-26 12:00-13:00).
   Re-observations of the same service span under 1 hour at p99. No
   change-over-time inside the file; "right now" = this scan, plus
   certificate issue/expiry dates. Freshness must come from comparing files.
4. **representative columns (07.1)**: r_vuln (K1), cpe23 (K2), module (K3),
   data_len (K4), domains (K5, the key), org (K6), cert_issuer_o (K7),
   r_selfsigned / r_certexpired (K8), r_waf (K9), country_code (K10), uptime (K11).
5. **coverage above 50 %**: C-13 (entity service breadth, 100 % of
   entities), D-18 (operator-only domain, decidable on 74.1 % of rows), D-20
   (no reverse DNS, decidable on 100 %). No positive raw signal reaches 50 %
   of rows; at entity grain C-01 (versioned fingerprint, r_cpe 70.2 % of
   entities) is the broadest raw one.
6. **ground truth**: none for buying. Proxies: vulns.kev on 282,801
   banners (1.94 %), ransomware_campaign Known on 56,631, vulns.verified on
   4,808, heartbleed VULNERABLE 160; existing security vendor on 83,779
   entities (17.3 %). 07_ground_truth.md.

---

### C-01  versioned software fingerprint

type            raw
columns         cpe23, product, version, http_server
computation     len(cpe23) > 0; version digits in http_server (queries/07_signals.py, slice `<populated>`)
coverage        20.91 % of rows; 70.2 % of entities (r_cpe entity rate)
direction       present = software and version are visible, so known CVEs and end-of-life status can be attached
evidence        cpe23 populated: banner lift r_vuln 4.76, r_eol 4.77, r_certexpired 2.85; product populated r_vuln 5.21, r_eol 5.52. Entity grain http_server "nginx/1.14.1" r_vuln 6.14 (ceiling), r_eol 11.0; "Apache/2.2.15 (CentOS)" r_vuln 6.14, r_selfsigned 3.35
cluster         K2
absence_meaning unobserved (fingerprinting only succeeds on some modules)
cost            cheap
ground_truth    vulns.kev, vulns.verified
confidence      high that it carries information; it is the input to C-02, not independent of it

### C-02  known-vulnerable version present

type            raw
columns         n_vulns, max_cvss, max_epss (vulns child table)
computation     n_vulns > 0 (or max_cvss >= 7)
coverage        3.20 % of rows; 16.3 % of entities
direction       present = needs help now: exposed software with published CVEs
evidence        max_cvss populated: banner lift r_eol 25.8, r_certexpired 4.48, r_selfsigned 2.05, r_waf 0.18
cluster         K1
absence_meaning unobserved where cpe23 is empty; informative (no known CVE) where cpe23 is present
cost            cheap (medium for kev/epss via the child table join)
ground_truth    vulns.verified (4,808 banners), opts_vulns, heartbleed VULNERABLE
confidence      medium: 99 % of CVEs are inferred from version strings (verified = false), so it measures version age as much as exposure

### C-03  end-of-life product tag

type            raw
columns         tags
computation     list_contains(tags, 'eol-product')
coverage        1.67 % of rows; 9.07 % of entities
direction       present = unsupported software, overdue for remediation
evidence        tag eol-product: banner lift r_vuln 25.8, r_cvss7 26.9, r_certexpired 4.49, r_waf 0.092
cluster         K2 (with K1)
absence_meaning unobserved where cpe23 is empty
cost            cheap
ground_truth    vulns.kev
confidence      medium: strong lift, but partly the same fact as C-02

### C-04  self-signed or device-default certificate

type            raw
columns         cert_issuer_o, cert_self_signed, tags
computation     cert_self_signed OR list_contains(tags,'self-signed'); issuer values in 07_rare_top_by_rep.csv
coverage        0.94 % of rows; 3.71 % of entities (r_selfsigned rate)
direction       present = unmanaged admin interface or appliance default config
evidence        tag self-signed: banner lift r_selfsigned 104, r_certexpired 36.4, r_vuln 2.05. Issuers: Plesk r_certexpired 216; Ubiquiti Networks Inc. r_vuln 27.1, r_certexpired 34.8; DrayTek Corp. r_certexpired 33.2; "HTTPS Management Certificate for SonicWALL (self-signed)" r_selfsigned 106.5
cluster         K8
absence_meaning unobserved outside rows with a TLS block (6.78 % of rows)
cost            cheap
ground_truth    none
confidence      medium: clear lift, small coverage

### C-05  legacy TLS negotiated (SSLv3 / TLSv1.0)

type            raw
columns         ssl_version
computation     ssl_version IN ('SSLv3','TLSv1.0')
coverage        6,707 rows (0.046 %); 1,745 entity-slice memberships (SSLv3 1,301, TLSv1.0 444)
direction       present = outdated crypto stack
evidence        SSLv3 banner lift r_certexpired 98.0, r_selfsigned 51.3, r_vuln 5.01; entity r_certexpired 7.67, r_selfsigned 10.3. TLSv1.0 banner r_certexpired 52.5, r_selfsigned 55.7; entity r_certexpired 5.50
cluster         K7
absence_meaning unobserved outside TLS rows
cost            cheap
ground_truth    none
confidence      low: very small coverage. The ssl_versions list (accepted versions) could widen it; not computed

### C-06  exposed remote-admin or data service on the entity

type            raw (entity roll-up)
columns         module, data_len, tags
computation     any banner of the entity with module in (rdp, ssh, smb, telnet, ftp, mysql) and a payload; 07_what_we_sell_map.csv P02
coverage        entities: ssh 8,698; ftp 5,969; rdp 2,157; mysql 1,820; smb 345; telnet 270 (overlapping); 188,512 rows
direction       present = internet-reachable attack surface
evidence        entity lifts r_vuln: smb 3.65, ssh 2.37, telnet 2.27, rdp 1.87, mysql 1.78, ftp 1.37; r_selfsigned: rdp 23.7, smb 6.87, telnet 6.48, ftp 5.42; r_waf: 0.13 to 0.29. Banner-grain lifts are not usable here (module decides which reps can exist)
cluster         K3
absence_meaning unobserved: absence means no probe hit, not proven closed
cost            medium (entity join)
ground_truth    opts_vulns (CVE-2020-0796, MS17-010 are SMB tests)
confidence      medium

### C-07  Windows host internals exposed (NTLM / RDP fingerprints)

type            raw
columns         blocks (ntlm, rdp_encryption), os
computation     list_contains(blocks,'ntlm') OR os LIKE 'Windows%'
coverage        29,748 rows with ntlm; 2,741 entities
direction       present = Windows server reachable; ntlm also leaks the internal AD domain name (05_semistructured.md)
evidence        entity lift ntlm r_selfsigned 19.6, r_vuln 1.74, r_eol 1.90, r_waf 0.24; os "Windows Server 2022 (build 10.0.20348)" entity r_selfsigned 20.5
cluster         K3 (overlaps C-06 rdp)
absence_meaning unobserved
cost            medium (extra_json parse for the domain name)
ground_truth    none
confidence      medium

### C-08  provider asset-class tags database / iot

type            raw
columns         tags
computation     list_contains(tags,'database') OR list_contains(tags,'iot')
coverage        45,054 rows (15,455 + 29,599 element counts); 2,202 + 276 entities
direction       present = sensitive asset class exposed
evidence        entity lift database r_eol 4.41, r_selfsigned 4.81, r_vuln 1.78, r_waf 0.12; iot r_selfsigned 6.44, r_eol 2.80, r_vuln 2.56
cluster         K3
absence_meaning unobserved
cost            cheap
ground_truth    none
confidence      low: small entity counts

### C-09  operating system fingerprinted

type            raw
columns         os
computation     os IS NOT NULL
coverage        4.10 % of rows
direction       present = the host leaks its OS, typically an older self-managed server
evidence        os populated: banner lift r_eol 12.7, r_vuln 7.99, r_selfsigned 6.47, r_waf 0.10
cluster         K2
absence_meaning unobserved
cost            cheap
ground_truth    vulns.kev
confidence      medium

### C-10  WAF / edge protection already in front (negative)

type            negative
columns         http_waf
computation     07_what_we_sell_map.csv W01
coverage        1,089,388 rows (7.46 %); 83,779 entities have any is_what_we_sell (17.3 %)
direction       present = already bought web protection; weaker need, possible competitive displacement
evidence        http_waf populated: banner lift r_waf 9.33, r_vuln 0.18, r_eol 0.092; Sucuri CloudProxy entity r_vuln 0.54, r_eol 0.22
cluster         K9
absence_meaning informative only on http/https rows (detector runs there)
cost            cheap
ground_truth    itself (existing-vendor proxy)
confidence      high

### C-11  network security appliance on the perimeter (negative, and surface)

type            negative
columns         product, cpe23
computation     07_what_we_sell_map.csv W03, W04
coverage        28,342 rows (product); entity SonicWall 930, FortiGate 161
direction       present = already owns a firewall/VPN vendor; but the appliance itself raises certificate hygiene issues
evidence        entity lift SonicWall r_selfsigned 12.9, r_certexpired 2.17, r_vuln 1.35; Fortinet FortiGate r_selfsigned 8.70, r_vuln 1.91
cluster         K2
absence_meaning unobserved
cost            cheap
ground_truth    itself
confidence      medium

### C-12  self-managed hardening headers (HSTS / CSP)

type            negative
columns         http_header_names
computation     07_what_we_sell_map.csv W07
coverage        401,994 rows (2.75 %)
direction       present = security-mature web team (substitute); absence on a live site = gap
evidence        strict-transport-security banner lift r_waf 2.93, r_vuln 1.58; content-security-policy r_waf 2.45, r_vuln 2.13
cluster         K9
absence_meaning informative within rows that have http headers (28.4 % of rows)
cost            cheap
ground_truth    none
confidence      low: lift on r_vuln is above 1, so it is not a clean "protected" marker

### C-13  entity service breadth

type            derived
columns         per entity: count distinct module, count distinct port
computation     07_derived.csv D-E04 (n_modules), D-E03 (n_ports)
coverage        100 % of entities
direction       high = larger exposed footprint
evidence        top vs bottom decile n_modules: r_selfsigned 3.25, r_vuln 1.34, r_waf 2.37; n_ports: r_selfsigned 3.06, r_vuln 1.25, r_waf 2.69. Quantiles n_modules p50 1, p90 2, p99 5
cluster         K3
absence_meaning n/a
cost            medium (group by entity)
ground_truth    vulns.kev
confidence      medium: broad coverage, moderate lift, and it rises with r_waf too (size effect)

### C-14  more web components than peers

type            derived
columns         http_components, module, country_code
computation     07_derived.csv D-P23: percent_rank(len(http_components)) within module x country_code
coverage        29.5 % of rows
direction       high = richer, more custom web stack
evidence        top vs bottom decile: r_vuln 9.21, r_cvss7 7.74, r_eol 3.84, r_waf 0.47
cluster         K2 / K4
absence_meaning unobserved outside http rows
cost            medium (window function)
ground_truth    vulns.kev
confidence      medium

### C-15  fingerprinted software per header (n_cpe / n_headers)

type            derived
columns         cpe23, http_header_names
computation     07_derived.csv D-R02
coverage        18.9 % of rows
direction       high = many identifiable products, few response headers: plain, unhardened server
evidence        top vs bottom decile: r_vuln 12.97, r_cvss7 13.35, r_eol 10.96, r_waf 0.026. Spearman vs inputs 0.65 / -0.68 (survives the 0.9 rule)
cluster         K2 x K4
absence_meaning unobserved
cost            cheap
ground_truth    vulns.kev
confidence      medium: strong lift, but partly re-expresses C-01

### C-16  old certificate for its peer group

type            derived
columns         cert_issued, timestamp, module, country_code
computation     07_derived.csv D-P25: percent_rank(cert_age_days) within module x country_code
coverage        6.78 % of rows
direction       high = certificate not rotated, neglected service
evidence        top vs bottom decile: r_certexpired 88.4, r_vuln 2.21, r_selfsigned 1.78
cluster         K8
absence_meaning unobserved outside TLS rows
cost            medium
ground_truth    none
confidence      medium (cert age and expiry are related by construction)

### C-17  hosted on a smaller cloud provider

type            raw
columns         cloud_provider
computation     cloud_provider IN ('DigitalOcean','Vultr','Linode')
coverage        143,194 rows (0.98 %); entities Linode 3,329, Vultr 2,229
direction       present = self-managed VMs rather than managed platforms
evidence        banner lift r_vuln: DigitalOcean 9.30, Linode 2.75, Vultr 2.47; r_eol 13.2 / 2.59 / 3.67. Entity Linode r_vuln 2.03, Vultr 1.58
cluster         K6
absence_meaning unknown
cost            cheap
ground_truth    none
confidence      low: provider mix may proxy for module mix

### D-18  only operator domains (disqualifier)

type            disqualifier
columns         domains, ip_str
computation     every domain on the row covers more than 50 IPs (07_negative.json)
coverage        decidable on 74.1 % of rows; triggers on 9,750,263 rows (66.7 %)
direction       present = the row belongs to a CDN, cloud or ISP, not a prospect
evidence        06_rollup.json domain_ip_cutoffs; 07_negative.json disqualifiers
cluster         K5 / K6
absence_meaning n/a
cost            medium (domain IP counts)
ground_truth    none
confidence      high on the big zones; the 50-IP cutoff is a parameter

### D-19  honeypot or scanner (disqualifier)

type            disqualifier
columns         tags
computation     list_contains(tags,'honeypot') OR list_contains(tags,'scanner')
coverage        250,530 rows (1.71 %); 322 entities
direction       present = not a real buyer's asset
evidence        banner lift r_eol 0.0, r_certexpired 0.092 (not ordinary hosts); entity r_certexpired 5.26, r_selfsigned 3.68. 154,211 of the honeypot rows are on 2 Aliyun org spellings
cluster         K3
absence_meaning unknown
cost            cheap
ground_truth    none
confidence      high

### D-20  no reverse DNS (disqualifier for name-based roll-up)

type            disqualifier
columns         domains
computation     len(domains) = 0
coverage        3,783,508 rows (25.9 %)
direction       present = cannot be named by the domain key; fall back to cert_subject_cn / http_host
evidence        07_negative.json disqualifiers; domains populated lifts r_vuln 0.80, r_waf 1.14 (07_rare_values.csv `<populated>`)
cluster         K5
absence_meaning informative: row is unattributable by this key
cost            cheap
ground_truth    none
confidence      high
