# Review of P2 (entity resolution), non-author

Reviewer: fresh Opus 5.5 session, 2026-11-02, with no part in the P2 build. Scope: correctness
of the code in `git diff 6c96317..e1eca2e -- sis/ config/ tests/` against cards/P2.md,
DATA_MODEL 2 and DESIGN 4. Deviations 1 to 5 are accepted by the architect and are not
re-argued here.

## Verdict: PASS WITH FIXES

2 bugs, both small in count, both fixed in commit "P2: review fixes":

| # | Bug | 1-line repro (before the fix) | Real file |
|---|---|---|---|
| F1 | `normalise_name` accepts partial IPs and version strings: `ipaddress` rejects only complete IPs, and nothing else rejects a numeric last label | `normalise_name("74.18.178")` -> `'74.18.178'` (and `"1.0"` -> `'1.0'`) | 5 domain-kind entities: `74.18.178`, `30.0`, `74.0`, `1.1`, `1.0` (8 banners) |
| F2 | A fallback name reached as `cert_cn` on some banners and as `http_host` on others gets 2 entity ids. Step 6 re-keys only to `domain` | `resolve` on rows `[{cert_subject_cn: "a.x.org"}, {http_host: "b.x.org"}]` -> entities `cert_cn:x.org` and `http_host:x.org` | 5 names: airthings.com, cloudflareaccess.com, ilovefbgames.com, playcom.ai, redcentricplc.com |

Fixes: F1 rejects a name whose last label is all digits (`sis/entities/normalise.py`). F2
gives a non-domain fallback name the best kind it was reached by anywhere in the file
(cert_cn before http_host), so the same rule as step 5 decides the key
(`sis/entities/sql/06_banner_entity.sql`). Each has a test that was red before the fix:
`test_normalise` (2 new asserts) and `test_fallback_name_reached_by_cert_and_host_is_one_entity`.

## a. Tests and acceptance commands, run by the reviewer

Before the fixes, on e1eca2e:

```
$ uv run pytest -q
79 passed in 22.20s
$ uv run ruff check .
All checks passed!
$ uv run mypy sis
Success: no issues found in 21 source files
$ uv run pytest tests/test_resolve.py -q
22 passed in 10.99s
$ time uv run sis resolve 8e252f8fadb5f0887ac6f7c59a757fc5ffc17324311b06c818abe87755a611ee-17619943483
entities active 495429 blocked 532
by_kind {'cert_cn': 12643, 'domain': 481186, 'http_host': 1600}
banners primary 1063060 fallback 38433 none 13506913
unattributed {'no_name': 3779115, 'operator_only': 9727798, 'over_cutoff': 0, 'blocked': 5314}
operators derived 3777
real	3m16.758s
$ uv run sis resolve --merge
merged 1 file(s): 495961 entities -> C:\Users\NIRANJAN VSKS\sis_data\current\entities.parquet
```

Determinism: md5 of entities.parquet `3afb9356...`, banner_entity.parquet `1f864d0b...` and
config/operator_domains.txt `c018f35d...` were identical before and after this rerun.

Domain-kind active entities 481,186 vs 485,089 - 343 blocked = 484,746: -0.73 %, inside the
1 % bar. over_cutoff 0. Merge count 495,961 = 495,429 + 532.

After the fixes:

```
$ uv run pytest -q
80 passed
$ uv run sis resolve 8e252f8f...-17619943483
entities active 495419 blocked 532
by_kind {'cert_cn': 12643, 'domain': 481181, 'http_host': 1595}
banners primary 1063054 fallback 38433 none 13506919
unattributed {'no_name': 3779121, 'operator_only': 9727798, 'over_cutoff': 0, 'blocked': 5314}
operators derived 3777
$ uv run sis resolve --merge
merged 1 file(s): 495951 entities -> C:\Users\NIRANJAN VSKS\sis_data\current\entities.parquet
```

Domain-kind active 481,181 vs 484,746: -0.74 %. operator_domains.txt unchanged (md5
`c018f35d...`).

## b. Data checks (DuckDB over $SIS_DATA/8e252f8f...-17619943483/)

Checks 1 to 4 below are on the fixed output; check 3 also shows the pre-fix result.

**1. No entity key_value is in config/operator_domains.txt.**

```sql
SELECT count(*) AS n_ops,
       (SELECT count(*) FROM e JOIN ops ON ops.name = e.key_value) AS entity_hits
FROM ops   -- ops = every non-comment line of operator_domains.txt, lowercased
```
`n_ops 3794 | entity_hits 0`. Pass.

**2. No banner has both a primary and a fallback row.**

```sql
SELECT count(*) FROM (SELECT banner_id FROM be GROUP BY 1
                      HAVING count(DISTINCT attribution) > 1)
```
`0`. Pass.

**3. Every fallback key_value that exists as a domain entity was re-keyed.**

```sql
-- 3b: fallback rows that kept a non-domain kind although the value is a domain entity
SELECT count(*) FROM be WHERE attribution = 'fallback' AND key_kind <> 'domain'
  AND key_value IN (SELECT key_value FROM e WHERE key_kind = 'domain')
-- 3a: any key_value under 2 key_kinds
SELECT count(*) FROM (SELECT key_value FROM e GROUP BY 1 HAVING count(DISTINCT key_kind) > 1)
```
3b: `0` before and after. 3a: `5` before the fix (all cert_cn + http_host pairs, F2), `0`
after. Fallback rows by key_kind after the fix: domain (re-keyed) 13,492, cert_cn 24,268,
http_host 1,726.

**4. The 20 largest active entities by n_banners.**

```sql
SELECT key_kind, key_value, n_banners, n_ips, n_ports, n_modules, country_code, org_mode
FROM e WHERE status = 'active' ORDER BY n_banners DESC, entity_id LIMIT 20
```

| key_value | n_banners | n_ips | ports | modules | org_mode | customer or operator |
|---|---|---|---|---|---|---|
| solveforce.com | 6,371 | 6 | 2 | 2 | Cloudflare, Inc. | customer (telecom reseller, thousands of microsite vhosts) |
| my-free.website | 6,200 | 2 | 2 | 2 | Cloudflare, Inc. | platform: free website builder; tenants are its subdomains. A business, but its banners describe the platform |
| btx.com | 4,701 | 4 | 2 | 2 | Cloudflare, Inc. | customer |
| ontraport.com | 3,748 | 11 | 2 | 2 | Flexential Colorado Corp. | customer (SaaS; hosts customer pages as vhosts) |
| mystrikingly.com | 3,724 | 6 | 2 | 2 | Amazon.com, Inc. | platform: website builder (as my-free.website) |
| p-kit.com | 3,210 | 7 | 2 | 2 | Amazon Technologies Inc. | platform: website builder (as above) |
| zubergardner.com | 3,163 | 1 | 2 | 2 | Amazon Technologies Inc. | customer |
| pclv.net | 3,058 | 4 | 2 | 2 | Amazon Data Services Northern Virginia | customer |
| bandzoogle.com | 2,756 | 4 | 2 | 2 | Cloudflare, Inc. | platform: musician website builder |
| teamleaseregtech.com | 2,680 | 8 | 9 | 4 | Cloudflare, Inc. | customer |
| lawyer.com | 2,674 | 5 | 2 | 2 | Equinix, Inc. | customer |
| bdo.com | 2,652 | 10 | 2 | 2 | Cloudflare, Inc. | customer |
| schoolloop.com | 2,312 | 3 | 2 | 2 | APNIC Research and Development | customer (SaaS) |
| cliniko.com | 2,252 | 50 | 2 | 2 | Amazon Technologies Inc. | customer (SaaS), exactly at the 50-IP cutoff |
| jubo.com.au | 2,013 | 5 | 2 | 2 | Linode | customer |
| alvon.nl | 2,007 | 1 | 2 | 2 | NG-BLU Networks B.V. | customer |
| staples.com | 2,002 | 19 | 2 | 2 | Amazon Technologies Inc. | customer |
| vodori.com | 1,950 | 29 | 2 | 2 | Amazon Technologies Inc. | customer |
| hpage.com | 1,862 | 3 | 2 | 2 | Jonas Frey trading as Probe Networks | platform: website builder |
| npage.de | 1,806 | 3 | 2 | 2 | Jonas Frey trading as Probe Networks | platform: website builder (same company as hpage.com) |

No network operator slipped through. 6 of 20 are website-builder platforms: each is a real
company running its own few IPs, so keeping them as entities is defensible, but their
n_banners counts tenant vhosts, not services (2 ports each). P3 does not use n_banners;
breadth is n_modules / n_ports, which stays 2 for all 6. No change made; noted for the
write-up.

**5. 20 random active entities (seed 13), up to 3 banners each** (run before the fixes; the
reservoir sample changes with the input, so it was not re-drawn).

```sql
CREATE TABLE s AS SELECT entity_id, key_kind, key_value, n_banners, org_mode
  FROM e WHERE status = 'active' ORDER BY entity_id;
WITH pick AS (SELECT * FROM s USING SAMPLE 20 ROWS (reservoir, 13)),
bb AS (SELECT p.key_kind, p.key_value, p.n_banners, x.banner_id,
         row_number() OVER (PARTITION BY p.entity_id ORDER BY x.banner_id) rn
       FROM pick p JOIN be x USING (entity_id))
SELECT bb.key_kind, bb.key_value, bb.n_banners, b.module, b.port, coalesce(b.ip_str, b.ipv6) ip,
       b.org, b.domains, b.hostnames, b.cert_subject_cn, b.http_host, left(b.http_title, 50)
FROM bb JOIN b ON b.id = bb.banner_id WHERE rn <= 3 ORDER BY bb.key_value, b.port
```

| entity | banners | what the banners show | grouping right? |
|---|---|---|---|
| 23-147-254-113-on-nets.com | 1 | HGC ISP; the reverse DNS embeds the IP, so every IP is its own registered domain | no: ISP per-IP zone, never over the cutoff |
| americaslngsummit.com | 5 | Incapsula edge IPs, `domains` holds ~20 tenant names | name right, banners describe the edge (the known case; P3 edge rule) |
| canadaboa.com | 1 | shared-hosting IP whose `domains` lists hundreds of names | weak: 1 shared server attributed to every tenant |
| ebi.com.gt | 6 | Incapsula edge, list includes imperva.com | name right, edge banners (P3 edge rule) |
| fiftyonegeel.be | 2 | own Scaleway host, ssh + ikettle | yes |
| fivestarplantation.com | 7 | Cloudflare, own cert and Host | yes (the site now serves gambling spam) |
| globalpay.com.co | 1 | EC2, `*.globalpay.com.co` cert | yes |
| insiderkontoret.no | 2 | own host, crm.insiderkontoret.no | yes |
| kualo.net | 11 | Kualo Limited's own servers (the hoster itself, 11 banners) | yes: the hosting company as a business |
| maormaymon.com | 1 | Firebase shared IP with many tenant domains | weak: shared server |
| mnw.agency | 1 | EC2, api.licensing.mnw.agency | yes |
| offtak.co.jp | 1 | etius.jp shared mail server | weak: the hoster's mail server |
| onemove.id | 1 | Linode, `*.onemove.id` cert | yes |
| personalcenterhost.com.br | 1 | Contabo shared IP with many tenant domains | weak: shared server |
| portolasystems.com | 1 | own host on Sonic.net | yes |
| rubysinn.com | 2 | Cloudflare, own cert | yes |
| savills-aguirrenewman.pt | 6 | Savills CloudFront distribution carrying ~40 savills domains | right company, split over many savills-* entities |
| tamazon.eg (cert_cn) | 8 | Amazon Egypt on CloudFront; `tamazon.eg` is a typo-defence SAN on Amazon's certificate | no: a SAN fan-out of an operator-sized company |
| thevisionaccelerator.com | 1 | Akamai edge serving GM microsites | name plausible (GM), banner is the edge |
| tochno-pridu.ru | 1 | own host | yes |

11 right, 5 right name but edge or split, 2 weak (shared server), 2 wrong. None of the wrong
ones is a code bug against the card: they are consequences of the card's key (reverse-DNS
registered domain, every SAN a candidate). Recorded as known limits below.

## c. Code read for bugs a test would not catch

| Area | Finding |
|---|---|
| Wildcards | `registered_domain` drops a leading `*.`; `*.*.example.com` and mid-label `*` are rejected by `_BAD_CHARS`. `domains` entries with `*` are rejected. Correct. |
| IP literals in Host | `host_registered_domain` strips 1 `:port`, rejects bracketed IPv6; unbracketed IPv6 has several `:` and is rejected by `_BAD_CHARS`; `1.2.3.4:80` and `1.2.3.4.` -> None. Correct. Partial IPs were the gap (F1). |
| Trailing dots | `rstrip(".")` before the `www.` strip; `example.com..` and `EXAMPLE.COM:443.` handled. Correct. |
| IDNA / punycode | No normalisation between U-labels and A-labels: `bücher.de` and `xn--bcher-kva.de` would be 2 entities. On this file every entity key is ASCII (0 non-ASCII keys, 444 `xn--` keys), so no effect today. Not fixed; a 1-line `idna` encode is the fix if a file ever carries U-labels. |
| Case | `.lower()` before every check. Correct. |
| Public suffix list | `tldextract` runs without the PSL private section, while Shodan's `domains` evidently uses it (1,104 domain keys such as `interlock.uk.com` are not their own tldextract registered domain). So a certificate-only customer on a private suffix (`foo.uk.com`, `x.herokuapp.com`) rolls up to `uk.com` / `herokuapp.com`, which is above the cutoff and becomes an operator. Consistent and harmless for primary keys; loses some fallback tenants. Not fixed (changes counts beyond a review fix); noted. |
| over_cutoff assert | Tautological by construction since deviation 1 (03_operators.sql makes every over-cutoff name an operator unless it is a domain-kind customer, and 05_fallback.sql admits those). It still guards a regression in either file. |
| SQL splitting | `run_sql` splits on `;`; no statement in sql/ holds a `;` inside a string. Fine. |

## Known limits, not bugs (for the write-up)

- Shared-server banners: a banner whose `domains` lists hundreds of tenants (shared hosting,
  Firebase, Incapsula edges) is attributed to every listed tenant. The P3 edge rule removes
  the Incapsula and CDN cases from exposure; plain shared hosting remains.
- Certificate SAN fan-out: every SAN's registered domain is a candidate, so a large
  multi-brand certificate creates entities for defensive registrations (`tamazon.eg`).
- ISP zones that embed the IP in the registered domain never cross the 50-IP cutoff.
