-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

-- KB-SEC-05: Enforce CredentialBoundary in PostgreSQL FORCE RLS Session GUCs

-- 1. Credential Boundary Session GUC Helper Functions
CREATE OR REPLACE FUNCTION app_credential_workspaces()
RETURNS uuid[]
LANGUAGE sql
STABLE PARALLEL SAFE
AS $$
    SELECT CASE
        WHEN NULLIF(current_setting('app.credential_workspaces', true), '') IS NULL THEN NULL
        ELSE string_to_array(current_setting('app.credential_workspaces', true), ',')::uuid[]
    END;
$$;

CREATE OR REPLACE FUNCTION app_credential_projects()
RETURNS uuid[]
LANGUAGE sql
STABLE PARALLEL SAFE
AS $$
    SELECT CASE
        WHEN NULLIF(current_setting('app.credential_projects', true), '') IS NULL THEN NULL
        ELSE string_to_array(current_setting('app.credential_projects', true), ',')::uuid[]
    END;
$$;

CREATE OR REPLACE FUNCTION app_credential_capability_mask()
RETURNS integer
LANGUAGE sql
STABLE PARALLEL SAFE
AS $$
    SELECT NULLIF(current_setting('app.credential_capability_mask', true), '')::integer;
$$;

GRANT EXECUTE ON FUNCTION app_credential_workspaces() TO kanban_app, app_rls_reader, kanban_migrator;
GRANT EXECUTE ON FUNCTION app_credential_projects() TO kanban_app, app_rls_reader, kanban_migrator;
GRANT EXECUTE ON FUNCTION app_credential_capability_mask() TO kanban_app, app_rls_reader, kanban_migrator;

ALTER FUNCTION app_credential_workspaces() OWNER TO kanban_migrator;
ALTER FUNCTION app_credential_projects() OWNER TO kanban_migrator;
ALTER FUNCTION app_credential_capability_mask() OWNER TO kanban_migrator;

-- 2. Upgrade app_current_workspace_id() to enforce app.credential_workspaces allowlist
CREATE OR REPLACE FUNCTION app_current_workspace_id()
RETURNS uuid
LANGUAGE sql
STABLE PARALLEL SAFE
AS $$
    SELECT CASE
        WHEN NULLIF(current_setting('app.workspace_id', true), '') IS NULL THEN NULL
        WHEN NULLIF(current_setting('app.credential_workspaces', true), '') IS NOT NULL
             AND NOT (NULLIF(current_setting('app.workspace_id', true), '')::uuid = ANY(string_to_array(current_setting('app.credential_workspaces', true), ',')::uuid[]))
             THEN NULL
        ELSE NULLIF(current_setting('app.workspace_id', true), '')::uuid
    END;
$$;

GRANT EXECUTE ON FUNCTION app_current_workspace_id() TO kanban_app, app_rls_reader, kanban_migrator;

-- 3. Upgrade app_principal_has_role to enforce app.credential_projects allowlist
CREATE OR REPLACE FUNCTION app_principal_has_role(p_project_id uuid, p_roles text[])
RETURNS boolean
LANGUAGE plpgsql
STABLE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_pset uuid[];
    v_ws uuid;
    v_cred_projs_str text;
BEGIN
    v_pset := app_effective_principal_set();
    IF cardinality(v_pset) = 0 THEN
        RETURN FALSE;
    END IF;

    v_ws := app_current_workspace_id();
    IF v_ws IS NULL THEN
        RETURN FALSE;
    END IF;

    IF p_project_id IS NOT NULL THEN
        v_cred_projs_str := NULLIF(current_setting('app.credential_projects', true), '');
        IF v_cred_projs_str IS NOT NULL THEN
            IF NOT (p_project_id = ANY (string_to_array(v_cred_projs_str, ',')::uuid[])) THEN
                RETURN FALSE;
            END IF;
        END IF;
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

GRANT EXECUTE ON FUNCTION app_principal_has_role(uuid, text[]) TO kanban_app, app_rls_reader, kanban_migrator;

-- 4. Upgrade app_has_object_capability to enforce capability_mask and project allowlist
CREATE OR REPLACE FUNCTION app_has_object_capability(p_object_id uuid, p_mask integer)
RETURNS boolean
LANGUAGE plpgsql
STABLE PARALLEL SAFE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_human_pset uuid[];
    v_agent_pset uuid[];
    v_agent_id_str text;
    v_eph_proj text;
    v_obj_proj uuid;
    v_obj_type text;
    v_cred_mask_str text;
    v_cred_mask integer;
    v_cred_projs_str text;
    v_cur_ws uuid;
BEGIN
    -- 1. Capability mask check when app.credential_capability_mask is set
    v_cred_mask_str := NULLIF(current_setting('app.credential_capability_mask', true), '');
    IF v_cred_mask_str IS NOT NULL THEN
        v_cred_mask := v_cred_mask_str::integer;
        IF (v_cred_mask & p_mask) <> p_mask THEN
            RETURN FALSE;
        END IF;
    END IF;

    -- 2. Workspace check (fail closed if app_current_workspace_id() is null or outside credential_workspaces)
    v_cur_ws := app_current_workspace_id();
    IF v_cur_ws IS NULL THEN
        RETURN FALSE;
    END IF;

    -- 3. Ephemeral project pin check when app.ephemeral_project_id is set
    v_eph_proj := NULLIF(current_setting('app.ephemeral_project_id', true), '');
    IF v_eph_proj IS NOT NULL THEN
        SELECT project_id, object_type::text INTO v_obj_proj, v_obj_type FROM objects WHERE id = p_object_id;
        IF NOT FOUND THEN
            RETURN FALSE;
        END IF;
        IF v_obj_type = 'project' THEN
            IF p_object_id <> v_eph_proj::uuid THEN
                RETURN FALSE;
            END IF;
        ELSIF v_obj_proj IS NULL OR v_obj_proj <> v_eph_proj::uuid THEN
            RETURN FALSE;
        END IF;
    END IF;

    -- 4. Credential project allowlist check when app.credential_projects is set
    v_cred_projs_str := NULLIF(current_setting('app.credential_projects', true), '');
    IF v_cred_projs_str IS NOT NULL THEN
        IF v_obj_proj IS NULL AND v_obj_type IS NULL THEN
            SELECT project_id, object_type::text INTO v_obj_proj, v_obj_type FROM objects WHERE id = p_object_id;
            IF NOT FOUND THEN
                RETURN FALSE;
            END IF;
        END IF;
        IF v_obj_type = 'project' THEN
            IF NOT (p_object_id = ANY (string_to_array(v_cred_projs_str, ',')::uuid[])) THEN
                RETURN FALSE;
            END IF;
        ELSIF v_obj_proj IS NOT NULL THEN
            IF NOT (v_obj_proj = ANY (string_to_array(v_cred_projs_str, ',')::uuid[])) THEN
                RETURN FALSE;
            END IF;
        END IF;
    END IF;

    -- 5. Human principal capability check
    v_human_pset := app_effective_principal_set();
    IF cardinality(v_human_pset) = 0 THEN
        RETURN FALSE;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM effective_resource_access era
        WHERE era.object_id = p_object_id
          AND era.workspace_id = v_cur_ws
          AND era.principal_id = ANY (v_human_pset)
          AND (era.allow_mask & p_mask) = p_mask
          AND (era.deny_mask  & p_mask) = 0
    ) THEN
        RETURN FALSE;
    END IF;

    -- 6. Agent capability check (OBO intersection) when app.agent_principal_id is set
    v_agent_id_str := NULLIF(current_setting('app.agent_principal_id', true), '');
    IF v_agent_id_str IS NOT NULL THEN
        v_agent_pset := app_effective_principal_set_for(v_agent_id_str::uuid);
        IF cardinality(v_agent_pset) = 0 THEN
            RETURN FALSE;
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM effective_resource_access era
            WHERE era.object_id = p_object_id
              AND era.workspace_id = v_cur_ws
              AND era.principal_id = ANY (v_agent_pset)
              AND (era.allow_mask & p_mask) = p_mask
              AND (era.deny_mask  & p_mask) = 0
        ) THEN
            RETURN FALSE;
        END IF;
    END IF;

    RETURN TRUE;
END;
$$;

GRANT EXECUTE ON FUNCTION app_has_object_capability(uuid, integer) TO kanban_app, app_rls_reader, kanban_migrator;

-- 5. Upgrade objects_select_rls to route through app_has_object_capability
DROP POLICY IF EXISTS objects_select_rls ON objects;
CREATE POLICY objects_select_rls ON objects
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(id, 1)
    );
