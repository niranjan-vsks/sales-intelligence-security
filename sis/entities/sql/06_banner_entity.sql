-- Step 6: entity ids. A fallback name that also exists as a primary domain entity is re-keyed
-- to kind 'domain' BEFORE hashing, so one company never gets two entity ids.
CREATE OR REPLACE TEMP TABLE banner_entity AS
WITH keyed AS (
    SELECT banner_id, 'domain' AS key_kind, name AS key_value, 'primary' AS attribution
    FROM primary_pairs
    UNION ALL
    SELECT f.banner_id,
           CASE WHEN f.name IN (SELECT DISTINCT name FROM primary_pairs) THEN 'domain'
                ELSE f.kind END,
           f.name, 'fallback'
    FROM fallback_pairs f
)
SELECT DISTINCT banner_id, sha1(key_kind || ':' || key_value) AS entity_id,
       key_kind, key_value, attribution
FROM keyed
