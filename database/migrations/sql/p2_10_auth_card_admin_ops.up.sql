-- Phase 2 / Auth: Auth card admin operations and public enabled-cards projection (KB-P2-10)

-- 1. Schema extension: add last_admin_handshake_at if not present
ALTER TABLE auth_provider_cards ADD COLUMN IF NOT EXISTS last_admin_handshake_at TIMESTAMPTZ;

-- 2. Update Function: card_list_enabled_public (include id)
DROP FUNCTION IF EXISTS kb_auth.card_list_enabled_public();
CREATE OR REPLACE FUNCTION kb_auth.card_list_enabled_public()
RETURNS TABLE (
    id              UUID,
    slug            TEXT,
    display_name    TEXT,
    button_subtext  TEXT,
    icon_preset     TEXT,
    provider_kind   TEXT
)
LANGUAGE plpgsql
STABLE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    RETURN QUERY
    SELECT
        c.id,
        c.slug,
        c.display_name,
        c.button_subtext,
        c.icon_preset,
        c.provider_kind
    FROM auth_provider_cards c
    WHERE c.is_enabled = TRUE
    ORDER BY c.sort_rank COLLATE "C" ASC, c.id ASC;
END;
$$;

ALTER FUNCTION kb_auth.card_list_enabled_public() OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.card_list_enabled_public() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.card_list_enabled_public() TO kanban_app;

-- 3. Function: card_admin_set_enabled
CREATE OR REPLACE FUNCTION kb_auth.card_admin_set_enabled(
    p_id            UUID,
    p_is_enabled    BOOLEAN
)
RETURNS BOOLEAN
LANGUAGE plpgsql
VOLATILE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_provider_kind TEXT;
    v_workspace_id UUID;
    v_old_enabled BOOLEAN;
    v_admin_count INT;
    v_external_recent_handshake BOOLEAN;
BEGIN
    IF NOT (
        EXISTS (
            SELECT 1
            FROM role_bindings rb
            WHERE rb.principal_id = ANY (app_effective_principal_set())
              AND rb.role = 'SERVER_ADMIN'
        )
        AND current_setting('app.aal_level', true) = '2'
    ) THEN
        RAISE EXCEPTION 'insufficient_privilege: SERVER_ADMIN with AAL2 required'
            USING ERRCODE = '42501';
    END IF;

    SELECT provider_kind, workspace_id, is_enabled
    INTO v_provider_kind, v_workspace_id, v_old_enabled
    FROM auth_provider_cards
    WHERE id = p_id;

    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;

    -- If disabling, enforce anti-lockout safeguards
    IF v_old_enabled AND NOT p_is_enabled THEN
        -- Layer 2 check: if disabling LOCAL_ADMIN, must have recent external admin login within 15 minutes
        IF v_provider_kind = 'LOCAL_ADMIN' THEN
            SELECT EXISTS (
                SELECT 1
                FROM auth_provider_cards
                WHERE (workspace_id IS NOT DISTINCT FROM v_workspace_id)
                  AND provider_kind IN ('OIDC', 'OAUTH2', 'LDAP')
                  AND is_enabled = TRUE
                  AND last_admin_handshake_at IS NOT NULL
                  AND last_admin_handshake_at >= clock_timestamp() - INTERVAL '15 minutes'
            ) INTO v_external_recent_handshake;

            IF NOT v_external_recent_handshake THEN
                RAISE EXCEPTION 'LOCKOUT_PREVENTED: disabling LOCAL_ADMIN requires verified login on an external card within 15 minutes'
                    USING ERRCODE = 'P0001', DETAIL = 'handshake_probe_15m';
            END IF;
        END IF;

        -- Layer 1 check: disabling this card must not leave 0 enabled cards that can authenticate a SERVER_ADMIN
        SELECT COUNT(*)
        INTO v_admin_count
        FROM auth_provider_cards
        WHERE (workspace_id IS NOT DISTINCT FROM v_workspace_id)
          AND is_enabled = TRUE
          AND id <> p_id;

        IF v_admin_count = 0 THEN
            RAISE EXCEPTION 'LOCKOUT_PREVENTED: zero enabled cards can authenticate an active SERVER_ADMIN'
                USING ERRCODE = 'P0001', DETAIL = 'db_trigger';
        END IF;
    END IF;

    UPDATE auth_provider_cards
    SET is_enabled = p_is_enabled,
        updated_at = clock_timestamp()
    WHERE id = p_id;

    RETURN TRUE;
END;
$$;

ALTER FUNCTION kb_auth.card_admin_set_enabled(UUID, BOOLEAN) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.card_admin_set_enabled(UUID, BOOLEAN) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.card_admin_set_enabled(UUID, BOOLEAN) TO kanban_app;

-- 4. Function: card_admin_reorder
CREATE OR REPLACE FUNCTION kb_auth.card_admin_reorder(
    p_id        UUID,
    p_sort_rank TEXT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
VOLATILE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF NOT (
        EXISTS (
            SELECT 1
            FROM role_bindings rb
            WHERE rb.principal_id = ANY (app_effective_principal_set())
              AND rb.role = 'SERVER_ADMIN'
        )
        AND current_setting('app.aal_level', true) = '2'
    ) THEN
        RAISE EXCEPTION 'insufficient_privilege: SERVER_ADMIN with AAL2 required'
            USING ERRCODE = '42501';
    END IF;

    UPDATE auth_provider_cards
    SET sort_rank = p_sort_rank,
        updated_at = clock_timestamp()
    WHERE id = p_id;

    RETURN FOUND;
END;
$$;

ALTER FUNCTION kb_auth.card_admin_reorder(UUID, TEXT) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.card_admin_reorder(UUID, TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.card_admin_reorder(UUID, TEXT) TO kanban_app;

-- 5. Function: card_admin_set_health
CREATE OR REPLACE FUNCTION kb_auth.card_admin_set_health(
    p_id        UUID,
    p_status    TEXT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
VOLATILE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF NOT (
        EXISTS (
            SELECT 1
            FROM role_bindings rb
            WHERE rb.principal_id = ANY (app_effective_principal_set())
              AND rb.role = 'SERVER_ADMIN'
        )
        AND current_setting('app.aal_level', true) = '2'
    ) THEN
        RAISE EXCEPTION 'insufficient_privilege: SERVER_ADMIN with AAL2 required'
            USING ERRCODE = '42501';
    END IF;

    UPDATE auth_provider_cards
    SET last_health_status = p_status,
        updated_at = clock_timestamp()
    WHERE id = p_id;

    RETURN FOUND;
END;
$$;

ALTER FUNCTION kb_auth.card_admin_set_health(UUID, TEXT) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.card_admin_set_health(UUID, TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.card_admin_set_health(UUID, TEXT) TO kanban_app;

-- 6. Function: card_admin_delete
CREATE OR REPLACE FUNCTION kb_auth.card_admin_delete(
    p_id UUID
)
RETURNS BOOLEAN
LANGUAGE plpgsql
VOLATILE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_provider_kind TEXT;
    v_workspace_id UUID;
    v_is_enabled BOOLEAN;
    v_admin_count INT;
    v_external_recent_handshake BOOLEAN;
BEGIN
    IF NOT (
        EXISTS (
            SELECT 1
            FROM role_bindings rb
            WHERE rb.principal_id = ANY (app_effective_principal_set())
              AND rb.role = 'SERVER_ADMIN'
        )
        AND current_setting('app.aal_level', true) = '2'
    ) THEN
        RAISE EXCEPTION 'insufficient_privilege: SERVER_ADMIN with AAL2 required'
            USING ERRCODE = '42501';
    END IF;

    SELECT provider_kind, workspace_id, is_enabled
    INTO v_provider_kind, v_workspace_id, v_is_enabled
    FROM auth_provider_cards
    WHERE id = p_id;

    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;

    -- If card is enabled, check anti-lockout safeguards
    IF v_is_enabled THEN
        IF v_provider_kind = 'LOCAL_ADMIN' THEN
            SELECT EXISTS (
                SELECT 1
                FROM auth_provider_cards
                WHERE (workspace_id IS NOT DISTINCT FROM v_workspace_id)
                  AND provider_kind IN ('OIDC', 'OAUTH2', 'LDAP')
                  AND is_enabled = TRUE
                  AND last_admin_handshake_at IS NOT NULL
                  AND last_admin_handshake_at >= clock_timestamp() - INTERVAL '15 minutes'
            ) INTO v_external_recent_handshake;

            IF NOT v_external_recent_handshake THEN
                RAISE EXCEPTION 'LOCKOUT_PREVENTED: disabling LOCAL_ADMIN requires verified login on an external card within 15 minutes'
                    USING ERRCODE = 'P0001', DETAIL = 'handshake_probe_15m';
            END IF;
        END IF;

        SELECT COUNT(*)
        INTO v_admin_count
        FROM auth_provider_cards
        WHERE (workspace_id IS NOT DISTINCT FROM v_workspace_id)
          AND is_enabled = TRUE
          AND id <> p_id;

        IF v_admin_count = 0 THEN
            RAISE EXCEPTION 'LOCKOUT_PREVENTED: zero enabled cards can authenticate an active SERVER_ADMIN'
                USING ERRCODE = 'P0001', DETAIL = 'db_trigger';
        END IF;
    END IF;

    DELETE FROM auth_provider_cards
    WHERE id = p_id;

    RETURN TRUE;
END;
$$;

ALTER FUNCTION kb_auth.card_admin_delete(UUID) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.card_admin_delete(UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.card_admin_delete(UUID) TO kanban_app;

-- 7. Refined Layer 1 Trigger: only disabling or deleting an ENABLED card can cause lockout
CREATE OR REPLACE FUNCTION kb_auth.auth_cards_prevent_lockout()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_ws_id uuid;
    v_has_active_admin boolean;
    v_admin_card_count int;
BEGIN
    -- Only disabling or deleting an ENABLED card can cause a lockout
    IF NOT OLD.is_enabled THEN
        RETURN NULL;
    END IF;

    v_ws_id := COALESCE(NEW.workspace_id, OLD.workspace_id);

    -- Acquire advisory lock for this workspace to prevent concurrent dual-disable race
    PERFORM pg_advisory_xact_lock(hashtextextended('auth_lockout:' || COALESCE(v_ws_id::text, 'global'), 0));

    -- Only evaluate when workspace already has >= 1 active SERVER_ADMIN
    SELECT EXISTS (
        SELECT 1
        FROM principals p
        JOIN role_bindings rb ON rb.principal_id = p.id
        WHERE p.status = 'ACTIVE'
          AND rb.role = 'SERVER_ADMIN'
          AND (v_ws_id IS NULL OR rb.workspace_id = v_ws_id)
    ) INTO v_has_active_admin;

    IF v_has_active_admin THEN
        SELECT count(*)
        INTO v_admin_card_count
        FROM auth_provider_cards c
        WHERE (v_ws_id IS NULL OR c.workspace_id = v_ws_id)
          AND c.is_enabled = TRUE
          AND kb_auth.card_can_authenticate_active_server_admin(c.id, c.provider_kind, c.workspace_id);

        IF v_admin_card_count = 0 THEN
            RAISE EXCEPTION 'LOCKOUT_PREVENTED: zero enabled cards can authenticate an active SERVER_ADMIN'
                USING ERRCODE = 'P0001', DETAIL = 'db_trigger';
        END IF;
    END IF;

    RETURN NULL;
END;
$$;

ALTER FUNCTION kb_auth.auth_cards_prevent_lockout() OWNER TO kb_auth_owner;

-- 8. Helper: card_record_admin_handshake
DROP FUNCTION IF EXISTS kb_auth.card_record_admin_handshake(UUID);
CREATE OR REPLACE FUNCTION kb_auth.card_record_admin_handshake(p_card_id UUID)
RETURNS BOOLEAN
LANGUAGE plpgsql
VOLATILE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    UPDATE auth_provider_cards
    SET last_admin_handshake_at = clock_timestamp(),
        updated_at = clock_timestamp()
    WHERE id = p_card_id;

    RETURN FOUND;
END;
$$;

ALTER FUNCTION kb_auth.card_record_admin_handshake(UUID) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.card_record_admin_handshake(UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.card_record_admin_handshake(UUID) TO kanban_app;
