-- Phase 4 / MCP: Scoped kb_* API keys, surface binding, scopes & introspection (KB-P4-02a)

CREATE TABLE mcp_api_keys (
    id              UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    principal_id    UUID NOT NULL REFERENCES principals(id) ON DELETE RESTRICT,
    surface         TEXT NOT NULL CHECK (surface IN ('agent', 'docs', 'admin')),
    key_prefix      TEXT NOT NULL CHECK (key_prefix IN ('kb_agt_', 'kb_doc_', 'kb_adm_')),
    key_sha256      BYTEA NOT NULL UNIQUE CHECK (octet_length(key_sha256) = 32),
    display_hint    TEXT NOT NULL CHECK (char_length(display_hint) = 4), -- last 4 chars only
    scopes          TEXT[] NOT NULL,
    created_by_id   UUID NOT NULL REFERENCES principals(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    expires_at      TIMESTAMPTZ NOT NULL,
    revoked_at      TIMESTAMPTZ,
    last_used_at    TIMESTAMPTZ,
    CHECK (expires_at <= created_at + interval '365 days'),
    CHECK ((surface, key_prefix) IN (('agent','kb_agt_'),('docs','kb_doc_'),('admin','kb_adm_')))
);

CREATE INDEX mcp_api_keys_workspace_idx ON mcp_api_keys (workspace_id);
CREATE INDEX mcp_api_keys_principal_idx ON mcp_api_keys (principal_id);
CREATE INDEX mcp_api_keys_key_sha256_idx ON mcp_api_keys (key_sha256);

ALTER TABLE mcp_api_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE mcp_api_keys FORCE ROW LEVEL SECURITY;

CREATE POLICY mcp_api_keys_select_rls ON mcp_api_keys
    FOR SELECT USING (
        app_current_workspace_id() IS NULL
        OR workspace_id = app_current_workspace_id()
    );

CREATE POLICY mcp_api_keys_insert_rls ON mcp_api_keys
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
    );

CREATE POLICY mcp_api_keys_update_rls ON mcp_api_keys
    FOR UPDATE USING (
        app_current_workspace_id() IS NULL
        OR workspace_id = app_current_workspace_id()
    ) WITH CHECK (
        app_current_workspace_id() IS NULL
        OR workspace_id = app_current_workspace_id()
    );

CREATE POLICY mcp_api_keys_delete_rls ON mcp_api_keys
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
    );

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE mcp_api_keys TO kanban_app;
GRANT SELECT ON TABLE mcp_api_keys TO app_rls_reader;

CREATE OR REPLACE FUNCTION introspect_mcp_api_key(p_key_sha256 BYTEA)
RETURNS TABLE (
    id UUID,
    workspace_id UUID,
    principal_id UUID,
    surface TEXT,
    key_prefix TEXT,
    scopes TEXT[],
    created_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ,
    principal_status TEXT
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_now TIMESTAMPTZ := clock_timestamp();
    v_key mcp_api_keys%ROWTYPE;
    v_status TEXT;
BEGIN
    SELECT * INTO v_key
    FROM mcp_api_keys k
    WHERE k.key_sha256 = p_key_sha256;

    IF NOT FOUND THEN
        RETURN;
    END IF;

    SELECT status INTO v_status
    FROM principals p
    WHERE p.id = v_key.principal_id;

    -- Update last_used_at at most once per 60 seconds
    IF v_key.last_used_at IS NULL OR v_key.last_used_at < (v_now - interval '60 seconds') THEN
        UPDATE mcp_api_keys
        SET last_used_at = v_now
        WHERE mcp_api_keys.id = v_key.id
        RETURNING * INTO v_key;
    END IF;

    RETURN QUERY
    SELECT
        v_key.id,
        v_key.workspace_id,
        v_key.principal_id,
        v_key.surface,
        v_key.key_prefix,
        v_key.scopes,
        v_key.created_at,
        v_key.expires_at,
        v_key.revoked_at,
        v_key.last_used_at,
        v_status;
END;
$$;

GRANT EXECUTE ON FUNCTION introspect_mcp_api_key(BYTEA) TO kanban_app;
