-- Migration: p1_13_access_control
-- Role bindings, resource ACL entries, and materialized effective_resource_access.

-- 1. Capability bit function and RBAC role enum
CREATE OR REPLACE FUNCTION capability_bit(p_name text)
RETURNS integer
LANGUAGE plpgsql
IMMUTABLE PARALLEL SAFE AS $$
DECLARE
    v_norm text := upper(btrim(p_name));
BEGIN
    IF v_norm = 'VIEW' THEN RETURN 1;
    ELSIF v_norm = 'COMMENT' THEN RETURN 2;
    ELSIF v_norm = 'EDIT' THEN RETURN 4;
    ELSIF v_norm = 'TRANSITION' THEN RETURN 8;
    ELSIF v_norm = 'LINK' THEN RETURN 16;
    ELSIF v_norm = 'SHARE' THEN RETURN 32;
    ELSIF v_norm = 'ADMIN' THEN RETURN 64;
    ELSIF v_norm = 'DELETE' THEN RETURN 128;
    ELSE
        RAISE EXCEPTION 'INVALID_CAPABILITY_NAME: capability % is not recognized', p_name
            USING ERRCODE = 'P0001';
    END IF;
END;
$$;

CREATE TYPE rbac_role AS ENUM (
    'SERVER_ADMIN',
    'WORKSPACE_ADMIN',
    'WORKSPACE_MEMBER',
    'WORKSPACE_GUEST',
    'PROJECT_ADMIN',
    'MEMBER',
    'VIEWER'
);

CREATE OR REPLACE FUNCTION rbac_role_mask(p_role rbac_role)
RETURNS integer
LANGUAGE plpgsql
IMMUTABLE PARALLEL SAFE AS $$
BEGIN
    RETURN CASE p_role
        WHEN 'SERVER_ADMIN' THEN 255
        WHEN 'WORKSPACE_ADMIN' THEN 255
        WHEN 'PROJECT_ADMIN' THEN 255
        WHEN 'WORKSPACE_MEMBER' THEN 31
        WHEN 'MEMBER' THEN 31
        WHEN 'VIEWER' THEN 3
        WHEN 'WORKSPACE_GUEST' THEN 0
        ELSE 0
    END;
END;
$$;

-- 2. DDL: role_bindings, resource_acl_entries, effective_resource_access
CREATE TABLE role_bindings (
    id            UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id  UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    principal_id  UUID NOT NULL REFERENCES principals(id) ON DELETE CASCADE,
    role          rbac_role NOT NULL,
    scope_type    TEXT NOT NULL CHECK (scope_type IN ('server', 'workspace', 'project')),
    project_id    UUID REFERENCES projects(id) ON DELETE CASCADE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CHECK (
        (scope_type = 'server'    AND role = 'SERVER_ADMIN' AND project_id IS NULL) OR
        (scope_type = 'workspace' AND role IN ('WORKSPACE_ADMIN', 'WORKSPACE_MEMBER', 'WORKSPACE_GUEST') AND project_id IS NULL) OR
        (scope_type = 'project'   AND role IN ('PROJECT_ADMIN', 'MEMBER', 'VIEWER') AND project_id IS NOT NULL)
    ),
    UNIQUE NULLS NOT DISTINCT (workspace_id, principal_id, role, scope_type, project_id)
);

CREATE INDEX role_bindings_principal_idx ON role_bindings (principal_id, workspace_id);
CREATE INDEX role_bindings_project_idx   ON role_bindings (project_id) WHERE project_id IS NOT NULL;

CREATE TABLE resource_acl_entries (
    id               UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id     UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    object_id        UUID NOT NULL REFERENCES objects(id)    ON DELETE CASCADE,
    principal_id     UUID NOT NULL REFERENCES principals(id) ON DELETE CASCADE,
    effect           TEXT NOT NULL CHECK (effect IN ('ALLOW', 'DENY')),
    capability_mask  INTEGER NOT NULL CHECK (capability_mask BETWEEN 1 AND 255),
    created_by_id    UUID REFERENCES principals(id) ON DELETE SET NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (object_id, principal_id, effect)
);

CREATE INDEX resource_acl_object_idx ON resource_acl_entries (object_id);

CREATE TABLE effective_resource_access (
    object_id       UUID    NOT NULL REFERENCES objects(id)    ON DELETE CASCADE,
    principal_id    UUID    NOT NULL REFERENCES principals(id) ON DELETE CASCADE,
    workspace_id    UUID    NOT NULL,
    allow_mask      INTEGER NOT NULL CHECK (allow_mask BETWEEN 0 AND 255),
    deny_mask       INTEGER NOT NULL CHECK (deny_mask  BETWEEN 0 AND 255),
    effective_mask  INTEGER GENERATED ALWAYS AS (allow_mask & (~deny_mask)) STORED,
    PRIMARY KEY (object_id, principal_id)
);

CREATE INDEX era_principal_obj_idx ON effective_resource_access (principal_id, object_id);

REVOKE INSERT, UPDATE, DELETE ON effective_resource_access FROM kanban_app, app_rls_reader;

-- 3. Guards: role_bindings_guard_biu & resource_acl_guard_biu
CREATE OR REPLACE FUNCTION role_bindings_guard_biu()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_princ_ws uuid;
    v_proj_ws uuid;
BEGIN
    SELECT workspace_id INTO v_princ_ws FROM principals WHERE id = NEW.principal_id;
    IF NOT FOUND OR v_princ_ws <> NEW.workspace_id THEN
        RAISE EXCEPTION 'ROLE_BINDING_WORKSPACE_MISMATCH: principal % does not belong to workspace %', NEW.principal_id, NEW.workspace_id
            USING ERRCODE = 'P0001';
    END IF;

    IF NEW.project_id IS NOT NULL THEN
        SELECT workspace_id INTO v_proj_ws FROM projects WHERE id = NEW.project_id;
        IF NOT FOUND OR v_proj_ws <> NEW.workspace_id THEN
            RAISE EXCEPTION 'ROLE_BINDING_WORKSPACE_MISMATCH: project % does not belong to workspace %', NEW.project_id, NEW.workspace_id
                USING ERRCODE = 'P0001';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER role_bindings_guard_biu_trg
BEFORE INSERT OR UPDATE ON role_bindings
FOR EACH ROW EXECUTE FUNCTION role_bindings_guard_biu();

CREATE OR REPLACE FUNCTION resource_acl_guard_biu()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_obj_ws uuid;
    v_princ_ws uuid;
BEGIN
    SELECT workspace_id INTO v_obj_ws FROM objects WHERE id = NEW.object_id;
    IF NOT FOUND OR v_obj_ws <> NEW.workspace_id THEN
        RAISE EXCEPTION 'ACL_WORKSPACE_MISMATCH: object % does not belong to workspace %', NEW.object_id, NEW.workspace_id
            USING ERRCODE = 'P0001';
    END IF;

    SELECT workspace_id INTO v_princ_ws FROM principals WHERE id = NEW.principal_id;
    IF NOT FOUND OR v_princ_ws <> NEW.workspace_id THEN
        RAISE EXCEPTION 'ACL_WORKSPACE_MISMATCH: principal % does not belong to workspace %', NEW.principal_id, NEW.workspace_id
            USING ERRCODE = 'P0001';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER resource_acl_guard_biu_trg
BEFORE INSERT OR UPDATE ON resource_acl_entries
FOR EACH ROW EXECUTE FUNCTION resource_acl_guard_biu();

-- 4. Session Helpers: app_effective_principal_set & app_principal_has_role
CREATE OR REPLACE FUNCTION app_effective_principal_set()
RETURNS uuid[]
LANGUAGE plpgsql
STABLE PARALLEL SAFE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_p uuid;
    v_ws uuid;
    v_status text;
    v_current_ws uuid;
    v_groups uuid[];
BEGIN
    v_p := app_current_principal_id();
    IF v_p IS NULL THEN
        RETURN '{}'::uuid[];
    END IF;

    v_current_ws := app_current_workspace_id();

    SELECT workspace_id, status
    INTO v_ws, v_status
    FROM principals
    WHERE id = v_p;

    IF NOT FOUND OR v_status <> 'ACTIVE' OR (v_current_ws IS NOT NULL AND v_ws <> v_current_ws) THEN
        RETURN '{}'::uuid[];
    END IF;

    SELECT COALESCE(array_agg(pgc.ancestor_group_id ORDER BY pgc.depth), '{}'::uuid[])
    INTO v_groups
    FROM principal_group_closure pgc
    JOIN principals gp ON gp.id = pgc.ancestor_group_id AND gp.status = 'ACTIVE'
    WHERE pgc.member_id = v_p;

    RETURN ARRAY[v_p] || v_groups;
END;
$$;

CREATE OR REPLACE FUNCTION app_principal_has_role(p_project_id uuid, p_roles text[])
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

    RETURN EXISTS (
        SELECT 1
        FROM role_bindings rb
        WHERE rb.principal_id = ANY (v_pset)
          AND rb.workspace_id = v_ws
          AND rb.role::text = ANY (p_roles)
          AND (
              rb.scope_type = 'server'
              OR rb.scope_type = 'workspace'
              OR (rb.scope_type = 'project' AND rb.project_id = p_project_id AND p_project_id IS NOT NULL)
          )
    );
END;
$$;

-- 5. Materialization Engine
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

CREATE OR REPLACE FUNCTION rebuild_effective_access_for_object(p_object_id uuid)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_ws uuid;
BEGIN
    SELECT workspace_id INTO v_ws FROM objects WHERE id = p_object_id;
    IF FOUND AND v_ws IS NOT NULL THEN
        PERFORM rebuild_effective_access_for_workspace(v_ws);
    END IF;
END;
$$;

-- 6. Trigger wiring for dynamic reactivity
CREATE OR REPLACE FUNCTION role_bindings_era_refresh_aiud()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM rebuild_effective_access_for_workspace(COALESCE(NEW.workspace_id, OLD.workspace_id));
    RETURN NULL;
END;
$$;

CREATE TRIGGER role_bindings_era_refresh_trg
AFTER INSERT OR UPDATE OR DELETE ON role_bindings
FOR EACH ROW EXECUTE FUNCTION role_bindings_era_refresh_aiud();

CREATE OR REPLACE FUNCTION resource_acl_era_refresh_aiud()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM rebuild_effective_access_for_workspace(COALESCE(NEW.workspace_id, OLD.workspace_id));
    RETURN NULL;
END;
$$;

CREATE TRIGGER resource_acl_era_refresh_trg
AFTER INSERT OR UPDATE OR DELETE ON resource_acl_entries
FOR EACH ROW EXECUTE FUNCTION resource_acl_era_refresh_aiud();

CREATE OR REPLACE FUNCTION principal_group_edges_era_refresh_aiud()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM rebuild_effective_access_for_workspace(COALESCE(NEW.workspace_id, OLD.workspace_id));
    RETURN NULL;
END;
$$;

CREATE TRIGGER principal_group_edges_era_refresh_trg
AFTER INSERT OR UPDATE OR DELETE ON principal_group_edges
FOR EACH ROW EXECUTE FUNCTION principal_group_edges_era_refresh_aiud();

CREATE OR REPLACE FUNCTION principals_era_refresh_au()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.status <> OLD.status THEN
        PERFORM rebuild_effective_access_for_workspace(NEW.workspace_id);
    END IF;
    RETURN NULL;
END;
$$;

CREATE TRIGGER principals_era_refresh_trg
AFTER UPDATE OF status ON principals
FOR EACH ROW EXECUTE FUNCTION principals_era_refresh_au();

CREATE OR REPLACE FUNCTION objects_era_refresh_aiud()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM rebuild_effective_access_for_workspace(COALESCE(NEW.workspace_id, OLD.workspace_id));
    RETURN NULL;
END;
$$;

CREATE TRIGGER objects_era_refresh_trg
AFTER INSERT OR DELETE OR UPDATE OF project_id, deleted_at ON objects
FOR EACH ROW EXECUTE FUNCTION objects_era_refresh_aiud();

CREATE OR REPLACE FUNCTION views_era_refresh_au()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM rebuild_effective_access_for_workspace(COALESCE(NEW.workspace_id, OLD.workspace_id));
    RETURN NULL;
END;
$$;

CREATE TRIGGER views_era_refresh_trg
AFTER UPDATE OF visibility, owner_principal_id, project_id ON views
FOR EACH ROW EXECUTE FUNCTION views_era_refresh_au();

-- 7. Grants
GRANT EXECUTE ON FUNCTION capability_bit(text) TO kanban_app, app_rls_reader, kanban_migrator;
GRANT EXECUTE ON FUNCTION rbac_role_mask(rbac_role) TO kanban_app, app_rls_reader, kanban_migrator;
GRANT EXECUTE ON FUNCTION app_effective_principal_set() TO kanban_app, app_rls_reader, kanban_migrator;
GRANT EXECUTE ON FUNCTION app_principal_has_role(uuid, text[]) TO kanban_app, app_rls_reader, kanban_migrator;
GRANT EXECUTE ON FUNCTION rebuild_effective_access_for_workspace(uuid) TO kanban_app, kanban_migrator;
GRANT EXECUTE ON FUNCTION rebuild_effective_access_for_object(uuid) TO kanban_app, kanban_migrator;

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE role_bindings, resource_acl_entries TO kanban_app;
GRANT SELECT ON TABLE role_bindings, resource_acl_entries TO app_rls_reader;
GRANT SELECT ON TABLE effective_resource_access TO kanban_app, app_rls_reader;
