-- Migration: p1_10_views
-- Views table, view_layout enum, and filter/WIP JSON validators.

-- 1. JSON Validator Functions (IMMUTABLE PARALLEL SAFE)
CREATE OR REPLACE FUNCTION validate_view_filters_json(p_doc jsonb)
RETURNS boolean
LANGUAGE plpgsql
IMMUTABLE PARALLEL SAFE AS $$
DECLARE
    v_key text;
    v_allowed text[] := ARRAY[
        'state_ids', 'state_groups', 'priority_ids', 'assignee_ids',
        'label_ids', 'cycle_ids', 'module_ids', 'start_date',
        'due_date', 'gate_status', 'search_query'
    ];
BEGIN
    IF p_doc IS NULL THEN
        RETURN FALSE;
    END IF;
    IF jsonb_typeof(p_doc) <> 'object' THEN
        RETURN FALSE;
    END IF;
    IF octet_length(p_doc::text) > 16384 THEN
        RETURN FALSE;
    END IF;
    FOR v_key IN SELECT jsonb_object_keys(p_doc) LOOP
        IF NOT (v_key = ANY(v_allowed)) THEN
            RETURN FALSE;
        END IF;
    END LOOP;
    RETURN TRUE;
END;
$$;

CREATE OR REPLACE FUNCTION validate_view_wip_limits_json(p_doc jsonb)
RETURNS boolean
LANGUAGE plpgsql
IMMUTABLE PARALLEL SAFE AS $$
DECLARE
    v_k text;
    v_v jsonb;
    v_prop_k text;
    v_soft_present boolean;
    v_hard_present boolean;
    v_soft_val int;
    v_hard_val int;
    v_num_val numeric;
BEGIN
    IF p_doc IS NULL THEN
        RETURN FALSE;
    END IF;
    IF jsonb_typeof(p_doc) <> 'object' THEN
        RETURN FALSE;
    END IF;
    IF octet_length(p_doc::text) > 8192 THEN
        RETURN FALSE;
    END IF;

    FOR v_k, v_v IN SELECT * FROM jsonb_each(p_doc) LOOP
        -- Key must be valid UUID string
        IF v_k !~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$' THEN
            RETURN FALSE;
        END IF;

        -- Value must be a JSON object
        IF jsonb_typeof(v_v) <> 'object' THEN
            RETURN FALSE;
        END IF;

        v_soft_present := FALSE;
        v_hard_present := FALSE;
        v_soft_val := NULL;
        v_hard_val := NULL;

        -- Keys of v_v must be subset of ('soft', 'hard')
        FOR v_prop_k IN SELECT jsonb_object_keys(v_v) LOOP
            IF v_prop_k NOT IN ('soft', 'hard') THEN
                RETURN FALSE;
            END IF;
        END LOOP;

        -- Check 'soft' if present
        IF v_v ? 'soft' AND jsonb_typeof(v_v->'soft') <> 'null' THEN
            IF jsonb_typeof(v_v->'soft') <> 'number' THEN
                RETURN FALSE;
            END IF;
            BEGIN
                v_num_val := (v_v->>'soft')::numeric;
                IF v_num_val <> trunc(v_num_val) OR v_num_val < 1 OR v_num_val > 10000 THEN
                    RETURN FALSE;
                END IF;
                v_soft_val := v_num_val::int;
                v_soft_present := TRUE;
            EXCEPTION WHEN OTHERS THEN
                RETURN FALSE;
            END;
        END IF;

        -- Check 'hard' if present
        IF v_v ? 'hard' AND jsonb_typeof(v_v->'hard') <> 'null' THEN
            IF jsonb_typeof(v_v->'hard') <> 'number' THEN
                RETURN FALSE;
            END IF;
            BEGIN
                v_num_val := (v_v->>'hard')::numeric;
                IF v_num_val <> trunc(v_num_val) OR v_num_val < 1 OR v_num_val > 10000 THEN
                    RETURN FALSE;
                END IF;
                v_hard_val := v_num_val::int;
                v_hard_present := TRUE;
            EXCEPTION WHEN OTHERS THEN
                RETURN FALSE;
            END;
        END IF;

        -- When both soft and hard are non-null: hard >= soft
        IF v_soft_present AND v_hard_present THEN
            IF v_hard_val < v_soft_val THEN
                RETURN FALSE;
            END IF;
        END IF;

    END LOOP;

    RETURN TRUE;
END;
$$;

-- 2. view_layout Enum
CREATE TYPE view_layout AS ENUM ('list', 'board', 'table', 'calendar', 'timeline');

-- 3. views Table
CREATE TABLE views (
    id                    UUID PRIMARY KEY,
    object_type           object_kind NOT NULL DEFAULT 'view' CHECK (object_type = 'view'),
    workspace_id          UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    project_id            UUID REFERENCES projects(id) ON DELETE RESTRICT,
    owner_principal_id    UUID NOT NULL REFERENCES principals(id) ON DELETE RESTRICT,
    visibility            TEXT NOT NULL DEFAULT 'project'
                          CHECK (visibility IN ('private', 'project', 'workspace')),
    name                  TEXT NOT NULL CHECK (char_length(btrim(name)) BETWEEN 1 AND 200),
    summary_markdown      TEXT NOT NULL DEFAULT '' CHECK (octet_length(summary_markdown) <= 65536),
    summary_sha256        BYTEA GENERATED ALWAYS AS (digest(summary_markdown, 'sha256')) STORED,
    layout                view_layout NOT NULL DEFAULT 'board',
    group_by              TEXT CHECK (group_by IS NULL OR group_by IN
                            ('state', 'priority', 'assignee', 'cycle', 'module', 'label', 'project')),
    sub_group_by          TEXT CHECK (sub_group_by IS NULL OR sub_group_by IN
                            ('assignee', 'priority', 'cycle', 'module', 'label', 'state')),
    filters_json          JSONB NOT NULL DEFAULT '{}'::jsonb
                          CHECK (validate_view_filters_json(filters_json)),
    display_props_json    JSONB NOT NULL DEFAULT '{}'::jsonb
                          CHECK (jsonb_typeof(display_props_json) = 'object'
                                 AND octet_length(display_props_json::text) <= 8192),
    wip_limits_json       JSONB NOT NULL DEFAULT '{}'::jsonb
                          CHECK (validate_view_wip_limits_json(wip_limits_json)),
    sort_rank             TEXT COLLATE "C" NOT NULL DEFAULT 'a0',
    CHECK (visibility <> 'project' OR project_id IS NOT NULL),
    CHECK (group_by IS NULL OR sub_group_by IS NULL OR group_by <> sub_group_by),
    FOREIGN KEY (id, object_type) REFERENCES objects (id, object_type) ON DELETE RESTRICT
);

CREATE INDEX views_project_rank_idx ON views (project_id, sort_rank COLLATE "C") WHERE project_id IS NOT NULL;
CREATE INDEX views_ws_owner_idx ON views (workspace_id, owner_principal_id);

-- 4. Integrity Trigger: views_spine_match_biu
CREATE OR REPLACE FUNCTION views_spine_match_biu()
RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_obj_ws uuid;
    v_obj_project uuid;
    v_princ_ws uuid;
    v_princ_type text;
    v_proj_ws uuid;
BEGIN
    -- 1. Objects spine match
    SELECT workspace_id, project_id
    INTO v_obj_ws, v_obj_project
    FROM objects
    WHERE id = NEW.id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'VIEW_SPINE_MISMATCH: object % does not exist', NEW.id
            USING ERRCODE = 'P0001';
    END IF;

    IF v_obj_ws <> NEW.workspace_id OR (v_obj_project IS DISTINCT FROM NEW.project_id) THEN
        RAISE EXCEPTION 'VIEW_SPINE_MISMATCH: workspace or project mismatch for view %', NEW.id
            USING ERRCODE = 'P0001';
    END IF;

    -- 2. Owner principal validation
    SELECT workspace_id, principal_type
    INTO v_princ_ws, v_princ_type
    FROM principals
    WHERE id = NEW.owner_principal_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'VIEW_INVALID_OWNER: principal % does not exist', NEW.owner_principal_id
            USING ERRCODE = 'P0001';
    END IF;

    IF v_princ_ws <> NEW.workspace_id OR v_princ_type NOT IN ('USER', 'AGENT', 'SERVICE_PRINCIPAL') THEN
        RAISE EXCEPTION 'VIEW_INVALID_OWNER: owner principal % must belong to same workspace and be USER, AGENT, or SERVICE_PRINCIPAL', NEW.owner_principal_id
            USING ERRCODE = 'P0001';
    END IF;

    -- 3. Project workspace match (if project_id is NOT NULL)
    IF NEW.project_id IS NOT NULL THEN
        SELECT workspace_id
        INTO v_proj_ws
        FROM projects
        WHERE id = NEW.project_id;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'VIEW_PROJECT_WORKSPACE_MISMATCH: project % does not exist', NEW.project_id
                USING ERRCODE = 'P0001';
        END IF;

        IF v_proj_ws <> NEW.workspace_id THEN
            RAISE EXCEPTION 'VIEW_PROJECT_WORKSPACE_MISMATCH: project % workspace % does not match view workspace %', NEW.project_id, v_proj_ws, NEW.workspace_id
                USING ERRCODE = 'P0001';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER views_spine_match_biu_trg
BEFORE INSERT OR UPDATE ON views
FOR EACH ROW EXECUTE FUNCTION views_spine_match_biu();

-- 5. Permissions
GRANT EXECUTE ON FUNCTION validate_view_filters_json(jsonb) TO kanban_app, kanban_migrator, app_rls_reader;
GRANT EXECUTE ON FUNCTION validate_view_wip_limits_json(jsonb) TO kanban_app, kanban_migrator, app_rls_reader;
GRANT EXECUTE ON FUNCTION views_spine_match_biu() TO kanban_app, kanban_migrator;

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE views TO kanban_app;
GRANT SELECT ON TABLE views TO app_rls_reader;
