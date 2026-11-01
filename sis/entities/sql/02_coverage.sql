-- Step 2: IP coverage per (kind, name).
CREATE OR REPLACE TEMP TABLE coverage AS
SELECT kind, name, count(DISTINCT ip) AS n_ips FROM names GROUP BY kind, name
