-- Phase 6: Granular RBAC Roles, Role Permissions, and Multi-Role Principal Labels (KB-GRANULAR-RBAC / KAN-83)

-- 1. Create rbac_roles table
CREATE TABLE IF NOT EXISTS rbac_roles (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    slug TEXT NOT NULL,
    name TEXT NOT NULL,
    color_hex TEXT NOT NULL,
    description TEXT,
    is_system BOOLEAN NOT NULL DEFAULT FALSE,
    system_role TEXT,
    scope_tier TEXT NOT NULL DEFAULT 'workspace',
    base_capability_mask INTEGER NOT NULL DEFAULT 0,
    created_by_id UUID REFERENCES principals(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT uq_rbac_roles_workspace_slug UNIQUE (workspace_id, slug)
);

CREATE INDEX IF NOT EXISTS idx_rbac_roles_workspace ON rbac_roles (workspace_id);

ALTER TABLE rbac_roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE rbac_roles FORCE ROW LEVEL SECURITY;

CREATE POLICY rbac_roles_select_rls ON rbac_roles
    FOR SELECT USING (
        app_current_workspace_id() IS NULL
        OR workspace_id = app_current_workspace_id()
    );

CREATE POLICY rbac_roles_insert_rls ON rbac_roles
    FOR INSERT WITH CHECK (
        app_current_workspace_id() IS NULL
        OR workspace_id = app_current_workspace_id()
    );

CREATE POLICY rbac_roles_update_rls ON rbac_roles
    FOR UPDATE USING (
        app_current_workspace_id() IS NULL
        OR workspace_id = app_current_workspace_id()
    ) WITH CHECK (
        app_current_workspace_id() IS NULL
        OR workspace_id = app_current_workspace_id()
    );

CREATE POLICY rbac_roles_delete_rls ON rbac_roles
    FOR DELETE USING (
        app_current_workspace_id() IS NULL
        OR workspace_id = app_current_workspace_id()
    );

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE rbac_roles TO kanban_app;
GRANT SELECT ON TABLE rbac_roles TO app_rls_reader;
ALTER TABLE rbac_roles OWNER TO kanban_migrator;

-- 2. Create rbac_role_permissions table
CREATE TABLE IF NOT EXISTS rbac_role_permissions (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    role_id UUID NOT NULL REFERENCES rbac_roles(id) ON DELETE CASCADE,
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    permission_key TEXT NOT NULL,
    effect TEXT NOT NULL DEFAULT 'ALLOW',
    updated_by_id UUID REFERENCES principals(id) ON DELETE SET NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT uq_rbac_role_permissions_unique UNIQUE NULLS NOT DISTINCT (workspace_id, role_id, project_id, permission_key)
);

CREATE INDEX IF NOT EXISTS idx_rbac_role_perms_role ON rbac_role_permissions (role_id);
CREATE INDEX IF NOT EXISTS idx_rbac_role_perms_ws ON rbac_role_permissions (workspace_id);

ALTER TABLE rbac_role_permissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE rbac_role_permissions FORCE ROW LEVEL SECURITY;

CREATE POLICY rbac_role_permissions_select_rls ON rbac_role_permissions
    FOR SELECT USING (
        app_current_workspace_id() IS NULL
        OR workspace_id = app_current_workspace_id()
    );

CREATE POLICY rbac_role_permissions_insert_rls ON rbac_role_permissions
    FOR INSERT WITH CHECK (
        app_current_workspace_id() IS NULL
        OR workspace_id = app_current_workspace_id()
    );

CREATE POLICY rbac_role_permissions_update_rls ON rbac_role_permissions
    FOR UPDATE USING (
        app_current_workspace_id() IS NULL
        OR workspace_id = app_current_workspace_id()
    ) WITH CHECK (
        app_current_workspace_id() IS NULL
        OR workspace_id = app_current_workspace_id()
    );

CREATE POLICY rbac_role_permissions_delete_rls ON rbac_role_permissions
    FOR DELETE USING (
        app_current_workspace_id() IS NULL
        OR workspace_id = app_current_workspace_id()
    );

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE rbac_role_permissions TO kanban_app;
GRANT SELECT ON TABLE rbac_role_permissions TO app_rls_reader;
ALTER TABLE rbac_role_permissions OWNER TO kanban_migrator;

-- 3. Create principal_role_labels table
CREATE TABLE IF NOT EXISTS principal_role_labels (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    principal_id UUID NOT NULL REFERENCES principals(id) ON DELETE CASCADE,
    role_id UUID NOT NULL REFERENCES rbac_roles(id) ON DELETE CASCADE,
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    assigned_by_id UUID REFERENCES principals(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT uq_principal_role_labels_unique UNIQUE NULLS NOT DISTINCT (workspace_id, principal_id, role_id, project_id)
);

CREATE INDEX IF NOT EXISTS idx_principal_role_labels_p ON principal_role_labels (principal_id);
CREATE INDEX IF NOT EXISTS idx_principal_role_labels_ws ON principal_role_labels (workspace_id);

ALTER TABLE principal_role_labels ENABLE ROW LEVEL SECURITY;
ALTER TABLE principal_role_labels FORCE ROW LEVEL SECURITY;

CREATE POLICY principal_role_labels_select_rls ON principal_role_labels
    FOR SELECT USING (
        app_current_workspace_id() IS NULL
        OR workspace_id = app_current_workspace_id()
    );

CREATE POLICY principal_role_labels_insert_rls ON principal_role_labels
    FOR INSERT WITH CHECK (
        app_current_workspace_id() IS NULL
        OR workspace_id = app_current_workspace_id()
    );

CREATE POLICY principal_role_labels_update_rls ON principal_role_labels
    FOR UPDATE USING (
        app_current_workspace_id() IS NULL
        OR workspace_id = app_current_workspace_id()
    ) WITH CHECK (
        app_current_workspace_id() IS NULL
        OR workspace_id = app_current_workspace_id()
    );

CREATE POLICY principal_role_labels_delete_rls ON principal_role_labels
    FOR DELETE USING (
        app_current_workspace_id() IS NULL
        OR workspace_id = app_current_workspace_id()
    );

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE principal_role_labels TO kanban_app;
GRANT SELECT ON TABLE principal_role_labels TO app_rls_reader;
ALTER TABLE principal_role_labels OWNER TO kanban_migrator;

-- 4. Function: derive_role_base_capability_mask
CREATE OR REPLACE FUNCTION derive_role_base_capability_mask(p_role_id UUID)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_mask INTEGER := 0;
BEGIN
    SELECT COALESCE(BIT_OR(
        CASE
            WHEN permission_key = 'issue:view' THEN 1
            WHEN permission_key = 'issue:comment' THEN 2
            WHEN permission_key IN (
                'field:modify_summary', 'field:modify_description', 'field:modify_priority',
                'field:modify_assignees', 'field:modify_labels', 'field:modify_dates',
                'field:modify_cycle', 'field:modify_modules', 'field:modify_parent',
                'field:modify_custom_fields', 'field:attach_files'
            ) THEN 4
            WHEN permission_key IN ('issue:transition', 'field:modify_state') THEN 8
            WHEN permission_key = 'issue:link' THEN 16
            WHEN permission_key = 'issue:manage_acl' THEN 32
            WHEN permission_key LIKE 'workspace:%' THEN 64
            WHEN permission_key IN ('issue:delete', 'issue:archive') THEN 128
            ELSE 0
        END
    ), 0) INTO v_mask
    FROM rbac_role_permissions
    WHERE role_id = p_role_id AND effect = 'ALLOW';

    IF EXISTS (
        SELECT 1 FROM rbac_roles
        WHERE id = p_role_id AND (
            system_role IN ('SERVER_ADMIN', 'WORKSPACE_ADMIN')
            OR slug IN ('system-admin', 'workspace-admin')
        )
    ) THEN
        v_mask := v_mask | 64;
    END IF;

    RETURN v_mask;
END;
$$;

GRANT EXECUTE ON FUNCTION derive_role_base_capability_mask(UUID) TO kanban_app, kanban_migrator;
ALTER FUNCTION derive_role_base_capability_mask(UUID) OWNER TO kanban_migrator;

-- 5. Function: app_principal_has_permission
CREATE OR REPLACE FUNCTION app_principal_has_permission(p_permission_key text, p_project_id uuid DEFAULT NULL)
RETURNS boolean
LANGUAGE plpgsql
STABLE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_pset uuid[];
    v_ws uuid;
BEGIN
    v_pset := app_effective_principal_set();
    IF cardinality(v_pset) = 0 THEN
        RETURN FALSE;
    END IF;

    v_ws := app_current_workspace_id();
    IF v_ws IS NULL THEN
        RETURN FALSE;
    END IF;

    IF app_principal_has_role(NULL, ARRAY['SERVER_ADMIN']) THEN
        RETURN TRUE;
    END IF;

    RETURN EXISTS (
        SELECT 1
        FROM principal_role_labels prl
        JOIN rbac_role_permissions rrp ON rrp.role_id = prl.role_id
            AND rrp.workspace_id = v_ws
            AND rrp.permission_key = p_permission_key
            AND rrp.effect = 'ALLOW'
            AND (rrp.project_id IS NULL OR rrp.project_id = p_project_id)
        WHERE prl.principal_id = ANY (v_pset)
          AND prl.workspace_id = v_ws
          AND (prl.project_id IS NULL OR prl.project_id = p_project_id)
    );
END;
$$;

GRANT EXECUTE ON FUNCTION app_principal_has_permission(text, uuid) TO kanban_app, app_rls_reader, kanban_migrator;
ALTER FUNCTION app_principal_has_permission(text, uuid) OWNER TO kanban_migrator;

-- 6. Function: seed_workspace_rbac_roles
CREATE OR REPLACE FUNCTION seed_workspace_rbac_roles(p_workspace_id UUID)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_sys_admin_id UUID := uuidv7();
    v_ws_admin_id UUID := uuidv7();
    v_proj_admin_id UUID := uuidv7();
    v_users_id UUID := uuidv7();
    v_viewer_id UUID := uuidv7();
    v_guest_id UUID := uuidv7();
    v_now TIMESTAMPTZ := clock_timestamp();
    v_perm TEXT;
    v_ws_perms TEXT[] := ARRAY[
        'workspace:create', 'workspace:edit_settings', 'workspace:manage_members',
        'workspace:manage_groups', 'workspace:create_role', 'workspace:create_project',
        'workspace:manage_trash', 'workspace:manage_mcp_keys'
    ];
    v_ws_admin_perms TEXT[] := ARRAY[
        'workspace:edit_settings', 'workspace:manage_members', 'workspace:manage_groups',
        'workspace:create_role', 'workspace:create_project', 'workspace:manage_trash',
        'workspace:manage_mcp_keys'
    ];
    v_issue_perms TEXT[] := ARRAY[
        'issue:create', 'issue:view', 'issue:comment', 'issue:transition',
        'issue:move_rank', 'issue:link', 'issue:copy', 'issue:archive',
        'issue:delete', 'issue:manage_acl'
    ];
    v_user_issue_perms TEXT[] := ARRAY[
        'issue:create', 'issue:view', 'issue:comment', 'issue:transition',
        'issue:move_rank', 'issue:link', 'issue:copy'
    ];
    v_field_perms TEXT[] := ARRAY[
        'field:modify_summary', 'field:modify_description', 'field:modify_state',
        'field:modify_priority', 'field:modify_assignees', 'field:modify_labels',
        'field:modify_dates', 'field:modify_cycle', 'field:modify_modules',
        'field:modify_parent', 'field:modify_custom_fields', 'field:attach_files'
    ];
BEGIN
    -- 1. Insert built-in roles
    INSERT INTO rbac_roles (id, workspace_id, slug, name, color_hex, description, is_system, system_role, scope_tier, base_capability_mask, created_at, updated_at)
    VALUES
    (v_sys_admin_id, p_workspace_id, 'system-admin', 'System Admin', '#ef4444', 'Full administrative authority across the entire platform.', TRUE, 'SERVER_ADMIN', 'server', 255, v_now, v_now),
    (v_ws_admin_id, p_workspace_id, 'workspace-admin', 'Workspace Admin', '#f97316', 'Full administrative access within the workspace tier.', TRUE, 'WORKSPACE_ADMIN', 'workspace', 255, v_now, v_now),
    (v_proj_admin_id, p_workspace_id, 'project-admin', 'Project Admin', '#8b5cf6', 'Project-level administrative privileges.', TRUE, 'PROJECT_ADMIN', 'project', 255, v_now, v_now),
    (v_users_id, p_workspace_id, 'users', 'Users', '#3b82f6', 'Standard team member with issue create and edit capabilities.', TRUE, 'WORKSPACE_MEMBER', 'workspace', 31, v_now, v_now),
    (v_viewer_id, p_workspace_id, 'viewer', 'Viewer', '#64748b', 'Read-only access with commenting privileges.', TRUE, 'VIEWER', 'workspace', 3, v_now, v_now),
    (v_guest_id, p_workspace_id, 'guest', 'Guest', '#94a3b8', 'Restricted guest with view-only privileges.', TRUE, 'WORKSPACE_GUEST', 'workspace', 1, v_now, v_now)
    ON CONFLICT (workspace_id, slug) DO UPDATE SET
        is_system = EXCLUDED.is_system,
        system_role = EXCLUDED.system_role;

    -- Lookup actual IDs in case of pre-existing roles
    SELECT id INTO v_sys_admin_id FROM rbac_roles WHERE workspace_id = p_workspace_id AND slug = 'system-admin';
    SELECT id INTO v_ws_admin_id FROM rbac_roles WHERE workspace_id = p_workspace_id AND slug = 'workspace-admin';
    SELECT id INTO v_proj_admin_id FROM rbac_roles WHERE workspace_id = p_workspace_id AND slug = 'project-admin';
    SELECT id INTO v_users_id FROM rbac_roles WHERE workspace_id = p_workspace_id AND slug = 'users';
    SELECT id INTO v_viewer_id FROM rbac_roles WHERE workspace_id = p_workspace_id AND slug = 'viewer';
    SELECT id INTO v_guest_id FROM rbac_roles WHERE workspace_id = p_workspace_id AND slug = 'guest';

    -- 2. Seed system-admin permissions (all 30)
    FOREACH v_perm IN ARRAY (v_ws_perms || v_issue_perms || v_field_perms) LOOP
        INSERT INTO rbac_role_permissions (workspace_id, role_id, project_id, permission_key, effect, updated_at)
        VALUES (p_workspace_id, v_sys_admin_id, NULL, v_perm, 'ALLOW', v_now)
        ON CONFLICT DO NOTHING;
    END LOOP;

    -- 3. Seed workspace-admin permissions (7 workspace + 10 issue + 12 field)
    FOREACH v_perm IN ARRAY (v_ws_admin_perms || v_issue_perms || v_field_perms) LOOP
        INSERT INTO rbac_role_permissions (workspace_id, role_id, project_id, permission_key, effect, updated_at)
        VALUES (p_workspace_id, v_ws_admin_id, NULL, v_perm, 'ALLOW', v_now)
        ON CONFLICT DO NOTHING;
    END LOOP;

    -- 4. Seed project-admin permissions (10 issue + 12 field)
    FOREACH v_perm IN ARRAY (v_issue_perms || v_field_perms) LOOP
        INSERT INTO rbac_role_permissions (workspace_id, role_id, project_id, permission_key, effect, updated_at)
        VALUES (p_workspace_id, v_proj_admin_id, NULL, v_perm, 'ALLOW', v_now)
        ON CONFLICT DO NOTHING;
    END LOOP;

    -- 5. Seed users permissions (7 issue + 12 field)
    FOREACH v_perm IN ARRAY (v_user_issue_perms || v_field_perms) LOOP
        INSERT INTO rbac_role_permissions (workspace_id, role_id, project_id, permission_key, effect, updated_at)
        VALUES (p_workspace_id, v_users_id, NULL, v_perm, 'ALLOW', v_now)
        ON CONFLICT DO NOTHING;
    END LOOP;

    -- 6. Seed viewer permissions (issue:view, issue:comment)
    INSERT INTO rbac_role_permissions (workspace_id, role_id, project_id, permission_key, effect, updated_at)
    VALUES
    (p_workspace_id, v_viewer_id, NULL, 'issue:view', 'ALLOW', v_now),
    (p_workspace_id, v_viewer_id, NULL, 'issue:comment', 'ALLOW', v_now)
    ON CONFLICT DO NOTHING;

    -- 7. Seed guest permissions (issue:view)
    INSERT INTO rbac_role_permissions (workspace_id, role_id, project_id, permission_key, effect, updated_at)
    VALUES (p_workspace_id, v_guest_id, NULL, 'issue:view', 'ALLOW', v_now)
    ON CONFLICT DO NOTHING;
END;
$$;

GRANT EXECUTE ON FUNCTION seed_workspace_rbac_roles(UUID) TO kanban_app, kanban_migrator;
ALTER FUNCTION seed_workspace_rbac_roles(UUID) OWNER TO kanban_migrator;

-- Seed all existing workspaces
DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN SELECT id FROM workspaces LOOP
        PERFORM seed_workspace_rbac_roles(r.id);
    END LOOP;
END;
$$;

-- 7. Trigger on rbac_role_permissions for Governance Rules 1 & 2 + Mask Derivation
CREATE OR REPLACE FUNCTION rbac_role_permissions_governance_trg()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_perm TEXT;
    v_proj UUID;
    v_role_id UUID;
    v_ws UUID;
BEGIN
    IF CURRENT_USER IN ('postgres', 'kanban_migrator', 'kanban_test') THEN
        RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
    END IF;

    v_perm := CASE WHEN TG_OP = 'DELETE' THEN OLD.permission_key ELSE NEW.permission_key END;
    v_proj := CASE WHEN TG_OP = 'DELETE' THEN OLD.project_id ELSE NEW.project_id END;
    v_role_id := CASE WHEN TG_OP = 'DELETE' THEN OLD.role_id ELSE NEW.role_id END;
    v_ws := CASE WHEN TG_OP = 'DELETE' THEN OLD.workspace_id ELSE NEW.workspace_id END;

    -- Rule 1: WORKSPACE_ADMIN cannot modify workspace:* permissions (only SERVER_ADMIN)
    IF v_perm LIKE 'workspace:%' THEN
        IF NOT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN']) THEN
            RAISE EXCEPTION 'WORKSPACE_PERMISSION_LOCKED: only SERVER_ADMIN can modify workspace:* permissions'
                USING ERRCODE = '42501';
        END IF;
    END IF;

    -- Rule 2: Standard user cannot modify issue:* or field:* permissions
    IF v_perm NOT LIKE 'workspace:%' THEN
        IF v_proj IS NULL THEN
            IF NOT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN']) THEN
                RAISE EXCEPTION 'INSUFFICIENT_CAPABILITY: modifying workspace permissions requires workspace or server admin'
                    USING ERRCODE = '42501';
            END IF;
        ELSE
            IF NOT app_principal_has_role(v_proj, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN']) THEN
                RAISE EXCEPTION 'INSUFFICIENT_CAPABILITY: modifying project permissions requires project admin'
                    USING ERRCODE = '42501';
            END IF;
        END IF;
    END IF;

    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

CREATE TRIGGER trg_rbac_role_permissions_governance
    BEFORE INSERT OR UPDATE OR DELETE ON rbac_role_permissions
    FOR EACH ROW
    EXECUTE FUNCTION rbac_role_permissions_governance_trg();

ALTER FUNCTION rbac_role_permissions_governance_trg() OWNER TO kanban_migrator;

CREATE OR REPLACE FUNCTION rbac_role_permissions_after_sync_trg()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_role_id UUID;
    v_ws UUID;
    v_new_mask INTEGER;
BEGIN
    v_role_id := CASE WHEN TG_OP = 'DELETE' THEN OLD.role_id ELSE NEW.role_id END;
    v_ws := CASE WHEN TG_OP = 'DELETE' THEN OLD.workspace_id ELSE NEW.workspace_id END;

    v_new_mask := derive_role_base_capability_mask(v_role_id);
    UPDATE rbac_roles
    SET base_capability_mask = v_new_mask,
        updated_at = clock_timestamp()
    WHERE id = v_role_id;

    PERFORM rebuild_effective_access_for_workspace(v_ws);
    RETURN NULL;
END;
$$;

CREATE TRIGGER trg_rbac_role_permissions_after_sync
    AFTER INSERT OR UPDATE OR DELETE ON rbac_role_permissions
    FOR EACH ROW
    EXECUTE FUNCTION rbac_role_permissions_after_sync_trg();

ALTER FUNCTION rbac_role_permissions_after_sync_trg() OWNER TO kanban_migrator;

-- 8. Trigger on rbac_roles for Governance Rules 1 & 3
CREATE OR REPLACE FUNCTION rbac_roles_governance_trg()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF CURRENT_USER IN ('postgres', 'kanban_migrator', 'kanban_test') THEN
        RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
    END IF;

    -- Standard user cannot modify or delete roles
    IF NOT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN']) THEN
        RAISE EXCEPTION 'INSUFFICIENT_CAPABILITY: role creation/modification requires workspace or server admin'
            USING ERRCODE = '42501';
    END IF;

    -- Rule 1: WORKSPACE_ADMIN cannot modify/delete a role that holds workspace:* permissions
    IF (TG_OP IN ('UPDATE', 'DELETE')) THEN
        IF OLD.slug = 'system-admin' OR OLD.system_role = 'SERVER_ADMIN' OR EXISTS (
            SELECT 1 FROM rbac_role_permissions
            WHERE role_id = OLD.id AND permission_key LIKE 'workspace:%' AND effect = 'ALLOW'
        ) THEN
            IF NOT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN']) THEN
                RAISE EXCEPTION 'WORKSPACE_PERMISSION_LOCKED: only SERVER_ADMIN can modify or delete roles with workspace permissions'
                    USING ERRCODE = '42501';
            END IF;
        END IF;
    END IF;

    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

CREATE TRIGGER trg_rbac_roles_governance
    BEFORE INSERT OR UPDATE OR DELETE ON rbac_roles
    FOR EACH ROW
    EXECUTE FUNCTION rbac_roles_governance_trg();

ALTER FUNCTION rbac_roles_governance_trg() OWNER TO kanban_migrator;

-- 9. Trigger on principal_role_labels for Role Binding Sync & Governance
CREATE OR REPLACE FUNCTION principal_role_labels_governance_trg()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_role RECORD;
    v_proj UUID;
BEGIN
    IF CURRENT_USER IN ('postgres', 'kanban_migrator', 'kanban_test') THEN
        RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
    END IF;

    v_proj := CASE WHEN TG_OP = 'DELETE' THEN OLD.project_id ELSE NEW.project_id END;

    SELECT id, slug, system_role INTO v_role
    FROM rbac_roles
    WHERE id = (CASE WHEN TG_OP = 'DELETE' THEN OLD.role_id ELSE NEW.role_id END);

    -- Rule 1: Binding/unbinding a role that grants workspace permissions requires SERVER_ADMIN
    IF v_role.slug = 'system-admin' OR v_role.system_role = 'SERVER_ADMIN' OR EXISTS (
        SELECT 1 FROM rbac_role_permissions
        WHERE role_id = v_role.id AND permission_key LIKE 'workspace:%' AND effect = 'ALLOW'
    ) THEN
        IF NOT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN']) THEN
            RAISE EXCEPTION 'ROLE_ESCALATION_DENIED: binding or unbinding a role with workspace permissions requires SERVER_ADMIN'
                USING ERRCODE = '42501';
        END IF;
    END IF;

    -- Standard user cannot bind/unbind roles
    IF v_proj IS NULL THEN
        IF NOT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN']) THEN
            RAISE EXCEPTION 'INSUFFICIENT_CAPABILITY: assigning workspace role labels requires workspace or server admin'
                USING ERRCODE = '42501';
        END IF;
    ELSE
        IF NOT app_principal_has_role(v_proj, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN']) THEN
            RAISE EXCEPTION 'INSUFFICIENT_CAPABILITY: assigning project role labels requires project admin'
                USING ERRCODE = '42501';
        END IF;
    END IF;

    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

CREATE TRIGGER trg_principal_role_labels_governance
    BEFORE INSERT OR UPDATE OR DELETE ON principal_role_labels
    FOR EACH ROW
    EXECUTE FUNCTION principal_role_labels_governance_trg();

ALTER FUNCTION principal_role_labels_governance_trg() OWNER TO kanban_migrator;

CREATE OR REPLACE FUNCTION principal_role_labels_after_sync_trg()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_sys_role TEXT;
BEGIN
    IF TG_OP = 'INSERT' THEN
        SELECT system_role INTO v_sys_role FROM rbac_roles WHERE id = NEW.role_id;
        IF v_sys_role IS NOT NULL THEN
            IF v_sys_role = 'SERVER_ADMIN' THEN
                INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type, project_id)
                VALUES (NEW.workspace_id, NEW.principal_id, 'SERVER_ADMIN'::rbac_role, 'server', NULL)
                ON CONFLICT DO NOTHING;
            ELSIF v_sys_role = 'WORKSPACE_ADMIN' AND NEW.project_id IS NULL THEN
                INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type, project_id)
                VALUES (NEW.workspace_id, NEW.principal_id, 'WORKSPACE_ADMIN'::rbac_role, 'workspace', NULL)
                ON CONFLICT DO NOTHING;
            ELSIF v_sys_role = 'WORKSPACE_GUEST' AND NEW.project_id IS NULL THEN
                INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type, project_id)
                VALUES (NEW.workspace_id, NEW.principal_id, 'WORKSPACE_GUEST'::rbac_role, 'workspace', NULL)
                ON CONFLICT DO NOTHING;
            ELSIF v_sys_role = 'WORKSPACE_MEMBER' THEN
                IF NEW.project_id IS NULL THEN
                    INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type, project_id)
                    VALUES (NEW.workspace_id, NEW.principal_id, 'WORKSPACE_MEMBER'::rbac_role, 'workspace', NULL)
                    ON CONFLICT DO NOTHING;
                ELSE
                    INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type, project_id)
                    VALUES (NEW.workspace_id, NEW.principal_id, 'MEMBER'::rbac_role, 'project', NEW.project_id)
                    ON CONFLICT DO NOTHING;
                END IF;
            ELSIF v_sys_role = 'PROJECT_ADMIN' AND NEW.project_id IS NOT NULL THEN
                INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type, project_id)
                VALUES (NEW.workspace_id, NEW.principal_id, 'PROJECT_ADMIN'::rbac_role, 'project', NEW.project_id)
                ON CONFLICT DO NOTHING;
            ELSIF v_sys_role = 'VIEWER' AND NEW.project_id IS NOT NULL THEN
                INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type, project_id)
                VALUES (NEW.workspace_id, NEW.principal_id, 'VIEWER'::rbac_role, 'project', NEW.project_id)
                ON CONFLICT DO NOTHING;
            END IF;
        END IF;
        PERFORM rebuild_effective_access_for_workspace(NEW.workspace_id);
    ELSIF TG_OP = 'DELETE' THEN
        SELECT system_role INTO v_sys_role FROM rbac_roles WHERE id = OLD.role_id;
        IF v_sys_role IS NOT NULL THEN
            IF v_sys_role = 'SERVER_ADMIN' THEN
                DELETE FROM role_bindings
                WHERE workspace_id = OLD.workspace_id
                  AND principal_id = OLD.principal_id
                  AND role = 'SERVER_ADMIN'::rbac_role
                  AND scope_type = 'server';
            ELSIF v_sys_role = 'WORKSPACE_ADMIN' AND OLD.project_id IS NULL THEN
                DELETE FROM role_bindings
                WHERE workspace_id = OLD.workspace_id
                  AND principal_id = OLD.principal_id
                  AND role = 'WORKSPACE_ADMIN'::rbac_role
                  AND scope_type = 'workspace';
            ELSIF v_sys_role = 'WORKSPACE_GUEST' AND OLD.project_id IS NULL THEN
                DELETE FROM role_bindings
                WHERE workspace_id = OLD.workspace_id
                  AND principal_id = OLD.principal_id
                  AND role = 'WORKSPACE_GUEST'::rbac_role
                  AND scope_type = 'workspace';
            ELSIF v_sys_role = 'WORKSPACE_MEMBER' THEN
                IF OLD.project_id IS NULL THEN
                    DELETE FROM role_bindings
                    WHERE workspace_id = OLD.workspace_id
                      AND principal_id = OLD.principal_id
                      AND role = 'WORKSPACE_MEMBER'::rbac_role
                      AND scope_type = 'workspace';
                ELSE
                    DELETE FROM role_bindings
                    WHERE workspace_id = OLD.workspace_id
                      AND principal_id = OLD.principal_id
                      AND role = 'MEMBER'::rbac_role
                      AND scope_type = 'project'
                      AND project_id = OLD.project_id;
                END IF;
            ELSIF v_sys_role = 'PROJECT_ADMIN' AND OLD.project_id IS NOT NULL THEN
                DELETE FROM role_bindings
                WHERE workspace_id = OLD.workspace_id
                  AND principal_id = OLD.principal_id
                  AND role = 'PROJECT_ADMIN'::rbac_role
                  AND scope_type = 'project'
                  AND project_id = OLD.project_id;
            ELSIF v_sys_role = 'VIEWER' AND OLD.project_id IS NOT NULL THEN
                DELETE FROM role_bindings
                WHERE workspace_id = OLD.workspace_id
                  AND principal_id = OLD.principal_id
                  AND role = 'VIEWER'::rbac_role
                  AND scope_type = 'project'
                  AND project_id = OLD.project_id;
            END IF;
        END IF;
        PERFORM rebuild_effective_access_for_workspace(OLD.workspace_id);
    END IF;
    RETURN NULL;
END;
$$;

CREATE TRIGGER trg_principal_role_labels_after_sync
    AFTER INSERT OR DELETE ON principal_role_labels
    FOR EACH ROW
    EXECUTE FUNCTION principal_role_labels_after_sync_trg();

ALTER FUNCTION principal_role_labels_after_sync_trg() OWNER TO kanban_migrator;

-- Backfill principal_role_labels from existing role_bindings
INSERT INTO principal_role_labels (workspace_id, principal_id, role_id, project_id)
SELECT DISTINCT
    rb.workspace_id,
    rb.principal_id,
    rr.id AS role_id,
    rb.project_id
FROM role_bindings rb
JOIN rbac_roles rr ON rr.workspace_id = rb.workspace_id
    AND (
        (rb.role = 'SERVER_ADMIN' AND rr.slug = 'system-admin')
        OR (rb.role = 'WORKSPACE_ADMIN' AND rr.slug = 'workspace-admin')
        OR (rb.role = 'PROJECT_ADMIN' AND rr.slug = 'project-admin')
        OR (rb.role IN ('WORKSPACE_MEMBER', 'MEMBER') AND rr.slug = 'users')
        OR (rb.role = 'VIEWER' AND rr.slug = 'viewer')
        OR (rb.role = 'WORKSPACE_GUEST' AND rr.slug = 'guest')
    )
ON CONFLICT DO NOTHING;

-- 10. Upgrade rebuild_effective_access_for_workspace
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
            BOOL_OR(
                rb.role IN ('SERVER_ADMIN', 'WORKSPACE_ADMIN')
                OR rr.system_role IN ('SERVER_ADMIN', 'WORKSPACE_ADMIN')
                OR rr.slug IN ('system-admin', 'workspace-admin')
            ) AS is_admin,
            BOOL_OR(
                rb.role = 'WORKSPACE_MEMBER'
                OR rr.system_role = 'WORKSPACE_MEMBER'
                OR rr.slug IN ('users', 'workspace-member')
            ) AS is_ws_member,
            COALESCE(BIT_OR(CASE WHEN prl.project_id IS NULL THEN rr.base_capability_mask ELSE 0 END), 0) AS ws_label_mask
        FROM concrete_principals cp
        JOIN q_principals qp ON qp.concrete_id = cp.id
        LEFT JOIN role_bindings rb ON rb.principal_id = qp.q_id AND rb.workspace_id = p_workspace_id
        LEFT JOIN principal_role_labels prl ON prl.principal_id = qp.q_id AND prl.workspace_id = p_workspace_id
        LEFT JOIN rbac_roles rr ON rr.id = prl.role_id
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
            COALESCE(pf.is_ws_member, FALSE) AS is_ws_member,
            COALESCE(pf.ws_label_mask, 0) AS ws_label_mask
        FROM objs o
        CROSS JOIN principal_flags pf
    ),
    project_rbac AS (
        SELECT
            combined.concrete_id,
            combined.project_id,
            BIT_OR(combined.mask) AS prj_mask
        FROM (
            SELECT
                qp.concrete_id,
                rb.project_id,
                rbac_role_mask(rb.role) AS mask
            FROM q_principals qp
            JOIN role_bindings rb ON rb.principal_id = qp.q_id
            WHERE rb.workspace_id = p_workspace_id
              AND rb.scope_type = 'project'
              AND rb.project_id IS NOT NULL
            UNION ALL
            SELECT
                qp.concrete_id,
                prl.project_id,
                rr.base_capability_mask AS mask
            FROM q_principals qp
            JOIN principal_role_labels prl ON prl.principal_id = qp.q_id
            JOIN rbac_roles rr ON rr.id = prl.role_id
            WHERE prl.workspace_id = p_workspace_id
              AND prl.project_id IS NOT NULL
        ) combined
        GROUP BY combined.concrete_id, combined.project_id
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
            (
                CASE
                    WHEN p.is_admin THEN 255
                    WHEN p.principal_type IN ('AGENT', 'SERVICE_PRINCIPAL') THEN
                        COALESCE(pr.prj_mask, 0) | p.ws_label_mask
                    WHEN p.eff_project_id IS NOT NULL THEN
                        COALESCE(pr.prj_mask, 0) | (CASE WHEN p.is_ws_member THEN 31 ELSE 0 END) | p.ws_label_mask
                    WHEN p.object_type = 'user' THEN
                        (CASE WHEN p.is_ws_member THEN 1 ELSE 0 END) | (p.ws_label_mask & 1)
                    WHEN p.object_type IN ('doc', 'page', 'sticky', 'view') THEN
                        CASE
                            WHEN p.object_type = 'view' AND p.view_visibility = 'private' THEN
                                (CASE WHEN p.concrete_id = p.view_owner_id THEN 255 ELSE 0 END)
                            ELSE
                                (CASE WHEN p.is_ws_member THEN 31 ELSE 0 END) | p.ws_label_mask
                        END
                    ELSE p.ws_label_mask
                END
                | COALESCE(da.direct_allow, 0)
            ) AS allow_mask,
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

-- 11. Update projects_insert_rls policy
DROP POLICY IF EXISTS projects_insert_rls ON projects;
CREATE POLICY projects_insert_rls ON projects
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND (
            app_principal_has_permission('workspace:create_project')
            OR app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'WORKSPACE_MEMBER'])
        )
    );

-- 12. Upgrade kb_auth_create_workspace to auto-seed RBAC roles & labels
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
    v_ws_admin_role_id UUID;
    v_sys_admin_role_id UUID;
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

    -- 5. Seed RBAC roles for the new workspace
    PERFORM seed_workspace_rbac_roles(v_new_ws_id);

    -- 6. Bind WORKSPACE_ADMIN role & label
    INSERT INTO role_bindings (id, workspace_id, principal_id, role, scope_type, project_id)
    VALUES (uuidv7(), v_new_ws_id, v_new_principal_id, 'WORKSPACE_ADMIN', 'workspace', NULL);

    SELECT rbac_roles.id INTO v_ws_admin_role_id FROM rbac_roles WHERE rbac_roles.workspace_id = v_new_ws_id AND rbac_roles.slug = 'workspace-admin';
    IF v_ws_admin_role_id IS NOT NULL THEN
        INSERT INTO principal_role_labels (workspace_id, principal_id, role_id, project_id)
        VALUES (v_new_ws_id, v_new_principal_id, v_ws_admin_role_id, NULL)
        ON CONFLICT DO NOTHING;
    END IF;

    -- Check if caller is SERVER_ADMIN
    SELECT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN']) INTO v_is_server_admin;
    IF v_is_server_admin THEN
        INSERT INTO role_bindings (id, workspace_id, principal_id, role, scope_type, project_id)
        VALUES (uuidv7(), v_new_ws_id, v_new_principal_id, 'SERVER_ADMIN', 'server', NULL);

        SELECT rbac_roles.id INTO v_sys_admin_role_id FROM rbac_roles WHERE rbac_roles.workspace_id = v_new_ws_id AND rbac_roles.slug = 'system-admin';
        IF v_sys_admin_role_id IS NOT NULL THEN
            INSERT INTO principal_role_labels (workspace_id, principal_id, role_id, project_id)
            VALUES (v_new_ws_id, v_new_principal_id, v_sys_admin_role_id, NULL)
            ON CONFLICT DO NOTHING;
        END IF;
    END IF;

    PERFORM rebuild_effective_access_for_workspace(v_new_ws_id);

    RETURN QUERY SELECT v_new_ws_id, v_new_principal_id;
END;
$$;

GRANT EXECUTE ON FUNCTION kb_auth_create_workspace(TEXT, TEXT, UUID) TO kanban_app, kanban_migrator;
ALTER FUNCTION kb_auth_create_workspace(TEXT, TEXT, UUID) OWNER TO kanban_migrator;
