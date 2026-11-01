-- Step 4: primary attribution = domain-kind names within the cutoff that are not operators.
CREATE OR REPLACE TEMP TABLE primary_pairs AS
SELECT DISTINCT n.banner_id, n.name
FROM names n JOIN coverage c ON c.kind = n.kind AND c.name = n.name
WHERE n.kind = 'domain' AND c.n_ips <= $cutoff AND n.name NOT IN (SELECT name FROM operators)
