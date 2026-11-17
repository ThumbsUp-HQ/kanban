-- Phase 4 / OAuth & MCP Scoping & RLS-Safe Helpers (KB-P4-02b, KB-P4-14, KB-P4-15, KANBA-183, KANBA-184)

-- 1. Add optional label column to mcp_api_keys if missing
ALTER TABLE mcp_api_keys ADD COLUMN IF NOT EXISTS label TEXT;

-- 2. Helper functions for workspace and project resolution under FORCE RLS
CREATE OR REPLACE FUNCTION resolve_workspace_slug(p_workspace_id UUID)
RETURNS TEXT
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
    SELECT w.slug FROM workspaces w WHERE w.id = p_workspace_id;
$$;
GRANT EXECUTE ON FUNCTION resolve_workspace_slug(UUID) TO kanban_app, app_rls_reader;

CREATE OR REPLACE FUNCTION resolve_workspace_by_slug_or_id(p_identifier TEXT)
RETURNS UUID
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_id UUID;
BEGIN
    IF p_identifier IS NULL OR btrim(p_identifier) = '' THEN
        RETURN NULL;
    END IF;
    -- Try as UUID
    BEGIN
        v_id := p_identifier::UUID;
        SELECT w.id INTO v_id FROM workspaces w WHERE w.id = v_id;
        IF FOUND THEN
            RETURN v_id;
        END IF;
    EXCEPTION WHEN invalid_text_representation THEN
        NULL;
    END;
    -- Try as slug
    SELECT w.id INTO v_id FROM workspaces w WHERE w.slug = p_identifier;
    RETURN v_id;
END;
$$;
GRANT EXECUTE ON FUNCTION resolve_workspace_by_slug_or_id(TEXT) TO kanban_app, app_rls_reader;

CREATE OR REPLACE FUNCTION get_default_workspace_id()
RETURNS UUID
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
    SELECT w.id FROM workspaces w ORDER BY w.created_at ASC LIMIT 1;
$$;
GRANT EXECUTE ON FUNCTION get_default_workspace_id() TO kanban_app, app_rls_reader;

CREATE OR REPLACE FUNCTION resolve_project_key(p_project_id UUID)
RETURNS TEXT
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
    SELECT p.identifier FROM projects p WHERE p.id = p_project_id;
$$;
GRANT EXECUTE ON FUNCTION resolve_project_key(UUID) TO kanban_app, app_rls_reader;

CREATE OR REPLACE FUNCTION resolve_project_keys(p_project_ids UUID[])
RETURNS TEXT[]
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
    SELECT coalesce(array_agg(p.identifier), ARRAY[]::TEXT[]) FROM projects p WHERE p.id = ANY(p_project_ids);
$$;
GRANT EXECUTE ON FUNCTION resolve_project_keys(UUID[]) TO kanban_app, app_rls_reader;

CREATE OR REPLACE FUNCTION resolve_project_id_by_key_or_id(p_workspace_id UUID, p_identifier TEXT)
RETURNS UUID
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_id UUID;
BEGIN
    IF p_identifier IS NULL OR btrim(p_identifier) = '' THEN
        RETURN NULL;
    END IF;
    -- Try as UUID
    BEGIN
        v_id := p_identifier::UUID;
        IF p_workspace_id IS NOT NULL THEN
            SELECT p.id INTO v_id FROM projects p WHERE p.id = v_id AND p.workspace_id = p_workspace_id;
        ELSE
            SELECT p.id INTO v_id FROM projects p WHERE p.id = v_id;
        END IF;
        IF FOUND THEN
            RETURN v_id;
        END IF;
    EXCEPTION WHEN invalid_text_representation THEN
        NULL;
    END;
    -- Try as project identifier / key
    IF p_workspace_id IS NOT NULL THEN
        SELECT p.id INTO v_id FROM projects p WHERE p.identifier = upper(p_identifier) AND p.workspace_id = p_workspace_id;
    ELSE
        SELECT p.id INTO v_id FROM projects p WHERE p.identifier = upper(p_identifier);
    END IF;
    RETURN v_id;
END;
$$;
GRANT EXECUTE ON FUNCTION resolve_project_id_by_key_or_id(UUID, TEXT) TO kanban_app, app_rls_reader;

-- 3. Update introspect_mcp_api_key to also return workspace_slug and project_key
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
    allowed_cidrs CIDR[],
    workspace_slug TEXT,
    project_key TEXT
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_now TIMESTAMPTZ := clock_timestamp();
    v_key mcp_api_keys%ROWTYPE;
    v_status TEXT;
    v_workspace_slug TEXT;
    v_project_key TEXT;
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

    IF v_key.workspace_id IS NOT NULL THEN
        SELECT w.slug INTO v_workspace_slug FROM workspaces w WHERE w.id = v_key.workspace_id;
    END IF;

    IF v_key.project_id IS NOT NULL THEN
        SELECT p.identifier INTO v_project_key FROM projects p WHERE p.id = v_key.project_id;
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
        v_key.allowed_cidrs,
        v_workspace_slug,
        v_project_key;
END;
$$;
GRANT EXECUTE ON FUNCTION introspect_mcp_api_key(BYTEA) TO kanban_app, app_rls_reader;

-- 4. RLS-safe workspace management functions in kb_auth
CREATE OR REPLACE FUNCTION kb_auth_list_user_workspaces(p_principal_id UUID)
RETURNS TABLE (
    id UUID,
    name TEXT,
    slug TEXT,
    role TEXT
)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_email TEXT;
    v_is_server_admin BOOLEAN := FALSE;
BEGIN
    SELECT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN']) INTO v_is_server_admin;
    IF v_is_server_admin THEN
        RETURN QUERY
        SELECT w.id, w.name, w.slug, 'SERVER_ADMIN'::TEXT
        FROM workspaces w
        ORDER BY w.created_at ASC;
        RETURN;
    END IF;

    SELECT u.email INTO v_email FROM users u WHERE u.id = p_principal_id;
    IF v_email IS NOT NULL THEN
        RETURN QUERY
        SELECT DISTINCT w.id, w.name, w.slug, rb.role::TEXT
        FROM workspaces w
        JOIN principals p ON p.workspace_id = w.id
        JOIN users u ON u.id = p.id
        LEFT JOIN role_bindings rb ON rb.workspace_id = w.id AND rb.principal_id = p.id
        WHERE lower(u.email) = lower(v_email) AND p.status = 'ACTIVE'
        ORDER BY w.name ASC;
    END IF;
END;
$$;
GRANT EXECUTE ON FUNCTION kb_auth_list_user_workspaces(UUID) TO kanban_app;

CREATE OR REPLACE FUNCTION kb_auth_create_workspace(
    p_name TEXT,
    p_slug TEXT,
    p_creator_principal_id UUID
)
RETURNS TABLE (
    workspace_id UUID,
    principal_id UUID
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_new_ws_id UUID := uuidv7();
    v_new_principal_id UUID := uuidv7();
    v_email TEXT;
    v_display_name TEXT;
    v_ckey TEXT;
    v_is_server_admin BOOLEAN := FALSE;
BEGIN
    -- Check slug conflict
    IF EXISTS (SELECT 1 FROM workspaces WHERE slug = p_slug) THEN
        RAISE EXCEPTION USING ERRCODE = '23505', MESSAGE = 'WORKSPACE_SLUG_CONFLICT';
    END IF;

    -- Lookup caller info
    SELECT u.email, p.display_name, o.canonical_key
    INTO v_email, v_display_name, v_ckey
    FROM users u
    JOIN principals p ON p.id = u.id
    JOIN objects o ON o.id = u.id
    WHERE u.id = p_creator_principal_id;

    IF v_email IS NULL THEN
        v_email := 'admin@local.kanban';
    END IF;
    IF v_display_name IS NULL THEN
        v_display_name := 'Workspace Admin';
    END IF;
    IF v_ckey IS NULL THEN
        v_ckey := 'usr-' || substr(replace(v_new_principal_id::text, '-', ''), 1, 12);
    END IF;

    -- 1. Create workspace
    INSERT INTO workspaces (id, slug, name) VALUES (v_new_ws_id, p_slug, p_name);

    -- 2. Register user object in new workspace
    PERFORM register_object('user'::object_kind, v_new_ws_id, NULL, v_ckey, v_display_name, v_new_principal_id, v_new_principal_id);

    -- 3. Create principal
    INSERT INTO principals (id, principal_type, workspace_id, display_name, status)
    VALUES (v_new_principal_id, 'USER', v_new_ws_id, v_display_name, 'ACTIVE');

    -- 4. Create user record
    INSERT INTO users (id, object_type, principal_type, workspace_id, email)
    VALUES (v_new_principal_id, 'user', 'USER', v_new_ws_id, v_email);

    -- 5. Bind WORKSPACE_ADMIN role
    INSERT INTO role_bindings (id, workspace_id, principal_id, role, scope_type, project_id)
    VALUES (uuidv7(), v_new_ws_id, v_new_principal_id, 'WORKSPACE_ADMIN', 'workspace', NULL);

    -- Check if caller is SERVER_ADMIN
    SELECT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN']) INTO v_is_server_admin;
    IF v_is_server_admin THEN
        INSERT INTO role_bindings (id, workspace_id, principal_id, role, scope_type, project_id)
        VALUES (uuidv7(), v_new_ws_id, v_new_principal_id, 'SERVER_ADMIN', 'server', NULL);
    END IF;

    RETURN QUERY SELECT v_new_ws_id, v_new_principal_id;
END;
$$;
GRANT EXECUTE ON FUNCTION kb_auth_create_workspace(TEXT, TEXT, UUID) TO kanban_app;

CREATE OR REPLACE FUNCTION kb_auth_switch_workspace(
    p_target_workspace_id UUID,
    p_caller_principal_id UUID
)
RETURNS TABLE (
    workspace_id UUID,
    principal_id UUID
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
#variable_conflict use_column
DECLARE
    v_target_ws workspaces%ROWTYPE;
    v_target_pid UUID;
    v_is_server_admin BOOLEAN := FALSE;
    v_email TEXT;
    v_display_name TEXT;
    v_ckey TEXT;
BEGIN
    SELECT * INTO v_target_ws FROM workspaces WHERE id = p_target_workspace_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'WORKSPACE_NOT_FOUND';
    END IF;

    SELECT EXISTS (
        SELECT 1 FROM role_bindings rb WHERE rb.principal_id = p_caller_principal_id AND rb.role = 'SERVER_ADMIN'
    ) INTO v_is_server_admin;

    -- Check direct principal match
    SELECT p.id INTO v_target_pid
    FROM principals p
    WHERE p.id = p_caller_principal_id AND p.workspace_id = p_target_workspace_id AND p.status = 'ACTIVE';

    -- Check email match
    IF v_target_pid IS NULL THEN
        SELECT u.email, p.display_name INTO v_email, v_display_name
        FROM users u JOIN principals p ON p.id = u.id
        WHERE u.id = p_caller_principal_id;

        IF v_email IS NOT NULL THEN
            SELECT p.id INTO v_target_pid
            FROM principals p
            JOIN users u ON u.id = p.id
            WHERE p.workspace_id = p_target_workspace_id AND lower(u.email) = lower(v_email) AND p.status = 'ACTIVE'
            LIMIT 1;
        END IF;
    END IF;

    -- If server admin and no principal in target workspace, auto-provision
    IF v_target_pid IS NULL AND v_is_server_admin THEN
        v_target_pid := uuidv7();
        IF v_email IS NULL THEN v_email := 'server-admin@local.kanban'; END IF;
        IF v_display_name IS NULL THEN v_display_name := 'Server Admin'; END IF;
        v_ckey := 'usr-' || substr(replace(v_target_pid::text, '-', ''), 1, 12);

        PERFORM register_object('user'::object_kind, p_target_workspace_id, NULL, v_ckey, v_display_name, v_target_pid, v_target_pid);

        INSERT INTO principals (id, principal_type, workspace_id, display_name, status)
        VALUES (v_target_pid, 'USER', p_target_workspace_id, v_display_name, 'ACTIVE');

        INSERT INTO users (id, object_type, principal_type, workspace_id, email)
        VALUES (v_target_pid, 'user', 'USER', p_target_workspace_id, v_email);

        INSERT INTO role_bindings (id, workspace_id, principal_id, role, scope_type, project_id)
        VALUES (uuidv7(), p_target_workspace_id, v_target_pid, 'SERVER_ADMIN', 'server', NULL);
    END IF;

    IF v_target_pid IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'FORBIDDEN_WORKSPACE_SWITCH';
    END IF;

    RETURN QUERY SELECT p_target_workspace_id, v_target_pid;
END;
$$;
GRANT EXECUTE ON FUNCTION kb_auth_switch_workspace(UUID, UUID) TO kanban_app;

CREATE OR REPLACE FUNCTION kb_auth_ensure_server_admin_role(
    p_workspace_id UUID,
    p_principal_id UUID
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM role_bindings
        WHERE workspace_id = p_workspace_id
          AND principal_id = p_principal_id
          AND role = 'SERVER_ADMIN'
          AND scope_type = 'server'
    ) THEN
        INSERT INTO role_bindings (id, workspace_id, principal_id, role, scope_type, project_id)
        VALUES (uuidv7(), p_workspace_id, p_principal_id, 'SERVER_ADMIN', 'server', NULL)
        ON CONFLICT DO NOTHING;
    END IF;
END;
$$;
GRANT EXECUTE ON FUNCTION kb_auth_ensure_server_admin_role(UUID, UUID) TO kanban_app;
