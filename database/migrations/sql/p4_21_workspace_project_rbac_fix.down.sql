-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

-- 1. Restore previous projects_insert_rls policy
DROP POLICY IF EXISTS projects_insert_rls ON projects;
CREATE POLICY projects_insert_rls ON projects
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
    );

-- 2. Restore previous objects_insert_rls policy
DROP POLICY IF EXISTS objects_insert_rls ON objects;
CREATE POLICY objects_insert_rls ON objects
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_current_principal_id() IS NOT NULL
        AND (
            (project_id IS NULL AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN']))
            OR (project_id IS NOT NULL AND app_has_object_capability(project_id, 4))
        )
    );

-- 3. Restore previous kb_auth_list_user_workspaces function (from p4_18)
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

-- 4. Restore previous kb_auth_switch_workspace function (from p4_18)
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
