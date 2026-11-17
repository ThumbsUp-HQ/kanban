-- Revert Phase 2 / Auth: auth_provider_cards DDL, kb_auth data boundary (KB-P2-03)

DO $$
BEGIN
    EXECUTE format('GRANT kb_auth_owner TO %I WITH SET TRUE, INHERIT TRUE', CURRENT_USER);
    EXECUTE format('GRANT ALL ON SCHEMA kb_auth TO %I', CURRENT_USER);
EXCEPTION
    WHEN OTHERS THEN NULL;
END $$;

REVOKE EXECUTE ON FUNCTION kb_auth.card_rewrap(UUID, BYTEA, TEXT, TEXT) FROM kanban_app;
REVOKE EXECUTE ON FUNCTION kb_auth.card_admin_list() FROM kanban_app;
REVOKE EXECUTE ON FUNCTION kb_auth.card_admin_get(UUID) FROM kanban_app;
REVOKE EXECUTE ON FUNCTION kb_auth.card_admin_upsert(UUID, UUID, TEXT, TEXT, TEXT, TEXT, TEXT, BOOLEAN, TEXT, BOOLEAN, TEXT[], JSONB, BYTEA, BYTEA, TEXT, TEXT) FROM kanban_app;
REVOKE EXECUTE ON FUNCTION kb_auth.card_get_for_login(TEXT) FROM kanban_app;
REVOKE EXECUTE ON FUNCTION kb_auth.card_list_enabled_public() FROM kanban_app;

DROP FUNCTION IF EXISTS kb_auth.card_rewrap(UUID, BYTEA, TEXT, TEXT);
DROP FUNCTION IF EXISTS kb_auth.card_admin_list();
DROP FUNCTION IF EXISTS kb_auth.card_admin_get(UUID);
DROP FUNCTION IF EXISTS kb_auth.card_admin_upsert(UUID, UUID, TEXT, TEXT, TEXT, TEXT, TEXT, BOOLEAN, TEXT, BOOLEAN, TEXT[], JSONB, BYTEA, BYTEA, TEXT, TEXT);
DROP FUNCTION IF EXISTS kb_auth.card_get_for_login(TEXT);
DROP FUNCTION IF EXISTS kb_auth.card_list_enabled_public();

DROP TRIGGER IF EXISTS auth_provider_cards_set_updated_at ON auth_provider_cards;
DROP TABLE IF EXISTS auth_provider_cards CASCADE;

REVOKE USAGE ON SCHEMA kb_auth FROM kanban_app;
DROP SCHEMA IF EXISTS kb_auth CASCADE;

REVOKE SELECT ON TABLE role_bindings FROM kb_auth_owner;
REVOKE EXECUTE ON FUNCTION app_effective_principal_set() FROM kb_auth_owner;
REVOKE USAGE, CREATE ON SCHEMA public FROM kb_auth_owner;

-- Note: cluster-level role kb_auth_owner and its membership on kanban_migrator are retained
-- so concurrent databases on the same cluster do not lose role membership during downgrades.
