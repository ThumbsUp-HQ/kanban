-- Phase 4 / MCP: Revert Hierarchical Scopable Keys (KB-P4-14 / KANBA-106)

-- 1. Restore introspect_mcp_api_key function to original 11-column signature
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

-- 2. Restore original RLS policies
DROP POLICY IF EXISTS mcp_api_keys_select_rls ON mcp_api_keys;
DROP POLICY IF EXISTS mcp_api_keys_insert_rls ON mcp_api_keys;
DROP POLICY IF EXISTS mcp_api_keys_update_rls ON mcp_api_keys;
DROP POLICY IF EXISTS mcp_api_keys_delete_rls ON mcp_api_keys;

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

-- 3. Drop constraints, indexes, and revert columns
DROP INDEX IF EXISTS mcp_api_keys_project_idx;
DROP INDEX IF EXISTS mcp_api_keys_scope_tier_idx;
DROP INDEX IF EXISTS mcp_api_keys_owner_kind_idx;

ALTER TABLE mcp_api_keys DROP CONSTRAINT IF EXISTS mcp_keys_tier_shape_chk;
ALTER TABLE mcp_api_keys DROP CONSTRAINT IF EXISTS mcp_api_keys_expires_at_check;
ALTER TABLE mcp_api_keys ADD CONSTRAINT mcp_api_keys_expires_at_check
    CHECK (expires_at <= created_at + interval '365 days');

-- Ensure no NULL expires_at or workspace_id before enforcing NOT NULL
UPDATE mcp_api_keys SET expires_at = created_at + interval '30 days' WHERE expires_at IS NULL;
DELETE FROM mcp_api_keys WHERE workspace_id IS NULL;

ALTER TABLE mcp_api_keys
    ALTER COLUMN workspace_id SET NOT NULL,
    ALTER COLUMN expires_at SET NOT NULL,
    DROP COLUMN IF EXISTS scope_tier,
    DROP COLUMN IF EXISTS owner_kind,
    DROP COLUMN IF EXISTS project_id,
    DROP COLUMN IF EXISTS allowed_workspace_ids,
    DROP COLUMN IF EXISTS allowed_project_ids,
    DROP COLUMN IF EXISTS capability_mask,
    DROP COLUMN IF EXISTS allowed_tools,
    DROP COLUMN IF EXISTS disabled_tools,
    DROP COLUMN IF EXISTS allowed_cidrs;
