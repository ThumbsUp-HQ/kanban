-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

-- 1. Tables: user_identities and identity_link_intents
CREATE TABLE user_identities (
    id                    UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id          UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    principal_id          UUID NOT NULL REFERENCES principals(id) ON DELETE CASCADE,
    auth_card_id          UUID NOT NULL REFERENCES auth_provider_cards(id) ON DELETE RESTRICT,
    immutable_subject_id  TEXT NOT NULL CHECK (char_length(btrim(immutable_subject_id)) BETWEEN 1 AND 255),
    subject_email_at_link TEXT,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    last_login_at         TIMESTAMPTZ,
    UNIQUE (auth_card_id, immutable_subject_id)
);

CREATE INDEX user_identities_principal_idx ON user_identities (principal_id);
CREATE INDEX user_identities_workspace_idx ON user_identities (workspace_id);

ALTER TABLE user_identities OWNER TO kb_auth_owner;
REVOKE ALL ON user_identities FROM PUBLIC, kanban_app, app_rls_reader;
ALTER TABLE user_identities ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_identities FORCE ROW LEVEL SECURITY;
CREATE POLICY kb_auth_owner_all ON user_identities FOR ALL TO kb_auth_owner USING (true) WITH CHECK (true);

CREATE TABLE identity_link_intents (
    id              UUID PRIMARY KEY DEFAULT uuidv7(),
    principal_id    UUID NOT NULL REFERENCES principals(id) ON DELETE CASCADE,
    session_id      UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    target_card_id  UUID NOT NULL REFERENCES auth_provider_cards(id) ON DELETE CASCADE,
    expires_at      TIMESTAMPTZ NOT NULL,
    consumed_at     TIMESTAMPTZ
);

CREATE INDEX identity_link_intents_principal_idx ON identity_link_intents (principal_id);
CREATE INDEX identity_link_intents_session_idx ON identity_link_intents (session_id);

ALTER TABLE identity_link_intents OWNER TO kb_auth_owner;
REVOKE ALL ON identity_link_intents FROM PUBLIC, kanban_app, app_rls_reader;
ALTER TABLE identity_link_intents ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_link_intents FORCE ROW LEVEL SECURITY;
CREATE POLICY kb_auth_owner_all ON identity_link_intents FOR ALL TO kb_auth_owner USING (true) WITH CHECK (true);

-- 2. Permissions and RLS policies for kb_auth_owner on dependent core tables
GRANT SELECT, INSERT ON TABLE principals TO kb_auth_owner;
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'principals' AND policyname = 'kb_auth_owner_all_principals'
    ) THEN
        CREATE POLICY kb_auth_owner_all_principals ON principals FOR ALL TO kb_auth_owner USING (true) WITH CHECK (true);
    END IF;
END $$;

GRANT SELECT, INSERT ON TABLE users TO kb_auth_owner;
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'users' AND policyname = 'kb_auth_owner_all_users'
    ) THEN
        CREATE POLICY kb_auth_owner_all_users ON users FOR ALL TO kb_auth_owner USING (true) WITH CHECK (true);
    END IF;
END $$;

GRANT SELECT, INSERT ON TABLE objects TO kb_auth_owner;
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'objects' AND policyname = 'kb_auth_owner_all_objects'
    ) THEN
        CREATE POLICY kb_auth_owner_all_objects ON objects FOR ALL TO kb_auth_owner USING (true) WITH CHECK (true);
    END IF;
END $$;

GRANT SELECT, INSERT ON TABLE role_bindings TO kb_auth_owner;
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'role_bindings' AND policyname = 'kb_auth_owner_all_role_bindings'
    ) THEN
        CREATE POLICY kb_auth_owner_all_role_bindings ON role_bindings FOR ALL TO kb_auth_owner USING (true) WITH CHECK (true);
    END IF;
END $$;

GRANT SELECT ON TABLE workspaces TO kb_auth_owner;
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'workspaces' AND policyname = 'kb_auth_owner_select_workspaces'
    ) THEN
        CREATE POLICY kb_auth_owner_select_workspaces ON workspaces FOR SELECT TO kb_auth_owner USING (true);
    END IF;
END $$;

-- 3. Functions in schema kb_auth (owned by kb_auth_owner, SECURITY DEFINER)

-- Function 0: card_get_by_id (safe public card lookup by id for login / linking)
CREATE OR REPLACE FUNCTION kb_auth.card_get_by_id(p_id UUID)
RETURNS TABLE (
    id UUID,
    workspace_id UUID,
    provider_kind TEXT,
    slug TEXT,
    display_name TEXT,
    button_subtext TEXT,
    icon_preset TEXT,
    is_enabled BOOLEAN,
    sort_rank TEXT,
    auto_provision_users BOOLEAN,
    allowed_email_domains TEXT[],
    public_config JSONB
)
LANGUAGE plpgsql
STABLE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    RETURN QUERY
    SELECT
        c.id,
        c.workspace_id,
        c.provider_kind,
        c.slug,
        c.display_name,
        c.button_subtext,
        c.icon_preset,
        c.is_enabled,
        c.sort_rank::TEXT,
        c.auto_provision_users,
        c.allowed_email_domains,
        c.public_config
    FROM auth_provider_cards c
    WHERE c.id = p_id;
END;
$$;

ALTER FUNCTION kb_auth.card_get_by_id(UUID) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.card_get_by_id(UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.card_get_by_id(UUID) TO kanban_app;

-- Function 1: identity_lookup
CREATE OR REPLACE FUNCTION kb_auth.identity_lookup(
    p_card_id UUID,
    p_subject TEXT
)
RETURNS TABLE (
    id UUID,
    workspace_id UUID,
    principal_id UUID,
    status TEXT,
    last_login_at TIMESTAMPTZ,
    subject_email_at_link TEXT,
    user_email TEXT,
    display_name TEXT
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    RETURN QUERY
    SELECT
        ui.id,
        ui.workspace_id,
        ui.principal_id,
        p.status,
        ui.last_login_at,
        ui.subject_email_at_link,
        u.email AS user_email,
        p.display_name
    FROM user_identities ui
    JOIN principals p ON p.id = ui.principal_id
    JOIN users u ON u.id = ui.principal_id
    WHERE ui.auth_card_id = p_card_id
      AND ui.immutable_subject_id = p_subject;
END;
$$;

ALTER FUNCTION kb_auth.identity_lookup(UUID, TEXT) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.identity_lookup(UUID, TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.identity_lookup(UUID, TEXT) TO kanban_app;

-- Function 2: identity_record_login
CREATE OR REPLACE FUNCTION kb_auth.identity_record_login(
    p_identity_id UUID
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    UPDATE user_identities
    SET last_login_at = clock_timestamp()
    WHERE id = p_identity_id;
END;
$$;

ALTER FUNCTION kb_auth.identity_record_login(UUID) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.identity_record_login(UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.identity_record_login(UUID) TO kanban_app;

-- Function 3: identity_provision_new_user
CREATE OR REPLACE FUNCTION kb_auth.identity_provision_new_user(
    p_workspace_id UUID,
    p_card_id UUID,
    p_subject TEXT,
    p_email TEXT,
    p_display_name TEXT
)
RETURNS TABLE (
    principal_id UUID,
    identity_id UUID
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_principal_id UUID;
    v_identity_id UUID;
    v_clean_display TEXT;
    v_clean_key TEXT;
BEGIN
    IF p_workspace_id IS NULL OR p_card_id IS NULL OR p_subject IS NULL OR p_email IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'NULL_ARGUMENT';
    END IF;

    -- Zero email auto-merge invariant: never auto-attach to existing user
    IF EXISTS (
        SELECT 1 FROM users
        WHERE workspace_id = p_workspace_id
          AND lower(email) = lower(p_email)
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '23505', MESSAGE = 'IDENTITY_LINK_REQUIRED';
    END IF;

    -- Verify card subject is not already bound
    IF EXISTS (
        SELECT 1 FROM user_identities
        WHERE auth_card_id = p_card_id
          AND immutable_subject_id = p_subject
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '23505', MESSAGE = 'IDENTITY_ALREADY_LINKED';
    END IF;

    v_principal_id := uuidv7();
    v_identity_id := uuidv7();
    v_clean_display := substr(COALESCE(NULLIF(btrim(p_display_name), ''), p_email), 1, 200);
    v_clean_key := substr(lower(p_email), 1, 200);

    INSERT INTO principals (id, principal_type, workspace_id, status, display_name)
    VALUES (v_principal_id, 'USER', p_workspace_id, 'ACTIVE', v_clean_display);

    INSERT INTO objects (id, object_type, workspace_id, project_id, canonical_key, display_title, created_by_id)
    VALUES (v_principal_id, 'user'::object_kind, p_workspace_id, NULL, v_clean_key, v_clean_display, v_principal_id);

    INSERT INTO users (id, object_type, principal_type, workspace_id, email)
    VALUES (v_principal_id, 'user', 'USER', p_workspace_id, lower(p_email));

    INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type)
    VALUES (p_workspace_id, v_principal_id, 'WORKSPACE_MEMBER'::rbac_role, 'workspace');

    INSERT INTO user_identities (
        id, workspace_id, principal_id, auth_card_id, immutable_subject_id, subject_email_at_link, created_at, last_login_at
    ) VALUES (
        v_identity_id, p_workspace_id, v_principal_id, p_card_id, p_subject, p_email, clock_timestamp(), clock_timestamp()
    );

    RETURN QUERY SELECT v_principal_id, v_identity_id;
END;
$$;

ALTER FUNCTION kb_auth.identity_provision_new_user(UUID, UUID, TEXT, TEXT, TEXT) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.identity_provision_new_user(UUID, UUID, TEXT, TEXT, TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.identity_provision_new_user(UUID, UUID, TEXT, TEXT, TEXT) TO kanban_app;

-- Function 4: identity_list_for_principal
CREATE OR REPLACE FUNCTION kb_auth.identity_list_for_principal(
    p_principal UUID
)
RETURNS TABLE (
    id UUID,
    auth_card_id UUID,
    card_slug TEXT,
    card_display_name TEXT,
    provider_kind TEXT,
    immutable_subject_id TEXT,
    subject_email_at_link TEXT,
    created_at TIMESTAMPTZ,
    last_login_at TIMESTAMPTZ
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    RETURN QUERY
    SELECT
        ui.id,
        ui.auth_card_id,
        c.slug AS card_slug,
        c.display_name AS card_display_name,
        c.provider_kind,
        ui.immutable_subject_id,
        ui.subject_email_at_link,
        ui.created_at,
        ui.last_login_at
    FROM user_identities ui
    JOIN auth_provider_cards c ON c.id = ui.auth_card_id
    WHERE ui.principal_id = p_principal
    ORDER BY ui.created_at ASC;
END;
$$;

ALTER FUNCTION kb_auth.identity_list_for_principal(UUID) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.identity_list_for_principal(UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.identity_list_for_principal(UUID) TO kanban_app;

-- Function 5: identity_link_intent_create
CREATE OR REPLACE FUNCTION kb_auth.identity_link_intent_create(
    p_principal_id UUID,
    p_session_id UUID,
    p_target_card_id UUID,
    p_ttl_seconds INT DEFAULT 300,
    p_id UUID DEFAULT NULL
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_id UUID;
    v_ttl INT;
BEGIN
    IF p_principal_id IS NULL OR p_session_id IS NULL OR p_target_card_id IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'NULL_ARGUMENT';
    END IF;

    v_id := COALESCE(p_id, uuidv7());
    v_ttl := GREATEST(COALESCE(p_ttl_seconds, 300), 1);

    INSERT INTO identity_link_intents (
        id, principal_id, session_id, target_card_id, expires_at, consumed_at
    ) VALUES (
        v_id, p_principal_id, p_session_id, p_target_card_id,
        clock_timestamp() + (v_ttl::text || ' seconds')::interval,
        NULL
    );
    RETURN v_id;
END;
$$;

ALTER FUNCTION kb_auth.identity_link_intent_create(UUID, UUID, UUID, INT, UUID) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.identity_link_intent_create(UUID, UUID, UUID, INT, UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.identity_link_intent_create(UUID, UUID, UUID, INT, UUID) TO kanban_app;

-- Function 5b: identity_link_intent_get
CREATE OR REPLACE FUNCTION kb_auth.identity_link_intent_get(
    p_intent_id UUID
)
RETURNS TABLE (
    id UUID,
    principal_id UUID,
    session_id UUID,
    target_card_id UUID,
    expires_at TIMESTAMPTZ,
    consumed_at TIMESTAMPTZ
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    RETURN QUERY
    SELECT i.id, i.principal_id, i.session_id, i.target_card_id, i.expires_at, i.consumed_at
    FROM identity_link_intents i
    WHERE i.id = p_intent_id;
END;
$$;

ALTER FUNCTION kb_auth.identity_link_intent_get(UUID) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.identity_link_intent_get(UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.identity_link_intent_get(UUID) TO kanban_app;

-- Function 6: identity_link_consume_and_bind
CREATE OR REPLACE FUNCTION kb_auth.identity_link_consume_and_bind(
    p_intent_id UUID,
    p_principal_id UUID,
    p_session_id UUID,
    p_card_id UUID,
    p_subject TEXT,
    p_email TEXT DEFAULT NULL
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_intent RECORD;
    v_workspace_id UUID;
    v_identity_id UUID;
BEGIN
    IF p_intent_id IS NULL OR p_principal_id IS NULL OR p_session_id IS NULL OR p_card_id IS NULL OR p_subject IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'LINK_INTENT_INVALID';
    END IF;

    SELECT * INTO v_intent
    FROM identity_link_intents
    WHERE id = p_intent_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'LINK_INTENT_INVALID';
    END IF;

    IF v_intent.consumed_at IS NOT NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'LINK_INTENT_INVALID';
    END IF;

    IF v_intent.expires_at <= clock_timestamp() THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'LINK_INTENT_INVALID';
    END IF;

    IF v_intent.principal_id != p_principal_id OR v_intent.session_id != p_session_id OR v_intent.target_card_id != p_card_id THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'LINK_INTENT_INVALID';
    END IF;

    IF EXISTS (
        SELECT 1 FROM user_identities
        WHERE auth_card_id = p_card_id AND immutable_subject_id = p_subject
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '23505', MESSAGE = 'IDENTITY_ALREADY_LINKED';
    END IF;

    UPDATE identity_link_intents
    SET consumed_at = clock_timestamp()
    WHERE id = p_intent_id;

    SELECT workspace_id INTO v_workspace_id FROM principals WHERE id = p_principal_id;
    IF v_workspace_id IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'PRINCIPAL_NOT_FOUND';
    END IF;

    v_identity_id := uuidv7();
    INSERT INTO user_identities (
        id, workspace_id, principal_id, auth_card_id, immutable_subject_id, subject_email_at_link, created_at, last_login_at
    ) VALUES (
        v_identity_id, v_workspace_id, p_principal_id, p_card_id, p_subject, p_email, clock_timestamp(), clock_timestamp()
    );

    RETURN v_identity_id;
END;
$$;

ALTER FUNCTION kb_auth.identity_link_consume_and_bind(UUID, UUID, UUID, UUID, TEXT, TEXT) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.identity_link_consume_and_bind(UUID, UUID, UUID, UUID, TEXT, TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.identity_link_consume_and_bind(UUID, UUID, UUID, UUID, TEXT, TEXT) TO kanban_app;

-- Function 7: identity_unlink
CREATE OR REPLACE FUNCTION kb_auth.identity_unlink(
    p_principal UUID,
    p_identity_id UUID
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_ident_count INT;
    v_local_count INT;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM user_identities
        WHERE id = p_identity_id AND principal_id = p_principal
    ) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'IDENTITY_NOT_FOUND';
    END IF;

    SELECT count(*) INTO v_ident_count FROM user_identities WHERE principal_id = p_principal;
    SELECT count(*) INTO v_local_count FROM local_admin_credentials WHERE principal_id = p_principal;

    IF v_ident_count <= 1 AND v_local_count = 0 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'LAST_AUTH_METHOD';
    END IF;

    DELETE FROM user_identities WHERE id = p_identity_id AND principal_id = p_principal;
    RETURN TRUE;
END;
$$;

ALTER FUNCTION kb_auth.identity_unlink(UUID, UUID) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.identity_unlink(UUID, UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.identity_unlink(UUID, UUID) TO kanban_app;
