-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

-- 1. Revoke and drop functions
REVOKE EXECUTE ON FUNCTION kb_auth.identity_unlink(UUID, UUID) FROM kanban_app;
DROP FUNCTION IF EXISTS kb_auth.identity_unlink(UUID, UUID);

REVOKE EXECUTE ON FUNCTION kb_auth.identity_link_consume_and_bind(UUID, UUID, UUID, UUID, TEXT, TEXT) FROM kanban_app;
DROP FUNCTION IF EXISTS kb_auth.identity_link_consume_and_bind(UUID, UUID, UUID, UUID, TEXT, TEXT);

REVOKE EXECUTE ON FUNCTION kb_auth.identity_link_intent_create(UUID, UUID, UUID, INT, UUID) FROM kanban_app;
DROP FUNCTION IF EXISTS kb_auth.identity_link_intent_create(UUID, UUID, UUID, INT, UUID);

REVOKE EXECUTE ON FUNCTION kb_auth.identity_link_intent_get(UUID) FROM kanban_app;
DROP FUNCTION IF EXISTS kb_auth.identity_link_intent_get(UUID);

REVOKE EXECUTE ON FUNCTION kb_auth.identity_list_for_principal(UUID) FROM kanban_app;
DROP FUNCTION IF EXISTS kb_auth.identity_list_for_principal(UUID);

REVOKE EXECUTE ON FUNCTION kb_auth.identity_provision_new_user(UUID, UUID, TEXT, TEXT, TEXT) FROM kanban_app;
DROP FUNCTION IF EXISTS kb_auth.identity_provision_new_user(UUID, UUID, TEXT, TEXT, TEXT);

REVOKE EXECUTE ON FUNCTION kb_auth.identity_record_login(UUID) FROM kanban_app;
DROP FUNCTION IF EXISTS kb_auth.identity_record_login(UUID);

REVOKE EXECUTE ON FUNCTION kb_auth.identity_lookup(UUID, TEXT) FROM kanban_app;
DROP FUNCTION IF EXISTS kb_auth.identity_lookup(UUID, TEXT);

REVOKE EXECUTE ON FUNCTION kb_auth.card_get_by_id(UUID) FROM kanban_app;
DROP FUNCTION IF EXISTS kb_auth.card_get_by_id(UUID);

-- 2. Drop RLS policies and revoke grants for kb_auth_owner
DROP POLICY IF EXISTS kb_auth_owner_select_workspaces ON workspaces;
REVOKE SELECT ON TABLE workspaces FROM kb_auth_owner;

DROP POLICY IF EXISTS kb_auth_owner_all_role_bindings ON role_bindings;
REVOKE SELECT, INSERT ON TABLE role_bindings FROM kb_auth_owner;

DROP POLICY IF EXISTS kb_auth_owner_all_objects ON objects;
REVOKE SELECT, INSERT ON TABLE objects FROM kb_auth_owner;

DROP POLICY IF EXISTS kb_auth_owner_all_users ON users;
REVOKE SELECT, INSERT ON TABLE users FROM kb_auth_owner;

DROP POLICY IF EXISTS kb_auth_owner_all_principals ON principals;
REVOKE SELECT, INSERT ON TABLE principals FROM kb_auth_owner;

-- 3. Drop tables
DROP TABLE IF EXISTS identity_link_intents CASCADE;
DROP TABLE IF EXISTS user_identities CASCADE;
