-- Phase 5 / Database + API: remote_runner registry and mTLS enrollment tokens (KB-P5-22a, S14.2, S11.4)

CREATE TABLE remote_runner_enrollment_tokens (
    id                    UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id          UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    pool_slug             TEXT NOT NULL CHECK (pool_slug ~ '^[a-z0-9][a-z0-9-]{1,62}$'),
    token_sha256          BYTEA NOT NULL UNIQUE CHECK (octet_length(token_sha256) = 32),
    created_by_id         UUID NOT NULL REFERENCES principals(id),
    expires_at            TIMESTAMPTZ NOT NULL,
    consumed_at           TIMESTAMPTZ,
    consumed_by_runner_id UUID,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE remote_runners (
    id                    UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id          UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    pool_slug             TEXT NOT NULL CHECK (pool_slug ~ '^[a-z0-9][a-z0-9-]{1,62}$'),
    hostname              TEXT NOT NULL CHECK (char_length(btrim(hostname)) BETWEEN 1 AND 253),
    client_cert_sha256    BYTEA NOT NULL UNIQUE CHECK (octet_length(client_cert_sha256) = 32),
    cert_expires_at       TIMESTAMPTZ NOT NULL,
    capabilities_json     JSONB NOT NULL DEFAULT '{}'::jsonb,
    status                TEXT NOT NULL DEFAULT 'offline' CHECK (status IN ('online', 'offline', 'revoked')),
    last_heartbeat_at     TIMESTAMPTZ,
    revoked_at            TIMESTAMPTZ,
    revoked_by_id         UUID REFERENCES principals(id),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- Indexes
CREATE INDEX idx_remote_runner_tokens_workspace_pool ON remote_runner_enrollment_tokens (workspace_id, pool_slug);
CREATE INDEX idx_remote_runners_workspace_pool ON remote_runners (workspace_id, pool_slug, status);
CREATE INDEX idx_remote_runners_client_cert_sha256 ON remote_runners (client_cert_sha256);

-- RLS Enforcement
ALTER TABLE remote_runner_enrollment_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE remote_runner_enrollment_tokens FORCE ROW LEVEL SECURITY;

ALTER TABLE remote_runners ENABLE ROW LEVEL SECURITY;
ALTER TABLE remote_runners FORCE ROW LEVEL SECURITY;

-- Policies for remote_runner_enrollment_tokens
CREATE POLICY remote_runner_enrollment_tokens_select_rls ON remote_runner_enrollment_tokens
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
    );

CREATE POLICY remote_runner_enrollment_tokens_insert_rls ON remote_runner_enrollment_tokens
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
    );

CREATE POLICY remote_runner_enrollment_tokens_update_rls ON remote_runner_enrollment_tokens
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
    );

CREATE POLICY remote_runner_enrollment_tokens_delete_rls ON remote_runner_enrollment_tokens
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
    );

-- Policies for remote_runners
CREATE POLICY remote_runners_select_rls ON remote_runners
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
    );

CREATE POLICY remote_runners_insert_rls ON remote_runners
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
    );

CREATE POLICY remote_runners_update_rls ON remote_runners
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
    );

CREATE POLICY remote_runners_delete_rls ON remote_runners
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
    );

-- Grants
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE remote_runner_enrollment_tokens TO kanban_app;
GRANT SELECT ON TABLE remote_runner_enrollment_tokens TO app_rls_reader;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE remote_runners TO kanban_app;
GRANT SELECT ON TABLE remote_runners TO app_rls_reader;

-- Helper SECURITY DEFINER functions for unauthenticated enrollment and WSS authentication
CREATE OR REPLACE FUNCTION consume_runner_enrollment_token(
    p_token_sha256 BYTEA
)
RETURNS TABLE (
    token_id UUID,
    workspace_id UUID,
    pool_slug TEXT
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    RETURN QUERY
    UPDATE remote_runner_enrollment_tokens
    SET consumed_at = clock_timestamp()
    WHERE token_sha256 = p_token_sha256
      AND consumed_at IS NULL
      AND expires_at > clock_timestamp()
    RETURNING id, remote_runner_enrollment_tokens.workspace_id, remote_runner_enrollment_tokens.pool_slug;
END;
$$;

CREATE OR REPLACE FUNCTION register_remote_runner(
    p_runner_id UUID,
    p_workspace_id UUID,
    p_pool_slug TEXT,
    p_hostname TEXT,
    p_client_cert_sha256 BYTEA,
    p_cert_expires_at TIMESTAMPTZ,
    p_capabilities_json JSONB,
    p_token_id UUID
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    INSERT INTO remote_runners (
        id, workspace_id, pool_slug, hostname,
        client_cert_sha256, cert_expires_at, capabilities_json, status
    ) VALUES (
        p_runner_id, p_workspace_id, p_pool_slug, p_hostname,
        p_client_cert_sha256, p_cert_expires_at, COALESCE(p_capabilities_json, '{}'::jsonb), 'offline'
    );

    UPDATE remote_runner_enrollment_tokens
    SET consumed_by_runner_id = p_runner_id
    WHERE id = p_token_id;
END;
$$;

CREATE OR REPLACE FUNCTION enroll_remote_runner(
    p_token_sha256 BYTEA,
    p_hostname TEXT,
    p_client_cert_sha256 BYTEA,
    p_cert_expires_at TIMESTAMPTZ,
    p_capabilities_json JSONB
)
RETURNS TABLE (
    runner_id UUID,
    workspace_id UUID,
    pool_slug TEXT
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_token_id UUID;
    v_workspace_id UUID;
    v_pool_slug TEXT;
    v_runner_id UUID;
BEGIN
    -- Atomically consume token
    UPDATE remote_runner_enrollment_tokens
    SET consumed_at = clock_timestamp()
    WHERE token_sha256 = p_token_sha256
      AND consumed_at IS NULL
      AND expires_at > clock_timestamp()
    RETURNING id, remote_runner_enrollment_tokens.workspace_id, remote_runner_enrollment_tokens.pool_slug
    INTO v_token_id, v_workspace_id, v_pool_slug;

    IF v_token_id IS NULL THEN
        RETURN;
    END IF;

    -- Insert new runner record
    INSERT INTO remote_runners (
        workspace_id,
        pool_slug,
        hostname,
        client_cert_sha256,
        cert_expires_at,
        capabilities_json,
        status
    ) VALUES (
        v_workspace_id,
        v_pool_slug,
        p_hostname,
        p_client_cert_sha256,
        p_cert_expires_at,
        COALESCE(p_capabilities_json, '{}'::jsonb),
        'offline'
    )
    RETURNING id INTO v_runner_id;

    -- Record runner on consumed token
    UPDATE remote_runner_enrollment_tokens
    SET consumed_by_runner_id = v_runner_id
    WHERE id = v_token_id;

    runner_id := v_runner_id;
    workspace_id := v_workspace_id;
    pool_slug := v_pool_slug;
    RETURN NEXT;
END;
$$;

CREATE OR REPLACE FUNCTION get_runner_by_cert_sha256(
    p_cert_sha256 BYTEA
)
RETURNS TABLE (
    runner_id UUID,
    workspace_id UUID,
    pool_slug TEXT,
    hostname TEXT,
    status TEXT,
    cert_expires_at TIMESTAMPTZ,
    capabilities_json JSONB
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    RETURN QUERY
    SELECT r.id, r.workspace_id, r.pool_slug, r.hostname, r.status, r.cert_expires_at, r.capabilities_json
    FROM remote_runners r
    WHERE r.client_cert_sha256 = p_cert_sha256;
END;
$$;

CREATE OR REPLACE FUNCTION touch_runner_heartbeat(
    p_runner_id UUID,
    p_status TEXT DEFAULT NULL
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    UPDATE remote_runners
    SET last_heartbeat_at = clock_timestamp(),
        status = CASE
            WHEN status = 'revoked' THEN 'revoked'
            WHEN p_status IS NOT NULL THEN p_status
            ELSE status
        END
    WHERE id = p_runner_id;
END;
$$;

GRANT EXECUTE ON FUNCTION consume_runner_enrollment_token(BYTEA) TO kanban_app;
GRANT EXECUTE ON FUNCTION register_remote_runner(UUID, UUID, TEXT, TEXT, BYTEA, TIMESTAMPTZ, JSONB, UUID) TO kanban_app;
GRANT EXECUTE ON FUNCTION enroll_remote_runner(BYTEA, TEXT, BYTEA, TIMESTAMPTZ, JSONB) TO kanban_app;
GRANT EXECUTE ON FUNCTION get_runner_by_cert_sha256(BYTEA) TO kanban_app;
GRANT EXECUTE ON FUNCTION touch_runner_heartbeat(UUID, TEXT) TO kanban_app;
