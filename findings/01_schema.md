# 01_schema.md

The JSON was not loaded with schema inference. queries/01_flatten.py extracts
a fixed set of 93 columns (EXPLORATION.md 1b) and a child table (1c). Full
per-column profile: 02_columns.csv. type_decided = type_in_file for every
column: the flattener already typed them; nothing else was cast.

## Conversion record (1b)

| item | value |
|---|---|
| compressed input | 17,619,943,483 bytes |
| decompressed JSONL | 122,782,583,953 bytes (ratio 6.97) |
| lines (queries/01_linecount.py, in-process zstd, whole input consumed) | 14,608,407 |
| rows written (banners) | 14,608,406 |
| lines that failed to parse | 1 (orjson: lone UTF-16 surrogate in `data`; dropped, logged in stats.json) |
| wall time, zstd -dc piped into flattener, 11 workers | 1,473 s |
| Parquet size, banners | 2,176,821,150 bytes, 1,220 files |
| Parquet size, vulns | 324,331,486 bytes, 20,988,468 rows |
| parquet (banners + vulns) / compressed input | 0.142 (banners alone 0.124) |
| top-level JSON keys seen | 205 |
| distinct `_shodan.module` | 246 |

A 2nd line count with `zstd -dc | wc -l` stopped at 1,221,316 lines with
"zstd: error 70: Write error: Invalid argument": a Windows pipe failure
in that shell, not a data property. The in-process count above is the
authoritative one.

## Columns and types

| group | columns | type |
|---|---|---|
| scan | id (_shodan.id), module, shodan_region, crawler, ptr, timestamp | VARCHAR, BOOLEAN, TIMESTAMP |
| network | port, transport, ip_str, ipv6, org, isp, asn, hash, link | BIGINT / VARCHAR |
| location | country_code, country_name, city, region_code, latitude, longitude | VARCHAR / DOUBLE |
| fingerprint | os, product, version, info, uptime, devicetype, device, vendor, cpe23[] | VARCHAR, BIGINT, LIST |
| names | hostnames[], domains[], tags[] | LIST<VARCHAR> |
| vulns summary | vuln_ids[], n_vulns, max_cvss, max_epss, opts_heartbleed, opts_vulns[] | LIST, BIGINT, DOUBLE |
| http | http_status, title, server, waf, host, location, 6 hashes, securitytxt/robots/sitemap present, redirects count, html_len, components[], component_cats[], header_names[], headers (JSON text), identifiers (JSON text) | mixed |
| tls | ssl_version, ssl_cipher, ssl_cipher_bits, cert_issued, cert_expires, cert_expired, cert_subject_cn, cert_subject_o, cert_issuer_cn, cert_issuer_o, cert_self_signed (subject == issuer), cert_pubkey_type, cert_pubkey_bits, cert_sig_alg, cert_sha256, cert_san[] (regex over the raw extension), jarm, ja3s, trust_revoked, trust_browser, ssl_chain_len, ssl_versions[], ssl_alpn[] | mixed |
| cloud | cloud_provider, cloud_region, cloud_service | VARCHAR |
| payload | data (first 2,000 chars), data_len, html_len (top-level html), record_bytes | VARCHAR, BIGINT |
| catch-all | blocks[] (names of protocol blocks present), extra_json (every top-level key not above, minus `html` and `screenshot`) | LIST, VARCHAR |

Dropped on purpose, lengths kept: http.html body, top-level html body,
screenshot data, favicon data, ssl.chain PEMs, ssl.ciphers list, tlsext,
handshake_states. `hash` and the http_*_hash columns are identifiers, not
quantities.

Child table `vulns` (1 row per banner x CVE): id, module, cve, cvss,
cvss_version, cvss_v2, epss, ranking_epss, verified, kev, n_references,
summary (first 500 chars), other_keys (JSON; only `ransomware_campaign`
occurs). Keys inventoried over every record, not the first 10,000 (counts
in 06_relationships.md).

## Type observations

- `cert_issued` / `cert_expires` contain sentinels 0001-01-01 and
  9999-12-31 (04_distributions.md).
- `version` contains escaped control characters (`7.4\r\n`): raw banner
  fragments, not clean versions.
- `ptr` is never false: approx_unique 1, 93.4 % true, rest NULL.
- `trust_revoked` likewise has 1 value.
- approx_unique of `id` (21,529,044) exceeds the row count: HyperLogLog
  error. Exact distinct is 14,608,406 (06_rollup.json).
