-- KB-P1-08: cycles, modules, assignees, labels & subscriptions join tables

-- 1. Cycles Table
CREATE TABLE cycles (
    id            UUID PRIMARY KEY,
    object_type   object_kind NOT NULL DEFAULT 'cycle' CHECK (object_type = 'cycle'),
    workspace_id  UUID NOT NULL,
    project_id    UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    name          TEXT NOT NULL CHECK (char_length(btrim(name)) BETWEEN 1 AND 200),
    status        TEXT NOT NULL DEFAULT 'upcoming' CHECK (status IN ('upcoming','active','completed')),
    start_date    DATE,
    end_date      DATE,
    CHECK (end_date IS NULL OR start_date IS NULL OR end_date >= start_date),
    FOREIGN KEY (id, object_type) REFERENCES objects (id, object_type) ON DELETE RESTRICT,
    EXCLUDE USING gist (project_id WITH =, daterange(start_date, end_date, '[]') WITH &&)
        WHERE (start_date IS NOT NULL AND end_date IS NOT NULL)
);

CREATE UNIQUE INDEX cycles_one_active_per_project ON cycles (project_id) WHERE status = 'active';
CREATE INDEX cycles_project_idx ON cycles (project_id);

-- 2. Foreign Key from issues to cycles
ALTER TABLE issues ADD CONSTRAINT issues_cycle_fk
    FOREIGN KEY (cycle_id) REFERENCES cycles(id) ON DELETE SET NULL;

-- 3. Modules Table
CREATE TABLE modules (
    id            UUID PRIMARY KEY,
    object_type   object_kind NOT NULL DEFAULT 'module' CHECK (object_type = 'module'),
    workspace_id  UUID NOT NULL,
    project_id    UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    name          TEXT NOT NULL CHECK (char_length(btrim(name)) BETWEEN 1 AND 200),
    start_date    DATE,
    target_date   DATE,
    CHECK (target_date IS NULL OR start_date IS NULL OR target_date >= start_date),
    UNIQUE (project_id, name),
    FOREIGN KEY (id, object_type) REFERENCES objects (id, object_type) ON DELETE RESTRICT
);

CREATE INDEX modules_project_idx ON modules (project_id);

-- 4. Join Tables
CREATE TABLE project_module_defaults (
    project_id   UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    module_id    UUID NOT NULL REFERENCES modules(id)  ON DELETE CASCADE,
    workspace_id UUID NOT NULL,
    PRIMARY KEY (project_id, module_id)
);

CREATE TABLE issue_modules (
    issue_id     UUID NOT NULL REFERENCES issues(id)  ON DELETE CASCADE,
    module_id    UUID NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL,
    PRIMARY KEY (issue_id, module_id)
);
CREATE INDEX issue_modules_module_idx ON issue_modules (module_id);

CREATE TABLE issue_assignees (
    id                  UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id        UUID NOT NULL,
    issue_id            UUID NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
    principal_id        UUID REFERENCES principals(id) ON DELETE RESTRICT,
    free_text_assignee  TEXT CHECK (free_text_assignee IS NULL OR char_length(btrim(free_text_assignee)) BETWEEN 1 AND 120),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CHECK (num_nonnulls(principal_id, free_text_assignee) = 1)
);
CREATE UNIQUE INDEX issue_assignees_principal_uq ON issue_assignees (issue_id, principal_id) WHERE principal_id IS NOT NULL;
CREATE UNIQUE INDEX issue_assignees_text_uq ON issue_assignees (issue_id, lower(free_text_assignee)) WHERE free_text_assignee IS NOT NULL;
CREATE INDEX issue_assignees_issue_idx ON issue_assignees (issue_id);
CREATE INDEX issue_assignees_principal_idx ON issue_assignees (principal_id) WHERE principal_id IS NOT NULL;

COMMENT ON COLUMN issue_assignees.free_text_assignee IS 'Vendor or external assignee; grants zero system access and is omitted from effective_resource_access computation.';

CREATE TABLE issue_labels (
    issue_id     UUID NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
    label_id     UUID NOT NULL REFERENCES project_labels(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL,
    PRIMARY KEY (issue_id, label_id)
);
CREATE INDEX issue_labels_label_idx ON issue_labels (label_id);

CREATE TABLE issue_subscriptions (
    issue_id      UUID NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
    principal_id  UUID NOT NULL REFERENCES principals(id) ON DELETE CASCADE,
    workspace_id  UUID NOT NULL,
    source        TEXT NOT NULL CHECK (source IN ('MANUAL','CREATOR','ASSIGNEE','MENTION')),
    is_muted      BOOLEAN NOT NULL DEFAULT FALSE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (issue_id, principal_id)
);
CREATE INDEX issue_subscriptions_principal_idx ON issue_subscriptions (principal_id);

-- 5. Triggers and Functions

-- Spine validation for cycles
CREATE FUNCTION cycles_spine_match_biu() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_ws_id UUID;
    v_proj_id UUID;
BEGIN
    SELECT workspace_id, project_id
      INTO v_ws_id, v_proj_id
      FROM objects
     WHERE id = NEW.id AND object_type = 'cycle';

    IF NOT FOUND OR v_ws_id <> NEW.workspace_id OR v_proj_id IS DISTINCT FROM NEW.project_id THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'PLANNING_SPINE_MISMATCH';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER cycles_spine_match_biu_trg
    BEFORE INSERT OR UPDATE ON cycles
    FOR EACH ROW EXECUTE FUNCTION cycles_spine_match_biu();

-- Spine validation for modules
CREATE FUNCTION modules_spine_match_biu() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_ws_id UUID;
    v_proj_id UUID;
BEGIN
    SELECT workspace_id, project_id
      INTO v_ws_id, v_proj_id
      FROM objects
     WHERE id = NEW.id AND object_type = 'module';

    IF NOT FOUND OR v_ws_id <> NEW.workspace_id OR v_proj_id IS DISTINCT FROM NEW.project_id THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'PLANNING_SPINE_MISMATCH';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER modules_spine_match_biu_trg
    BEFORE INSERT OR UPDATE ON modules
    FOR EACH ROW EXECUTE FUNCTION modules_spine_match_biu();

-- Issues cycle_id project verification
CREATE FUNCTION issues_cycle_project_biu() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_cycle_proj UUID;
BEGIN
    IF NEW.cycle_id IS NOT NULL THEN
        SELECT project_id INTO v_cycle_proj FROM cycles WHERE id = NEW.cycle_id;
        IF v_cycle_proj IS NULL OR v_cycle_proj <> NEW.project_id THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'CYCLE_PROJECT_MISMATCH';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER issues_cycle_project_biu_trg
    BEFORE INSERT OR UPDATE OF cycle_id ON issues
    FOR EACH ROW EXECUTE FUNCTION issues_cycle_project_biu();

-- Issue modules guard: module project must equal issue project, modules_enabled must be true
CREATE FUNCTION issue_modules_guard_bi() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_issue_ws UUID;
    v_issue_proj UUID;
    v_mod_proj UUID;
    v_modules_enabled BOOLEAN;
BEGIN
    SELECT workspace_id, project_id
      INTO v_issue_ws, v_issue_proj
      FROM issues WHERE id = NEW.issue_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'ISSUE_NOT_FOUND';
    END IF;

    SELECT project_id INTO v_mod_proj FROM modules WHERE id = NEW.module_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'MODULE_NOT_FOUND';
    END IF;

    IF v_mod_proj <> v_issue_proj THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'MODULE_PROJECT_MISMATCH';
    END IF;

    SELECT modules_enabled INTO v_modules_enabled FROM projects WHERE id = v_issue_proj;
    IF v_modules_enabled IS NOT TRUE THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'MODULES_DISABLED';
    END IF;

    NEW.workspace_id := v_issue_ws;
    RETURN NEW;
END;
$$;

CREATE TRIGGER issue_modules_guard_bi_trg
    BEFORE INSERT ON issue_modules
    FOR EACH ROW EXECUTE FUNCTION issue_modules_guard_bi();

-- Project module defaults guard: module project must equal project, modules_enabled must be true
CREATE FUNCTION project_module_defaults_guard_bi() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_proj_ws UUID;
    v_modules_enabled BOOLEAN;
    v_mod_proj UUID;
BEGIN
    SELECT workspace_id, modules_enabled
      INTO v_proj_ws, v_modules_enabled
      FROM projects WHERE id = NEW.project_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'PROJECT_NOT_FOUND';
    END IF;

    IF v_modules_enabled IS NOT TRUE THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'MODULES_DISABLED';
    END IF;

    SELECT project_id INTO v_mod_proj FROM modules WHERE id = NEW.module_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'MODULE_NOT_FOUND';
    END IF;

    IF v_mod_proj <> NEW.project_id THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'MODULE_PROJECT_MISMATCH';
    END IF;

    NEW.workspace_id := v_proj_ws;
    RETURN NEW;
END;
$$;

CREATE TRIGGER project_module_defaults_guard_bi_trg
    BEFORE INSERT ON project_module_defaults
    FOR EACH ROW EXECUTE FUNCTION project_module_defaults_guard_bi();

-- Apply module defaults after issue insert
CREATE FUNCTION issues_apply_module_defaults_ai() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_modules_enabled BOOLEAN;
BEGIN
    SELECT modules_enabled INTO v_modules_enabled FROM projects WHERE id = NEW.project_id;
    IF v_modules_enabled IS TRUE THEN
        INSERT INTO issue_modules (issue_id, module_id, workspace_id)
        SELECT NEW.id, pmd.module_id, NEW.workspace_id
          FROM project_module_defaults pmd
         WHERE pmd.project_id = NEW.project_id
        ON CONFLICT DO NOTHING;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER issues_apply_module_defaults_ai_trg
    AFTER INSERT ON issues
    FOR EACH ROW EXECUTE FUNCTION issues_apply_module_defaults_ai();

-- Issue assignees guard: principal must be USER or AGENT, ACTIVE status, same workspace
CREATE FUNCTION issue_assignees_guard_bi() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_issue_ws UUID;
    v_p_type TEXT;
    v_p_status TEXT;
    v_p_ws UUID;
BEGIN
    SELECT workspace_id INTO v_issue_ws FROM issues WHERE id = NEW.issue_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'ISSUE_NOT_FOUND';
    END IF;

    IF NEW.principal_id IS NOT NULL THEN
        SELECT principal_type, status, workspace_id
          INTO v_p_type, v_p_status, v_p_ws
          FROM principals
         WHERE id = NEW.principal_id;

        IF NOT FOUND OR v_p_type NOT IN ('USER', 'AGENT') OR v_p_status <> 'ACTIVE' OR v_p_ws <> v_issue_ws THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'ASSIGNEE_INVALID_PRINCIPAL';
        END IF;
    END IF;

    NEW.workspace_id := v_issue_ws;
    RETURN NEW;
END;
$$;

CREATE TRIGGER issue_assignees_guard_bi_trg
    BEFORE INSERT ON issue_assignees
    FOR EACH ROW EXECUTE FUNCTION issue_assignees_guard_bi();

-- Issue labels exclusive group replacement and project check
CREATE FUNCTION issue_labels_exclusive_bi() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_issue_proj UUID;
    v_issue_ws UUID;
    v_label_proj UUID;
    v_exclusive_group TEXT;
BEGIN
    -- Lock parent issue FOR UPDATE to prevent race conditions during exclusive group check
    SELECT project_id, workspace_id
      INTO v_issue_proj, v_issue_ws
      FROM issues
     WHERE id = NEW.issue_id
       FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'ISSUE_NOT_FOUND';
    END IF;

    SELECT project_id, exclusive_group
      INTO v_label_proj, v_exclusive_group
      FROM project_labels
     WHERE id = NEW.label_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'LABEL_NOT_FOUND';
    END IF;

    IF v_label_proj <> v_issue_proj THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'LABEL_PROJECT_MISMATCH';
    END IF;

    -- If label belongs to an exclusive group, remove existing labels in that group for this issue
    IF v_exclusive_group IS NOT NULL THEN
        DELETE FROM issue_labels il
         USING project_labels pl
         WHERE il.issue_id = NEW.issue_id
           AND il.label_id = pl.id
           AND pl.exclusive_group = v_exclusive_group;
    END IF;

    NEW.workspace_id := v_issue_ws;
    RETURN NEW;
END;
$$;

CREATE TRIGGER issue_labels_exclusive_bi_trg
    BEFORE INSERT ON issue_labels
    FOR EACH ROW EXECUTE FUNCTION issue_labels_exclusive_bi();

-- Autosubscribe issue creator on issue insert
CREATE FUNCTION issues_autosubscribe_creator_ai() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO issue_subscriptions (issue_id, principal_id, workspace_id, source)
    VALUES (NEW.id, NEW.created_by_id, NEW.workspace_id, 'CREATOR')
    ON CONFLICT (issue_id, principal_id) DO NOTHING;
    RETURN NEW;
END;
$$;

CREATE TRIGGER issues_autosubscribe_creator_ai_trg
    AFTER INSERT ON issues
    FOR EACH ROW EXECUTE FUNCTION issues_autosubscribe_creator_ai();

-- Autosubscribe principal assignee on assignee insert
CREATE FUNCTION issue_assignees_autosubscribe_ai() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.principal_id IS NOT NULL THEN
        INSERT INTO issue_subscriptions (issue_id, principal_id, workspace_id, source)
        VALUES (NEW.issue_id, NEW.principal_id, NEW.workspace_id, 'ASSIGNEE')
        ON CONFLICT (issue_id, principal_id) DO NOTHING;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER issue_assignees_autosubscribe_ai_trg
    AFTER INSERT ON issue_assignees
    FOR EACH ROW EXECUTE FUNCTION issue_assignees_autosubscribe_ai();

-- Issue subscriptions guard: principal and issue must share workspace
CREATE FUNCTION issue_subscriptions_guard_bi() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_issue_ws UUID;
    v_p_ws UUID;
BEGIN
    SELECT workspace_id INTO v_issue_ws FROM issues WHERE id = NEW.issue_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'ISSUE_NOT_FOUND';
    END IF;

    SELECT workspace_id INTO v_p_ws FROM principals WHERE id = NEW.principal_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'PRINCIPAL_NOT_FOUND';
    END IF;

    IF v_p_ws <> v_issue_ws THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'SUBSCRIPTION_WORKSPACE_MISMATCH';
    END IF;

    NEW.workspace_id := v_issue_ws;
    RETURN NEW;
END;
$$;

CREATE TRIGGER issue_subscriptions_guard_bi_trg
    BEFORE INSERT ON issue_subscriptions
    FOR EACH ROW EXECUTE FUNCTION issue_subscriptions_guard_bi();

-- Grants
GRANT EXECUTE ON FUNCTION cycles_spine_match_biu() TO kanban_app;
GRANT EXECUTE ON FUNCTION modules_spine_match_biu() TO kanban_app;
GRANT EXECUTE ON FUNCTION issues_cycle_project_biu() TO kanban_app;
GRANT EXECUTE ON FUNCTION issue_modules_guard_bi() TO kanban_app;
GRANT EXECUTE ON FUNCTION project_module_defaults_guard_bi() TO kanban_app;
GRANT EXECUTE ON FUNCTION issues_apply_module_defaults_ai() TO kanban_app;
GRANT EXECUTE ON FUNCTION issue_assignees_guard_bi() TO kanban_app;
GRANT EXECUTE ON FUNCTION issue_labels_exclusive_bi() TO kanban_app;
GRANT EXECUTE ON FUNCTION issues_autosubscribe_creator_ai() TO kanban_app;
GRANT EXECUTE ON FUNCTION issue_assignees_autosubscribe_ai() TO kanban_app;
GRANT EXECUTE ON FUNCTION issue_subscriptions_guard_bi() TO kanban_app;
