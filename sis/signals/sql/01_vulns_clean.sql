-- Step 1: banners of active entities (be_active), and the held-out exclusion (step 2).
-- kev and verified are P4's evaluation labels, so a CVE row carrying either is never an input
-- (DESIGN.md 5.5, DATA_MODEL 3.1). The banner row's own n_vulns and max_cvss include those rows
-- and are never read for scoring.
CREATE OR REPLACE TEMP TABLE be_active AS
SELECT DISTINCT x.banner_id, x.entity_id
FROM be x JOIN ent e USING (entity_id)
WHERE e.status = 'active';
CREATE OR REPLACE TEMP TABLE vulns_clean AS
SELECT v.id AS banner_id, count(*) AS n_clean, max(v.cvss) AS max_clean_cvss,
       list(v.cve ORDER BY v.cvss DESC NULLS LAST, v.cve)[1:10] AS clean_cves
FROM v
WHERE coalesce(v.kev, false) = false AND coalesce(v.verified, false) = false
  AND v.id IN (SELECT banner_id FROM be_active)
GROUP BY v.id
