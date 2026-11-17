-- Revert p4_18_oauth_mcp_scoping

DROP FUNCTION IF EXISTS kb_auth_switch_workspace(UUID, UUID);
DROP FUNCTION IF EXISTS kb_auth_create_workspace(TEXT, TEXT, UUID);
DROP FUNCTION IF EXISTS kb_auth_list_user_workspaces(UUID);
DROP FUNCTION IF EXISTS resolve_project_id_by_key_or_id(UUID, TEXT);
DROP FUNCTION IF EXISTS resolve_project_keys(UUID[]);
DROP FUNCTION IF EXISTS resolve_project_key(UUID);
DROP FUNCTION IF EXISTS get_default_workspace_id();
DROP FUNCTION IF EXISTS resolve_workspace_by_slug_or_id(TEXT);
DROP FUNCTION IF EXISTS resolve_workspace_slug(UUID);

-- Restore original introspect_mcp_api_key without workspace_slug/project_key
DROP FUNCTION IF EXISTS introspect_mcp_api_key(BYTEA);
CREATE FUNCTION introspect_mcp_api_key(p_key_sha256 BYTEA)
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
    principal_status TEXT,
    scope_tier TEXT,
    owner_kind TEXT,
    project_id UUID,
    allowed_workspace_ids UUID[],
    allowed_project_ids UUID[],
    capability_mask INTEGER,
    allowed_tools TEXT[],
    disabled_tools TEXT[],
    allowed_cidrs CIDR[]
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
        v_status,
        v_key.scope_tier,
        v_key.owner_kind,
        v_key.project_id,
        v_key.allowed_workspace_ids,
        v_key.allowed_project_ids,
        v_key.capability_mask,
        v_key.allowed_tools,
        v_key.disabled_tools,
        v_key.allowed_cidrs;
END;
$$;
GRANT EXECUTE ON FUNCTION introspect_mcp_api_key(BYTEA) TO kanban_app;

ALTER TABLE mcp_api_keys DROP COLUMN IF EXISTS label;
