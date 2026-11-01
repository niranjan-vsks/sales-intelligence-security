-- Step 7: one row per entity (DATA_MODEL 2.2). Blocked when any attributed banner matches
-- B01 (honeypot or scanner tags) or B02 (c2 or malware tags); B02 wins when both match.
-- Tags come from config/blocked_tags.yaml. peer_group is left null for P3.
CREATE OR REPLACE TEMP TABLE be_attr AS
SELECT e.entity_id, e.key_kind, e.key_value, b.id AS banner_id,
       coalesce(b.ip_str, b.ipv6) AS ip, b.port, b.module, b.country_code, b.org,
       b.cloud_provider,
       coalesce(list_has_any(b.tags, $b01), false) AS is_b01,
       coalesce(list_has_any(b.tags, $b02), false) AS is_b02
FROM banner_entity e JOIN b ON b.id = e.banner_id;
CREATE OR REPLACE TEMP TABLE entities AS
WITH base AS (
    SELECT entity_id, any_value(key_kind) AS key_kind, any_value(key_value) AS key_value,
           count(*) AS n_banners, count(DISTINCT ip) AS n_ips, count(DISTINCT port) AS n_ports,
           count(DISTINCT module) AS n_modules,
           list_sort(list_distinct(list(country_code))) AS country_codes,
           list_sort(list_distinct(list(cloud_provider))) AS cloud_providers,
           bool_or(is_b01) AS b01, bool_or(is_b02) AS b02
    FROM be_attr GROUP BY entity_id
), cc AS (
    SELECT entity_id, first(country_code ORDER BY n DESC, country_code) AS country_code
    FROM (SELECT entity_id, country_code, count(*) AS n FROM be_attr
          WHERE country_code IS NOT NULL GROUP BY entity_id, country_code)
    GROUP BY entity_id
), oo AS (
    SELECT entity_id, first(org ORDER BY n DESC, org) AS org_mode
    FROM (SELECT entity_id, org, count(*) AS n FROM be_attr
          WHERE org IS NOT NULL GROUP BY entity_id, org)
    GROUP BY entity_id
)
SELECT base.entity_id, base.key_kind, base.key_value, base.key_value AS display_name,
       base.n_banners, base.n_ips, base.n_ports, base.n_modules,
       cc.country_code, coalesce(base.country_codes, []::VARCHAR[]) AS country_codes,
       oo.org_mode, coalesce(base.cloud_providers, []::VARCHAR[]) AS cloud_providers,
       $file_id::VARCHAR AS first_seen_file, $file_id::VARCHAR AS last_seen_file,
       CASE WHEN base.b02 OR base.b01 THEN 'blocked' ELSE 'active' END AS status,
       CASE WHEN base.b02 THEN 'c2_or_malware' WHEN base.b01 THEN 'honeypot_or_scanner' END
           AS blocked_reason,
       NULL::VARCHAR AS peer_group, $file_id::VARCHAR AS file_id
FROM base LEFT JOIN cc USING (entity_id) LEFT JOIN oo USING (entity_id)
