-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

CREATE TABLE oauth_clients (
    id              UUID PRIMARY KEY DEFAULT uuidv7(),
    client_id       TEXT NOT NULL UNIQUE,
    client_name     TEXT NOT NULL,
    client_type     TEXT NOT NULL DEFAULT 'public' CHECK (client_type = 'public'),
    redirect_uris   TEXT[] NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'pending_admin_approval', 'disabled')),
    workspace_id    UUID REFERENCES workspaces(id) ON DELETE CASCADE,
    created_by_id   UUID REFERENCES principals(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE oauth_grants (
    id                  UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id        UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    principal_id        UUID NOT NULL REFERENCES principals(id) ON DELETE CASCADE,
    client_id           UUID NOT NULL REFERENCES oauth_clients(id) ON DELETE CASCADE,
    surface             TEXT NOT NULL CHECK (surface IN ('agent', 'docs', 'admin')),
    scopes              TEXT[] NOT NULL,
    allowed_projects    UUID[],
    created_at          TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    revoked_at          TIMESTAMPTZ
);

CREATE TABLE oauth_authorization_codes (
    id                      UUID PRIMARY KEY DEFAULT uuidv7(),
    code_sha256             BYTEA NOT NULL UNIQUE CHECK (octet_length(code_sha256) = 32),
    grant_id                UUID REFERENCES oauth_grants(id) ON DELETE CASCADE,
    client_id               UUID NOT NULL REFERENCES oauth_clients(id) ON DELETE CASCADE,
    principal_id            UUID NOT NULL REFERENCES principals(id) ON DELETE CASCADE,
    workspace_id            UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    code_challenge          TEXT NOT NULL,
    code_challenge_method   TEXT NOT NULL CHECK (code_challenge_method = 'S256'),
    resource                TEXT NOT NULL,
    redirect_uri            TEXT NOT NULL,
    surface                 TEXT NOT NULL CHECK (surface IN ('agent', 'docs', 'admin')),
    scopes                  TEXT[] NOT NULL,
    allowed_projects        UUID[],
    created_at              TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    expires_at              TIMESTAMPTZ NOT NULL,
    consumed_at             TIMESTAMPTZ
);

CREATE TABLE oauth_refresh_tokens (
    id              UUID PRIMARY KEY DEFAULT uuidv7(),
    token_sha256    BYTEA NOT NULL UNIQUE CHECK (octet_length(token_sha256) = 32),
    grant_id        UUID NOT NULL REFERENCES oauth_grants(id) ON DELETE CASCADE,
    workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    client_id       UUID NOT NULL REFERENCES oauth_clients(id) ON DELETE CASCADE,
    principal_id    UUID NOT NULL REFERENCES principals(id) ON DELETE CASCADE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    expires_at      TIMESTAMPTZ NOT NULL,
    revoked_at      TIMESTAMPTZ
);

CREATE TABLE oauth_revoked_jtis (
    jti             UUID PRIMARY KEY,
    grant_id        UUID NOT NULL REFERENCES oauth_grants(id) ON DELETE CASCADE,
    workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    expires_at      TIMESTAMPTZ NOT NULL,
    revoked_at      TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- RLS Enforcement
ALTER TABLE oauth_clients ENABLE ROW LEVEL SECURITY;
ALTER TABLE oauth_clients FORCE ROW LEVEL SECURITY;

ALTER TABLE oauth_grants ENABLE ROW LEVEL SECURITY;
ALTER TABLE oauth_grants FORCE ROW LEVEL SECURITY;

ALTER TABLE oauth_authorization_codes ENABLE ROW LEVEL SECURITY;
ALTER TABLE oauth_authorization_codes FORCE ROW LEVEL SECURITY;

ALTER TABLE oauth_refresh_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE oauth_refresh_tokens FORCE ROW LEVEL SECURITY;

ALTER TABLE oauth_revoked_jtis ENABLE ROW LEVEL SECURITY;
ALTER TABLE oauth_revoked_jtis FORCE ROW LEVEL SECURITY;

-- Workspace Isolation Policies
CREATE POLICY oauth_clients_workspace_policy ON oauth_clients
    FOR ALL
    USING (
        workspace_id IS NULL OR
        app_current_workspace_id() IS NULL OR
        workspace_id = app_current_workspace_id()
    )
    WITH CHECK (
        workspace_id IS NULL OR
        app_current_workspace_id() IS NULL OR
        workspace_id = app_current_workspace_id()
    );

CREATE POLICY oauth_grants_workspace_policy ON oauth_grants
    FOR ALL
    USING (
        app_current_workspace_id() IS NULL OR
        workspace_id = app_current_workspace_id()
    )
    WITH CHECK (
        app_current_workspace_id() IS NULL OR
        workspace_id = app_current_workspace_id()
    );

CREATE POLICY oauth_codes_workspace_policy ON oauth_authorization_codes
    FOR ALL
    USING (
        app_current_workspace_id() IS NULL OR
        workspace_id = app_current_workspace_id()
    )
    WITH CHECK (
        app_current_workspace_id() IS NULL OR
        workspace_id = app_current_workspace_id()
    );

CREATE POLICY oauth_refresh_workspace_policy ON oauth_refresh_tokens
    FOR ALL
    USING (
        app_current_workspace_id() IS NULL OR
        workspace_id = app_current_workspace_id()
    )
    WITH CHECK (
        app_current_workspace_id() IS NULL OR
        workspace_id = app_current_workspace_id()
    );

CREATE POLICY oauth_revoked_jtis_workspace_policy ON oauth_revoked_jtis
    FOR ALL
    USING (
        app_current_workspace_id() IS NULL OR
        workspace_id = app_current_workspace_id()
    )
    WITH CHECK (
        app_current_workspace_id() IS NULL OR
        workspace_id = app_current_workspace_id()
    );

-- Table Grants
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE oauth_clients TO kanban_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE oauth_grants TO kanban_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE oauth_authorization_codes TO kanban_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE oauth_refresh_tokens TO kanban_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE oauth_revoked_jtis TO kanban_app;
GRANT SELECT ON TABLE oauth_clients, oauth_grants, oauth_authorization_codes, oauth_refresh_tokens, oauth_revoked_jtis TO app_rls_reader;

CREATE OR REPLACE FUNCTION check_oauth_token_status(
    p_grant_id UUID,
    p_jti UUID,
    p_principal_id UUID
)
RETURNS TABLE (
    grant_revoked BOOLEAN,
    jti_revoked BOOLEAN,
    principal_active BOOLEAN
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_grant_revoked BOOLEAN := TRUE;
    v_jti_revoked BOOLEAN := FALSE;
    v_principal_active BOOLEAN := FALSE;
    v_grant_revoked_at TIMESTAMPTZ;
    v_status TEXT;
BEGIN
    -- 1. Check Grant
    IF p_grant_id IS NOT NULL THEN
        SELECT revoked_at INTO v_grant_revoked_at FROM oauth_grants WHERE id = p_grant_id;
        IF FOUND AND v_grant_revoked_at IS NULL THEN
            v_grant_revoked := FALSE;
        ELSE
            v_grant_revoked := TRUE;
        END IF;
    ELSE
        v_grant_revoked := FALSE;
    END IF;

    -- 2. Check JTI
    IF p_jti IS NOT NULL THEN
        PERFORM 1 FROM oauth_revoked_jtis WHERE jti = p_jti;
        IF FOUND THEN
            v_jti_revoked := TRUE;
        END IF;
    END IF;

    -- 3. Check Principal
    IF p_principal_id IS NOT NULL THEN
        SELECT status INTO v_status FROM principals WHERE id = p_principal_id;
        IF FOUND AND v_status = 'ACTIVE' THEN
            v_principal_active := TRUE;
        END IF;
    END IF;

    RETURN QUERY SELECT v_grant_revoked, v_jti_revoked, v_principal_active;
END;
$$;

GRANT EXECUTE ON FUNCTION check_oauth_token_status(UUID, UUID, UUID) TO kanban_app, app_rls_reader;

-- Ensure activity ledger append is security definer so unauthenticated and member activity can be written
ALTER FUNCTION append_activity(uuid, uuid, object_kind, uuid, text, jsonb)
    SECURITY DEFINER SET search_path = pg_catalog, public;
