-- Migration: p1_06_parent_dag (down)
-- Drops parent DAG triggers and restores KB-P1-05 path logic

DROP TRIGGER IF EXISTS issues_parent_dag_au_trg ON issues;
DROP FUNCTION IF EXISTS issues_parent_dag_au();

DROP TRIGGER IF EXISTS issues_parent_dag_biu_trg ON issues;
DROP FUNCTION IF EXISTS issues_parent_dag_biu();

DROP INDEX IF EXISTS issues_ancestry_gist;
ALTER TABLE issues DROP CONSTRAINT IF EXISTS issues_ancestry_depth_chk;

DROP FUNCTION IF EXISTS issue_ltree_label(uuid);

-- Restore issues_validate_biu from KB-P1-05
CREATE OR REPLACE FUNCTION issues_validate_biu()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_project projects%ROWTYPE;
    v_object objects%ROWTYPE;
    v_state workflow_states%ROWTYPE;
    v_priority project_priorities%ROWTYPE;
    v_parent issues%ROWTYPE;
BEGIN
    -- 1. Verify project exists and workspace matches
    SELECT * INTO v_project FROM projects WHERE id = NEW.project_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'PROJECT_NOT_FOUND';
    END IF;

    IF NEW.workspace_id <> v_project.workspace_id THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'ISSUE_WORKSPACE_MISMATCH';
    END IF;

    -- 2. Verify spine object matches
    SELECT * INTO v_object FROM objects WHERE id = NEW.id;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'ISSUE_SPINE_NOT_FOUND';
    END IF;

    IF v_object.project_id IS DISTINCT FROM NEW.project_id
       OR v_object.canonical_key <> (v_project.identifier || '-' || NEW.sequence_id::text) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'ISSUE_SPINE_MISMATCH';
    END IF;

    -- 3. Verify sequence_id has been allocated
    IF NEW.sequence_id > v_project.issue_seq_counter THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'ISSUE_SEQUENCE_NOT_ALLOCATED';
    END IF;

    -- 4. Verify state_id and priority_id belong to NEW.project_id
    SELECT * INTO v_state FROM workflow_states WHERE id = NEW.state_id;
    IF NOT FOUND OR v_state.project_id <> NEW.project_id THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'ISSUE_STATE_PROJECT_MISMATCH';
    END IF;

    SELECT * INTO v_priority FROM project_priorities WHERE id = NEW.priority_id;
    IF NOT FOUND OR v_priority.project_id <> NEW.project_id THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'ISSUE_PRIORITY_PROJECT_MISMATCH';
    END IF;

    -- 5. On UPDATE: sequence_id and project_id are immutable
    IF TG_OP = 'UPDATE' THEN
        IF NEW.sequence_id <> OLD.sequence_id OR NEW.project_id <> OLD.project_id THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'ISSUE_KEY_IMMUTABLE';
        END IF;
    END IF;

    -- 6. On INSERT: compute ancestry_path (KB-P1-05 baseline logic)
    IF TG_OP = 'INSERT' THEN
        IF NEW.parent_issue_id IS NULL THEN
            NEW.ancestry_path := text2ltree(replace(NEW.id::text, '-', ''));
        ELSE
            SELECT * INTO v_parent FROM issues WHERE id = NEW.parent_issue_id;
            IF NOT FOUND THEN
                RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'PARENT_NOT_FOUND';
            END IF;
            NEW.ancestry_path := v_parent.ancestry_path || text2ltree(replace(NEW.id::text, '-', ''));
        END IF;
    END IF;

    RETURN NEW;
END;
$$;
