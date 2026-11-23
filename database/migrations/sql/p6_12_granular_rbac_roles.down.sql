-- Revert Phase 6: Granular RBAC Roles, Role Permissions, and Multi-Role Principal Labels (KB-GRANULAR-RBAC / KAN-83)

-- 1. Restore projects_insert_rls policy from p4_21 (breaks dependency on app_principal_has_permission)
DROP POLICY IF EXISTS projects_insert_rls ON projects;
CREATE POLICY projects_insert_rls ON projects
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'WORKSPACE_MEMBER'])
    );

-- 2. Drop triggers
DROP TRIGGER IF EXISTS trg_principal_role_labels_after_sync ON principal_role_labels;
DROP TRIGGER IF EXISTS trg_principal_role_labels_governance ON principal_role_labels;
DROP TRIGGER IF EXISTS trg_rbac_roles_governance ON rbac_roles;
DROP TRIGGER IF EXISTS trg_rbac_role_permissions_after_sync ON rbac_role_permissions;
DROP TRIGGER IF EXISTS trg_rbac_role_permissions_governance ON rbac_role_permissions;

-- 3. Drop trigger functions
DROP FUNCTION IF EXISTS principal_role_labels_after_sync_trg();
DROP FUNCTION IF EXISTS principal_role_labels_governance_trg();
DROP FUNCTION IF EXISTS rbac_roles_governance_trg();
DROP FUNCTION IF EXISTS rbac_role_permissions_after_sync_trg();
DROP FUNCTION IF EXISTS rbac_role_permissions_governance_trg();

-- 4. Drop helper functions
DROP FUNCTION IF EXISTS seed_workspace_rbac_roles(UUID);
DROP FUNCTION IF EXISTS derive_role_base_capability_mask(UUID);
DROP FUNCTION IF EXISTS app_principal_has_permission(text, uuid) CASCADE;

-- 5. Restore kb_auth_create_workspace from p4_18
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
    IF EXISTS (SELECT 1 FROM workspaces WHERE slug = p_slug) THEN
        RAISE EXCEPTION USING ERRCODE = '23505', MESSAGE = 'WORKSPACE_SLUG_CONFLICT';
    END IF;

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

GRANT EXECUTE ON FUNCTION kb_auth_create_workspace(TEXT, TEXT, UUID) TO kanban_app, kanban_migrator;
ALTER FUNCTION kb_auth_create_workspace(TEXT, TEXT, UUID) OWNER TO kanban_migrator;

-- 6. Restore rebuild_effective_access_for_workspace from p1_13
CREATE OR REPLACE FUNCTION rebuild_effective_access_for_workspace(p_workspace_id uuid)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended('era:' || p_workspace_id::text, 0));

    DELETE FROM effective_resource_access WHERE workspace_id = p_workspace_id;

    WITH
    concrete_principals AS (
        SELECT id, workspace_id, principal_type
        FROM principals
        WHERE workspace_id = p_workspace_id
          AND status = 'ACTIVE'
          AND principal_type IN ('USER', 'AGENT', 'SERVICE_PRINCIPAL', 'SCRIPT_EPHEMERAL')
    ),
    q_principals AS (
        SELECT cp.id AS concrete_id, cp.id AS q_id
        FROM concrete_principals cp
        UNION ALL
        SELECT cp.id AS concrete_id, pgc.ancestor_group_id AS q_id
        FROM concrete_principals cp
        JOIN principal_group_closure pgc ON pgc.member_id = cp.id
        JOIN principals gp ON gp.id = pgc.ancestor_group_id AND gp.status = 'ACTIVE'
        WHERE gp.workspace_id = p_workspace_id
    ),
    principal_flags AS (
        SELECT
            cp.id AS concrete_id,
            cp.principal_type,
            BOOL_OR(rb.role IN ('SERVER_ADMIN', 'WORKSPACE_ADMIN')) AS is_admin,
            BOOL_OR(rb.role = 'WORKSPACE_MEMBER') AS is_ws_member
        FROM concrete_principals cp
        JOIN q_principals qp ON qp.concrete_id = cp.id
        LEFT JOIN role_bindings rb ON rb.principal_id = qp.q_id AND rb.workspace_id = p_workspace_id
        GROUP BY cp.id, cp.principal_type
    ),
    objs AS (
        SELECT
            o.id AS object_id,
            o.object_type,
            o.project_id,
            CASE
                WHEN o.object_type = 'project' THEN o.id
                ELSE o.project_id
            END AS eff_project_id,
            v.visibility AS view_visibility,
            v.owner_principal_id AS view_owner_id
        FROM objects o
        LEFT JOIN views v ON v.id = o.id
        WHERE o.workspace_id = p_workspace_id
    ),
    pairs AS (
        SELECT
            o.object_id,
            o.object_type,
            o.project_id,
            o.eff_project_id,
            o.view_visibility,
            o.view_owner_id,
            pf.concrete_id,
            pf.principal_type,
            COALESCE(pf.is_admin, FALSE) AS is_admin,
            COALESCE(pf.is_ws_member, FALSE) AS is_ws_member
        FROM objs o
        CROSS JOIN principal_flags pf
    ),
    project_rbac AS (
        SELECT
            qp.concrete_id,
            rb.project_id,
            BIT_OR(rbac_role_mask(rb.role)) AS prj_mask
        FROM q_principals qp
        JOIN role_bindings rb ON rb.principal_id = qp.q_id
        WHERE rb.workspace_id = p_workspace_id
          AND rb.scope_type = 'project'
          AND rb.project_id IS NOT NULL
        GROUP BY qp.concrete_id, rb.project_id
    ),
    direct_acls AS (
        SELECT
            ra.object_id,
            qp.concrete_id,
            BIT_OR(CASE WHEN ra.effect = 'ALLOW' THEN ra.capability_mask ELSE 0 END) AS direct_allow,
            BIT_OR(CASE WHEN ra.effect = 'DENY' THEN ra.capability_mask ELSE 0 END) AS direct_deny
        FROM resource_acl_entries ra
        JOIN q_principals qp ON qp.q_id = ra.principal_id
        WHERE ra.workspace_id = p_workspace_id
        GROUP BY ra.object_id, qp.concrete_id
    ),
    project_denys AS (
        SELECT
            ra.object_id AS prj_id,
            qp.concrete_id,
            BIT_OR(ra.capability_mask) AS prj_deny
        FROM resource_acl_entries ra
        JOIN q_principals qp ON qp.q_id = ra.principal_id
        WHERE ra.workspace_id = p_workspace_id
          AND ra.effect = 'DENY'
        GROUP BY ra.object_id, qp.concrete_id
    ),
    calculated AS (
        SELECT
            p.object_id,
            p.concrete_id AS principal_id,
            CASE
                WHEN p.is_admin THEN 255
                WHEN p.principal_type IN ('AGENT', 'SERVICE_PRINCIPAL') THEN
                    COALESCE(pr.prj_mask, 0)
                WHEN p.eff_project_id IS NOT NULL THEN
                    COALESCE(pr.prj_mask, 0) | (CASE WHEN p.is_ws_member THEN 31 ELSE 0 END)
                WHEN p.object_type = 'user' THEN
                    (CASE WHEN p.is_ws_member THEN 1 ELSE 0 END)
                WHEN p.object_type IN ('doc', 'page', 'sticky', 'view') THEN
                    CASE
                        WHEN p.object_type = 'view' AND p.view_visibility = 'private' THEN
                            (CASE WHEN p.concrete_id = p.view_owner_id THEN 255 ELSE 0 END)
                        ELSE
                            (CASE WHEN p.is_ws_member THEN 31 ELSE 0 END)
                    END
                ELSE 0
            END
            | COALESCE(da.direct_allow, 0) AS allow_mask,
            COALESCE(da.direct_deny, 0)
            | (CASE
                WHEN p.eff_project_id IS NOT NULL AND p.object_id <> p.eff_project_id THEN
                    COALESCE(pd.prj_deny, 0)
                ELSE 0
               END) AS deny_mask
        FROM pairs p
        LEFT JOIN project_rbac pr ON pr.concrete_id = p.concrete_id AND pr.project_id = p.eff_project_id
        LEFT JOIN direct_acls da ON da.object_id = p.object_id AND da.concrete_id = p.concrete_id
        LEFT JOIN project_denys pd ON pd.prj_id = p.eff_project_id AND pd.concrete_id = p.concrete_id
    )
    INSERT INTO effective_resource_access (object_id, principal_id, workspace_id, allow_mask, deny_mask)
    SELECT object_id, principal_id, p_workspace_id, allow_mask, deny_mask
    FROM calculated
    WHERE allow_mask > 0 OR deny_mask > 0;
END;
$$;

GRANT EXECUTE ON FUNCTION rebuild_effective_access_for_workspace(uuid) TO kanban_app, kanban_migrator;
ALTER FUNCTION rebuild_effective_access_for_workspace(uuid) OWNER TO kanban_migrator;

-- 7. Drop tables
DROP TABLE IF EXISTS principal_role_labels CASCADE;
DROP TABLE IF EXISTS rbac_role_permissions CASCADE;
DROP TABLE IF EXISTS rbac_roles CASCADE;
