-- Revert KB-P1-14: FORCE ROW LEVEL SECURITY policies, session context helpers & schema-wide RLS catalog gate

-- 1. Drop Policies
DROP POLICY IF EXISTS workspaces_select_rls ON workspaces;
DROP POLICY IF EXISTS workspaces_update_rls ON workspaces;

DROP POLICY IF EXISTS principals_select_rls ON principals;
DROP POLICY IF EXISTS principals_insert_rls ON principals;
DROP POLICY IF EXISTS principals_update_rls ON principals;
DROP POLICY IF EXISTS principals_delete_rls ON principals;

DROP POLICY IF EXISTS users_select_rls ON users;
DROP POLICY IF EXISTS users_insert_rls ON users;
DROP POLICY IF EXISTS users_update_rls ON users;
DROP POLICY IF EXISTS users_delete_rls ON users;

DROP POLICY IF EXISTS groups_select_rls ON groups;
DROP POLICY IF EXISTS groups_insert_rls ON groups;
DROP POLICY IF EXISTS groups_update_rls ON groups;
DROP POLICY IF EXISTS groups_delete_rls ON groups;

DROP POLICY IF EXISTS principal_group_edges_select_rls ON principal_group_edges;
DROP POLICY IF EXISTS principal_group_edges_insert_rls ON principal_group_edges;
DROP POLICY IF EXISTS principal_group_edges_update_rls ON principal_group_edges;
DROP POLICY IF EXISTS principal_group_edges_delete_rls ON principal_group_edges;

DROP POLICY IF EXISTS principal_group_closure_select_rls ON principal_group_closure;

DROP POLICY IF EXISTS objects_select_rls ON objects;
DROP POLICY IF EXISTS objects_insert_rls ON objects;
DROP POLICY IF EXISTS objects_update_rls ON objects;
DROP POLICY IF EXISTS objects_delete_rls ON objects;

DROP POLICY IF EXISTS projects_select_rls ON projects;
DROP POLICY IF EXISTS projects_insert_rls ON projects;
DROP POLICY IF EXISTS projects_update_rls ON projects;
DROP POLICY IF EXISTS projects_delete_rls ON projects;

DROP POLICY IF EXISTS workflow_states_select_rls ON workflow_states;
DROP POLICY IF EXISTS workflow_states_insert_rls ON workflow_states;
DROP POLICY IF EXISTS workflow_states_update_rls ON workflow_states;
DROP POLICY IF EXISTS workflow_states_delete_rls ON workflow_states;

DROP POLICY IF EXISTS project_priorities_select_rls ON project_priorities;
DROP POLICY IF EXISTS project_priorities_insert_rls ON project_priorities;
DROP POLICY IF EXISTS project_priorities_update_rls ON project_priorities;
DROP POLICY IF EXISTS project_priorities_delete_rls ON project_priorities;

DROP POLICY IF EXISTS project_labels_select_rls ON project_labels;
DROP POLICY IF EXISTS project_labels_insert_rls ON project_labels;
DROP POLICY IF EXISTS project_labels_update_rls ON project_labels;
DROP POLICY IF EXISTS project_labels_delete_rls ON project_labels;

DROP POLICY IF EXISTS project_module_defaults_select_rls ON project_module_defaults;
DROP POLICY IF EXISTS project_module_defaults_insert_rls ON project_module_defaults;
DROP POLICY IF EXISTS project_module_defaults_update_rls ON project_module_defaults;
DROP POLICY IF EXISTS project_module_defaults_delete_rls ON project_module_defaults;

DROP POLICY IF EXISTS issues_select_rls ON issues;
DROP POLICY IF EXISTS issues_insert_rls ON issues;
DROP POLICY IF EXISTS issues_update_rls ON issues;
DROP POLICY IF EXISTS issues_delete_rls ON issues;

DROP POLICY IF EXISTS cycles_select_rls ON cycles;
DROP POLICY IF EXISTS cycles_insert_rls ON cycles;
DROP POLICY IF EXISTS cycles_update_rls ON cycles;
DROP POLICY IF EXISTS cycles_delete_rls ON cycles;

DROP POLICY IF EXISTS modules_select_rls ON modules;
DROP POLICY IF EXISTS modules_insert_rls ON modules;
DROP POLICY IF EXISTS modules_update_rls ON modules;
DROP POLICY IF EXISTS modules_delete_rls ON modules;

DROP POLICY IF EXISTS issue_modules_select_rls ON issue_modules;
DROP POLICY IF EXISTS issue_modules_insert_rls ON issue_modules;
DROP POLICY IF EXISTS issue_modules_update_rls ON issue_modules;
DROP POLICY IF EXISTS issue_modules_delete_rls ON issue_modules;

DROP POLICY IF EXISTS issue_assignees_select_rls ON issue_assignees;
DROP POLICY IF EXISTS issue_assignees_insert_rls ON issue_assignees;
DROP POLICY IF EXISTS issue_assignees_update_rls ON issue_assignees;
DROP POLICY IF EXISTS issue_assignees_delete_rls ON issue_assignees;

DROP POLICY IF EXISTS issue_labels_select_rls ON issue_labels;
DROP POLICY IF EXISTS issue_labels_insert_rls ON issue_labels;
DROP POLICY IF EXISTS issue_labels_update_rls ON issue_labels;
DROP POLICY IF EXISTS issue_labels_delete_rls ON issue_labels;

DROP POLICY IF EXISTS issue_subscriptions_select_rls ON issue_subscriptions;
DROP POLICY IF EXISTS issue_subscriptions_insert_rls ON issue_subscriptions;
DROP POLICY IF EXISTS issue_subscriptions_update_rls ON issue_subscriptions;
DROP POLICY IF EXISTS issue_subscriptions_delete_rls ON issue_subscriptions;

DROP POLICY IF EXISTS views_select_rls ON views;
DROP POLICY IF EXISTS views_insert_rls ON views;
DROP POLICY IF EXISTS views_update_rls ON views;
DROP POLICY IF EXISTS views_delete_rls ON views;

DROP POLICY IF EXISTS object_links_select_rls ON object_links;
DROP POLICY IF EXISTS object_links_insert_rls ON object_links;
DROP POLICY IF EXISTS object_links_update_rls ON object_links;
DROP POLICY IF EXISTS object_links_delete_rls ON object_links;

DROP POLICY IF EXISTS activity_records_select_rls ON activity_records;
DROP POLICY IF EXISTS activity_records_insert_rls ON activity_records;

DROP POLICY IF EXISTS role_bindings_select_rls ON role_bindings;
DROP POLICY IF EXISTS role_bindings_insert_rls ON role_bindings;
DROP POLICY IF EXISTS role_bindings_update_rls ON role_bindings;
DROP POLICY IF EXISTS role_bindings_delete_rls ON role_bindings;

DROP POLICY IF EXISTS resource_acl_entries_select_rls ON resource_acl_entries;
DROP POLICY IF EXISTS resource_acl_entries_insert_rls ON resource_acl_entries;
DROP POLICY IF EXISTS resource_acl_entries_update_rls ON resource_acl_entries;
DROP POLICY IF EXISTS resource_acl_entries_delete_rls ON resource_acl_entries;

DROP POLICY IF EXISTS effective_resource_access_select_rls ON effective_resource_access;

DROP POLICY IF EXISTS issue_comments_select_rls ON issue_comments;
DROP POLICY IF EXISTS issue_comments_insert_rls ON issue_comments;
DROP POLICY IF EXISTS issue_comments_update_rls ON issue_comments;
DROP POLICY IF EXISTS issue_comments_delete_rls ON issue_comments;

DROP POLICY IF EXISTS docs_select_rls ON docs;
DROP POLICY IF EXISTS docs_insert_rls ON docs;
DROP POLICY IF EXISTS docs_update_rls ON docs;
DROP POLICY IF EXISTS docs_delete_rls ON docs;

DROP POLICY IF EXISTS pages_select_rls ON pages;
DROP POLICY IF EXISTS pages_insert_rls ON pages;
DROP POLICY IF EXISTS pages_update_rls ON pages;
DROP POLICY IF EXISTS pages_delete_rls ON pages;

DROP POLICY IF EXISTS page_versions_select_rls ON page_versions;
DROP POLICY IF EXISTS page_versions_insert_rls ON page_versions;

DROP POLICY IF EXISTS stickies_select_rls ON stickies;
DROP POLICY IF EXISTS stickies_insert_rls ON stickies;
DROP POLICY IF EXISTS stickies_update_rls ON stickies;
DROP POLICY IF EXISTS stickies_delete_rls ON stickies;

-- 2. Disable FORCE RLS and RLS on all tenant tables and child partitions
ALTER TABLE workspaces NO FORCE ROW LEVEL SECURITY;
ALTER TABLE workspaces DISABLE ROW LEVEL SECURITY;

ALTER TABLE principals NO FORCE ROW LEVEL SECURITY;
ALTER TABLE principals DISABLE ROW LEVEL SECURITY;

ALTER TABLE users NO FORCE ROW LEVEL SECURITY;
ALTER TABLE users DISABLE ROW LEVEL SECURITY;

ALTER TABLE groups NO FORCE ROW LEVEL SECURITY;
ALTER TABLE groups DISABLE ROW LEVEL SECURITY;

ALTER TABLE principal_group_edges NO FORCE ROW LEVEL SECURITY;
ALTER TABLE principal_group_edges DISABLE ROW LEVEL SECURITY;

ALTER TABLE principal_group_closure NO FORCE ROW LEVEL SECURITY;
ALTER TABLE principal_group_closure DISABLE ROW LEVEL SECURITY;

ALTER TABLE projects NO FORCE ROW LEVEL SECURITY;
ALTER TABLE projects DISABLE ROW LEVEL SECURITY;

ALTER TABLE workflow_states NO FORCE ROW LEVEL SECURITY;
ALTER TABLE workflow_states DISABLE ROW LEVEL SECURITY;

ALTER TABLE project_priorities NO FORCE ROW LEVEL SECURITY;
ALTER TABLE project_priorities DISABLE ROW LEVEL SECURITY;

ALTER TABLE project_labels NO FORCE ROW LEVEL SECURITY;
ALTER TABLE project_labels DISABLE ROW LEVEL SECURITY;

ALTER TABLE project_module_defaults NO FORCE ROW LEVEL SECURITY;
ALTER TABLE project_module_defaults DISABLE ROW LEVEL SECURITY;

ALTER TABLE objects NO FORCE ROW LEVEL SECURITY;
ALTER TABLE objects DISABLE ROW LEVEL SECURITY;

ALTER TABLE issues NO FORCE ROW LEVEL SECURITY;
ALTER TABLE issues DISABLE ROW LEVEL SECURITY;

ALTER TABLE cycles NO FORCE ROW LEVEL SECURITY;
ALTER TABLE cycles DISABLE ROW LEVEL SECURITY;

ALTER TABLE modules NO FORCE ROW LEVEL SECURITY;
ALTER TABLE modules DISABLE ROW LEVEL SECURITY;

ALTER TABLE issue_modules NO FORCE ROW LEVEL SECURITY;
ALTER TABLE issue_modules DISABLE ROW LEVEL SECURITY;

ALTER TABLE issue_assignees NO FORCE ROW LEVEL SECURITY;
ALTER TABLE issue_assignees DISABLE ROW LEVEL SECURITY;

ALTER TABLE issue_labels NO FORCE ROW LEVEL SECURITY;
ALTER TABLE issue_labels DISABLE ROW LEVEL SECURITY;

ALTER TABLE issue_subscriptions NO FORCE ROW LEVEL SECURITY;
ALTER TABLE issue_subscriptions DISABLE ROW LEVEL SECURITY;

ALTER TABLE views NO FORCE ROW LEVEL SECURITY;
ALTER TABLE views DISABLE ROW LEVEL SECURITY;

ALTER TABLE object_links NO FORCE ROW LEVEL SECURITY;
ALTER TABLE object_links DISABLE ROW LEVEL SECURITY;

ALTER TABLE activity_records NO FORCE ROW LEVEL SECURITY;
ALTER TABLE activity_records DISABLE ROW LEVEL SECURITY;

ALTER TABLE activity_chain_heads NO FORCE ROW LEVEL SECURITY;
ALTER TABLE activity_chain_heads DISABLE ROW LEVEL SECURITY;

ALTER TABLE role_bindings NO FORCE ROW LEVEL SECURITY;
ALTER TABLE role_bindings DISABLE ROW LEVEL SECURITY;

ALTER TABLE resource_acl_entries NO FORCE ROW LEVEL SECURITY;
ALTER TABLE resource_acl_entries DISABLE ROW LEVEL SECURITY;

ALTER TABLE effective_resource_access NO FORCE ROW LEVEL SECURITY;
ALTER TABLE effective_resource_access DISABLE ROW LEVEL SECURITY;

ALTER TABLE issue_comments NO FORCE ROW LEVEL SECURITY;
ALTER TABLE issue_comments DISABLE ROW LEVEL SECURITY;

ALTER TABLE docs NO FORCE ROW LEVEL SECURITY;
ALTER TABLE docs DISABLE ROW LEVEL SECURITY;

ALTER TABLE pages NO FORCE ROW LEVEL SECURITY;
ALTER TABLE pages DISABLE ROW LEVEL SECURITY;

ALTER TABLE page_versions NO FORCE ROW LEVEL SECURITY;
ALTER TABLE page_versions DISABLE ROW LEVEL SECURITY;

ALTER TABLE stickies NO FORCE ROW LEVEL SECURITY;
ALTER TABLE stickies DISABLE ROW LEVEL SECURITY;

DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN (
        SELECT tablename FROM pg_tables
        WHERE schemaname = 'public' AND tablename LIKE 'activity_records_y%'
    ) LOOP
        EXECUTE format('ALTER TABLE public.%I NO FORCE ROW LEVEL SECURITY', r.tablename);
        EXECUTE format('ALTER TABLE public.%I DISABLE ROW LEVEL SECURITY', r.tablename);
    END LOOP;
END $$;

-- 3. Restore original ensure_activity_partitions (without RLS enablement)
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
            v_created_count := v_created_count + 1;
        END IF;
    END LOOP;

    RETURN v_created_count;
END $$;

GRANT EXECUTE ON FUNCTION ensure_activity_partitions(timestamptz, int, int) TO kanban_app;

-- 4. Revert Trigger Functions to SECURITY INVOKER
ALTER FUNCTION issues_validate_biu() SECURITY INVOKER;
ALTER FUNCTION issues_parent_dag_biu() SECURITY INVOKER;
ALTER FUNCTION docs_spine_match_biu() SECURITY INVOKER;

-- 5. Drop Capability & Session Helpers
DROP FUNCTION IF EXISTS app_has_object_capability(uuid, integer);
DROP FUNCTION IF EXISTS app_current_aal_level();
DROP FUNCTION IF EXISTS app_current_token_scopes();
