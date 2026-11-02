-- Step 1 (cont.): `eb`, 1 row per (active entity, banner) with only the columns signals and
-- evidence read, the clean vuln columns, and the edge flag (DESIGN.md 5.5): {edge} is the
-- predicate built from mapping W01 and the cdn tag. org, asn, isp, city and lat/long are not
-- carried, so no signal can read them.
CREATE OR REPLACE TEMP TABLE eb0 AS
SELECT a.entity_id, b.id AS banner_id, coalesce(b.ip_str, b.ipv6) AS ip, b.port, b.module,
       b.timestamp, b.tags, b.cpe23, b.product, b.version, b.os, b.http_status,
       b.http_header_names, b.http_components, b.http_waf, b.cert_self_signed, b.cert_expired,
       b.cert_expires, b.cert_issued, b.cert_issuer_o, b.ssl_version, b.ssl_versions, b.blocks,
       b.data_len, b.cloud_provider,
       left(regexp_replace(b.data, '[\r\n]+', ' | ', 'g'), 300) AS snippet,
       coalesce(vc.n_clean, 0) AS n_clean, vc.max_clean_cvss,
       coalesce(vc.clean_cves, []::VARCHAR[]) AS clean_cves
FROM be_active a
JOIN b ON b.id = a.banner_id
LEFT JOIN vulns_clean vc ON vc.banner_id = a.banner_id;
CREATE OR REPLACE TEMP TABLE eb AS
SELECT *, ({edge}) AS is_edge FROM eb0
