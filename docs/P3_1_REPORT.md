# P3.1 report: hosting zones, surface definition, label scope

File 8e252f8fadb5f0887ac6f7c59a757fc5ffc17324311b06c818abe87755a611ee-17619943483.
"Before" is the P3/P4 state (scoring_version 1.0.0, copied to `$SIS_DATA/p31_before/` before
any rerun); "after" is the final P3.1 run (scoring_version 1.1.0). Every number below comes
from a query on those 2 sets of outputs or from the runs' own printed output.

## 1. Operators added (defect 1)

| source | matched | added beyond seed and cutoff |
|---|---|---|
| rule 1, template zone (registered domain encodes an IP fragment) | 6,732 | 6,729 |
| rule 2, templated hostnames (>= 10 IPs, >= 80% of hostnames with 2+ digit groups in the first label) | 1,859 | 1,858 (not counting rule 1) |
| hand list, top-100 eyeball, round 1 | 57 | 57 |
| hand list, top-100 eyeball, round 2 | 72 | 72 |

Rule 2, the 30 largest by banners, with the builder's verdict. None is plainly a single
business, so none was reverted.

| name | banners | ips | hostnames | templated | verdict |
|---|---|---|---|---|---|
| nextgenerationnetworks.nl | 2,054 | 43 | 43 | 41 | NG-BLU network zone (already in the seed) |
| vercel-dns-016.com | 947 | 14 | 412 | 410 | Vercel platform DNS, operator |
| herokudns.com | 707 | 32 | 316 | 274 | Heroku platform DNS, operator |
| above.com | 578 | 25 | 25 | 24 | domain parking (Trellian), operator |
| vercel-dns-017.com | 351 | 14 | 151 | 150 | Vercel platform DNS, operator |
| interconnect.cz | 328 | 16 | 16 | 15 | ISP customer zone |
| 153.in-addr.arpa | 302 | 25 | 25 | 24 | reverse DNS |
| netdatacomm.cz | 268 | 13 | 13 | 13 | ISP |
| fiberby.net | 237 | 36 | 36 | 34 | ISP |
| wilkes.net | 235 | 15 | 16 | 15 | ISP (address-named hosts) |
| vermontel.net | 179 | 10 | 10 | 10 | ISP |
| misaka.io | 161 | 29 | 29 | 26 | network operator, customer zone |
| triara.com | 149 | 40 | 40 | 40 | data centre, `cust-<ip>` hosts |
| rain-pods.com | 148 | 42 | 13 | 13 | UUID-named pods on AWS; a platform's tenant pods, the least clear-cut, kept as operator |
| oneqode.net | 139 | 10 | 10 | 10 | hosting |
| as47215.net | 136 | 10 | 10 | 10 | ASN reverse zone |
| silicanetworks.com | 129 | 50 | 50 | 50 | ISP |
| g30.se | 128 | 20 | 20 | 20 | ISP (Videnca), address-named hosts |
| fasthosts.net.uk | 115 | 46 | 46 | 46 | hosting |
| selfnet.cz | 113 | 14 | 14 | 14 | ISP |
| plateautel.net | 100 | 46 | 47 | 44 | ISP |
| ves.io | 99 | 26 | 97 | 97 | F5 Distributed Cloud edge, operator |
| medianetitalia.net | 97 | 44 | 44 | 44 | ISP |
| spil.co.id | 97 | 33 | 34 | 32 | ISP, `ip-<addr>` hosts |
| hebergement-tasfrance.com | 96 | 25 | 25 | 22 | hosting |
| vetta.net.nz | 95 | 20 | 19 | 17 | ISP |
| googlesyndication.com | 93 | 16 | 94 | 92 | Google ad-serving infrastructure, not a prospect |
| yourhostingaccount.com | 90 | 45 | 45 | 43 | shared hosting (Newfold) |
| imatrix.nl | 89 | 14 | 14 | 14 | FttH ISP |
| ruraltel.net | 86 | 18 | 18 | 16 | ISP |

## 2. Entities

| | before | after |
|---|---|---|
| active | 495,419 | 487,133 |
| blocked | 532 | 489 |
| active domain | 481,181 | 472,508 |
| active cert_cn | 12,643 | 12,983 |
| active http_host | 1,595 | 1,642 |
| banners primary | 1,063,054 | 991,550 |
| banners fallback | 38,433 | 39,993 |

cert_cn and http_host entities grow slightly: banners of a hosting zone that is now an operator
can fall back to a tenant's certificate or Host name. Unattributed after: no_name 3,779,121,
operator_only 9,797,742, over_cutoff 0, blocked 4,745.

## 3. Segments (defect 2)

| segment | before | share | after | share |
|---|---|---|---|---|
| untouched | 148,502 | 29.98% | 300,849 | 61.76% |
| partially_covered | 105,054 | 21.21% | 103,141 | 21.17% |
| displace | 77,966 | 15.74% | 77,530 | 15.92% |
| low_surface | 163,897 | 33.08% | 5,613 | 1.15% |
| total | 495,419 | | 487,133 | |

`C_any_service` fires on almost every entity with a non-edge banner: on this file 6,813,284 of
14.6M banners are an `auto` probe with no payload, and only entities whose every non-edge banner
is such a probe (or edge-only entities) stay `low_surface`. Tested-positive rate by segment
(label_any_tested): untouched 0.213% -> 0.194%, partially_covered 0.106% -> 0.068%, displace
0.065% -> 0.035%, low_surface 0.199% -> 0.000% (0 of 5,613). The segment now means what its
name says. Stage 1 target group recomputed: 129,495 against 131,104 (-1.23%).

## 4. Labels (defect 3, plus the entity change)

| label | before | base rate | after | base rate |
|---|---|---|---|---|
| label_kev | 53,287 | 10.756% | 49,844 | 10.232% |
| label_verified | 791 | 0.160% | 669 | 0.137% |
| label_heartbleed | 50 | 0.010% | 44 | 0.009% |
| label_opts_vulns | 791 | 0.160% | 669 | 0.137% |
| label_any_tested | 805 | 0.162% | 681 | 0.140% |
| label_has_vendor | 77,966 | 15.737% | 77,530 | 15.916% |
| label_ransomware | 14,010 | 2.828% | 12,947 | 2.658% |

The after column carries both changes, the edge-banner scope and the 8,286 fewer active
entities; they were not measured separately. label_has_vendor keeps edge banners by design and
moves only with the entities.

## 5. Headline metrics

label_any_tested, ranking by each model:

| model | p@100 | p@1000 [95% CI] | p@10000 | lift@1000 | rank-biserial |
|---|---|---|---|---|---|
| full before | 10.00% | 5.10% [3.90, 6.64] | 1.99% | 31.39 | 0.481 |
| full after | 3.00% | 3.90% [2.87, 5.29] | 1.57% | 27.90 | 0.597 |
| no_A before | 11.00% | 4.60% [3.47, 6.08] | 2.04% | 28.31 | 0.790 |
| no_A after | 6.00% | 2.80% [1.94, 4.02] | 1.41% | 20.03 | 0.845 |
| no_B before | 9.00% | 3.90% [2.87, 5.29] | 1.93% | 24.00 | 0.333 |
| no_B after | 3.00% | 2.30% [1.54, 3.43] | 1.40% | 16.45 | 0.278 |
| no_C before | 4.00% | 2.60% [1.78, 3.78] | 1.63% | 16.00 | 0.440 |
| no_C after | 3.00% | 2.30% [1.54, 3.43] | 1.38% | 16.45 | 0.576 |
| no_D before | 13.00% | 6.60% [5.22, 8.31] | 2.36% | 40.62 | 0.599 |
| no_D after | 11.00% | 4.50% [3.38, 5.97] | 1.72% | 32.19 | 0.579 |
| breadth_only before | 4.00% | 5.10% [3.90, 6.64] | 1.77% | 31.39 | 0.224 |
| breadth_only after | 4.00% | 3.40% [2.44, 4.71] | 0.97% | 24.32 | 0.124 |
| cve_count_only before | 7.00% | 3.30% [2.36, 4.60] | 1.03% | 20.31 | 0.278 |
| cve_count_only after | 7.00% | 3.30% [2.36, 4.60] | 0.85% | 23.61 | 0.239 |
| random before | 0.40% | 0.14% [0.07, 0.29] | 0.15% | 0.86 | 0.001 |
| random after | 0.20% | 0.12% [0.06, 0.26] | 0.12% | 0.86 | -0.004 |

label_kev:

| model | p@100 | p@1000 [95% CI] | p@10000 | lift@1000 | rank-biserial |
|---|---|---|---|---|---|
| full before | 72.00% | 57.50% [54.41, 60.53] | 61.80% | 5.35 | 0.854 |
| full after | 55.00% | 49.10% [46.01, 52.20] | 62.58% | 4.80 | 0.917 |
| no_D before | 81.00% | 74.40% [71.61, 77.01] | 66.17% | 6.92 | 0.893 |
| no_D after | 86.00% | 63.40% [60.37, 66.33] | 64.49% | 6.20 | 0.918 |
| breadth_only before | 67.00% | 59.80% [56.73, 62.80] | 32.72% | 5.56 | 0.039 |
| breadth_only after | 62.00% | 49.70% [46.61, 52.79] | 24.02% | 4.86 | 0.008 |
| cve_count_only before | 99.00% | 99.60% [98.98, 99.84] | 95.28% | 9.26 | 0.928 |
| cve_count_only after | 99.00% | 99.40% [98.70, 99.72] | 94.21% | 9.71 | 0.944 |

Untouched only, p@1000: label_any_tested 4.20% (base 0.213%) -> 3.40% (base 0.194%);
label_kev 53.40% -> 43.20%.

What this says, without softening:

- Precision at the top fell on every label. The hosting zones that became operators held many
  tested positives (a hoster's shared servers are exactly where the provider's probes hit), so
  removing them removed hits as well as noise. The ranking is more honest about who is a
  prospect, and less rich in tested vulnerabilities.
- The full model now edges past breadth_only at p@1000 on label_any_tested (3.9% against 3.4%),
  but the intervals overlap, so it does not clearly beat it there. It separates on rank-biserial:
  0.597 against 0.124 (it was 0.481 against 0.224).
- no_D still beats the full model at p@1000 on label_any_tested (4.5% against 3.9%) and on
  label_kev (63.4% against 49.1%). The gap is smaller than at 1.0.0 (6.6 against 5.1), but the
  segment multipliers still cost precision on vulnerability labels. With `low_surface` now 1% of
  entities, the remaining cost comes from `displace` (x0.6) and `partially_covered` (x0.85).
  Not changed: P3.1 does not touch multipliers.
- rank-biserial on label_kev rose from 0.854 to 0.917, and no_A still shows fact A carries the
  kev ranking (0.334), the circularity DESIGN.md 6 already states.
- The eval fixture was rewritten once with `--fixture` (the sanctioned use: scoring_version
  changed): precision_at_1000 on the fixture 0.022 (any_tested) and 0.612 (kev); thresholds
  0.0209 and 0.5814. A rerun of `sis evaluate` without `--fixture` gave a byte-identical report
  apart from wall time.

## 6. Top-100 hosting count

Counted by hand from key_value, org_mode and 4 sample hostnames per entity (`hosting` = a hosting
company, colocation, ISP or network operator's zone, or a reverse-DNS zone).

| state | hosting or network operators in the top 100 |
|---|---|
| before (1.0.0) | 95 (37 of them caught by rules 1 and 2) |
| after rules + hand list round 1 | 72 |
| after hand list round 2 (final) | 57 |

Target under 10: **not met**. The card allows 1 extension of the hand list; it was used. After
it, ranks 1 to 30 hold no hosting provider (universities, government sites, small businesses and
SaaS companies); from rank 31 down, hosters return. The rules catch zones whose names come from
an address (`ip-15-235-134.net`, `222-98-223-67-static.prioritycolo.com`), not hosters that
number their servers (`server150138.webhi.org`, `vm612.dnspropio.com`, `vps48110...`).

What-if for the architect (measured, not built): a rule-2 variant that counts a first label with
any digit (`\d`) instead of 2 digit groups, same 10-IP and 80% thresholds, would have caught 61
of the 129 hand-listed names. Its false-positive rate on real businesses was not measured.

## 7. Deviations

1. The card says rule 2 "catches hostinguk.net-style zones whose hostnames are
   server123.hostinguk.net", but the regex it gives (`\d+\D+\d+`, 2 digit groups) does not match
   `server123`. Built as the regex says; such zones went to the hand list (see 6).
2. Rule 2's "equals an IP with dots replaced" alternative is not coded separately: every such
   label already matches `\d+\D+\d+`.
3. Rule 2 is evaluated only for names with n_ips between `template_min_ips` and the cutoff;
   names above the cutoff are operators already.
4. Rules 1 and 2 add their names to the file's `# derived from` section of
   config/operator_domains.txt, like the cutoff-derived names, so a rerun is idempotent.
5. The hand list ran 2 rounds (57 + 72 = 129 names), round 2 tagged
   `# hosting, top-100 eyeball P3.1 round 2`. The operator file now allows a trailing `#`
   comment after a name, and the writer keeps the seed block verbatim.
6. The prerequisite moved from SQL into `config/scoring.yaml` as a list of signal ids
   (`prerequisite:`), validated against the catalogue; `02_facts.sql` uses it for both the
   prerequisite column and the `untouched` branch of the segment.
7. `C_any_service` gets evidence rows like every signal (up to 5 per entity), which grew
   evidence.parquet from 4,115,664 to 4,549,051 rows.
8. docs/RESOLVE_REPORT and docs/SCORE_REPORT were regenerated; their eyeball samples changed and
   were not re-judged. The P2 and P3 hand notes are kept at the end of each, labelled as history.
