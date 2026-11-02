-- Step 3: operator list = seed file + data-derived. Derived: every domain-kind name above the
-- cutoff, plus every cert or http_host name above the cutoff that is not also a customer-sized
-- domain-kind name (so a wildcard certificate on 300 hosts never demotes a real domain).
-- After this, no name can be "over the cutoff and not an operator".
-- Rules 1 and 2 (config/resolve.yaml) add hosting zones that stay under the cutoff.
-- Rule 1, template zone: the domain-kind name itself encodes an IP fragment.
CREATE OR REPLACE TEMP TABLE op_rule1 AS
SELECT DISTINCT name FROM coverage
WHERE kind = 'domain' AND regexp_matches(name, $zone_re, 'i');
-- Rule 2, templated hostnames: share of the name's distinct hostnames whose first label has 2
-- or more digit groups. Names above the cutoff are operators already and are skipped.
CREATE OR REPLACE TEMP TABLE host_template AS
WITH cand AS (
    SELECT name FROM coverage
    WHERE kind = 'domain' AND n_ips >= $tpl_min_ips AND n_ips <= $cutoff
), hn AS (
    SELECT DISTINCT n.name, rtrim(lower(h.hostname), '.') AS hostname
    FROM names n
    JOIN cand USING (name)
    JOIN (SELECT id, unnest(hostnames) AS hostname FROM b) h ON h.id = n.banner_id
    WHERE n.kind = 'domain'
)
SELECT name, count(*) AS n_hostnames,
       count(*) FILTER (WHERE regexp_matches(split_part(hostname, '.', 1), $tpl_label_re))
           AS n_templated
FROM hn
WHERE hostname = name OR ends_with(hostname, '.' || name)
GROUP BY name;
CREATE OR REPLACE TEMP TABLE op_rule2 AS
SELECT name FROM host_template WHERE n_templated >= $tpl_share * n_hostnames;
CREATE OR REPLACE TEMP TABLE op_derived AS
SELECT DISTINCT name FROM (
    SELECT name FROM coverage WHERE kind = 'domain' AND n_ips > $cutoff
    UNION ALL
    SELECT c.name FROM coverage c
    WHERE c.kind <> 'domain' AND c.n_ips > $cutoff
      AND NOT EXISTS (SELECT 1 FROM coverage d
                      WHERE d.kind = 'domain' AND d.name = c.name AND d.n_ips <= $cutoff)
    UNION ALL
    SELECT name FROM op_rule1
    UNION ALL
    SELECT name FROM op_rule2
)
WHERE name NOT IN (SELECT name FROM op_seed);
CREATE OR REPLACE TEMP TABLE operators AS
SELECT name FROM op_seed UNION SELECT name FROM op_derived
