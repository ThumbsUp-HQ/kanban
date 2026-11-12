-- KB-P1-14: FORCE ROW LEVEL SECURITY policies, session context helpers & schema-wide RLS catalog gate

-- 1. Session GUC & Capability Helpers
CREATE OR REPLACE FUNCTION app_current_token_scopes()
RETURNS text[]
LANGUAGE sql
STABLE PARALLEL SAFE
AS $$
    SELECT COALESCE(string_to_array(NULLIF(current_setting('app.token_scopes', true), ''), ','), '{}'::text[]);
$$;

CREATE OR REPLACE FUNCTION app_current_aal_level()
RETURNS integer
LANGUAGE sql
STABLE PARALLEL SAFE
AS $$
    SELECT COALESCE(NULLIF(current_setting('app.aal_level', true), '')::integer, 0);
$$;

CREATE OR REPLACE FUNCTION app_has_object_capability(p_object_id uuid, p_mask integer)
RETURNS boolean
LANGUAGE sql
STABLE PARALLEL SAFE SECURITY INVOKER
AS $$
    SELECT EXISTS (
        SELECT 1 FROM effective_resource_access era
        WHERE era.object_id = p_object_id
          AND era.workspace_id = app_current_workspace_id()
          AND era.principal_id = ANY (app_effective_principal_set())
          AND (era.allow_mask & p_mask) = p_mask
          AND (era.deny_mask  & p_mask) = 0
    );
$$;

GRANT EXECUTE ON FUNCTION app_current_token_scopes() TO kanban_app, app_rls_reader, kanban_migrator;
GRANT EXECUTE ON FUNCTION app_current_aal_level() TO kanban_app, app_rls_reader, kanban_migrator;
GRANT EXECUTE ON FUNCTION app_has_object_capability(uuid, integer) TO kanban_app, app_rls_reader, kanban_migrator;

-- 2. Update ensure_activity_partitions to apply ENABLE & FORCE RLS on dynamic monthly partitions
CREATE OR REPLACE FUNCTION ensure_activity_partitions(
    p_ref timestamptz DEFAULT clock_timestamp(),
    p_months_back int DEFAULT 1,
    p_months_ahead int DEFAULT 6
) RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE
    v_created_count integer := 0;
    v_i integer;
    v_ref_utc timestamp without time zone;
    v_start_ts timestamp with time zone;
    v_end_ts timestamp with time zone;
    v_part_name text;
    v_start_str text;
    v_end_str text;
BEGIN
    IF p_months_back < 0 OR p_months_back > 24 OR p_months_ahead < 0 OR p_months_ahead > 36 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'PARTITION_RANGE_INVALID';
    END IF;

    PERFORM pg_advisory_xact_lock(hashtextextended('activity_partitions', 0));

    v_ref_utc := date_trunc('month', p_ref AT TIME ZONE 'UTC');

    FOR v_i IN (-p_months_back)..p_months_ahead LOOP
        v_start_ts := (v_ref_utc + (v_i || ' month')::interval) AT TIME ZONE 'UTC';
        v_end_ts := (v_ref_utc + ((v_i + 1) || ' month')::interval) AT TIME ZONE 'UTC';

        v_part_name := 'activity_records_y' || to_char(v_start_ts, 'YYYY') || 'm' || to_char(v_start_ts, 'MM');
        v_start_str := to_char(v_start_ts, 'YYYY-MM-DD 00:00:00+00');
        v_end_str := to_char(v_end_ts, 'YYYY-MM-DD 00:00:00+00');

        IF NOT EXISTS (
            SELECT 1 FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relname = v_part_name
        ) THEN
            EXECUTE format(
                'CREATE TABLE public.%I PARTITION OF public.activity_records FOR VALUES FROM (%L) TO (%L)',
                v_part_name,
                v_start_str,
                v_end_str
            );
            EXECUTE format(
                'REVOKE UPDATE, DELETE, TRUNCATE ON public.%I FROM kanban_app, app_rls_reader',
                v_part_name
            );
            EXECUTE format(
                'ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',
                v_part_name
            );
            EXECUTE format(
                'ALTER TABLE public.%I FORCE ROW LEVEL SECURITY',
                v_part_name
            );
            v_created_count := v_created_count + 1;
        END IF;
    END LOOP;

    RETURN v_created_count;
END $$;

GRANT EXECUTE ON FUNCTION ensure_activity_partitions(timestamptz, int, int) TO kanban_app, kanban_migrator;

-- 2.1 Set integrity triggers to SECURITY DEFINER so internal constraint checks succeed under RLS
ALTER FUNCTION issues_validate_biu() SECURITY DEFINER SET search_path = pg_catalog, public;
ALTER FUNCTION issues_parent_dag_biu() SECURITY DEFINER SET search_path = pg_catalog, public;
ALTER FUNCTION docs_spine_match_biu() SECURITY DEFINER SET search_path = pg_catalog, public;

-- 3. ENABLE and FORCE ROW LEVEL SECURITY across all tenant tables and existing monthly partitions
ALTER TABLE workspaces ENABLE ROW LEVEL SECURITY;
ALTER TABLE workspaces FORCE ROW LEVEL SECURITY;

ALTER TABLE principals ENABLE ROW LEVEL SECURITY;
ALTER TABLE principals FORCE ROW LEVEL SECURITY;

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE users FORCE ROW LEVEL SECURITY;

ALTER TABLE groups ENABLE ROW LEVEL SECURITY;
ALTER TABLE groups FORCE ROW LEVEL SECURITY;

ALTER TABLE principal_group_edges ENABLE ROW LEVEL SECURITY;
ALTER TABLE principal_group_edges FORCE ROW LEVEL SECURITY;

ALTER TABLE principal_group_closure ENABLE ROW LEVEL SECURITY;
ALTER TABLE principal_group_closure FORCE ROW LEVEL SECURITY;

ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects FORCE ROW LEVEL SECURITY;

ALTER TABLE workflow_states ENABLE ROW LEVEL SECURITY;
ALTER TABLE workflow_states FORCE ROW LEVEL SECURITY;

ALTER TABLE project_priorities ENABLE ROW LEVEL SECURITY;
ALTER TABLE project_priorities FORCE ROW LEVEL SECURITY;

ALTER TABLE project_labels ENABLE ROW LEVEL SECURITY;
ALTER TABLE project_labels FORCE ROW LEVEL SECURITY;

ALTER TABLE project_module_defaults ENABLE ROW LEVEL SECURITY;
ALTER TABLE project_module_defaults FORCE ROW LEVEL SECURITY;

ALTER TABLE objects ENABLE ROW LEVEL SECURITY;
ALTER TABLE objects FORCE ROW LEVEL SECURITY;

ALTER TABLE issues ENABLE ROW LEVEL SECURITY;
ALTER TABLE issues FORCE ROW LEVEL SECURITY;

ALTER TABLE cycles ENABLE ROW LEVEL SECURITY;
ALTER TABLE cycles FORCE ROW LEVEL SECURITY;

ALTER TABLE modules ENABLE ROW LEVEL SECURITY;
ALTER TABLE modules FORCE ROW LEVEL SECURITY;

ALTER TABLE issue_modules ENABLE ROW LEVEL SECURITY;
ALTER TABLE issue_modules FORCE ROW LEVEL SECURITY;

ALTER TABLE issue_assignees ENABLE ROW LEVEL SECURITY;
ALTER TABLE issue_assignees FORCE ROW LEVEL SECURITY;

ALTER TABLE issue_labels ENABLE ROW LEVEL SECURITY;
ALTER TABLE issue_labels FORCE ROW LEVEL SECURITY;

ALTER TABLE issue_subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE issue_subscriptions FORCE ROW LEVEL SECURITY;

ALTER TABLE views ENABLE ROW LEVEL SECURITY;
ALTER TABLE views FORCE ROW LEVEL SECURITY;

ALTER TABLE object_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE object_links FORCE ROW LEVEL SECURITY;

ALTER TABLE activity_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE activity_records FORCE ROW LEVEL SECURITY;

ALTER TABLE activity_chain_heads ENABLE ROW LEVEL SECURITY;
ALTER TABLE activity_chain_heads FORCE ROW LEVEL SECURITY;

ALTER TABLE role_bindings ENABLE ROW LEVEL SECURITY;
ALTER TABLE role_bindings FORCE ROW LEVEL SECURITY;

ALTER TABLE resource_acl_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE resource_acl_entries FORCE ROW LEVEL SECURITY;

ALTER TABLE effective_resource_access ENABLE ROW LEVEL SECURITY;
ALTER TABLE effective_resource_access FORCE ROW LEVEL SECURITY;

ALTER TABLE issue_comments ENABLE ROW LEVEL SECURITY;
ALTER TABLE issue_comments FORCE ROW LEVEL SECURITY;

ALTER TABLE docs ENABLE ROW LEVEL SECURITY;
ALTER TABLE docs FORCE ROW LEVEL SECURITY;

ALTER TABLE pages ENABLE ROW LEVEL SECURITY;
ALTER TABLE pages FORCE ROW LEVEL SECURITY;

ALTER TABLE page_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE page_versions FORCE ROW LEVEL SECURITY;

ALTER TABLE stickies ENABLE ROW LEVEL SECURITY;
ALTER TABLE stickies FORCE ROW LEVEL SECURITY;

DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN (
        SELECT tablename FROM pg_tables
        WHERE schemaname = 'public' AND tablename LIKE 'activity_records_y%'
    ) LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', r.tablename);
        EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY', r.tablename);
    END LOOP;
END $$;

-- 4. Row Level Security Policies Across All Tenant Tables

-- 4.1 Workspaces
CREATE POLICY workspaces_select_rls ON workspaces
    FOR SELECT USING (
        id = app_current_workspace_id()
        AND cardinality(app_effective_principal_set()) > 0
    );

CREATE POLICY workspaces_update_rls ON workspaces
    FOR UPDATE USING (
        id = app_current_workspace_id()
        AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
    ) WITH CHECK (
        id = app_current_workspace_id()
        AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
    );

-- 4.2 Principals & Identity
CREATE POLICY principals_select_rls ON principals
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND cardinality(app_effective_principal_set()) > 0
    );

CREATE POLICY principals_insert_rls ON principals
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
    );

CREATE POLICY principals_update_rls ON principals
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
    );

CREATE POLICY principals_delete_rls ON principals
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
    );

CREATE POLICY users_select_rls ON users
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND cardinality(app_effective_principal_set()) > 0
    );

CREATE POLICY users_insert_rls ON users
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
    );

CREATE POLICY users_update_rls ON users
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
    );

CREATE POLICY users_delete_rls ON users
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
    );

CREATE POLICY groups_select_rls ON groups
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND cardinality(app_effective_principal_set()) > 0
    );

CREATE POLICY groups_insert_rls ON groups
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
    );

CREATE POLICY groups_update_rls ON groups
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
    );

CREATE POLICY groups_delete_rls ON groups
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
    );

CREATE POLICY principal_group_edges_select_rls ON principal_group_edges
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND cardinality(app_effective_principal_set()) > 0
    );

CREATE POLICY principal_group_edges_insert_rls ON principal_group_edges
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
    );

CREATE POLICY principal_group_edges_update_rls ON principal_group_edges
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
    );

CREATE POLICY principal_group_edges_delete_rls ON principal_group_edges
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
    );

CREATE POLICY principal_group_closure_select_rls ON principal_group_closure
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND cardinality(app_effective_principal_set()) > 0
    );

-- 4.3 Universal Objects Spine (S3.3)
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

CREATE POLICY objects_insert_rls ON objects
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_current_principal_id() IS NOT NULL
        AND (
            (project_id IS NULL AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN']))
            OR (project_id IS NOT NULL AND app_has_object_capability(project_id, 4))
        )
    );

CREATE POLICY objects_update_rls ON objects
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(id, 4)
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(id, 4)
    );

CREATE POLICY objects_delete_rls ON objects
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(id, 128)
    );

-- 4.4 Object-Spine Entity Tables (projects, issues, cycles, modules, docs, pages, stickies, views)

-- projects
CREATE POLICY projects_select_rls ON projects
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(id, 1)
    );

CREATE POLICY projects_insert_rls ON projects
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
    );

CREATE POLICY projects_update_rls ON projects
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(id, 64)
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(id, 64)
    );

CREATE POLICY projects_delete_rls ON projects
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(id, 128)
    );

-- issues
CREATE POLICY issues_select_rls ON issues
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(id, 1)
    );

CREATE POLICY issues_insert_rls ON issues
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(project_id, 4)
    );

CREATE POLICY issues_update_rls ON issues
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(id, 1)
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND (app_has_object_capability(id, 4) OR app_has_object_capability(id, 8))
    );

CREATE POLICY issues_delete_rls ON issues
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(id, 128)
    );

-- cycles
CREATE POLICY cycles_select_rls ON cycles
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(id, 1)
    );

CREATE POLICY cycles_insert_rls ON cycles
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(project_id, 4)
    );

CREATE POLICY cycles_update_rls ON cycles
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(id, 4)
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(id, 4)
    );

CREATE POLICY cycles_delete_rls ON cycles
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(id, 128)
    );

-- modules
CREATE POLICY modules_select_rls ON modules
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(id, 1)
    );

CREATE POLICY modules_insert_rls ON modules
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(project_id, 4)
    );

CREATE POLICY modules_update_rls ON modules
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(id, 4)
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(id, 4)
    );

CREATE POLICY modules_delete_rls ON modules
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(id, 128)
    );

-- docs
CREATE POLICY docs_select_rls ON docs
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(id, 1)
    );

CREATE POLICY docs_insert_rls ON docs
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND (project_id IS NULL OR app_has_object_capability(project_id, 4))
    );

CREATE POLICY docs_update_rls ON docs
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(id, 4)
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(id, 4)
    );

CREATE POLICY docs_delete_rls ON docs
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(id, 128)
    );

-- pages
CREATE POLICY pages_select_rls ON pages
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(id, 1)
    );

CREATE POLICY pages_insert_rls ON pages
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(doc_id, 4)
    );

CREATE POLICY pages_update_rls ON pages
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(id, 4)
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(id, 4)
    );

CREATE POLICY pages_delete_rls ON pages
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(id, 128)
    );

-- stickies
CREATE POLICY stickies_select_rls ON stickies
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(id, 1)
    );

CREATE POLICY stickies_insert_rls ON stickies
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND (project_id IS NULL OR app_has_object_capability(project_id, 4))
    );

CREATE POLICY stickies_update_rls ON stickies
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(id, 4)
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(id, 4)
    );

CREATE POLICY stickies_delete_rls ON stickies
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(id, 128)
    );

-- views (private views visible to owner or project admins)
CREATE POLICY views_select_rls ON views
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(id, 1)
        AND (
            visibility <> 'private'
            OR owner_principal_id = app_current_principal_id()
            OR app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN'])
        )
    );

CREATE POLICY views_insert_rls ON views
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND (project_id IS NULL OR app_has_object_capability(project_id, 4))
    );

CREATE POLICY views_update_rls ON views
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(id, 4)
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(id, 4)
    );

CREATE POLICY views_delete_rls ON views
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(id, 128)
    );

-- 4.5 Project Configuration Child Tables
CREATE POLICY workflow_states_select_rls ON workflow_states
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(project_id, 1)
    );

CREATE POLICY workflow_states_insert_rls ON workflow_states
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(project_id, 64)
    );

CREATE POLICY workflow_states_update_rls ON workflow_states
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(project_id, 64)
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(project_id, 64)
    );

CREATE POLICY workflow_states_delete_rls ON workflow_states
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(project_id, 64)
    );

CREATE POLICY project_priorities_select_rls ON project_priorities
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(project_id, 1)
    );

CREATE POLICY project_priorities_insert_rls ON project_priorities
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(project_id, 64)
    );

CREATE POLICY project_priorities_update_rls ON project_priorities
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(project_id, 64)
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(project_id, 64)
    );

CREATE POLICY project_priorities_delete_rls ON project_priorities
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(project_id, 64)
    );

CREATE POLICY project_labels_select_rls ON project_labels
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(project_id, 1)
    );

CREATE POLICY project_labels_insert_rls ON project_labels
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(project_id, 64)
    );

CREATE POLICY project_labels_update_rls ON project_labels
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(project_id, 64)
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(project_id, 64)
    );

CREATE POLICY project_labels_delete_rls ON project_labels
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(project_id, 64)
    );

CREATE POLICY project_module_defaults_select_rls ON project_module_defaults
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(project_id, 1)
    );

CREATE POLICY project_module_defaults_insert_rls ON project_module_defaults
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(project_id, 64)
    );

CREATE POLICY project_module_defaults_update_rls ON project_module_defaults
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(project_id, 64)
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(project_id, 64)
    );

CREATE POLICY project_module_defaults_delete_rls ON project_module_defaults
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(project_id, 64)
    );

-- 4.6 Issue Join & Prose Child Tables
CREATE POLICY issue_modules_select_rls ON issue_modules
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(issue_id, 1)
    );

CREATE POLICY issue_modules_insert_rls ON issue_modules
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(issue_id, 4)
    );

CREATE POLICY issue_modules_update_rls ON issue_modules
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(issue_id, 4)
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(issue_id, 4)
    );

CREATE POLICY issue_modules_delete_rls ON issue_modules
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(issue_id, 4)
    );

CREATE POLICY issue_assignees_select_rls ON issue_assignees
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(issue_id, 1)
    );

CREATE POLICY issue_assignees_insert_rls ON issue_assignees
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(issue_id, 4)
    );

CREATE POLICY issue_assignees_update_rls ON issue_assignees
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(issue_id, 4)
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(issue_id, 4)
    );

CREATE POLICY issue_assignees_delete_rls ON issue_assignees
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(issue_id, 4)
    );

CREATE POLICY issue_labels_select_rls ON issue_labels
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(issue_id, 1)
    );

CREATE POLICY issue_labels_insert_rls ON issue_labels
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(issue_id, 4)
    );

CREATE POLICY issue_labels_update_rls ON issue_labels
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(issue_id, 4)
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(issue_id, 4)
    );

CREATE POLICY issue_labels_delete_rls ON issue_labels
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(issue_id, 4)
    );

CREATE POLICY issue_subscriptions_select_rls ON issue_subscriptions
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(issue_id, 1)
        AND (
            principal_id = app_current_principal_id()
            OR app_has_object_capability(issue_id, 64)
        )
    );

CREATE POLICY issue_subscriptions_insert_rls ON issue_subscriptions
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(issue_id, 1)
        AND (
            principal_id = app_current_principal_id()
            OR app_has_object_capability(issue_id, 4)
        )
    );

CREATE POLICY issue_subscriptions_update_rls ON issue_subscriptions
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(issue_id, 1)
        AND (
            principal_id = app_current_principal_id()
            OR app_has_object_capability(issue_id, 4)
        )
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(issue_id, 1)
        AND (
            principal_id = app_current_principal_id()
            OR app_has_object_capability(issue_id, 4)
        )
    );

CREATE POLICY issue_subscriptions_delete_rls ON issue_subscriptions
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(issue_id, 1)
        AND (
            principal_id = app_current_principal_id()
            OR app_has_object_capability(issue_id, 4)
        )
    );

CREATE POLICY issue_comments_select_rls ON issue_comments
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(issue_id, 1)
    );

CREATE POLICY issue_comments_insert_rls ON issue_comments
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND author_id = app_current_principal_id()
        AND app_has_object_capability(issue_id, 2)
    );

CREATE POLICY issue_comments_update_rls ON issue_comments
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
        AND (
            (author_id = app_current_principal_id() AND app_has_object_capability(issue_id, 2))
            OR app_has_object_capability(issue_id, 64)
        )
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND (
            (author_id = app_current_principal_id() AND app_has_object_capability(issue_id, 2))
            OR app_has_object_capability(issue_id, 64)
        )
    );

CREATE POLICY issue_comments_delete_rls ON issue_comments
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
        AND (
            (author_id = app_current_principal_id() AND app_has_object_capability(issue_id, 2))
            OR app_has_object_capability(issue_id, 64)
        )
    );

CREATE POLICY page_versions_select_rls ON page_versions
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(page_id, 1)
    );

CREATE POLICY page_versions_insert_rls ON page_versions
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(page_id, 4)
    );

-- 4.7 Graph Links & Audit Ledger
CREATE POLICY object_links_select_rls ON object_links
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND (
            app_has_object_capability(source_id, 1)
            OR app_has_object_capability(target_id, 1)
        )
    );

CREATE POLICY object_links_insert_rls ON object_links
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(source_id, 16)
        AND app_has_object_capability(target_id, 1)
    );

CREATE POLICY object_links_update_rls ON object_links
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(source_id, 16)
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(source_id, 16)
        AND app_has_object_capability(target_id, 1)
    );

CREATE POLICY object_links_delete_rls ON object_links
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(source_id, 16)
    );

CREATE POLICY activity_records_select_rls ON activity_records
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND (
            (object_id IS NOT NULL AND app_has_object_capability(object_id, 1))
            OR app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
        )
    );

CREATE POLICY activity_records_insert_rls ON activity_records
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND (actor_id IS NULL OR actor_id = app_current_principal_id())
    );

-- 4.8 Access Control & Permissions
CREATE POLICY role_bindings_select_rls ON role_bindings
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND (
            principal_id = ANY (app_effective_principal_set())
            OR app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN'])
        )
    );

CREATE POLICY role_bindings_insert_rls ON role_bindings
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND (
            (scope_type = 'server' AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN']))
            OR (scope_type = 'workspace' AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN']))
            OR (scope_type = 'project' AND app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN']))
        )
    );

CREATE POLICY role_bindings_update_rls ON role_bindings
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
        AND (
            (scope_type = 'server' AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN']))
            OR (scope_type = 'workspace' AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN']))
            OR (scope_type = 'project' AND app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN']))
        )
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND (
            (scope_type = 'server' AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN']))
            OR (scope_type = 'workspace' AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN']))
            OR (scope_type = 'project' AND app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN']))
        )
    );

CREATE POLICY role_bindings_delete_rls ON role_bindings
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
        AND (
            (scope_type = 'server' AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN']))
            OR (scope_type = 'workspace' AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN']))
            OR (scope_type = 'project' AND app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN']))
        )
    );

CREATE POLICY resource_acl_entries_select_rls ON resource_acl_entries
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(object_id, 1)
    );

CREATE POLICY resource_acl_entries_insert_rls ON resource_acl_entries
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND (
            app_has_object_capability(object_id, 32)
            OR app_has_object_capability(object_id, 64)
        )
    );

CREATE POLICY resource_acl_entries_update_rls ON resource_acl_entries
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
        AND (
            app_has_object_capability(object_id, 32)
            OR app_has_object_capability(object_id, 64)
        )
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND (
            app_has_object_capability(object_id, 32)
            OR app_has_object_capability(object_id, 64)
        )
    );

CREATE POLICY resource_acl_entries_delete_rls ON resource_acl_entries
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
        AND (
            app_has_object_capability(object_id, 32)
            OR app_has_object_capability(object_id, 64)
        )
    );

-- Non-recursive RLS policy on effective_resource_access: avoids calling app_has_object_capability
CREATE POLICY effective_resource_access_select_rls ON effective_resource_access
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND cardinality(app_effective_principal_set()) > 0
    );
