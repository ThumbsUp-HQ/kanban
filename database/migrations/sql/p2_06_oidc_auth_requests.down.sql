-- Revert Phase 2 / Auth: OIDC and OAuth2 authentication requests and state tracking (KB-P2-06)

DROP FUNCTION IF EXISTS kb_auth.oidc_request_consume(BYTEA, BYTEA);
DROP FUNCTION IF EXISTS kb_auth.oidc_request_create(UUID, BYTEA, BYTEA, BYTEA, BYTEA, TEXT, UUID, TIMESTAMPTZ, UUID);

DROP TABLE IF EXISTS oidc_auth_requests CASCADE;
