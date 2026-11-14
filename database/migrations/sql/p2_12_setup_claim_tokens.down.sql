-- Revert Phase 2 / Auth: First-boot setup claim tokens and kb_auth functions (KB-P2-12)

DROP FUNCTION IF EXISTS kb_auth.setup_consume_and_create_admin(bytea, text, text, text, text);
DROP FUNCTION IF EXISTS kb_auth.setup_mint_token(bytea, int);
DROP FUNCTION IF EXISTS kb_auth.setup_is_initialized();

DROP POLICY IF EXISTS kb_auth_owner_activity_chain_heads ON activity_chain_heads;
DROP POLICY IF EXISTS kb_auth_owner_activity_records ON activity_records;
DROP POLICY IF EXISTS kb_auth_owner_role_bindings ON role_bindings;
DROP POLICY IF EXISTS kb_auth_owner_users ON users;
DROP POLICY IF EXISTS kb_auth_owner_principals_all ON principals;
DROP POLICY IF EXISTS kb_auth_owner_objects ON objects;
DROP POLICY IF EXISTS kb_auth_owner_workspaces ON workspaces;

REVOKE EXECUTE ON FUNCTION append_activity(uuid, uuid, object_kind, uuid, text, jsonb) FROM kb_auth_owner;
REVOKE SELECT, INSERT, UPDATE ON TABLE activity_chain_heads FROM kb_auth_owner;
REVOKE SELECT, INSERT, UPDATE ON TABLE activity_records FROM kb_auth_owner;
REVOKE SELECT, INSERT, UPDATE ON TABLE auth_provider_cards FROM kb_auth_owner;
REVOKE SELECT, INSERT, UPDATE ON TABLE role_bindings FROM kb_auth_owner;
REVOKE SELECT, INSERT, UPDATE ON TABLE users FROM kb_auth_owner;
REVOKE SELECT, INSERT, UPDATE ON TABLE principals FROM kb_auth_owner;
REVOKE SELECT, INSERT, UPDATE ON TABLE objects FROM kb_auth_owner;
REVOKE SELECT, INSERT, UPDATE ON TABLE workspaces FROM kb_auth_owner;

DROP TABLE IF EXISTS setup_claim_tokens CASCADE;
