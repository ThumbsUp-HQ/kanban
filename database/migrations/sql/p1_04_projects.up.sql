CREATE TABLE projects (
    id                      UUID PRIMARY KEY,
    object_type             object_kind NOT NULL DEFAULT 'project' CHECK (object_type = 'project'),
    workspace_id            UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    identifier              TEXT NOT NULL CHECK (identifier ~ '^[A-Z][A-Z0-9]{1,9}$'),
    name                    TEXT NOT NULL,
    description_markdown    TEXT NOT NULL DEFAULT '' CHECK (octet_length(description_markdown) <= 524288),
    modules_enabled         BOOLEAN NOT NULL DEFAULT FALSE,
    issue_seq_counter       BIGINT NOT NULL DEFAULT 0,
    auto_archive_days       INTEGER CHECK (auto_archive_days IS NULL OR auto_archive_days BETWEEN 1 AND 365),
    UNIQUE (workspace_id, identifier),
    FOREIGN KEY (id, object_type) REFERENCES objects (id, object_type) ON DELETE RESTRICT
);

ALTER TABLE objects ADD CONSTRAINT objects_project_fk
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED;

CREATE FUNCTION projects_spine_match_biu() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_workspace_id UUID;
    v_canonical_key TEXT;
BEGIN
    SELECT workspace_id, canonical_key
      INTO v_workspace_id, v_canonical_key
      FROM objects
     WHERE id = NEW.id AND object_type = 'project';

    IF NOT FOUND OR v_workspace_id <> NEW.workspace_id OR v_canonical_key <> NEW.identifier THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'PROJECT_SPINE_MISMATCH';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER projects_spine_match_biu_trg
    BEFORE INSERT OR UPDATE ON projects
    FOR EACH ROW EXECUTE FUNCTION projects_spine_match_biu();

CREATE FUNCTION projects_seq_guard_bu() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.issue_seq_counter < OLD.issue_seq_counter THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'ISSUE_SEQ_DECREASE_FORBIDDEN';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER projects_seq_guard_bu_trg
    BEFORE UPDATE ON projects
    FOR EACH ROW EXECUTE FUNCTION projects_seq_guard_bu();

CREATE TABLE workflow_states (
    id            UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id  UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    project_id    UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    name          TEXT NOT NULL CHECK (char_length(btrim(name)) BETWEEN 1 AND 100),
    state_group   TEXT NOT NULL CHECK (state_group IN ('backlog','unstarted','started','completed','cancelled')),
    color_hex     TEXT NOT NULL CHECK (color_hex ~ '^#[0-9A-Fa-f]{6}$'),
    sort_order    INTEGER NOT NULL DEFAULT 0,
    is_default    BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (project_id, name)
);

CREATE UNIQUE INDEX workflow_states_one_default ON workflow_states (project_id) WHERE is_default;

CREATE FUNCTION workflow_states_workspace_match_biu() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_project_workspace_id UUID;
BEGIN
    SELECT workspace_id INTO v_project_workspace_id FROM projects WHERE id = NEW.project_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'PROJECT_NOT_FOUND';
    END IF;
    IF NEW.workspace_id IS NULL THEN
        NEW.workspace_id := v_project_workspace_id;
    ELSIF NEW.workspace_id <> v_project_workspace_id THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'PROJECT_CHILD_WORKSPACE_MISMATCH';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER workflow_states_workspace_match_biu_trg
    BEFORE INSERT OR UPDATE ON workflow_states
    FOR EACH ROW EXECUTE FUNCTION workflow_states_workspace_match_biu();

CREATE TABLE project_priorities (
    id           UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    project_id   UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    slug         TEXT NOT NULL CHECK (slug ~ '^[a-z][a-z0-9_-]{0,31}$'),
    label        TEXT NOT NULL CHECK (char_length(btrim(label)) BETWEEN 1 AND 50),
    emoji        TEXT CHECK (emoji IS NULL OR char_length(emoji) BETWEEN 1 AND 8),
    color_hex    TEXT NOT NULL CHECK (color_hex ~ '^#[0-9A-Fa-f]{6}$'),
    sort_order   INTEGER NOT NULL,
    is_default   BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (project_id, slug)
);

CREATE UNIQUE INDEX project_priorities_one_default ON project_priorities (project_id) WHERE is_default;

CREATE FUNCTION project_priorities_workspace_match_biu() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_project_workspace_id UUID;
BEGIN
    SELECT workspace_id INTO v_project_workspace_id FROM projects WHERE id = NEW.project_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'PROJECT_NOT_FOUND';
    END IF;
    IF NEW.workspace_id IS NULL THEN
        NEW.workspace_id := v_project_workspace_id;
    ELSIF NEW.workspace_id <> v_project_workspace_id THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'PROJECT_CHILD_WORKSPACE_MISMATCH';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER project_priorities_workspace_match_biu_trg
    BEFORE INSERT OR UPDATE ON project_priorities
    FOR EACH ROW EXECUTE FUNCTION project_priorities_workspace_match_biu();

CREATE TABLE project_labels (
    id              UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    project_id      UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    name            TEXT NOT NULL CHECK (char_length(btrim(name)) BETWEEN 1 AND 100),
    color_hex       TEXT NOT NULL CHECK (color_hex ~ '^#[0-9A-Fa-f]{6}$'),
    exclusive_group TEXT CHECK (exclusive_group IS NULL OR exclusive_group ~ '^[a-z][a-z0-9_-]{0,31}$'),
    UNIQUE (project_id, name)
);

CREATE FUNCTION project_labels_workspace_match_biu() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_project_workspace_id UUID;
BEGIN
    SELECT workspace_id INTO v_project_workspace_id FROM projects WHERE id = NEW.project_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'PROJECT_NOT_FOUND';
    END IF;
    IF NEW.workspace_id IS NULL THEN
        NEW.workspace_id := v_project_workspace_id;
    ELSIF NEW.workspace_id <> v_project_workspace_id THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'PROJECT_CHILD_WORKSPACE_MISMATCH';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER project_labels_workspace_match_biu_trg
    BEFORE INSERT OR UPDATE ON project_labels
    FOR EACH ROW EXECUTE FUNCTION project_labels_workspace_match_biu();

CREATE FUNCTION projects_seed_defaults_ai() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
BEGIN
    INSERT INTO workflow_states (
        workspace_id, project_id, name, state_group, color_hex, sort_order, is_default
    ) VALUES
        (NEW.workspace_id, NEW.id, 'Backlog',     'backlog',   '#A3A3A3', 0, TRUE),
        (NEW.workspace_id, NEW.id, 'Todo',        'unstarted', '#3B82F6', 1, FALSE),
        (NEW.workspace_id, NEW.id, 'In Progress', 'started',   '#F59E0B', 2, FALSE),
        (NEW.workspace_id, NEW.id, 'Done',        'completed', '#16A34A', 3, FALSE),
        (NEW.workspace_id, NEW.id, 'Cancelled',   'cancelled', '#DC2626', 4, FALSE);

    INSERT INTO project_priorities (
        workspace_id, project_id, slug, label, emoji, color_hex, sort_order, is_default
    ) VALUES
        (NEW.workspace_id, NEW.id, 'urgent', 'Urgent', '🔥',   '#DC2626', 0, FALSE),
        (NEW.workspace_id, NEW.id, 'high',   'High',   '⚡',   '#F97316', 1, FALSE),
        (NEW.workspace_id, NEW.id, 'medium', 'Medium', '🔹',   '#EAB308', 2, FALSE),
        (NEW.workspace_id, NEW.id, 'low',    'Low',    '💤',   '#22C55E', 3, FALSE),
        (NEW.workspace_id, NEW.id, 'none',   'None',   NULL,   '#A3A3A3', 4, TRUE);

    RETURN NEW;
END;
$$;

CREATE TRIGGER projects_seed_defaults_ai_trg
    AFTER INSERT ON projects
    FOR EACH ROW EXECUTE FUNCTION projects_seed_defaults_ai();

REVOKE ALL ON FUNCTION projects_seed_defaults_ai() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION projects_seed_defaults_ai() TO kanban_app, kanban_migrator;

CREATE FUNCTION workflow_states_group_guard_bd() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_remaining INTEGER;
BEGIN
    IF OLD.state_group IN ('completed', 'cancelled') THEN
        SELECT count(*)
          INTO v_remaining
          FROM workflow_states
         WHERE project_id = OLD.project_id
           AND state_group = OLD.state_group
           AND id <> OLD.id;

        IF v_remaining = 0 THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'LAST_TERMINAL_STATE_REQUIRED';
        END IF;
    END IF;
    RETURN OLD;
END;
$$;

CREATE TRIGGER workflow_states_group_guard_bd_trg
    BEFORE DELETE ON workflow_states
    FOR EACH ROW EXECUTE FUNCTION workflow_states_group_guard_bd();
