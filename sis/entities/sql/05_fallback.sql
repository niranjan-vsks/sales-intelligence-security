-- Step 5: fallback only for banners with no primary row, cert names first then http_host.
-- a banner takes rows from the first kind that yields any.
CREATE OR REPLACE TEMP TABLE fb_eligible AS
SELECT n.banner_id, n.kind, n.name, CASE n.kind WHEN 'cert_cn' THEN 1 ELSE 2 END AS kind_rank
FROM names n JOIN coverage c ON c.kind = n.kind AND c.name = n.name
WHERE n.kind IN ('cert_cn', 'http_host') AND c.n_ips <= $cutoff
  AND n.name NOT IN (SELECT name FROM operators)
  AND n.banner_id NOT IN (SELECT banner_id FROM primary_pairs);
CREATE OR REPLACE TEMP TABLE fallback_pairs AS
SELECT DISTINCT banner_id, kind, name FROM (
    SELECT *, min(kind_rank) OVER (PARTITION BY banner_id) AS best FROM fb_eligible
) WHERE kind_rank = best
