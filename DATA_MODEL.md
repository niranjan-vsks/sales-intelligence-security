# DATA_MODEL.md

Every table the platform produces, where it lives, what computes it, and
whether it is built offline or read live. Column names in this document
are the names the build must use. Column names of the source banner table
are the ones the explorer's flattener already produces
(findings/02_columns.csv); they are not renamed.

Conventions:

- All offline tables are Parquet under `$SIS_DATA/<file_id>/...` for
  per-file tables and `$SIS_DATA/current/...` for the merged current
  state. `$SIS_DATA` defaults to `C:/Users/NIRANJAN VSKS/sis_data` and is
  never inside the repo.
- Every table has a `built_at TIMESTAMP` and a `pipeline_version VARCHAR`
  column, or a sidecar `_meta.json` with the same, so any row can be traced
  to a code version. As built this holds only for the P2 and P3 per-file
  tables (`resolve_meta.json`, `score_meta.json`) and the bundle
  (`bundle.json`). banners and vulns trace through their `ingest_log` row
  (`pipeline_version`, no `built_at`); `current/*.parquet`, `history/*` and
  `eval/*` carry neither (not built).
- IDs are deterministic. Re-running the same code on the same input yields
  byte-identical IDs. No autoincrement anywhere.
- Timestamps are UTC.

---

## 0. Source of truth: the raw delivery

A delivery is 1 compressed JSONL file as received. It is never modified.

```
file_id         VARCHAR   sha256 of the first 64 MiB, hex, then '-' and the total byte length
                          (a '-' not a ':' because file_id names a directory and ':' is illegal on Windows).
                          Cheap and stable. Real value for the delivery: 8e252f8f...-17619943483.
original_name   VARCHAR   filename as delivered
byte_length     BIGINT
received_at     TIMESTAMP
```

---

## 1. Layer 1: per-file flattened tables (offline, P1)

### 1.1 `banners` (per file)

Path: `$SIS_DATA/<file_id>/banners/part-*.parquet`
Grain: 1 row per banner. Key: `id` (the provider's `_shodan.id`, unique).

Columns: exactly the 93 columns in findings/02_columns.csv (the earlier
"96" was a miscount), produced by the flattener now at
sis/ingest/flatten.py. The
important ones for later layers:

```
id, module, timestamp, port, transport, ip_str, ipv6, org, isp, asn, os,
product, version, uptime, hostnames[], domains[], tags[], cpe23[],
vuln_ids[], n_vulns, max_cvss, max_epss, opts_heartbleed, opts_vulns[],
country_code, city, region_code,
http_status, http_title, http_server, http_waf, http_host, http_components[],
http_component_cats[], http_header_names[], http_headers (JSON string),
ssl_version, cert_issued, cert_expires, cert_expired, cert_subject_cn,
cert_subject_o, cert_issuer_o, cert_self_signed, cert_san[], ssl_versions[],
cloud_provider, cloud_region, data (first 2,000 chars), data_len, blocks[],
extra_json, record_bytes
```

Plus 1 new column added by P1: `file_id VARCHAR`.

### 1.2 `vulns` (per file)

Path: `$SIS_DATA/<file_id>/vulns/part-*.parquet`
Grain: 1 row per (banner, CVE). Key: (`id`, `cve`).

As built by P1 (the explorer's schema, unchanged on purpose):

```
id                   VARCHAR   = banners.id   (NOT banner_id)
module               VARCHAR
cve                  VARCHAR
cvss                 DOUBLE
cvss_version         DOUBLE
cvss_v2              DOUBLE
epss                 DOUBLE
ranking_epss         DOUBLE
verified             BOOLEAN
kev                  BOOLEAN   null when absent in source
n_references         BIGINT
summary              VARCHAR   first 500 chars
other_keys           VARCHAR   JSON of every other key; ransomware_campaign lives here:
                               json_extract_string(other_keys, '$.ransomware_campaign') -> 'Known' | 'Unknown' | null
file_id              VARCHAR
```

P4 (the eval labels) reads `ransomware_campaign` with that extraction;
P3 does not read it. Join to
banners on `vulns.id = banners.id`.

### 1.3 `ingest_log` (append-only, all files)

Path: `$SIS_DATA/ingest_log.parquet` (rewritten atomically on each append;
it is tiny).

```
file_id, original_name, byte_length, received_at, started_at, finished_at,
status            VARCHAR   'ok' | 'failed' | 'duplicate' | 'quarantined' | 'rejected' (not zstd)
lines_read, rows_written, rows_dropped, vuln_rows_written  BIGINT
dropped_reasons   VARCHAR   JSON, sorted keys, from: blank, json_parse, missing_id,
                            flatten_error, type_error, oversize
wall_seconds      DOUBLE
pipeline_version  VARCHAR
error             VARCHAR   null unless failed, rejected or quarantined
```

---

## 2. Layer 2: entities (offline, P2)

### 2.1 `banner_entity` (per file)

Path: `$SIS_DATA/<file_id>/banner_entity.parquet`
Grain: 1 row per (banner, entity). A banner can map to more than 1 entity
(a row with 2 customer domains). Most map to 0 or 1.

```
banner_id      VARCHAR
entity_id      VARCHAR   sha1 of (key_kind || ':' || key_value), hex, 40 chars
key_kind       VARCHAR   'domain' | 'cert_cn' | 'http_host'
key_value      VARCHAR   the normalised domain
attribution    VARCHAR   'primary' | 'fallback'   (primary = from `domains`; fallback = from
                                                   cert or Host, even when re-keyed to kind 'domain')
file_id        VARCHAR
```

Rules that produce it (P2 spec; items 5 and 6 as built):

1. Normalise every candidate name: lowercase, strip trailing dot, strip
   leading `www.`, must contain at least 1 dot, must not be an IP literal.
2. Primary key: each element of `domains` whose IP coverage in this file
   is `<= ROLLUP_MAX_IPS` (default 50). IP coverage = count distinct
   `coalesce(ip_str, ipv6)` over all banners carrying that domain.
3. Fallback keys, used only for banners with 0 primary attributions:
   registered domain of `cert_subject_cn` (and each `cert_san`), then
   registered domain of `http_host` when it is not an IP. Registered
   domain = the public-suffix-aware base domain (use `tldextract`). The
   same `<= ROLLUP_MAX_IPS` rule applies, computed over the fallback
   name's coverage.
4. A name that appears in `config/operator_domains.txt` (seeded from the
   top operator zones in findings/06_relationships.md: incapdns.net,
   googleusercontent.com, amazonaws.com, cloudfront.net,
   akamaitechnologies.com, and every domain over the cutoff) never becomes
   an entity, regardless of coverage.
5. A cert or Host name above the cutoff in its own kind is still
   attributed when the same name already exists as a primary domain
   entity (otherwise 4,729 banners were unattributable for no good
   reason). Accepted as built.
6. `blocked_reason = 'operator_domain'` is never produced: operator names
   never become entities at all. The B01/B02 tag lists live in
   `config/blocked_tags.yaml`.

### 2.2 `entities` (per file, then merged to current)

Path: `$SIS_DATA/<file_id>/entities.parquet` and
`$SIS_DATA/current/entities.parquet`
Grain: 1 row per entity. Key: `entity_id`.

```
entity_id            VARCHAR
key_kind, key_value  VARCHAR
display_name         VARCHAR   key_value
n_banners            BIGINT
n_ips                BIGINT
n_ports              BIGINT
n_modules            BIGINT
country_code         VARCHAR   mode over banners, ties broken alphabetically
country_codes        VARCHAR[] distinct
org_mode             VARCHAR   mode of org (the hosting operator)
cloud_providers      VARCHAR[] distinct non-null
first_seen_file      VARCHAR   file_id
last_seen_file       VARCHAR   file_id
status               VARCHAR   'active' | 'blocked'
blocked_reason       VARCHAR   null | 'honeypot_or_scanner' | 'c2_or_malware'  (c2 wins when both match)
peer_group           VARCHAR   null after P2; P3 fills it: country_code || '|' || bucket, else
                               '*|' || bucket, else '*|*' when the group is under PEER_MIN_SIZE;
                               null for blocked
file_id              VARCHAR
```

`status = 'blocked'` when any banner of the entity matches mapping B01 or
B02 in findings/07_what_we_sell_map.csv (tags in config/blocked_tags.yaml).
Operator names never become entities (rule 6).
Blocked entities are kept (so the diff layer can see them) but never
scored or shown.

### 2.3 `unattributed_summary` (per file)

Path: `$SIS_DATA/<file_id>/unattributed_summary.parquet`
1 row per reason, for the write-up and the ingest report:

```
reason      VARCHAR   'no_name' | 'operator_only' | 'over_cutoff' | 'blocked'
n_banners   BIGINT
pct         DOUBLE
```

---

## 3. Layer 3: signals, evidence, scores (offline, P3)

### 3.1 `signals` (per file)

Path: `$SIS_DATA/<file_id>/signals.parquet`
Grain: 1 row per (entity, signal). Only present signals are stored, plus
the always-present breadth signals.

```
entity_id     VARCHAR
signal_id     VARCHAR   see catalogue below
fact          VARCHAR   'A' | 'B' | 'C' | 'D' | 'X'
value         DOUBLE    raw value (count, days, 0/1, cvss)
n_banners     BIGINT    banners of the entity that fire it
pct_in_peer   DOUBLE    percent_rank of value within peer_group, null for 0/1 signals
file_id       VARCHAR
```

Signal catalogue, 24 signals (P3.1 added C_any_service). `source` cites the
Stage 1 candidate. Every predicate is over the `banners` table restricted to
the entity's banners unless stated.

| signal_id | fact | value | predicate / computation | source |
|---|---|---|---|---|
| A_fingerprinted | A | 0/1 | any banner with len(cpe23) > 0 or version not null | C-01 |
| A_inferred_cves | A | max n_vulns over banners | n_vulns > 0 | C-02 |
| A_max_cvss | A | max max_cvss | n_vulns > 0 | C-02 |
| A_eol | A | 0/1 | list_contains(tags, 'eol-product') or 'eol-os' | C-03 |
| A_os_leak | A | 0/1 | os is not null | C-09 |
| A_cpe_per_header | A | max over banners of len(cpe23) / greatest(len(http_header_names), 1) | http banners with len(cpe23) > 0 | C-15 |
| B_self_signed | B | 0/1 | cert_self_signed or list_contains(tags, 'self-signed') | C-04 |
| B_expired | B | 0/1 | cert_expired = true | C-04 |
| B_legacy_tls | B | 0/1 | ssl_version in ('SSLv3', 'TLSv1.0') or ssl_versions contains 'SSLv3' or 'TLSv1' without a leading '-' | C-05 |
| B_cert_age_days | B | max over banners of date_diff('day', cert_issued, timestamp), clipped to [0, 7300] | cert_issued not null and > 1990-01-01 | C-16 |
| C_admin_services | C | count distinct module in (rdp, ssh, telnet, smb, ftp, vnc, x11, mysql, clickhouse-native, weblogic) with data_len > 0 and not tag cdn | mapping P02 | C-06 |
| C_windows_internals | C | 0/1 | list_contains(blocks, 'ntlm') or os like 'Windows%' | C-07 |
| C_asset_tags | C | count distinct of tags among (database, iot, ics, medical, devops, open-dir) | mapping P03 | C-08 |
| C_breadth_modules | C | count distinct module over non-edge banners (not `n_modules`, which counts every banner) | always present | C-13 |
| C_breadth_ports | C | count distinct port over non-edge banners (not `n_ports`) | always present | C-13 |
| C_components_vs_peers | C | max over http banners of len(http_components) | http banners with len(http_components) > 0 | C-14 |
| C_live_web | C | 0/1 | mapping P01 | prerequisite |
| C_any_service | C | 0/1 | any non-edge banner of the entity with data_len > 0, OR any non-edge banner with module not in ('auto') | DATA_MODEL 3.1 addition, P3.1 |
| D_waf | D | 0/1 | mapping W01 | C-10 |
| D_edge_substitute | D | 0/1 | mapping W02 | C-10 |
| D_security_appliance | D | 0/1 | mapping W03 or W04 | C-11 |
| D_vpn | D | 0/1 | mapping W05 or W06 | 07_negative |
| D_hardening_headers | D | 0/1 | mapping W07 | C-12 |
| X_small_cloud | X | 0/1 | cloud_provider in (DigitalOcean, Vultr, Linode) | C-17, informational only, weight 0 |

Held out, never a signal, used only by P4 evaluation: `vulns.kev`,
`vulns.verified`, `vulns.ransomware_campaign`, `opts_heartbleed`,
`opts_vulns`. `A_inferred_cves` and `A_max_cvss` must be computed from
vulns rows where `kev` is null or false AND `verified` is false, so the
held-out labels are not inputs. (`n_vulns` and `max_cvss` on the banner row
include them; P3 recomputes from the vulns table instead.)

### 3.2 `evidence` (per file)

Path: `$SIS_DATA/<file_id>/evidence.parquet`
Grain: 1 row per (entity, signal, banner), capped at 5 banners per signal
per entity (the 5 with the largest `data_len`, then lowest `port`).

```
entity_id, signal_id, banner_id  VARCHAR
ip          VARCHAR   coalesce(ip_str, ipv6)
port        BIGINT
module      VARCHAR
field       VARCHAR   the source column, e.g. 'http_waf', 'cpe23', 'cert_expires'
value       VARCHAR   the value that fired, as text, max 300 chars
snippet     VARCHAR   first 300 chars of `data` with CR/LF collapsed, or null
observed_at TIMESTAMP banners.timestamp
file_id     VARCHAR
```

### 3.3 `scores` (per file, then merged to current)

Path: `$SIS_DATA/<file_id>/scores.parquet` and
`$SIS_DATA/current/scores.parquet`
Grain: 1 row per active entity.

```
entity_id         VARCHAR
fact_a            DOUBLE   0..1
fact_b            DOUBLE   0..1
fact_c            DOUBLE   0..1
fact_d            DOUBLE   0..1   protection present
exposure          DOUBLE   0..100
segment           VARCHAR  'untouched' | 'partially_covered' | 'displace' | 'low_surface'
priority          DOUBLE   0..100
rank_overall      BIGINT   1 = highest priority among active entities
rank_in_segment   BIGINT
rank_in_country   BIGINT
top_signals       VARCHAR[] up to 5 signal_ids ordered by contribution
scoring_version   VARCHAR  from config/scoring.yaml
file_id           VARCHAR
```

Formulas are in DESIGN.md section 5 and fixed in `config/scoring.yaml`.

---

## 4. Layer 4: deltas and events (offline, P6)

### 4.1 `entity_history`

Path: `$SIS_DATA/history/entity_history.parquet`
Grain: 1 row per (entity, file). Append-only. Columns = `entities` columns
+ `scores` columns for that file.

### 4.2 `events`

Path: `$SIS_DATA/history/events.parquet`
Grain: 1 row per detected change between consecutive files for an entity.

```
event_id         VARCHAR   sha1(entity_id || event_type || from_file || to_file || subject)
entity_id        VARCHAR
event_type       VARCHAR   see list
subject          VARCHAR   what changed: a signal_id, 'ip:port', the entity key_value,
                           'exposure' or 'segment' (a new CVE is subject A_inferred_cves;
                           a WAF name goes in from_value / to_value)
from_file, to_file VARCHAR
from_value, to_value VARCHAR
detected_at      TIMESTAMP
severity         INTEGER   1..3
```

Event types: `entity_new`, `entity_gone`, `service_new`, `service_gone`,
`signal_appeared`, `signal_cleared`, `cert_expired_since`,
`protection_removed`, `protection_added`, `exposure_up`, `exposure_down`
(threshold: 10 points), `segment_changed`.

---

## 5. Layer 5: LLM enrichments (offline, on demand, P7 and P8) (not built)

Nothing writes these 3 tables yet: `sis classify` and `sis reportcard`
are stubs. Only the `llm_calls` path helper and `config/llm_tiers.yaml`
exist.

### 5.1 `entity_profile` (not built)

Path: `$SIS_DATA/current/entity_profile.parquet`
Grain: 1 row per classified entity.

```
entity_id         VARCHAR
is_business       BOOLEAN
industry          VARCHAR   1 of the fixed taxonomy in config/industry_taxonomy.yaml
description       VARCHAR   <= 160 chars
confidence        DOUBLE    0..1 as reported by the model
input_hash        VARCHAR   sha256 of the exact prompt input, for cache hits
model             VARCHAR
prompt_version    VARCHAR
input_tokens, output_tokens BIGINT
cost_usd          DOUBLE
classified_at     TIMESTAMP
```

### 5.2 `report_cards` (not built)

Path: `$SIS_DATA/current/report_cards/<entity_id>.json`, also served by
the API.

```
entity_id, generated_at, scoring_version, prompt_version, model
findings: [ { signal_id, fact, headline, what_it_means, what_to_do,
              evidence: [evidence rows] } ]
summary: { exposure, segment, n_findings, protection_present: [..] }
cost_usd, input_tokens, output_tokens
faithfulness_check: { passed: bool, violations: [..] }
```

### 5.3 `llm_calls` (append-only log) (not built)

Path: `$SIS_DATA/llm_calls.parquet`

```
call_id, task ('classify' | 'reportcard' | 'judge' | 'mcp_agent'), entity_id,
tier ('errand' | 'mid' | 'reasoning'), model_requested, model_used (from the response),
attempt INTEGER, escalated_from (tier or null), prompt_version, input_hash,
input_tokens, output_tokens, cost_usd, rate_limit_hits INTEGER, latency_ms,
status ('ok' | 'schema_fail' | 'refused' | 'error' | 'budget_exceeded'),
cache_hit BOOLEAN, called_at
```

---

## 6. Serving layer (live, P5)

The API never reads layers 1 to 4 directly. It reads 1 bundle:

Path: `$SIS_DATA/serve/<bundle_version>/`

```
accounts.parquet       1 row per active entity = entities (less status, blocked_reason, file_id)
                       + scores + entity_profile (left join: is_business, industry, description,
                       confidence as industry_confidence) + max_event_severity
evidence.parquet       as 3.2, active entities only
events.parquet         as 4.2, last 2 files only
signals.parquet        as 3.1, active entities only
bundle.json            { bundle_version, built_at, file_ids: [...], scoring_version,
                         n_accounts, n_evidence, pipeline_version }
```

Served by DuckDB in-process inside the FastAPI app, read-only, from the
bundle baked into the Docker image at `/app/bundle`. Expected size: on the order of 100s of
MB, dominated by evidence. The bundle is the only artefact deployed.

Computed offline: everything in layers 1 to 4 (layer 5 is not built).
Queried live: filtering, sorting, paging, and lookup over the bundle only.
Generated on demand but persisted: report cards (P8), triggered from the UI,
written back to the bundle directory and to layer 5.3 (not built). Today
the UI writes back only `feedback.jsonl` in the bundle directory.

---

## 7. Evaluation artefacts (offline, P4)

Path: `$SIS_DATA/<file_id>/eval/`

```
labels.parquet       entity_id, label_kev, label_verified, label_heartbleed, label_opts_vulns,
                     label_any_tested, label_has_vendor
metrics.json         see P4 for the exact keys
ablations.json       metric per fact removed
baselines.json       random, breadth-only, cve-count-only
```

`pytest -m eval` in CI recomputes only precision@1000 for label_any_tested
and label_kev, from the priorities stored in a fixed sample under
`tests/fixtures/`, and fails the build when either drops below the
committed threshold. The fixture holds scores, not scoring inputs.
