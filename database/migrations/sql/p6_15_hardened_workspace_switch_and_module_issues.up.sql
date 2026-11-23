-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

-- 1. Enforce security_invoker on module_issues view (KAN-334 / GSF-023):
-- Ensures tenant RLS policies on issues and issue_modules are invoked using the query caller's permissions.
CREATE OR REPLACE VIEW module_issues WITH (security_invoker = true) AS
SELECT module_id, issue_id, workspace_id, added_at, added_by_id
FROM issue_modules;

-- 2. Scoped identity uniqueness across workspaces (KAN-329 / GSF-001):
-- Scope unique constraint to (workspace_id, auth_card_id, immutable_subject_id) so verified IdP accounts
-- can be linked across workspaces without colliding globally.
ALTER TABLE user_identities DROP CONSTRAINT IF EXISTS user_identities_auth_card_id_immutable_subject_id_key;
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'user_identities_ws_card_subject_uq'
    ) THEN
        ALTER TABLE user_identities ADD CONSTRAINT user_identities_ws_card_subject_uq UNIQUE (workspace_id, auth_card_id, immutable_subject_id);
    END IF;
END $$;

-- 3. Hardened kb_auth_switch_workspace (KAN-329 / GSF-001):
-- - Eliminates unverified cross-tenant email matching for non-server-admin callers
-- - Enforces verified identity provenance via user_identities or direct principal membership
-- - Prevents unverified SERVER_ADMIN elevation by strictly checking caller's own roles
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

    -- Check if caller directly holds SERVER_ADMIN on their own principal or session
    SELECT (
        app_principal_has_role(NULL, ARRAY['SERVER_ADMIN'])
        OR EXISTS (
            SELECT 1 FROM role_bindings rb
            WHERE rb.principal_id = p_caller_principal_id AND rb.role = 'SERVER_ADMIN'
        )
    ) INTO v_is_server_admin;

    -- 1. Check direct principal match in target workspace
    SELECT p.id INTO v_target_pid
    FROM principals p
    WHERE p.id = p_caller_principal_id
      AND p.workspace_id = p_target_workspace_id
      AND p.status = 'ACTIVE';

    -- 1b. Check direct role binding in target workspace
    IF v_target_pid IS NULL THEN
        SELECT rb.principal_id INTO v_target_pid
        FROM role_bindings rb
        JOIN principals p ON p.id = rb.principal_id
        WHERE rb.workspace_id = p_target_workspace_id
          AND rb.principal_id = p_caller_principal_id
          AND p.status = 'ACTIVE'
        LIMIT 1;
    END IF;

    -- 2. Check verified identity provenance match via user_identities (same auth card + subject)
    IF v_target_pid IS NULL THEN
        SELECT ui_target.principal_id INTO v_target_pid
        FROM user_identities ui_caller
        JOIN user_identities ui_target
          ON ui_target.auth_card_id = ui_caller.auth_card_id
         AND ui_target.immutable_subject_id = ui_caller.immutable_subject_id
        JOIN principals p ON p.id = ui_target.principal_id
        WHERE ui_caller.principal_id = p_caller_principal_id
          AND p.workspace_id = p_target_workspace_id
          AND p.status = 'ACTIVE'
        LIMIT 1;
    END IF;

    -- 3. If genuine server admin and no target principal, find or auto-provision
    IF v_target_pid IS NULL AND v_is_server_admin THEN
        SELECT u.email, p.display_name INTO v_email, v_display_name
        FROM users u JOIN principals p ON p.id = u.id
        WHERE u.id = p_caller_principal_id;

        IF v_email IS NOT NULL THEN
            SELECT p.id INTO v_target_pid
            FROM principals p
            JOIN users u ON u.id = p.id
            WHERE p.workspace_id = p_target_workspace_id
              AND lower(u.email) = lower(v_email)
              AND p.status = 'ACTIVE'
            LIMIT 1;
        END IF;

        IF v_target_pid IS NULL THEN
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
    END IF;

    IF v_target_pid IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'FORBIDDEN_WORKSPACE_SWITCH';
    END IF;

    -- If caller is a verified server admin, ensure SERVER_ADMIN role exists on target principal
    IF v_is_server_admin THEN
        PERFORM kb_auth_ensure_server_admin_role(p_target_workspace_id, v_target_pid);
    END IF;

    RETURN QUERY SELECT p_target_workspace_id, v_target_pid;
END;
$$;
GRANT EXECUTE ON FUNCTION kb_auth_switch_workspace(UUID, UUID) TO kanban_app;

-- 4. Hardened kb_auth_list_user_workspaces (KAN-329 / GSF-001):
-- - Eliminates unverified email matching for workspace listing
-- - Lists direct principal workspace memberships, direct role bindings, and verified user_identities memberships
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
    v_is_server_admin BOOLEAN := FALSE;
BEGIN
    SELECT (
        app_principal_has_role(NULL, ARRAY['SERVER_ADMIN'])
        OR EXISTS (
            SELECT 1 FROM role_bindings rb
            WHERE rb.principal_id = p_principal_id AND rb.role = 'SERVER_ADMIN'
        )
    ) INTO v_is_server_admin;

    IF v_is_server_admin THEN
        RETURN QUERY
        SELECT w.id, w.name, w.slug, 'SERVER_ADMIN'::TEXT
        FROM workspaces w
        ORDER BY w.created_at ASC;
        RETURN;
    END IF;

    RETURN QUERY
    SELECT DISTINCT w.id, w.name, w.slug, COALESCE(rb.role::TEXT, 'WORKSPACE_MEMBER')
    FROM workspaces w
    JOIN principals p ON p.workspace_id = w.id
    LEFT JOIN role_bindings rb ON rb.workspace_id = w.id AND rb.principal_id = p.id
    WHERE p.status = 'ACTIVE'
      AND (
          p.id = p_principal_id
          OR rb.principal_id = p_principal_id
          OR EXISTS (
              SELECT 1
              FROM user_identities ui_caller
              JOIN user_identities ui_target
                ON ui_target.auth_card_id = ui_caller.auth_card_id
               AND ui_target.immutable_subject_id = ui_caller.immutable_subject_id
              WHERE ui_caller.principal_id = p_principal_id
                AND ui_target.principal_id = p.id
          )
      );
END;
$$;
GRANT EXECUTE ON FUNCTION kb_auth_list_user_workspaces(UUID) TO kanban_app;
