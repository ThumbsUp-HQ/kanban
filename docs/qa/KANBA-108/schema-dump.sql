-- ============================================================
-- TRIGGERS DUMP: trg_auth_cards_prevent_lockout, trg_local_admin_disable_probe, etc.
-- ============================================================
-- Table: auth_provider_cards | Trigger: trg_auth_cards_prevent_lockout | Timing: AFTER | Event: DELETE
-- Action: EXECUTE FUNCTION kb_auth.auth_cards_prevent_lockout()

-- Table: auth_provider_cards | Trigger: trg_auth_cards_prevent_lockout | Timing: AFTER | Event: UPDATE
-- Action: EXECUTE FUNCTION kb_auth.auth_cards_prevent_lockout()

-- Table: auth_provider_cards | Trigger: trg_local_admin_disable_probe | Timing: BEFORE | Event: DELETE
-- Action: EXECUTE FUNCTION kb_auth.auth_cards_local_admin_disable_probe()

-- Table: auth_provider_cards | Trigger: trg_local_admin_disable_probe | Timing: BEFORE | Event: UPDATE
-- Action: EXECUTE FUNCTION kb_auth.auth_cards_local_admin_disable_probe()

-- Table: local_admin_credentials | Trigger: trg_local_admin_prevent_lockout | Timing: AFTER | Event: DELETE
-- Action: EXECUTE FUNCTION kb_auth.local_admin_prevent_lockout()

-- Table: user_identities | Trigger: trg_user_identities_prevent_lockout | Timing: AFTER | Event: DELETE
-- Action: EXECUTE FUNCTION kb_auth.user_identities_prevent_lockout()

-- ============================================================
-- FUNCTION PRIVILEGES: kb_auth.emergency_enable_local_admin
-- Confirming kanban_app lacks EXECUTE on emergency_enable_local_admin
-- ============================================================
-- Grantee: kanban_migrator | Privilege: EXECUTE
-- Grantee: kb_auth_owner | Privilege: EXECUTE
