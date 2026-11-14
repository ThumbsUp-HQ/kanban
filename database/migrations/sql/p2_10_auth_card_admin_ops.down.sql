-- Revert Phase 2 / Auth: Auth card admin operations and public enabled-cards projection (KB-P2-10)

DROP FUNCTION IF EXISTS kb_auth.card_record_admin_handshake(UUID);
CREATE OR REPLACE FUNCTION kb_auth.card_record_admin_handshake(p_card_id uuid)
RETURNS void
LANGUAGE plpgsql
VOLATILE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    UPDATE auth_provider_cards
    SET last_admin_handshake_at = clock_timestamp()
    WHERE id = p_card_id;
END;
$$;

ALTER FUNCTION kb_auth.card_record_admin_handshake(uuid) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.card_record_admin_handshake(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.card_record_admin_handshake(uuid) TO kanban_app;
DROP FUNCTION IF EXISTS kb_auth.card_admin_delete(UUID);
DROP FUNCTION IF EXISTS kb_auth.card_admin_set_health(UUID, TEXT);
DROP FUNCTION IF EXISTS kb_auth.card_admin_reorder(UUID, TEXT);
DROP FUNCTION IF EXISTS kb_auth.card_admin_set_enabled(UUID, BOOLEAN);

DROP FUNCTION IF EXISTS kb_auth.card_list_enabled_public();
CREATE OR REPLACE FUNCTION kb_auth.card_list_enabled_public()
RETURNS TABLE (
    slug            TEXT,
    display_name    TEXT,
    button_subtext  TEXT,
    icon_preset     TEXT,
    provider_kind   TEXT,
    sort_rank       TEXT
)
LANGUAGE plpgsql
STABLE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    RETURN QUERY
    SELECT
        c.slug,
        c.display_name,
        c.button_subtext,
        c.icon_preset,
        c.provider_kind,
        c.sort_rank
    FROM auth_provider_cards c
    WHERE c.is_enabled = TRUE
    ORDER BY c.sort_rank COLLATE "C" ASC, c.id ASC;
END;
$$;

ALTER FUNCTION kb_auth.card_list_enabled_public() OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.card_list_enabled_public() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.card_list_enabled_public() TO kanban_app;


