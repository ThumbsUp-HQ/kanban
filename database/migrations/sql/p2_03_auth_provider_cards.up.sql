-- Phase 2 / Auth: auth_provider_cards DDL, kb_auth data boundary (KB-P2-03)

-- 1. kb_auth data boundary: role and schema
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'kb_auth_owner') THEN
        CREATE ROLE kb_auth_owner WITH NOLOGIN NOINHERIT NOBYPASSRLS;
    END IF;
    EXECUTE format('GRANT kb_auth_owner TO %I WITH SET TRUE, INHERIT TRUE', CURRENT_USER);
END $$;

GRANT USAGE, CREATE ON SCHEMA public TO kb_auth_owner;
GRANT SELECT ON TABLE role_bindings TO kb_auth_owner;
GRANT EXECUTE ON FUNCTION app_effective_principal_set() TO kb_auth_owner;

CREATE SCHEMA IF NOT EXISTS kb_auth AUTHORIZATION kb_auth_owner;
REVOKE ALL ON SCHEMA kb_auth FROM PUBLIC;
GRANT USAGE ON SCHEMA kb_auth TO kanban_app;
DO $$
BEGIN
    EXECUTE format('GRANT ALL ON SCHEMA kb_auth TO %I', CURRENT_USER);
END $$;

-- 2. DDL: auth_provider_cards
CREATE TABLE auth_provider_cards (
    id                      UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id            UUID REFERENCES workspaces(id) ON DELETE CASCADE,
    provider_kind           TEXT NOT NULL CHECK (provider_kind IN ('OIDC', 'OAUTH2', 'LDAP', 'LOCAL_ADMIN')),
    slug                    TEXT NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9][a-z0-9-]{1,46}[a-z0-9]$'),
    display_name            TEXT NOT NULL,
    button_subtext          TEXT,
    icon_preset             TEXT NOT NULL DEFAULT 'key',
    is_enabled              BOOLEAN NOT NULL DEFAULT FALSE,
    sort_rank               TEXT COLLATE "C" NOT NULL,
    auto_provision_users    BOOLEAN NOT NULL DEFAULT FALSE,
    allowed_email_domains   TEXT[] NOT NULL DEFAULT '{}',
    public_config           JSONB NOT NULL DEFAULT '{}'::jsonb,
    encrypted_secret_blob   BYTEA,          -- AES-256-GCM ciphertext (client_secret, bind_dn_password)
    wrapped_dek             BYTEA,          -- Per-card DEK wrapped by KMS / MASTER_KEK
    dek_kid                 TEXT NOT NULL DEFAULT 'kek-v1',
    last_health_status      TEXT NOT NULL DEFAULT 'UNVERIFIED',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CHECK ((encrypted_secret_blob IS NULL) = (wrapped_dek IS NULL))
);

-- Ownership and permissions
ALTER TABLE auth_provider_cards OWNER TO kb_auth_owner;
REVOKE ALL ON auth_provider_cards FROM PUBLIC, kanban_app, app_rls_reader;

-- RLS
ALTER TABLE auth_provider_cards ENABLE ROW LEVEL SECURITY;
ALTER TABLE auth_provider_cards FORCE ROW LEVEL SECURITY;
CREATE POLICY kb_auth_owner_all ON auth_provider_cards
    FOR ALL TO kb_auth_owner USING (true) WITH CHECK (true);

-- Updated at trigger
CREATE TRIGGER auth_provider_cards_set_updated_at
    BEFORE UPDATE ON auth_provider_cards
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 3. Functions in schema kb_auth (owned by kb_auth_owner, SECURITY DEFINER)

-- Function 1: card_list_enabled_public
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

-- Function 2: card_get_for_login(p_slug text)
CREATE OR REPLACE FUNCTION kb_auth.card_get_for_login(p_slug TEXT)
RETURNS SETOF auth_provider_cards
LANGUAGE plpgsql
STABLE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    RETURN QUERY
    SELECT *
    FROM auth_provider_cards c
    WHERE c.slug = p_slug
      AND c.is_enabled = TRUE;
END;
$$;

ALTER FUNCTION kb_auth.card_get_for_login(TEXT) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.card_get_for_login(TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.card_get_for_login(TEXT) TO kanban_app;

-- Function 3: card_admin_upsert(...)
CREATE OR REPLACE FUNCTION kb_auth.card_admin_upsert(
    p_id                    UUID,
    p_workspace_id          UUID,
    p_provider_kind         TEXT,
    p_slug                  TEXT,
    p_display_name          TEXT,
    p_button_subtext        TEXT,
    p_icon_preset           TEXT,
    p_is_enabled            BOOLEAN,
    p_sort_rank             TEXT,
    p_auto_provision_users  BOOLEAN,
    p_allowed_email_domains TEXT[],
    p_public_config         JSONB,
    p_encrypted_secret_blob BYTEA,
    p_wrapped_dek           BYTEA,
    p_dek_kid               TEXT,
    p_last_health_status    TEXT DEFAULT 'UNVERIFIED'
)
RETURNS UUID
LANGUAGE plpgsql
VOLATILE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_id UUID;
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

    v_id := COALESCE(p_id, uuidv7());

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
        public_config,
        encrypted_secret_blob,
        wrapped_dek,
        dek_kid,
        last_health_status
    ) VALUES (
        v_id,
        p_workspace_id,
        p_provider_kind,
        p_slug,
        p_display_name,
        p_button_subtext,
        COALESCE(p_icon_preset, 'key'),
        COALESCE(p_is_enabled, FALSE),
        p_sort_rank,
        COALESCE(p_auto_provision_users, FALSE),
        COALESCE(p_allowed_email_domains, '{}'),
        COALESCE(p_public_config, '{}'::jsonb),
        p_encrypted_secret_blob,
        p_wrapped_dek,
        COALESCE(p_dek_kid, 'kek-v1'),
        COALESCE(p_last_health_status, 'UNVERIFIED')
    )
    ON CONFLICT (id) DO UPDATE SET
        workspace_id            = EXCLUDED.workspace_id,
        provider_kind           = EXCLUDED.provider_kind,
        slug                    = EXCLUDED.slug,
        display_name            = EXCLUDED.display_name,
        button_subtext          = EXCLUDED.button_subtext,
        icon_preset             = EXCLUDED.icon_preset,
        is_enabled              = EXCLUDED.is_enabled,
        sort_rank               = EXCLUDED.sort_rank,
        auto_provision_users    = EXCLUDED.auto_provision_users,
        allowed_email_domains   = EXCLUDED.allowed_email_domains,
        public_config           = EXCLUDED.public_config,
        encrypted_secret_blob   = CASE
            WHEN EXCLUDED.encrypted_secret_blob IS NOT NULL THEN EXCLUDED.encrypted_secret_blob
            ELSE auth_provider_cards.encrypted_secret_blob
        END,
        wrapped_dek             = CASE
            WHEN EXCLUDED.wrapped_dek IS NOT NULL THEN EXCLUDED.wrapped_dek
            ELSE auth_provider_cards.wrapped_dek
        END,
        dek_kid                 = CASE
            WHEN EXCLUDED.wrapped_dek IS NOT NULL THEN EXCLUDED.dek_kid
            ELSE auth_provider_cards.dek_kid
        END,
        last_health_status      = EXCLUDED.last_health_status,
        updated_at              = clock_timestamp();

    RETURN v_id;
END;
$$;

ALTER FUNCTION kb_auth.card_admin_upsert(UUID, UUID, TEXT, TEXT, TEXT, TEXT, TEXT, BOOLEAN, TEXT, BOOLEAN, TEXT[], JSONB, BYTEA, BYTEA, TEXT, TEXT) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.card_admin_upsert(UUID, UUID, TEXT, TEXT, TEXT, TEXT, TEXT, BOOLEAN, TEXT, BOOLEAN, TEXT[], JSONB, BYTEA, BYTEA, TEXT, TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.card_admin_upsert(UUID, UUID, TEXT, TEXT, TEXT, TEXT, TEXT, BOOLEAN, TEXT, BOOLEAN, TEXT[], JSONB, BYTEA, BYTEA, TEXT, TEXT) TO kanban_app;

-- Function 4: card_admin_get(p_id uuid)
CREATE OR REPLACE FUNCTION kb_auth.card_admin_get(p_id UUID)
RETURNS SETOF auth_provider_cards
LANGUAGE plpgsql
STABLE SECURITY DEFINER
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

    RETURN QUERY
    SELECT *
    FROM auth_provider_cards c
    WHERE c.id = p_id;
END;
$$;

ALTER FUNCTION kb_auth.card_admin_get(UUID) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.card_admin_get(UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.card_admin_get(UUID) TO kanban_app;

-- Function 5: card_admin_list()
CREATE OR REPLACE FUNCTION kb_auth.card_admin_list()
RETURNS SETOF auth_provider_cards
LANGUAGE plpgsql
STABLE SECURITY DEFINER
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

    RETURN QUERY
    SELECT *
    FROM auth_provider_cards c
    ORDER BY c.sort_rank COLLATE "C" ASC, c.id ASC;
END;
$$;

ALTER FUNCTION kb_auth.card_admin_list() OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.card_admin_list() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.card_admin_list() TO kanban_app;

-- Function 6: card_rewrap(p_id uuid, p_wrapped_dek bytea, p_old_kid text, p_new_kid text)
CREATE OR REPLACE FUNCTION kb_auth.card_rewrap(
    p_id            UUID,
    p_wrapped_dek   BYTEA,
    p_old_kid       TEXT,
    p_new_kid       TEXT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
VOLATILE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_count INT;
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
    SET wrapped_dek = p_wrapped_dek,
        dek_kid     = p_new_kid,
        updated_at  = clock_timestamp()
    WHERE id = p_id
      AND dek_kid = p_old_kid;

    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count > 0;
END;
$$;

ALTER FUNCTION kb_auth.card_rewrap(UUID, BYTEA, TEXT, TEXT) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.card_rewrap(UUID, BYTEA, TEXT, TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.card_rewrap(UUID, BYTEA, TEXT, TEXT) TO kanban_app;
