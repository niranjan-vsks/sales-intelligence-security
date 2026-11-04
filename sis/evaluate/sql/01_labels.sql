-- phase P4 step 1: held-out labels at entity grain, from the full `v` and `b` (not
-- vulns_clean), over every banner attributed to an active entity (primary or fallback).
-- Needs views b, v, be, sig and table act (entity_id of every active entity).
-- Edge banners (DESIGN.md 5.5) carry the CDN or WAF vendor's findings, not the tenant's, so the
-- vulnerability labels skip them, as facts A to C do (phase P3.1 defect 3). {edge} is the
-- same predicate the signals use (sis.signals.catalogue.edge_predicate).
CREATE OR REPLACE TEMP TABLE pos_vulns AS
SELECT id,
       bool_or(coalesce(kev, false)) AS kev,
       bool_or(coalesce(verified, false)) AS verified,
       bool_or(coalesce(json_extract_string(other_keys, '$.ransomware_campaign') = 'Known', false))
           AS ransomware
FROM v
WHERE kev OR verified OR json_extract_string(other_keys, '$.ransomware_campaign') IS NOT NULL
GROUP BY id;
CREATE OR REPLACE TEMP TABLE labels AS
WITH bl AS (
    SELECT be.entity_id,
           coalesce(pv.kev, false) AS kev,
           coalesce(pv.verified, false) AS verified,
           coalesce(pv.ransomware, false) AS ransomware,
           coalesce(b.opts_heartbleed LIKE '%VULNERABLE%', false) AS heartbleed,
           coalesce(len(b.opts_vulns) > 0, false) AS opts_vulns
    FROM be
    JOIN act USING (entity_id)
    JOIN b ON b.id = be.banner_id
    LEFT JOIN pos_vulns pv ON pv.id = be.banner_id
    WHERE NOT ({edge})
), agg AS (
    SELECT entity_id, bool_or(kev) AS kev, bool_or(verified) AS verified,
           bool_or(ransomware) AS ransomware, bool_or(heartbleed) AS heartbleed,
           bool_or(opts_vulns) AS opts_vulns
    FROM bl GROUP BY entity_id
), vendor AS (
    SELECT DISTINCT entity_id FROM sig WHERE signal_id IN ('D_waf', 'D_security_appliance')
)
SELECT act.entity_id,
       coalesce(agg.kev, false) AS label_kev,
       coalesce(agg.verified, false) AS label_verified,
       coalesce(agg.heartbleed, false) AS label_heartbleed,
       coalesce(agg.opts_vulns, false) AS label_opts_vulns,
       coalesce(agg.verified OR agg.heartbleed OR agg.opts_vulns, false) AS label_any_tested,
       vendor.entity_id IS NOT NULL AS label_has_vendor,
       coalesce(agg.ransomware, false) AS label_ransomware
FROM act
LEFT JOIN agg USING (entity_id)
LEFT JOIN vendor USING (entity_id)
