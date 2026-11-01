-- Step 3: operator list = seed file + data-derived. Derived: every domain-kind name above the
-- cutoff, plus every cert or http_host name above the cutoff that is not also a customer-sized
-- domain-kind name (so a wildcard certificate on 300 hosts never demotes a real domain).
-- After this, no name can be "over the cutoff and not an operator".
CREATE OR REPLACE TEMP TABLE op_derived AS
SELECT DISTINCT name FROM (
    SELECT name FROM coverage WHERE kind = 'domain' AND n_ips > $cutoff
    UNION ALL
    SELECT c.name FROM coverage c
    WHERE c.kind <> 'domain' AND c.n_ips > $cutoff
      AND NOT EXISTS (SELECT 1 FROM coverage d
                      WHERE d.kind = 'domain' AND d.name = c.name AND d.n_ips <= $cutoff)
)
WHERE name NOT IN (SELECT name FROM op_seed);
CREATE OR REPLACE TEMP TABLE operators AS
SELECT name FROM op_seed UNION SELECT name FROM op_derived
