-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

-- Revert KB-SEC-05

DROP POLICY IF EXISTS objects_select_rls ON objects;
CREATE POLICY objects_select_rls ON objects
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND EXISTS (
            SELECT 1 FROM effective_resource_access era
            WHERE era.object_id = objects.id
              AND era.principal_id = ANY (app_effective_principal_set())
              AND (era.allow_mask & 1) = 1
              AND (era.deny_mask  & 1) = 0
        )
    );

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
BEGIN
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

    v_human_pset := app_effective_principal_set();
    IF cardinality(v_human_pset) = 0 THEN
        RETURN FALSE;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM effective_resource_access era
        WHERE era.object_id = p_object_id
          AND era.workspace_id = app_current_workspace_id()
          AND era.principal_id = ANY (v_human_pset)
          AND (era.allow_mask & p_mask) = p_mask
          AND (era.deny_mask  & p_mask) = 0
    ) THEN
        RETURN FALSE;
    END IF;

    v_agent_id_str := NULLIF(current_setting('app.agent_principal_id', true), '');
    IF v_agent_id_str IS NOT NULL THEN
        v_agent_pset := app_effective_principal_set_for(v_agent_id_str::uuid);
        IF cardinality(v_agent_pset) = 0 THEN
            RETURN FALSE;
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM effective_resource_access era
            WHERE era.object_id = p_object_id
              AND era.workspace_id = app_current_workspace_id()
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

GRANT EXECUTE ON FUNCTION app_principal_has_role(uuid, text[]) TO kanban_app, app_rls_reader, kanban_migrator;

CREATE OR REPLACE FUNCTION app_current_workspace_id()
RETURNS uuid
LANGUAGE sql
STABLE PARALLEL SAFE
AS $$ SELECT NULLIF(current_setting('app.workspace_id', true), '')::uuid $$;

GRANT EXECUTE ON FUNCTION app_current_workspace_id() TO kanban_app, app_rls_reader, kanban_migrator;

DROP FUNCTION IF EXISTS app_credential_capability_mask();
DROP FUNCTION IF EXISTS app_credential_projects();
DROP FUNCTION IF EXISTS app_credential_workspaces();
