-- Step 4: peer groups (DESIGN.md 5.1). bucket = the breadth bucket of n_modules (`buckets` is
-- registered from config/scoring.yaml). country|bucket when that group has $min_size active
-- entities, else *|bucket, else *|*. A null country always falls back.
CREATE OR REPLACE TEMP TABLE peer AS
WITH a AS (
    SELECT e.entity_id, e.country_code, k.label AS bucket
    FROM ent e JOIN buckets k ON e.n_modules >= k.lo AND (k.hi IS NULL OR e.n_modules <= k.hi)
    WHERE e.status = 'active'
), c AS (
    SELECT *, count(*) OVER (PARTITION BY country_code, bucket) AS n_cb,
           count(*) OVER (PARTITION BY bucket) AS n_b
    FROM a
)
SELECT entity_id, country_code, bucket,
       CASE WHEN country_code IS NOT NULL AND n_cb >= $min_size THEN country_code || '|' || bucket
            WHEN n_b >= $min_size THEN '*|' || bucket
            ELSE '*|*' END AS peer_group
FROM c
