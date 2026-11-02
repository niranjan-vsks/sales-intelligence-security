-- Step 8: ranks over `scored` (1 row per active entity, with country_code), ties broken by
-- exposure then entity_id so the order is total and deterministic. Used per file and by merge.
CREATE OR REPLACE TEMP TABLE scores AS
SELECT entity_id, fact_a, fact_b, fact_c, fact_d, exposure, segment, priority,
       row_number() OVER (ORDER BY priority DESC, exposure DESC, entity_id) AS rank_overall,
       row_number() OVER (PARTITION BY segment ORDER BY priority DESC, exposure DESC, entity_id)
           AS rank_in_segment,
       row_number() OVER (PARTITION BY country_code
                          ORDER BY priority DESC, exposure DESC, entity_id) AS rank_in_country,
       top_signals, scoring_version, file_id
FROM scored
