-- Step 6: entity ids. A fallback name that also exists as a primary domain entity is re-keyed
-- to kind 'domain' BEFORE hashing, so one company never gets two entity ids. Otherwise a name
-- reached as cert_cn on some banners and as http_host on others takes cert_cn everywhere.
CREATE OR REPLACE TEMP TABLE banner_entity AS
WITH fb_kind AS (
    SELECT name,
           CASE min(CASE kind WHEN 'cert_cn' THEN 1 ELSE 2 END) WHEN 1 THEN 'cert_cn'
                ELSE 'http_host' END AS kind
    FROM fallback_pairs GROUP BY name
), keyed AS (
    SELECT banner_id, 'domain' AS key_kind, name AS key_value, 'primary' AS attribution
    FROM primary_pairs
    UNION ALL
    SELECT f.banner_id,
           CASE WHEN f.name IN (SELECT DISTINCT name FROM primary_pairs) THEN 'domain'
                ELSE k.kind END,
           f.name, 'fallback'
    FROM fallback_pairs f JOIN fb_kind k USING (name)
)
SELECT DISTINCT banner_id, sha1(key_kind || ':' || key_value) AS entity_id,
       key_kind, key_value, attribution
FROM keyed
