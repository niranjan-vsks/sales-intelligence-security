# 05_semistructured.md

FULL unless marked. Source: queries/05_semistructured.py -> 05_semistructured.json,
values/blocks_fill.csv, values/extra_json_keys.csv, values/*_tokens.csv,
values/*_bigrams.csv, values/*_random50.txt. Element value tables for every
list column: values/<col>_elements.csv (queries/03_04_values_dist.py).

## Classification of high-cardinality text

| column | avg len | p95 len | class |
|---|---|---|---|
| data | 143.8 | 653 | prose-like raw protocol text (HTTP response heads, SSH/FTP/SMTP greetings, binary escapes); truncated at 2,000 by the flattener |
| http_title | 20.2 | 49 | short label, heavily templated |
| http_server | 11.4 | 22 | identifier-like product string |
| org, isp, city, product, version, info | short | | names |
| http_host, cert_subject_cn, hostnames | | | DNS names (identifiers) |
| http_headers, http_identifiers, extra_json | | | JSON |

## List columns

| list | rows with list | rows non-empty | length p50, p90, p99 | max |
|---|---|---|---|---|
| hostnames | 14,608,406 | 10,824,898 | 1, 1, 3 | 824 |
| domains | 14,608,406 | 10,824,898 | 1, 1, 2 | 342 |
| tags | 10,370,035 | 10,370,035 | 1, 1, 3 | 5 |
| cpe23 | 3,054,716 | 3,054,577 | 1, 3, 4 | 27 |
| vuln_ids | 467,424 | 467,424 | 11, 128, 417 | 1,000 |
| http_components | 4,311,673 | 2,724,802 | 1, 2, 5 | 35 |
| http_header_names | 4,143,249 | 4,143,249 | 6, 11, 22 | 52 |
| ssl_versions | 990,592 | 632,073 | 6, 6, 6 | 6 |
| ssl_alpn | 989,678 | 50,111 | 0, 0, 2 | 6 |

Element vocabularies are in values/; the useful ones are small and
controlled (tags 29, http_component_cats 94, ssl_versions 12) or medium
(http_components 1,299, http_header_names 9,857, cpe23 8,160).

## JSON: protocol blocks (values/blocks_fill.csv)

Fill over all rows, and fill inside the module that produces most of the block:

| block | rows | pct all | top module | fill inside top module |
|---|---|---|---|---|
| http | 4,311,673 | 29.5 | http | 94.6 % |
| cloud | 4,169,850 | 28.5 | auto | 30.1 % |
| ssl | 990,592 | 6.8 | https | 80.1 % |
| vulns | 467,424 | 3.2 | http | 13.8 % |
| snmp | 174,307 | 1.19 | snmp_v3 | 99.97 % |
| isakmp | 110,252 | 0.75 | ike | 45.9 % |
| ssh | 96,279 | 0.66 | ssh | 100 % |
| ntlm | 29,748 | 0.20 | rdp | 47.6 % |
| rdp_encryption | 25,051 | 0.17 | rdp | 48.6 % |
| ftp, ntp, l2tp | 20,536 / 19,242 / 19,057 | 0.14 / 0.13 / 0.13 | own module | ~100 % |

173 distinct block names in all.

## JSON: key tree of extra_json (values/extra_json_keys.csv, 1,558 (block, key) pairs)

671,356 rows carry extra_json. Level-2 keys of the largest blocks:

- snmp (174,307): versions, engineid_data, engine_time, enterprise,
  engine_boots, engineid_format, enterprise_name (48,644), objectid.
- isakmp (110,252): initiator_spi, version, responder_spi, flags, length,
  exchange_type, next_payload, vendor_ids.
- ssh (96,279): mac, hassh, cipher, kex, type, fingerprint, key.
- ntlm (29,738): target_realm, netbios_computer_name, netbios_domain_name,
  os_build, fqdn, dns_domain_name, timestamp, os. These name the internal
  Windows domain of the host: a 2nd company identifier, rare.
- rdp_encryption (25,051): protocols, methods, levels, rdp_version.

No extra_json key reaches 1 % of all rows, so none was promoted to a
virtual column. Within their module they are dense.

## JSON: http_identifiers

10,020 rows. Keys: google_analytics 5,818, google_tag_manager 4,470,
meta_pixel 558, google_ads 136, tiktok_pixel 25, x_pixel 10. Tracking ids
link sites owned by the same company across IPs.

## JSON: http_headers

Key inventory = values/http_header_names_elements.csv (9,857 names). Header
names in the file include content-security-policy,
strict-transport-security, x-frame-options, x-content-type-options,
x-xss-protection, referrer-policy, permissions-policy (counts in the file).

## Prose: data

- 56.4 % empty (data_len 0). Length of non-empty: p50 0 over all rows, p90
  351, p99 2,000 (truncation).
- duplicate rate count(distinct)/count = 0.288: strongly templated.
- top tokens (200k-row reservoir sample, seed 7): x00, content, x80, x01,
  type, gmt, text, 2026, length, oct, server, connection, cache, date,
  request, keep, alive, close, bad, 400, cloudfront, openssh.
- top bigrams: "x00 x00", "content type", "type text", "2026 gmt",
  "content length", "keep alive", "connection close", "bad request".
- what it is: raw protocol responses (HTTP status line + headers, binary
  handshakes). Templated; parse with regex, no LLM case here.
- 5 verbatim examples (values/data_random50.txt):
  1. `SSL Error: TLSV1_UNRECOGNIZED_NAME`
  2. `HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n... Server: Microsoft-IIS/10.0\r\nX-Powered-By: ASP.NET ...`
  3. `HTTP/1.1 302 Moved Temporarily\r\nConnection: close\r\nCache-Control: no-cache,no-store ...`
  4. `` (empty)
  5. `HTTP/1.1 200 OK\r\nServer: Angie\r\n... Content-Security-Policy: script-src 'nonce-...'`

## Prose: http_title

- 17.0 % of rows. Length p10 8, p50 16, p90 41, p99 63, max 139,765.
- duplicate rate 0.075: very templated.
- top tokens: request, moved, 301, permanently, found, 400, error, url, 404,
  web, invalid, bad, 403, forbidden, page, welcome, default, nginx, login.
- top bigrams: "301 moved", "moved permanently", "404 found", "invalid url",
  "403 forbidden", "bad request", "welcome nginx", "default page",
  "one moment" (Cloudflare challenge).
- what it is: page titles; most are server defaults and error pages, a
  minority are real site names. 5 examples: `IIS Windows Server`,
  `302 Found`, `FMS17 Website`, `Private Site`, `GamerHub Brasil - O Hub dos
  Melhores Servidores e empresas para jogos`.
- non-templated part (real titles) is the only prose that could describe
  the company; whether that is worth an LLM is Stage 2's decision.
