-- Revert Phase 2 / Kanban: Sliding-window rate limiting service (KB-P2-18)

REVOKE EXECUTE ON FUNCTION kb_infra.rate_limit_reset(text, bytea) FROM kanban_app;
REVOKE EXECUTE ON FUNCTION kb_infra.rate_limit_hit(text, bytea, integer, integer, timestamptz) FROM kanban_app;

DROP FUNCTION IF EXISTS kb_infra.rate_limit_reset(text, bytea);
DROP FUNCTION IF EXISTS kb_infra.rate_limit_hit(text, bytea, integer, integer, timestamptz);

DROP POLICY IF EXISTS kb_infra_owner_all ON rate_limit_buckets;
DROP TABLE IF EXISTS rate_limit_buckets CASCADE;

REVOKE USAGE ON SCHEMA kb_infra FROM kanban_app;
DROP SCHEMA IF EXISTS kb_infra CASCADE;
