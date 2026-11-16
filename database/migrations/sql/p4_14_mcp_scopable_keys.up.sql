-- Phase 4 / MCP: Hierarchical Scopable Keys (Global, Workspace, Project, Personal User) + Capability/Tool Narrowing (KB-P4-14 / KANBA-106)

-- 1. Schema modifications for mcp_api_keys
ALTER TABLE mcp_api_keys
    ALTER COLUMN workspace_id DROP NOT NULL,
    ALTER COLUMN expires_at DROP NOT NULL,
    ADD COLUMN scope_tier            TEXT NOT NULL DEFAULT 'workspace'
        CHECK (scope_tier IN ('global', 'workspace', 'project')),
    ADD COLUMN owner_kind            TEXT NOT NULL DEFAULT 'service_bot'
        CHECK (owner_kind IN ('personal_user', 'service_bot')),
    ADD COLUMN project_id            UUID REFERENCES projects(id) ON DELETE CASCADE,
    ADD COLUMN allowed_workspace_ids UUID[],
    ADD COLUMN allowed_project_ids   UUID[],
    ADD COLUMN capability_mask       INTEGER NOT NULL DEFAULT 7 CHECK (capability_mask BETWEEN 1 AND 255),
    ADD COLUMN allowed_tools         TEXT[],
    ADD COLUMN disabled_tools        TEXT[] NOT NULL DEFAULT '{}'::TEXT[],
    ADD COLUMN allowed_cidrs         CIDR[];

-- Update expires_at check constraint to permit NULL when unlimited
ALTER TABLE mcp_api_keys DROP CONSTRAINT IF EXISTS mcp_api_keys_expires_at_check;
ALTER TABLE mcp_api_keys ADD CONSTRAINT mcp_api_keys_expires_at_check
    CHECK (expires_at IS NULL OR expires_at <= created_at + interval '365 days');

-- Shape constraint enforcing tier-specific foreign key rules
ALTER TABLE mcp_api_keys ADD CONSTRAINT mcp_keys_tier_shape_chk CHECK (
    (scope_tier = 'global'    AND workspace_id IS NULL AND project_id IS NULL) OR
    (scope_tier = 'workspace' AND workspace_id IS NOT NULL AND project_id IS NULL) OR
    (scope_tier = 'project'   AND workspace_id IS NOT NULL AND project_id IS NOT NULL)
);

CREATE INDEX mcp_api_keys_project_idx ON mcp_api_keys (project_id);
CREATE INDEX mcp_api_keys_scope_tier_idx ON mcp_api_keys (scope_tier);
CREATE INDEX mcp_api_keys_owner_kind_idx ON mcp_api_keys (owner_kind);

-- 2. Update Row Level Security Policies
DROP POLICY IF EXISTS mcp_api_keys_select_rls ON mcp_api_keys;
DROP POLICY IF EXISTS mcp_api_keys_insert_rls ON mcp_api_keys;
DROP POLICY IF EXISTS mcp_api_keys_update_rls ON mcp_api_keys;
DROP POLICY IF EXISTS mcp_api_keys_delete_rls ON mcp_api_keys;

CREATE POLICY mcp_api_keys_select_rls ON mcp_api_keys
    FOR SELECT USING (
        (scope_tier = 'global' AND (app_current_workspace_id() IS NULL OR app_principal_has_role(NULL, ARRAY['SERVER_ADMIN'])))
        OR
        (scope_tier = 'workspace' AND (app_current_workspace_id() IS NULL OR workspace_id = app_current_workspace_id()) AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN']))
        OR
        (scope_tier = 'project' AND (app_current_workspace_id() IS NULL OR workspace_id = app_current_workspace_id()) AND app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN']))
        OR
        (owner_kind = 'personal_user' AND principal_id = app_current_principal_id() AND (workspace_id IS NULL OR app_current_workspace_id() IS NULL OR workspace_id = app_current_workspace_id()))
    );

CREATE POLICY mcp_api_keys_insert_rls ON mcp_api_keys
    FOR INSERT WITH CHECK (
        (scope_tier = 'global' AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN']))
        OR
        (scope_tier = 'workspace' AND (app_current_workspace_id() IS NULL OR workspace_id = app_current_workspace_id()) AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN']))
        OR
        (scope_tier = 'project' AND (app_current_workspace_id() IS NULL OR workspace_id = app_current_workspace_id()) AND app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN']))
        OR
        (owner_kind = 'personal_user' AND principal_id = app_current_principal_id())
    );

CREATE POLICY mcp_api_keys_update_rls ON mcp_api_keys
    FOR UPDATE USING (
        (scope_tier = 'global' AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN']))
        OR
        (scope_tier = 'workspace' AND (app_current_workspace_id() IS NULL OR workspace_id = app_current_workspace_id()) AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN']))
        OR
        (scope_tier = 'project' AND (app_current_workspace_id() IS NULL OR workspace_id = app_current_workspace_id()) AND app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN']))
        OR
        (owner_kind = 'personal_user' AND principal_id = app_current_principal_id())
    ) WITH CHECK (
        (scope_tier = 'global' AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN']))
        OR
        (scope_tier = 'workspace' AND (app_current_workspace_id() IS NULL OR workspace_id = app_current_workspace_id()) AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN']))
        OR
        (scope_tier = 'project' AND (app_current_workspace_id() IS NULL OR workspace_id = app_current_workspace_id()) AND app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN']))
        OR
        (owner_kind = 'personal_user' AND principal_id = app_current_principal_id())
    );

CREATE POLICY mcp_api_keys_delete_rls ON mcp_api_keys
    FOR DELETE USING (
        (scope_tier = 'global' AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN']))
        OR
        (scope_tier = 'workspace' AND (app_current_workspace_id() IS NULL OR workspace_id = app_current_workspace_id()) AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN']))
        OR
        (scope_tier = 'project' AND (app_current_workspace_id() IS NULL OR workspace_id = app_current_workspace_id()) AND app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN']))
        OR
        (owner_kind = 'personal_user' AND principal_id = app_current_principal_id())
    );

-- 3. Update introspect_mcp_api_key FUNCTION to return hierarchical scope, narrowing, and tool fields
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
