-- Revert Phase 2 / Auth: Local Admin card credentials and kb_auth functions (KB-P2-04)

REVOKE EXECUTE ON FUNCTION kb_auth.local_admin_create(UUID, TEXT, TEXT, TEXT) FROM kanban_app;
REVOKE EXECUTE ON FUNCTION kb_auth.local_set_password_hash(UUID, TEXT) FROM kanban_app;
REVOKE EXECUTE ON FUNCTION kb_auth.local_get_credential(TEXT) FROM kanban_app;

DROP FUNCTION IF EXISTS kb_auth.local_admin_create(UUID, TEXT, TEXT, TEXT);
DROP FUNCTION IF EXISTS kb_auth.local_set_password_hash(UUID, TEXT);
DROP FUNCTION IF EXISTS kb_auth.local_get_credential(TEXT);

DROP POLICY IF EXISTS kb_auth_owner_select_principals ON principals;
REVOKE SELECT ON TABLE principals FROM kb_auth_owner;

DROP POLICY IF EXISTS kb_auth_owner_all ON local_admin_credentials;
DROP TABLE IF EXISTS local_admin_credentials CASCADE;
