-- Step 1: candidate names per banner. Raw strings are mapped to normalised names in Python
-- (map_domain, map_cert, map_host: raw, name), so the rules live in one place.
CREATE OR REPLACE TEMP TABLE names AS
SELECT DISTINCT banner_id, ip, name, kind FROM (
    SELECT x.id AS banner_id, x.ip, m.name, 'domain' AS kind
    FROM (SELECT id, coalesce(ip_str, ipv6) AS ip, unnest(domains) AS raw FROM b) x
    JOIN map_domain m ON m.raw = x.raw
    UNION ALL
    SELECT x.id, x.ip, m.name, 'cert_cn'
    FROM (
        SELECT id, coalesce(ip_str, ipv6) AS ip, cert_subject_cn AS raw
        FROM b WHERE cert_subject_cn IS NOT NULL
        UNION ALL
        SELECT id, coalesce(ip_str, ipv6), unnest(cert_san) FROM b WHERE cert_san IS NOT NULL
    ) x
    JOIN map_cert m ON m.raw = x.raw
    UNION ALL
    SELECT x.id, x.ip, m.name, 'http_host'
    FROM (SELECT id, coalesce(ip_str, ipv6) AS ip, http_host AS raw
          FROM b WHERE http_host IS NOT NULL) x
    JOIN map_host m ON m.raw = x.raw
)
