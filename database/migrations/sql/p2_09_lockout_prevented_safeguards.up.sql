-- Phase 2 / Auth: LOCKOUT_PREVENTED 3-layer safeguards & emergency break-glass (KB-P2-09)

-- 1. Ensure user_identities exists (dependency KB-P2-08)
CREATE TABLE IF NOT EXISTS user_identities (
    id                      UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id            UUID REFERENCES workspaces(id) ON DELETE CASCADE,
    principal_id            UUID NOT NULL REFERENCES principals(id) ON DELETE CASCADE,
    auth_card_id            UUID NOT NULL REFERENCES auth_provider_cards(id) ON DELETE CASCADE,
    immutable_subject_id    TEXT NOT NULL,
    email_at_link           TEXT,
    subject_email_at_link   TEXT,
    display_name_at_link    TEXT,
    linked_at               TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    last_used_at            TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    last_login_at           TIMESTAMPTZ,
    UNIQUE (auth_card_id, immutable_subject_id)
);

ALTER TABLE user_identities OWNER TO kb_auth_owner;
REVOKE ALL ON user_identities FROM PUBLIC, kanban_app, app_rls_reader;
ALTER TABLE user_identities ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_identities FORCE ROW LEVEL SECURITY;
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'user_identities' AND policyname = 'kb_auth_owner_all'
    ) THEN
        CREATE POLICY kb_auth_owner_all ON user_identities
            FOR ALL TO kb_auth_owner USING (true) WITH CHECK (true);
    END IF;
END $$;

-- 2. Add last_admin_handshake_at to auth_provider_cards
ALTER TABLE auth_provider_cards ADD COLUMN IF NOT EXISTS last_admin_handshake_at TIMESTAMPTZ;

-- Allow kb_auth_owner to read role_bindings and workspaces, and write break-glass activity ledger rows
GRANT SELECT ON TABLE public.workspaces TO kb_auth_owner;
GRANT SELECT, INSERT ON TABLE public.activity_records TO kb_auth_owner;
GRANT SELECT, INSERT, UPDATE ON TABLE public.activity_chain_heads TO kb_auth_owner;
GRANT EXECUTE ON FUNCTION append_activity(uuid, uuid, object_kind, uuid, text, jsonb) TO kb_auth_owner;
GRANT EXECUTE ON FUNCTION verify_activity_chain(uuid) TO kb_auth_owner;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'role_bindings' AND policyname = 'kb_auth_owner_select_role_bindings'
    ) THEN
        CREATE POLICY kb_auth_owner_select_role_bindings ON role_bindings
            FOR SELECT TO kb_auth_owner USING (true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'workspaces' AND policyname = 'kb_auth_owner_select_workspaces'
    ) THEN
        CREATE POLICY kb_auth_owner_select_workspaces ON workspaces
            FOR SELECT TO kb_auth_owner USING (true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'activity_records' AND policyname = 'kb_auth_owner_all_activity_records'
    ) THEN
        CREATE POLICY kb_auth_owner_all_activity_records ON activity_records
            FOR ALL TO kb_auth_owner USING (true) WITH CHECK (true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'activity_chain_heads' AND policyname = 'kb_auth_owner_all_activity_chain_heads'
    ) THEN
        CREATE POLICY kb_auth_owner_all_activity_chain_heads ON activity_chain_heads
            FOR ALL TO kb_auth_owner USING (true) WITH CHECK (true);
    END IF;
END $$;

-- 3. Function: card_can_authenticate_active_server_admin
CREATE OR REPLACE FUNCTION kb_auth.card_can_authenticate_active_server_admin(
    p_card_id uuid,
    p_provider_kind text,
    p_workspace_id uuid
) RETURNS boolean
LANGUAGE plpgsql
STABLE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF p_provider_kind = 'LOCAL_ADMIN' THEN
        RETURN EXISTS (
            SELECT 1
            FROM local_admin_credentials lac
            JOIN principals p ON p.id = lac.principal_id
            JOIN role_bindings rb ON rb.principal_id = p.id
            WHERE p.status = 'ACTIVE'
              AND rb.role = 'SERVER_ADMIN'
              AND (p_workspace_id IS NULL OR rb.workspace_id = p_workspace_id)
        );
    ELSIF p_provider_kind IN ('OIDC', 'OAUTH2', 'LDAP') THEN
        RETURN EXISTS (
            SELECT 1
            FROM user_identities ui
            JOIN principals p ON p.id = ui.principal_id
            JOIN role_bindings rb ON rb.principal_id = p.id
            WHERE ui.auth_card_id = p_card_id
              AND p.status = 'ACTIVE'
              AND rb.role = 'SERVER_ADMIN'
              AND (p_workspace_id IS NULL OR rb.workspace_id = p_workspace_id)
        );
    ELSE
        RETURN FALSE;
    END IF;
END;
$$;

ALTER FUNCTION kb_auth.card_can_authenticate_active_server_admin(uuid, text, uuid) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.card_can_authenticate_active_server_admin(uuid, text, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.card_can_authenticate_active_server_admin(uuid, text, uuid) TO kanban_app;

-- 4. Function: card_record_admin_handshake
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

-- 5. Layer 2 Trigger: trg_local_admin_disable_probe
CREATE OR REPLACE FUNCTION kb_auth.auth_cards_local_admin_disable_probe()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_ws_id uuid;
    v_has_active_admin boolean;
    v_has_valid_external_admin boolean;
BEGIN
    IF OLD.provider_kind = 'LOCAL_ADMIN' AND OLD.is_enabled = TRUE AND (TG_OP = 'DELETE' OR NEW.is_enabled = FALSE) THEN
        v_ws_id := OLD.workspace_id;

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
            -- Check for external card with handshake within 15 minutes
            SELECT EXISTS (
                SELECT 1
                FROM auth_provider_cards c
                WHERE (v_ws_id IS NULL OR c.workspace_id = v_ws_id)
                  AND c.id <> OLD.id
                  AND c.provider_kind IN ('OIDC', 'OAUTH2', 'LDAP')
                  AND c.is_enabled = TRUE
                  AND kb_auth.card_can_authenticate_active_server_admin(c.id, c.provider_kind, c.workspace_id)
                  AND c.last_admin_handshake_at IS NOT NULL
                  AND c.last_admin_handshake_at >= clock_timestamp() - interval '15 minutes'
            ) INTO v_has_valid_external_admin;

            IF NOT v_has_valid_external_admin THEN
                RAISE EXCEPTION 'LOCKOUT_PREVENTED: disabling LOCAL_ADMIN requires a verified external SERVER_ADMIN login within 15 minutes'
                    USING ERRCODE = 'P0001', DETAIL = 'handshake_probe_15m';
            END IF;
        END IF;
    END IF;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    ELSE
        RETURN NEW;
    END IF;
END;
$$;

ALTER FUNCTION kb_auth.auth_cards_local_admin_disable_probe() OWNER TO kb_auth_owner;

DROP TRIGGER IF EXISTS trg_local_admin_disable_probe ON auth_provider_cards;
CREATE TRIGGER trg_local_admin_disable_probe
    BEFORE UPDATE OF is_enabled, provider_kind, workspace_id OR DELETE ON auth_provider_cards
    FOR EACH ROW EXECUTE FUNCTION kb_auth.auth_cards_local_admin_disable_probe();

-- 6. Layer 1 Trigger: trg_auth_cards_prevent_lockout
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

DROP TRIGGER IF EXISTS trg_auth_cards_prevent_lockout ON auth_provider_cards;
CREATE TRIGGER trg_auth_cards_prevent_lockout
    AFTER UPDATE OF is_enabled, provider_kind, workspace_id OR DELETE ON auth_provider_cards
    FOR EACH ROW EXECUTE FUNCTION kb_auth.auth_cards_prevent_lockout();

-- 7. Layer 1 Credential Delete Trigger on local_admin_credentials
CREATE OR REPLACE FUNCTION kb_auth.local_admin_prevent_lockout()
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
    SELECT workspace_id INTO v_ws_id
    FROM role_bindings
    WHERE principal_id = OLD.principal_id
    LIMIT 1;

    PERFORM pg_advisory_xact_lock(hashtextextended('auth_lockout:' || COALESCE(v_ws_id::text, 'global'), 0));

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

ALTER FUNCTION kb_auth.local_admin_prevent_lockout() OWNER TO kb_auth_owner;

DROP TRIGGER IF EXISTS trg_local_admin_prevent_lockout ON local_admin_credentials;
CREATE TRIGGER trg_local_admin_prevent_lockout
    AFTER DELETE ON local_admin_credentials
    FOR EACH ROW EXECUTE FUNCTION kb_auth.local_admin_prevent_lockout();

-- 8. Layer 1 Identity Delete Trigger on user_identities
CREATE OR REPLACE FUNCTION kb_auth.user_identities_prevent_lockout()
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
    SELECT workspace_id INTO v_ws_id
    FROM auth_provider_cards
    WHERE id = OLD.auth_card_id;

    IF v_ws_id IS NULL THEN
        SELECT workspace_id INTO v_ws_id
        FROM role_bindings
        WHERE principal_id = OLD.principal_id
        LIMIT 1;
    END IF;

    PERFORM pg_advisory_xact_lock(hashtextextended('auth_lockout:' || COALESCE(v_ws_id::text, 'global'), 0));

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

ALTER FUNCTION kb_auth.user_identities_prevent_lockout() OWNER TO kb_auth_owner;

DROP TRIGGER IF EXISTS trg_user_identities_prevent_lockout ON user_identities;
CREATE TRIGGER trg_user_identities_prevent_lockout
    AFTER DELETE ON user_identities
    FOR EACH ROW EXECUTE FUNCTION kb_auth.user_identities_prevent_lockout();

-- 9. Layer 3 Function: kb_auth.emergency_enable_local_admin
CREATE OR REPLACE FUNCTION kb_auth.emergency_enable_local_admin(
    p_workspace_id  UUID,
    p_os_uid        INT,
    p_tty           TEXT,
    p_reason        TEXT
)
RETURNS TABLE (
    workspace_id    UUID,
    card_id         UUID,
    activity_id     UUID
)
LANGUAGE plpgsql
VOLATILE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_ws_id         UUID;
    v_card_id       UUID;
    v_act_id        UUID;
    v_chain_valid   BOOLEAN;
    v_clean_reason  TEXT;
    v_payload       JSONB;
BEGIN
    -- 1. Resolve workspace_id
    IF p_workspace_id IS NOT NULL THEN
        SELECT id INTO v_ws_id FROM workspaces WHERE id = p_workspace_id;
        IF v_ws_id IS NULL THEN
            RAISE EXCEPTION 'WORKSPACE_NOT_FOUND: %', p_workspace_id
                USING ERRCODE = 'P0001';
        END IF;
    ELSE
        SELECT id INTO v_ws_id FROM workspaces ORDER BY created_at ASC LIMIT 1;
        IF v_ws_id IS NULL THEN
            RAISE EXCEPTION 'WORKSPACE_NOT_FOUND: no workspace exists'
                USING ERRCODE = 'P0001';
        END IF;
    END IF;

    -- Clean reason: strip control chars, max 256 chars
    v_clean_reason := regexp_replace(COALESCE(p_reason, 'Host shell emergency unlock'), '[\x00-\x1F\x7F]', '', 'g');
    IF length(v_clean_reason) > 256 THEN
        v_clean_reason := substring(v_clean_reason FROM 1 FOR 256);
    END IF;

    -- 2. Upsert/enable the workspace's LOCAL_ADMIN card
    SELECT id INTO v_card_id
    FROM auth_provider_cards
    WHERE (v_ws_id IS NULL OR auth_provider_cards.workspace_id = v_ws_id)
      AND provider_kind = 'LOCAL_ADMIN'
    ORDER BY created_at ASC
    LIMIT 1;

    IF v_card_id IS NOT NULL THEN
        UPDATE auth_provider_cards
        SET is_enabled = TRUE,
            updated_at = clock_timestamp()
        WHERE id = v_card_id;
    ELSE
        v_card_id := uuidv7();
        INSERT INTO auth_provider_cards (
            id,
            workspace_id,
            provider_kind,
            slug,
            display_name,
            button_subtext,
            icon_preset,
            is_enabled,
            sort_rank
        ) VALUES (
            v_card_id,
            v_ws_id,
            'LOCAL_ADMIN',
            'local-admin',
            'Local Administrator',
            'Sign in with administrator credentials',
            'key',
            TRUE,
            '0'
        );
    END IF;

    -- 3. Appends indelible row to activity_records (KB-P1-12 hash-chained ledger)
    v_payload := jsonb_build_object(
        'os_uid', p_os_uid,
        'tty', COALESCE(p_tty, ''),
        'reason', v_clean_reason,
        'card_id', v_card_id
    );

    v_act_id := append_activity(
        v_ws_id,
        NULL,
        NULL,
        NULL,
        'EMERGENCY_BREAK_GLASS_INVOKED',
        v_payload
    );

    -- 4. Verifies verify_activity_chain() remains valid after insert
    SELECT is_valid INTO v_chain_valid
    FROM verify_activity_chain(v_ws_id);

    IF NOT v_chain_valid THEN
        RAISE EXCEPTION 'ACTIVITY_CHAIN_CORRUPTED: break-glass verification failed'
            USING ERRCODE = 'P0001';
    END IF;

    RETURN QUERY SELECT v_ws_id, v_card_id, v_act_id;
END;
$$;

ALTER FUNCTION kb_auth.emergency_enable_local_admin(UUID, INT, TEXT, TEXT) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.emergency_enable_local_admin(UUID, INT, TEXT, TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION kb_auth.emergency_enable_local_admin(UUID, INT, TEXT, TEXT) FROM kanban_app;
GRANT EXECUTE ON FUNCTION kb_auth.emergency_enable_local_admin(UUID, INT, TEXT, TEXT) TO kanban_migrator;
DO $$
BEGIN
    EXECUTE format('GRANT EXECUTE ON FUNCTION kb_auth.emergency_enable_local_admin(UUID, INT, TEXT, TEXT) TO %I', CURRENT_USER);
END $$;
