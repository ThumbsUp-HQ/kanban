-- Downgrade: remove LOCKOUT_PREVENTED safeguards and emergency break-glass (KB-P2-09)

DROP TRIGGER IF EXISTS trg_user_identities_prevent_lockout ON user_identities;
DROP FUNCTION IF EXISTS kb_auth.user_identities_prevent_lockout();

DROP TRIGGER IF EXISTS trg_local_admin_prevent_lockout ON local_admin_credentials;
DROP FUNCTION IF EXISTS kb_auth.local_admin_prevent_lockout();

DROP TRIGGER IF EXISTS trg_auth_cards_prevent_lockout ON auth_provider_cards;
DROP FUNCTION IF EXISTS kb_auth.auth_cards_prevent_lockout();

DROP TRIGGER IF EXISTS trg_local_admin_disable_probe ON auth_provider_cards;
DROP FUNCTION IF EXISTS kb_auth.auth_cards_local_admin_disable_probe();

DROP FUNCTION IF EXISTS kb_auth.emergency_enable_local_admin(UUID, INT, TEXT, TEXT);
DROP FUNCTION IF EXISTS kb_auth.card_record_admin_handshake(uuid);
DROP FUNCTION IF EXISTS kb_auth.card_can_authenticate_active_server_admin(uuid, text, uuid);

ALTER TABLE auth_provider_cards DROP COLUMN IF EXISTS last_admin_handshake_at;

DROP POLICY IF EXISTS kb_auth_owner_all_activity_chain_heads ON activity_chain_heads;
DROP POLICY IF EXISTS kb_auth_owner_all_activity_records ON activity_records;
DROP POLICY IF EXISTS kb_auth_owner_select_workspaces ON workspaces;
DROP POLICY IF EXISTS kb_auth_owner_select_role_bindings ON role_bindings;
