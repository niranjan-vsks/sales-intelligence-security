-- Events between 2 files (DATA_MODEL.md 4.2, cards/P6.md step 3). Reads the temp tables diff.py
-- builds for each side s in (a, b):
--   act_s  active entities with their score: entity_id, key_kind, key_value, exposure, segment
--   sig_s  present signals (value > 0): entity_id, signal_id, fact, value
--   svc_s  services: entity_id, skey ('ip:port'), module
--   evd_s  evidence text per (entity_id, signal_id): v
-- Events other than entity_new / entity_gone are only for entities active in both files, so a
-- vanished entity is 1 event, not 1 per service. {severity} is a CASE built from config/delta.yaml.
-- A signal with its own event type (D_*: protection, B_expired: cert_expired_since) is not also
-- reported as signal_appeared.
CREATE OR REPLACE TEMP TABLE ev AS
SELECT entity_id, 'entity_new' AS event_type, key_value AS subject,
       NULL::VARCHAR AS from_value, segment AS to_value
FROM act_b WHERE entity_id NOT IN (SELECT entity_id FROM act_a)
UNION ALL
SELECT entity_id, 'entity_gone', key_value, segment, NULL
FROM act_a WHERE entity_id NOT IN (SELECT entity_id FROM act_b)
UNION ALL
SELECT s.entity_id, 'service_new', s.skey, NULL, s.module
FROM svc_b s SEMI JOIN act_a USING (entity_id)
ANTI JOIN svc_a USING (entity_id, skey)
UNION ALL
SELECT s.entity_id, 'service_gone', s.skey, s.module, NULL
FROM svc_a s SEMI JOIN act_b USING (entity_id)
ANTI JOIN svc_b USING (entity_id, skey)
UNION ALL
SELECT s.entity_id, 'signal_appeared', s.signal_id, NULL, printf('%g', s.value)
FROM sig_b s SEMI JOIN act_a USING (entity_id)
ANTI JOIN sig_a USING (entity_id, signal_id)
WHERE s.fact <> 'D' AND s.signal_id <> 'B_expired'
UNION ALL
SELECT s.entity_id, 'signal_cleared', s.signal_id, printf('%g', s.value), NULL
FROM sig_a s SEMI JOIN act_b USING (entity_id)
ANTI JOIN sig_b USING (entity_id, signal_id)
WHERE s.fact <> 'D'
UNION ALL
SELECT s.entity_id, 'cert_expired_since', s.signal_id, NULL, e.v
FROM sig_b s SEMI JOIN act_a USING (entity_id)
ANTI JOIN sig_a USING (entity_id, signal_id)
LEFT JOIN evd_b e USING (entity_id, signal_id)
WHERE s.signal_id = 'B_expired'
UNION ALL
SELECT s.entity_id, 'protection_added', s.signal_id, NULL, e.v
FROM sig_b s SEMI JOIN act_a USING (entity_id)
ANTI JOIN sig_a USING (entity_id, signal_id)
LEFT JOIN evd_b e USING (entity_id, signal_id)
WHERE s.fact = 'D'
UNION ALL
SELECT s.entity_id, 'protection_removed', s.signal_id, e.v, NULL
FROM sig_a s SEMI JOIN act_b USING (entity_id)
ANTI JOIN sig_b USING (entity_id, signal_id)
LEFT JOIN evd_a e USING (entity_id, signal_id)
WHERE s.fact = 'D'
UNION ALL
SELECT entity_id,
       CASE WHEN b.exposure - a.exposure > 0 THEN 'exposure_up' ELSE 'exposure_down' END,
       'exposure', printf('%.1f', a.exposure), printf('%.1f', b.exposure)
FROM act_a a JOIN act_b b USING (entity_id)
WHERE abs(b.exposure - a.exposure) >= $threshold
UNION ALL
SELECT entity_id, 'segment_changed', 'segment', a.segment, b.segment
FROM act_a a JOIN act_b b USING (entity_id)
WHERE a.segment <> b.segment;
CREATE OR REPLACE TEMP TABLE events AS
SELECT sha1(entity_id || event_type || $from_file || $to_file || subject) AS event_id,
       entity_id, event_type, subject, $from_file AS from_file, $to_file AS to_file,
       from_value, to_value, $detected_at::TIMESTAMP AS detected_at,
       ({severity})::INTEGER AS severity
FROM ev
