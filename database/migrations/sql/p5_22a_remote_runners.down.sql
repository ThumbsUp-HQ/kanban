-- Phase 5 / Database + API: remote_runner registry and mTLS enrollment tokens (KB-P5-22a, S14.2, S11.4)

DROP FUNCTION IF EXISTS register_remote_runner(UUID, UUID, TEXT, TEXT, BYTEA, TIMESTAMPTZ, JSONB, UUID);
DROP FUNCTION IF EXISTS consume_runner_enrollment_token(BYTEA);
DROP FUNCTION IF EXISTS touch_runner_heartbeat(UUID, TEXT);
DROP FUNCTION IF EXISTS get_runner_by_cert_sha256(BYTEA);
DROP FUNCTION IF EXISTS enroll_remote_runner(BYTEA, TEXT, BYTEA, TIMESTAMPTZ, JSONB);
DROP TABLE IF EXISTS remote_runners CASCADE;
DROP TABLE IF EXISTS remote_runner_enrollment_tokens CASCADE;
