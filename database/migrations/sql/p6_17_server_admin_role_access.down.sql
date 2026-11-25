-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

-- Revert app_principal_has_role to p6_04 definition
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
