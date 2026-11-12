CREATE FUNCTION build_markdown_tsvector(md text) RETURNS tsvector
LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
DECLARE
    v_text text := coalesce(md, '');
BEGIN
    -- 1. Remove fence delimiter lines and their info strings
    v_text := regexp_replace(v_text, '(?m)^\s{0,3}(```|~~~).*$', '', 'g');
    -- 2. Images and links -> link text, reference definitions -> empty
    v_text := regexp_replace(v_text, '!\[([^\]]*)\]\([^)]*\)', '\1', 'g');
    v_text := regexp_replace(v_text, '\[([^\]]*)\]\([^)]*\)', '\1', 'g');
    v_text := regexp_replace(v_text, '(?m)^\s{0,3}\[[^\]]+\]:\s*\S+.*$', '', 'g');
    -- 3. Autolinks and bare URLs -> empty
    v_text := regexp_replace(v_text, '<https?://[^>]+>', '', 'g');
    v_text := regexp_replace(v_text, 'https?://\S+', '', 'g');
    -- 4. Markdown punctuation -> space
    v_text := regexp_replace(v_text, '[#*_>`|~]', ' ', 'g');
    -- 5. Return tsvector
    RETURN to_tsvector('english'::regconfig, v_text);
END;
$$;

CREATE TABLE issues (
    id                          UUID PRIMARY KEY,
    object_type                 object_kind NOT NULL DEFAULT 'issue' CHECK (object_type = 'issue'),
    workspace_id                UUID NOT NULL,
    project_id                  UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    sequence_id                 BIGINT NOT NULL,
    summary                     TEXT NOT NULL CHECK (char_length(btrim(summary)) BETWEEN 1 AND 500),
    description_markdown        TEXT NOT NULL DEFAULT '' CHECK (octet_length(description_markdown) <= 1048576),
    description_sha256          BYTEA GENERATED ALWAYS AS (digest(description_markdown, 'sha256')) STORED,
    state_id                    UUID NOT NULL REFERENCES workflow_states(id),
    pending_transition_exec_id  UUID,
    priority_id                 UUID NOT NULL REFERENCES project_priorities(id),
    created_by_id               UUID NOT NULL REFERENCES users(id),
    original_created_by_id      UUID NOT NULL REFERENCES users(id),
    creator_modified_by_id      UUID REFERENCES users(id),
    creator_modified_at         TIMESTAMPTZ,
    start_date                  DATE,
    due_date                    DATE,
    cycle_id                    UUID,
    parent_issue_id             UUID REFERENCES issues(id) ON DELETE SET NULL,
    ancestry_path               ltree NOT NULL,
    board_rank                  TEXT COLLATE "C" NOT NULL,
    search_tsv                  tsvector GENERATED ALWAYS AS (
                                    setweight(to_tsvector('english', coalesce(summary, '')), 'A') ||
                                    setweight(build_markdown_tsvector(description_markdown), 'B')
                                ) STORED,
    CHECK (due_date IS NULL OR start_date IS NULL OR due_date >= start_date),
    UNIQUE (project_id, sequence_id),
    FOREIGN KEY (id, object_type) REFERENCES objects (id, object_type) ON DELETE RESTRICT
);

CREATE INDEX issues_search_tsv_gin ON issues USING gin (search_tsv);
CREATE INDEX issues_project_rank_idx ON issues (project_id, state_id, board_rank COLLATE "C");
CREATE INDEX issues_parent_idx ON issues (parent_issue_id) WHERE parent_issue_id IS NOT NULL;

CREATE FUNCTION allocate_issue_sequence(p_project_id uuid)
RETURNS bigint LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
    v_seq bigint;
BEGIN
    UPDATE projects SET issue_seq_counter = issue_seq_counter + 1
     WHERE id = p_project_id RETURNING issue_seq_counter INTO v_seq;
    IF v_seq IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'PROJECT_NOT_FOUND';
    END IF;
    RETURN v_seq;
END;
$$;

COMMENT ON FUNCTION allocate_issue_sequence(uuid) IS
  'Allocates the next atomic sequence_id for an issue within a project using row locking on projects. '
  'Gaps after transaction rollback are acceptable. '
  'App flow: allocate_issue_sequence -> register_object -> INSERT INTO issues.';

CREATE FUNCTION issues_validate_biu() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_proj_ws uuid;
    v_proj_ident text;
    v_proj_counter bigint;
    v_obj_key text;
    v_obj_proj uuid;
    v_state_proj uuid;
    v_prio_proj uuid;
    v_parent_path ltree;
BEGIN
    -- Immutability on UPDATE
    IF TG_OP = 'UPDATE' THEN
        IF NEW.sequence_id IS DISTINCT FROM OLD.sequence_id OR NEW.project_id IS DISTINCT FROM OLD.project_id THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'ISSUE_KEY_IMMUTABLE';
        END IF;
    END IF;

    -- Project existence and workspace verification
    SELECT workspace_id, identifier, issue_seq_counter
      INTO v_proj_ws, v_proj_ident, v_proj_counter
      FROM projects WHERE id = NEW.project_id;

    IF v_proj_ws IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'PROJECT_NOT_FOUND';
    END IF;

    IF NEW.workspace_id <> v_proj_ws THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'ISSUE_WORKSPACE_MISMATCH';
    END IF;

    -- Sequence allocated check
    IF NEW.sequence_id > v_proj_counter THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'ISSUE_SEQUENCE_NOT_ALLOCATED';
    END IF;

    -- Objects spine matching
    SELECT canonical_key, project_id
      INTO v_obj_key, v_obj_proj
      FROM objects WHERE id = NEW.id;

    IF v_obj_key IS NULL OR v_obj_key <> (v_proj_ident || '-' || NEW.sequence_id::text) OR v_obj_proj IS DISTINCT FROM NEW.project_id THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'ISSUE_SPINE_MISMATCH';
    END IF;

    -- State and Priority project matching
    SELECT project_id INTO v_state_proj FROM workflow_states WHERE id = NEW.state_id;
    IF v_state_proj IS NULL OR v_state_proj <> NEW.project_id THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'ISSUE_STATE_PROJECT_MISMATCH';
    END IF;

    SELECT project_id INTO v_prio_proj FROM project_priorities WHERE id = NEW.priority_id;
    IF v_prio_proj IS NULL OR v_prio_proj <> NEW.project_id THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'ISSUE_PRIORITY_PROJECT_MISMATCH';
    END IF;

    -- Ancestry path calculation on INSERT
    IF TG_OP = 'INSERT' THEN
        IF NEW.parent_issue_id IS NULL THEN
            NEW.ancestry_path := text2ltree(replace(NEW.id::text, '-', ''));
        ELSE
            SELECT ancestry_path INTO v_parent_path FROM issues WHERE id = NEW.parent_issue_id;
            IF v_parent_path IS NULL THEN
                RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'PARENT_ISSUE_NOT_FOUND';
            END IF;
            NEW.ancestry_path := v_parent_path || text2ltree(replace(NEW.id::text, '-', ''));
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER issues_validate_biu_trg
BEFORE INSERT OR UPDATE ON issues
FOR EACH ROW EXECUTE FUNCTION issues_validate_biu();

GRANT EXECUTE ON FUNCTION build_markdown_tsvector(text) TO kanban_app, app_rls_reader;
GRANT EXECUTE ON FUNCTION allocate_issue_sequence(uuid) TO kanban_app;
GRANT EXECUTE ON FUNCTION issues_validate_biu() TO kanban_app;

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE issues TO kanban_app;
GRANT SELECT ON TABLE issues TO app_rls_reader;
