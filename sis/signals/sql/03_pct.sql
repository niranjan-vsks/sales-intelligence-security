-- Step 5: percent rank of each count / max / ratio signal among the entities that have it,
-- inside the entity's peer set: its country|bucket group, the whole bucket for '*|bucket', the
-- whole population for '*|*' (DESIGN.md 5.1). 0/1 flags get null.
CREATE OR REPLACE TEMP TABLE sig AS
SELECT s.entity_id, s.signal_id, s.fact, s.kind, s.value, s.n_banners,
       CASE WHEN s.kind = 'flag' THEN NULL
            WHEN p.peer_group = '*|*'
                THEN percent_rank() OVER (PARTITION BY s.signal_id ORDER BY s.value)
            WHEN p.peer_group LIKE '*|%'
                THEN percent_rank() OVER (PARTITION BY s.signal_id, p.bucket ORDER BY s.value)
            ELSE percent_rank() OVER (PARTITION BY s.signal_id, p.peer_group ORDER BY s.value)
       END AS pct_in_peer
FROM sig_raw s JOIN peer p USING (entity_id)
