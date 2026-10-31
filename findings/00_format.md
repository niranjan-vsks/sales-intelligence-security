# 00_format.md (step 0, done by the architect on 2026-11-01)

Path on disk: C:\Users\NIRANJAN VSKS\Downloads\b2_download_file_by_id (no extension)
Size: 17,619,943,483 bytes (16.4 GB). The assignment said 9 to 12 GB.
Container: zstd (magic 28 b5 2f fd). `zstd` binary available via miniconda.
Inner format: JSON, 1 record per line (JSONL). No header record.
Line count: 14,608,407 (queries/01_linecount.py, FULL). Decompressed size
122,782,583,953 bytes. Time window 2026-10-25 18:13 to 2026-10-26 13:06
(06_relationships.md temporal). 1 entity type: the banner.

Record shape (from the first 50,000 records, so SAMPLE):
- 1 record = 1 service banner observed by an internet scanner on 1 IP and
  1 port at 1 timestamp. The `_shodan` block (module, crawler, id, region)
  identifies the scanner. This is a Shodan banner export.
- avg record 7,409 bytes, max 2,747,801 bytes in the sample. Set any JSON
  reader's maximum object size well above that.
- Every record has: data, opts, port, hostnames, domains, timestamp,
  location{}, org, isp, os, _shodan{}, hash, transport, asn.
- Present in most: tcp, ip, ip_str, tags, link.
- Present in a minority, keyed by protocol: http{}, ssl{}, cloud{}, cpe,
  cpe23, product, version, vulns, uptime, ipv6, and about 90 other
  protocol-specific blocks (ssh, snmp, isakmp, ftp, mysql, rdp_encryption,
  smb, telnet, kubernetes, ...), each present in under 1 percent of the
  sample.
- `_shodan.module` has 201 distinct values in the sample; `auto` is about
  half. 3,914 distinct ports in the sample.
- `data` is the raw banner text (HTTP response, SSH banner, etc). `http.html`
  holds full page HTML. Both are large free text.
- `timestamp` is the scan time. First records are 2026-10-26, matching the
  URL's embedded date d20261026.

Consequences for the plan:
1. The grain is service banner, not company. Companies do not exist as rows.
   Section 6.1 must establish how banners roll up to an organisation.
   Candidate roll-up keys visible in the sample: domains, hostnames, org,
   asn, ssl.cert.subject.CN, ip. Which of these is the right company key is
   a Stage 1 question, not a given.
2. The schema is ragged. Sections 2 to 4 run over JSON paths, not columns,
   and most paths are sparse by construction (present only for 1 module).
   Fill rate must be computed both over all records and over the records
   of the module that can produce the path.
3. The CSV branches in EXPLORATION.md section 1 do not apply. Section 0a
   of EXPLORATION.md replaces section 1.
