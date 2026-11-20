-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

-- 1. Restore original allocate_issue_sequence
CREATE OR REPLACE FUNCTION allocate_issue_sequence(p_project_id uuid)
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

GRANT EXECUTE ON FUNCTION allocate_issue_sequence(uuid) TO kanban_app;
ALTER FUNCTION allocate_issue_sequence(uuid) OWNER TO kanban_migrator;

-- 2. Drop batch functions
DROP FUNCTION IF EXISTS allocate_issue_sequences(uuid, integer, boolean);
DROP FUNCTION IF EXISTS compute_agent_safe_sequence_batch(bigint, integer, boolean);

-- 3. Drop columns
ALTER TABLE workspace_settings DROP COLUMN IF EXISTS default_skip_loaded_sequence_numbers;
ALTER TABLE projects DROP COLUMN IF EXISTS skip_loaded_sequence_numbers;
