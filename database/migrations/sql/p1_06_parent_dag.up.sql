-- Migration: p1_06_parent_dag (up)
-- Parent DAG trigger with FOR UPDATE ancestor locks and ltree ancestry

-- 1. Helper function to create ltree label from UUID
CREATE OR REPLACE FUNCTION issue_ltree_label(p_id uuid)
RETURNS ltree
LANGUAGE sql
IMMUTABLE PARALLEL SAFE
AS $$
    SELECT text2ltree(replace(p_id::text, '-', ''));
$$;

GRANT EXECUTE ON FUNCTION issue_ltree_label(uuid) TO kanban_app;
GRANT EXECUTE ON FUNCTION issue_ltree_label(uuid) TO app_rls_reader;

-- 2. Schema additions: GiST index and depth check constraint
CREATE INDEX issues_ancestry_gist ON issues USING gist (ancestry_path);
ALTER TABLE issues ADD CONSTRAINT issues_ancestry_depth_chk CHECK (nlevel(ancestry_path) BETWEEN 1 AND 6);

-- 3. Replace issues_validate_biu function body to remove KB-P1-05 simple path logic
-- (ancestry path is now exclusively managed by issues_parent_dag_biu and issues_parent_dag_au)
CREATE OR REPLACE FUNCTION issues_validate_biu()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_project projects%ROWTYPE;
    v_object objects%ROWTYPE;
    v_state workflow_states%ROWTYPE;
    v_priority project_priorities%ROWTYPE;
BEGIN
    -- 1. On UPDATE: sequence_id and project_id are immutable
    IF TG_OP = 'UPDATE' THEN
        IF NEW.sequence_id IS DISTINCT FROM OLD.sequence_id OR NEW.project_id IS DISTINCT FROM OLD.project_id THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'ISSUE_KEY_IMMUTABLE';
        END IF;
    END IF;

    -- 2. Verify project exists and workspace matches
    SELECT * INTO v_project FROM projects WHERE id = NEW.project_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'PROJECT_NOT_FOUND';
    END IF;

    IF NEW.workspace_id <> v_project.workspace_id THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'ISSUE_WORKSPACE_MISMATCH';
    END IF;

    -- 3. Verify sequence_id has been allocated
    IF NEW.sequence_id > v_project.issue_seq_counter THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'ISSUE_SEQUENCE_NOT_ALLOCATED';
    END IF;

    -- 4. Verify spine object matches
    SELECT * INTO v_object FROM objects WHERE id = NEW.id;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'ISSUE_SPINE_NOT_FOUND';
    END IF;

    IF v_object.project_id IS DISTINCT FROM NEW.project_id
       OR v_object.canonical_key <> (v_project.identifier || '-' || NEW.sequence_id::text) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'ISSUE_SPINE_MISMATCH';
    END IF;

    -- 5. Verify state_id and priority_id belong to NEW.project_id
    SELECT * INTO v_state FROM workflow_states WHERE id = NEW.state_id;
    IF NOT FOUND OR v_state.project_id <> NEW.project_id THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'ISSUE_STATE_PROJECT_MISMATCH';
    END IF;

    SELECT * INTO v_priority FROM project_priorities WHERE id = NEW.priority_id;
    IF NOT FOUND OR v_priority.project_id <> NEW.project_id THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'ISSUE_PRIORITY_PROJECT_MISMATCH';
    END IF;

    RETURN NEW;
END;
$$;

-- 4. BEFORE INSERT OR UPDATE OF parent_issue_id trigger function
CREATE OR REPLACE FUNCTION issues_parent_dag_biu()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_parent_path ltree;
    v_parent_project_id uuid;
    v_subtree_height integer := 0;
BEGIN
    -- 1. Root case
    IF NEW.parent_issue_id IS NULL THEN
        NEW.ancestry_path := issue_ltree_label(NEW.id);
        RETURN NEW;
    END IF;

    -- 2. Self-reference check
    IF NEW.parent_issue_id = NEW.id THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'PARENT_SELF_REFERENCE';
    END IF;

    -- 3. Lock ancestors top-down to avoid lock-order inversion
    SELECT ancestry_path, project_id
      INTO v_parent_path, v_parent_project_id
      FROM issues
     WHERE id = NEW.parent_issue_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'PARENT_NOT_FOUND';
    END IF;

    PERFORM 1
       FROM issues
      WHERE ancestry_path @> v_parent_path
      ORDER BY nlevel(ancestry_path)
        FOR UPDATE;

    -- Re-read parent path under lock
    SELECT ancestry_path, project_id
      INTO v_parent_path, v_parent_project_id
      FROM issues
     WHERE id = NEW.parent_issue_id;

    -- 4. Cross-project check
    IF v_parent_project_id <> NEW.project_id THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'PARENT_CROSS_PROJECT';
    END IF;

    -- 5. Cycle check
    IF v_parent_path ~ ('*.' || replace(NEW.id::text, '-', '') || '.*')::lquery THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'PARENT_CYCLE';
    END IF;

    -- 6. Depth check
    IF TG_OP = 'UPDATE' THEN
        SELECT COALESCE(max(nlevel(ancestry_path)) - nlevel(OLD.ancestry_path), 0)
          INTO v_subtree_height
          FROM issues
         WHERE ancestry_path <@ OLD.ancestry_path;
    ELSE
        v_subtree_height := 0;
    END IF;

    IF (nlevel(v_parent_path) + 1 + v_subtree_height) > 6 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'PARENT_MAX_DEPTH_EXCEEDED';
    END IF;

    -- 7. Compute new ancestry path
    NEW.ancestry_path := v_parent_path || issue_ltree_label(NEW.id);
    RETURN NEW;
END;
$$;

CREATE TRIGGER issues_parent_dag_biu_trg
BEFORE INSERT OR UPDATE OF parent_issue_id ON issues
FOR EACH ROW
EXECUTE FUNCTION issues_parent_dag_biu();

COMMENT ON TRIGGER issues_parent_dag_biu_trg ON issues IS
  'Enforces tree hierarchy, acquires top-down FOR UPDATE ancestor locks, and rejects cycles and depths > 6. Concurrent opposite reparenting may raise 40P01 deadlock_detected which safely aborts one transaction.';

-- 5. AFTER UPDATE OF parent_issue_id trigger function to rebase descendants
CREATE OR REPLACE FUNCTION issues_parent_dag_au()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.ancestry_path = NEW.ancestry_path THEN
        RETURN NEW;
    END IF;
    UPDATE issues
       SET ancestry_path = NEW.ancestry_path || subpath(ancestry_path, nlevel(OLD.ancestry_path))
     WHERE ancestry_path <@ OLD.ancestry_path AND id <> NEW.id;
    RETURN NEW;
END;
$$;

CREATE TRIGGER issues_parent_dag_au_trg
AFTER UPDATE OF parent_issue_id ON issues
FOR EACH ROW
WHEN (OLD.parent_issue_id IS DISTINCT FROM NEW.parent_issue_id)
EXECUTE FUNCTION issues_parent_dag_au();
