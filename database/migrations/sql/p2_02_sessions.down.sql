-- Revert Phase 2 / Auth: Server-side sessions, timeouts and security definer functions (KB-P2-02)

REVOKE EXECUTE ON FUNCTION kb_auth.session_revoke_all_for_principal(UUID) FROM kanban_app;
REVOKE EXECUTE ON FUNCTION kb_auth.session_rotate(UUID, BYTEA, SMALLINT) FROM kanban_app;
REVOKE EXECUTE ON FUNCTION kb_auth.session_revoke(UUID) FROM kanban_app;
REVOKE EXECUTE ON FUNCTION kb_auth.session_resolve(BYTEA) FROM kanban_app;
REVOKE EXECUTE ON FUNCTION kb_auth.session_create(UUID, BYTEA, UUID, UUID, UUID, SMALLINT, TIMESTAMPTZ, BOOLEAN, TIMESTAMPTZ, TIMESTAMPTZ, UUID) FROM kanban_app;

DROP FUNCTION IF EXISTS kb_auth.session_revoke_all_for_principal(UUID);
DROP FUNCTION IF EXISTS kb_auth.session_rotate(UUID, BYTEA, SMALLINT);
DROP FUNCTION IF EXISTS kb_auth.session_revoke(UUID);
DROP FUNCTION IF EXISTS kb_auth.session_resolve(BYTEA);
DROP FUNCTION IF EXISTS kb_auth.session_create(UUID, BYTEA, UUID, UUID, UUID, SMALLINT, TIMESTAMPTZ, BOOLEAN, TIMESTAMPTZ, TIMESTAMPTZ, UUID);

DROP TABLE IF EXISTS sessions CASCADE;
