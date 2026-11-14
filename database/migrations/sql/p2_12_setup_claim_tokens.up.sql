-- Phase 2 / Auth: First-boot setup claim tokens and kb_auth functions (KB-P2-12)

-- 1. Table: setup_claim_tokens
CREATE TABLE setup_claim_tokens (
    id                        UUID PRIMARY KEY DEFAULT uuidv7(),
    token_hmac                BYTEA NOT NULL UNIQUE CHECK (octet_length(token_hmac) = 32),
    created_at                TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    expires_at                TIMESTAMPTZ NOT NULL,
    revoked_at                TIMESTAMPTZ,
    consumed_at               TIMESTAMPTZ,
    consumed_by_principal_id  UUID REFERENCES principals(id) ON DELETE SET NULL
);

CREATE INDEX setup_claim_tokens_token_hmac_idx ON setup_claim_tokens (token_hmac);

-- Ownership and permissions
ALTER TABLE setup_claim_tokens OWNER TO kb_auth_owner;
REVOKE ALL ON setup_claim_tokens FROM PUBLIC, kanban_app, app_rls_reader;
ALTER TABLE setup_claim_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE setup_claim_tokens FORCE ROW LEVEL SECURITY;
CREATE POLICY kb_auth_owner_all ON setup_claim_tokens FOR ALL TO kb_auth_owner USING (true) WITH CHECK (true);

-- Ensure kb_auth_owner can insert/update required tables during initial setup claim
GRANT SELECT, INSERT, UPDATE ON TABLE workspaces TO kb_auth_owner;
GRANT SELECT, INSERT, UPDATE ON TABLE objects TO kb_auth_owner;
GRANT SELECT, INSERT, UPDATE ON TABLE principals TO kb_auth_owner;
GRANT SELECT, INSERT, UPDATE ON TABLE users TO kb_auth_owner;
GRANT SELECT, INSERT, UPDATE ON TABLE role_bindings TO kb_auth_owner;
GRANT SELECT, INSERT, UPDATE ON TABLE auth_provider_cards TO kb_auth_owner;
GRANT SELECT, INSERT, UPDATE ON TABLE activity_records TO kb_auth_owner;
GRANT SELECT, INSERT, UPDATE ON TABLE activity_chain_heads TO kb_auth_owner;
GRANT EXECUTE ON FUNCTION append_activity(uuid, uuid, object_kind, uuid, text, jsonb) TO kb_auth_owner;

CREATE POLICY kb_auth_owner_workspaces ON workspaces FOR ALL TO kb_auth_owner USING (true) WITH CHECK (true);
CREATE POLICY kb_auth_owner_objects ON objects FOR ALL TO kb_auth_owner USING (true) WITH CHECK (true);
CREATE POLICY kb_auth_owner_principals_all ON principals FOR ALL TO kb_auth_owner USING (true) WITH CHECK (true);
CREATE POLICY kb_auth_owner_users ON users FOR ALL TO kb_auth_owner USING (true) WITH CHECK (true);
CREATE POLICY kb_auth_owner_role_bindings ON role_bindings FOR ALL TO kb_auth_owner USING (true) WITH CHECK (true);
CREATE POLICY kb_auth_owner_activity_records ON activity_records FOR ALL TO kb_auth_owner USING (true) WITH CHECK (true);
CREATE POLICY kb_auth_owner_activity_chain_heads ON activity_chain_heads FOR ALL TO kb_auth_owner USING (true) WITH CHECK (true);

-- 2. Functions in schema kb_auth (owned by kb_auth_owner, SECURITY DEFINER)

-- Function 1: setup_is_initialized()
CREATE OR REPLACE FUNCTION kb_auth.setup_is_initialized()
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
    SELECT EXISTS (SELECT 1 FROM users LIMIT 1);
$$;

ALTER FUNCTION kb_auth.setup_is_initialized() OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.setup_is_initialized() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.setup_is_initialized() TO kanban_app;

-- Function 2: setup_mint_token(p_token_hmac bytea, p_ttl_seconds int)
CREATE OR REPLACE FUNCTION kb_auth.setup_mint_token(
    p_token_hmac bytea,
    p_ttl_seconds int DEFAULT 3600
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended('kb_setup_claim', 0));
    IF EXISTS (SELECT 1 FROM users LIMIT 1) THEN
        RETURN FALSE;
    END IF;

    UPDATE setup_claim_tokens
    SET revoked_at = clock_timestamp()
    WHERE consumed_at IS NULL
      AND revoked_at IS NULL;

    INSERT INTO setup_claim_tokens (
        id,
        token_hmac,
        created_at,
        expires_at
    ) VALUES (
        uuidv7(),
        p_token_hmac,
        clock_timestamp(),
        clock_timestamp() + (p_ttl_seconds || ' seconds')::interval
    );

    RETURN TRUE;
END;
$$;

ALTER FUNCTION kb_auth.setup_mint_token(bytea, int) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.setup_mint_token(bytea, int) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.setup_mint_token(bytea, int) TO kanban_app;

-- Function 3: setup_consume_and_create_admin(...)
CREATE OR REPLACE FUNCTION kb_auth.setup_consume_and_create_admin(
    p_token_hmac bytea,
    p_username text,
    p_display_name text,
    p_email text,
    p_password_hash text
)
RETURNS TABLE(
    principal_id uuid,
    workspace_id uuid,
    local_card_id uuid
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_token_id uuid;
    v_workspace_id uuid;
    v_principal_id uuid;
    v_card_id uuid;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended('kb_setup_claim', 0));

    -- Must not already be initialized
    IF EXISTS (SELECT 1 FROM users LIMIT 1) THEN
        RETURN;
    END IF;

    -- Atomically consume the matching unconsumed, unrevoked, unexpired token
    UPDATE setup_claim_tokens
    SET consumed_at = clock_timestamp()
    WHERE token_hmac = p_token_hmac
      AND consumed_at IS NULL
      AND revoked_at IS NULL
      AND expires_at > clock_timestamp()
    RETURNING id INTO v_token_id;

    IF v_token_id IS NULL THEN
        RETURN;
    END IF;

    -- Ensure a default workspace exists
    SELECT id INTO v_workspace_id
    FROM workspaces
    ORDER BY created_at ASC
    LIMIT 1;

    IF v_workspace_id IS NULL THEN
        v_workspace_id := uuidv7();
        INSERT INTO workspaces (id, slug, name, trash_retention_days)
        VALUES (v_workspace_id, 'default', 'Default Workspace', 30);
    END IF;

    -- Ensure an enabled LOCAL_ADMIN card exists
    SELECT id INTO v_card_id
    FROM auth_provider_cards
    WHERE slug = 'local-admin';

    IF v_card_id IS NULL THEN
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
            sort_rank,
            auto_provision_users,
            allowed_email_domains,
            public_config
        ) VALUES (
            v_card_id,
            v_workspace_id,
            'LOCAL_ADMIN',
            'local-admin',
            'Local Admin',
            'Username and password',
            'key',
            TRUE,
            '0',
            FALSE,
            '{}',
            '{}'::jsonb
        );
    ELSE
        UPDATE auth_provider_cards
        SET is_enabled = TRUE
        WHERE id = v_card_id;
    END IF;

    -- Create user principal
    v_principal_id := uuidv7();

    INSERT INTO principals (
        id,
        workspace_id,
        principal_type,
        status,
        display_name,
        created_at
    ) VALUES (
        v_principal_id,
        v_workspace_id,
        'USER',
        'ACTIVE',
        p_display_name,
        clock_timestamp()
    );

    -- Register object
    INSERT INTO objects (
        id,
        object_type,
        workspace_id,
        project_id,
        canonical_key,
        display_title,
        created_by_id,
        created_at
    ) VALUES (
        v_principal_id,
        'user'::object_kind,
        v_workspace_id,
        NULL,
        p_username,
        p_display_name,
        v_principal_id,
        clock_timestamp()
    );

    -- Insert into users
    INSERT INTO users (
        id,
        object_type,
        principal_type,
        workspace_id,
        email
    ) VALUES (
        v_principal_id,
        'user'::object_kind,
        'USER',
        v_workspace_id,
        p_email
    );

    -- Insert into local_admin_credentials
    INSERT INTO local_admin_credentials (
        principal_id,
        username,
        password_hash,
        pepper_kid,
        updated_at
    ) VALUES (
        v_principal_id,
        p_username,
        p_password_hash,
        'pepper-v1',
        clock_timestamp()
    );

    -- Bind SERVER_ADMIN role
    INSERT INTO role_bindings (
        id,
        workspace_id,
        principal_id,
        role,
        scope_type,
        project_id,
        created_at
    ) VALUES (
        uuidv7(),
        v_workspace_id,
        v_principal_id,
        'SERVER_ADMIN',
        'server',
        NULL,
        clock_timestamp()
    );

    -- Link consumed token to principal
    UPDATE setup_claim_tokens
    SET consumed_by_principal_id = v_principal_id
    WHERE id = v_token_id;

    -- Append FIRST_BOOT_SETUP_CLAIMED activity record
    PERFORM append_activity(
        v_workspace_id,
        v_principal_id,
        'user'::object_kind,
        v_principal_id,
        'FIRST_BOOT_SETUP_CLAIMED',
        jsonb_build_object('username', p_username, 'email', p_email)
    );

    RETURN QUERY
    SELECT v_principal_id, v_workspace_id, v_card_id;
END;
$$;

ALTER FUNCTION kb_auth.setup_consume_and_create_admin(bytea, text, text, text, text) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.setup_consume_and_create_admin(bytea, text, text, text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.setup_consume_and_create_admin(bytea, text, text, text, text) TO kanban_app;
