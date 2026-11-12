-- Table definition for issues
                                                                                                                            Table "public.issues"
           Column           |           Type           | Collation | Nullable |                                                                                           Default                                                                                            
----------------------------+--------------------------+-----------+----------+----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
 id                         | uuid                     |           | not null | 
 object_type                | object_kind              |           | not null | 'issue'::object_kind
 workspace_id               | uuid                     |           | not null | 
 project_id                 | uuid                     |           | not null | 
 sequence_id                | bigint                   |           | not null | 
 summary                    | text                     |           | not null | 
 description_markdown       | text                     |           | not null | ''::text
 description_sha256         | bytea                    |           |          | generated always as (digest(description_markdown, 'sha256'::text)) stored
 state_id                   | uuid                     |           | not null | 
 pending_transition_exec_id | uuid                     |           |          | 
 priority_id                | uuid                     |           | not null | 
 created_by_id              | uuid                     |           | not null | 
 original_created_by_id     | uuid                     |           | not null | 
 creator_modified_by_id     | uuid                     |           |          | 
 creator_modified_at        | timestamp with time zone |           |          | 
 start_date                 | date                     |           |          | 
 due_date                   | date                     |           |          | 
 cycle_id                   | uuid                     |           |          | 
 parent_issue_id            | uuid                     |           |          | 
 ancestry_path              | ltree                    |           | not null | 
 board_rank                 | text                     | C         | not null | 
 search_tsv                 | tsvector                 |           |          | generated always as (setweight(to_tsvector('english'::regconfig, COALESCE(summary, ''::text)), 'A'::"char") || setweight(build_markdown_tsvector(description_markdown), 'B'::"char")) stored
Indexes:
    "issues_pkey" PRIMARY KEY, btree (id)
    "issues_ancestry_gist" gist (ancestry_path)
    "issues_parent_idx" btree (parent_issue_id) WHERE parent_issue_id IS NOT NULL
    "issues_project_id_sequence_id_key" UNIQUE CONSTRAINT, btree (project_id, sequence_id)
    "issues_project_rank_idx" btree (project_id, state_id, board_rank)
    "issues_search_tsv_gin" gin (search_tsv)
Check constraints:
    "issues_ancestry_depth_chk" CHECK (nlevel(ancestry_path) >= 1 AND nlevel(ancestry_path) <= 6)
    "issues_check" CHECK (due_date IS NULL OR start_date IS NULL OR due_date >= start_date)
    "issues_description_markdown_check" CHECK (octet_length(description_markdown) <= 1048576)
    "issues_object_type_check" CHECK (object_type = 'issue'::object_kind)
    "issues_summary_check" CHECK (char_length(btrim(summary)) >= 1 AND char_length(btrim(summary)) <= 500)
Foreign-key constraints:
    "issues_created_by_id_fkey" FOREIGN KEY (created_by_id) REFERENCES users(id)
    "issues_creator_modified_by_id_fkey" FOREIGN KEY (creator_modified_by_id) REFERENCES users(id)
    "issues_id_object_type_fkey" FOREIGN KEY (id, object_type) REFERENCES objects(id, object_type) ON DELETE RESTRICT
    "issues_original_created_by_id_fkey" FOREIGN KEY (original_created_by_id) REFERENCES users(id)
    "issues_parent_issue_id_fkey" FOREIGN KEY (parent_issue_id) REFERENCES issues(id) ON DELETE SET NULL
    "issues_priority_id_fkey" FOREIGN KEY (priority_id) REFERENCES project_priorities(id)
    "issues_project_id_fkey" FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE RESTRICT
    "issues_state_id_fkey" FOREIGN KEY (state_id) REFERENCES workflow_states(id)
Referenced by:
    TABLE "issues" CONSTRAINT "issues_parent_issue_id_fkey" FOREIGN KEY (parent_issue_id) REFERENCES issues(id) ON DELETE SET NULL
Triggers:
    issues_parent_dag_au_trg AFTER UPDATE OF parent_issue_id ON issues FOR EACH ROW WHEN (old.ancestry_path IS DISTINCT FROM new.ancestry_path) EXECUTE FUNCTION issues_parent_dag_au()
    issues_parent_dag_biu_trg BEFORE INSERT OR UPDATE OF parent_issue_id ON issues FOR EACH ROW EXECUTE FUNCTION issues_parent_dag_biu()
    issues_validate_biu_trg BEFORE INSERT OR UPDATE ON issues FOR EACH ROW EXECUTE FUNCTION issues_validate_biu()


-- Function: issue_ltree_label
CREATE OR REPLACE FUNCTION public.issue_ltree_label(p_id uuid)
 RETURNS ltree
 LANGUAGE sql
 IMMUTABLE PARALLEL SAFE
AS $function$
    SELECT text2ltree(replace(p_id::text, '-', ''));
$function$

-- Function: issues_parent_dag_biu
CREATE OR REPLACE FUNCTION public.issues_parent_dag_biu()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
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
$function$

-- Function: issues_parent_dag_au
CREATE OR REPLACE FUNCTION public.issues_parent_dag_au()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
BEGIN
    UPDATE issues
       SET ancestry_path = NEW.ancestry_path || subpath(ancestry_path, nlevel(OLD.ancestry_path))
     WHERE ancestry_path <@ OLD.ancestry_path AND id <> NEW.id;
    RETURN NEW;
END;
$function$

-- Function: issues_validate_biu
CREATE OR REPLACE FUNCTION public.issues_validate_biu()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
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
$function$
