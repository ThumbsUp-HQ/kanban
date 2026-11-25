-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

-- Fix app_principal_has_role to support cross-workspace SERVER_ADMIN resolution
-- and enforce app.credential_projects boundary checks before role checks.
CREATE OR REPLACE FUNCTION app_principal_has_role(p_project_id uuid, p_roles text[])
RETURNS boolean
LANGUAGE plpgsql
STABLE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_principal_id uuid;
    v_pset uuid[];
    v_ws uuid;
    v_cred_projs_str text;
BEGIN
    -- (a) Enforce app.credential_projects FIRST whenever p_project_id IS NOT NULL
    --     and current_setting('app.credential_projects', true) is non-empty!
    IF p_project_id IS NOT NULL THEN
        v_cred_projs_str := NULLIF(current_setting('app.credential_projects', true), '');
        IF v_cred_projs_str IS NOT NULL THEN
            IF NOT (p_project_id = ANY (string_to_array(v_cred_projs_str, ',')::uuid[])) THEN
                RETURN FALSE;
            END IF;
        END IF;
    END IF;

    -- (b) When 'SERVER_ADMIN' = ANY (p_roles), resolve v_principal_id directly
    --     against principals p (p.id = v_principal_id AND p.status = 'ACTIVE')
    --     + role_bindings rb (rb.principal_id = p.id AND rb.role::text = 'SERVER_ADMIN' AND rb.scope_type = 'server'
    --     plus recursive group memberships if applicable) WITHOUT requiring p.workspace_id = app_current_workspace_id(),
    --     so SERVER_ADMIN works when app.workspace_id is ''/NULL, workspace A, OR secondary workspace B!
    IF 'SERVER_ADMIN' = ANY (p_roles) THEN
        v_principal_id := NULLIF(current_setting('app.principal_id', true), '')::uuid;
        IF v_principal_id IS NOT NULL THEN
            IF EXISTS (
                SELECT 1
                FROM principals p
                JOIN (
                    SELECT v_principal_id AS pid
                    UNION ALL
                    SELECT pgc.ancestor_group_id AS pid
                    FROM principal_group_closure pgc
                    JOIN principals gp ON gp.id = pgc.ancestor_group_id AND gp.status = 'ACTIVE'
                    WHERE pgc.member_id = v_principal_id
                ) eff ON true
                JOIN role_bindings rb ON rb.principal_id = eff.pid
                WHERE p.id = v_principal_id
                  AND p.status = 'ACTIVE'
                  AND rb.role::text = 'SERVER_ADMIN'
                  AND rb.scope_type = 'server'
            ) THEN
                RETURN TRUE;
            END IF;
        END IF;
    END IF;

    -- (c) For all non-SERVER_ADMIN roles (WORKSPACE_ADMIN, PROJECT_ADMIN, MEMBER, VIEWER, etc.),
    --     keep strict v_pset := app_effective_principal_set() + rb.workspace_id = app_current_workspace_id() isolation!
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
              rb.scope_type = 'workspace'
              OR (rb.scope_type = 'project' AND rb.project_id = p_project_id AND p_project_id IS NOT NULL)
          )
    );
END;
$$;

GRANT EXECUTE ON FUNCTION app_principal_has_role(uuid, text[]) TO kanban_app, app_rls_reader, kanban_migrator;

-- Align kb_auth.card_admin_list and kb_auth.card_admin_get to use app_principal_has_role
-- so SERVER_ADMIN principals active on secondary workspaces can administer auth provider cards.
CREATE OR REPLACE FUNCTION kb_auth.card_admin_list()
RETURNS SETOF auth_provider_cards
LANGUAGE plpgsql
STABLE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF NOT (
        app_principal_has_role(NULL, ARRAY['SERVER_ADMIN'])
        AND current_setting('app.aal_level', true) = '2'
    ) THEN
        RAISE EXCEPTION 'insufficient_privilege: SERVER_ADMIN with AAL2 required'
            USING ERRCODE = '42501';
    END IF;

    RETURN QUERY
    SELECT *
    FROM auth_provider_cards c
    ORDER BY c.sort_rank COLLATE "C" ASC, c.id ASC;
END;
$$;

ALTER FUNCTION kb_auth.card_admin_list() OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.card_admin_list() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.card_admin_list() TO kanban_app;

CREATE OR REPLACE FUNCTION kb_auth.card_admin_get(p_id UUID)
RETURNS SETOF auth_provider_cards
LANGUAGE plpgsql
STABLE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF NOT (
        app_principal_has_role(NULL, ARRAY['SERVER_ADMIN'])
        AND current_setting('app.aal_level', true) = '2'
    ) THEN
        RAISE EXCEPTION 'insufficient_privilege: SERVER_ADMIN with AAL2 required'
            USING ERRCODE = '42501';
    END IF;

    RETURN QUERY
    SELECT *
    FROM auth_provider_cards c
    WHERE c.id = p_id;
END;
$$;

ALTER FUNCTION kb_auth.card_admin_get(UUID) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.card_admin_get(UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.card_admin_get(UUID) TO kanban_app;
