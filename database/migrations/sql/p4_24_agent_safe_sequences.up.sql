-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

-- 1. Add skip_loaded_sequence_numbers columns
ALTER TABLE projects
    ADD COLUMN IF NOT EXISTS skip_loaded_sequence_numbers BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE workspace_settings
    ADD COLUMN IF NOT EXISTS default_skip_loaded_sequence_numbers BOOLEAN NOT NULL DEFAULT FALSE;

-- 2. Pure sequence computation function (IMMUTABLE PARALLEL SAFE)
CREATE OR REPLACE FUNCTION compute_agent_safe_sequence_batch(
    p_current_seq BIGINT,
    p_count INTEGER,
    p_skip_loaded BOOLEAN
)
RETURNS TABLE (
    allocated_sequences BIGINT[],
    skipped_sequences BIGINT[]
)
LANGUAGE plpgsql
IMMUTABLE
PARALLEL SAFE
AS $$
DECLARE
    c_max_skip_iterations CONSTANT INTEGER := 16;
    c_loaded_numbers CONSTANT BIGINT[] := ARRAY[13, 69, 88, 404, 420, 666, 1337, 1488];
    v_allocated BIGINT[] := '{}';
    v_skipped BIGINT[] := '{}';
    v_skip_count INTEGER := 0;
    v_seq BIGINT;
    v_skip BOOLEAN := COALESCE(p_skip_loaded, FALSE);
BEGIN
    IF p_count IS NULL OR p_count < 1 OR p_count > 1000 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'INVALID_SEQUENCE_COUNT';
    END IF;

    v_seq := COALESCE(p_current_seq, 0);

    WHILE cardinality(v_allocated) < p_count LOOP
        v_seq := v_seq + 1;
        IF v_skip AND (v_seq = ANY(c_loaded_numbers)) THEN
            v_skip_count := v_skip_count + 1;
            IF v_skip_count > c_max_skip_iterations THEN
                RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'SEQUENCE_SKIP_CEILING_EXCEEDED';
            END IF;
            v_skipped := array_append(v_skipped, v_seq);
        ELSE
            v_allocated := array_append(v_allocated, v_seq);
        END IF;
    END LOOP;

    allocated_sequences := v_allocated;
    skipped_sequences := v_skipped;
    RETURN NEXT;
END;
$$;

GRANT EXECUTE ON FUNCTION compute_agent_safe_sequence_batch(BIGINT, INTEGER, BOOLEAN) TO kanban_app, app_rls_reader;
ALTER FUNCTION compute_agent_safe_sequence_batch(BIGINT, INTEGER, BOOLEAN) OWNER TO kanban_migrator;

-- 3. Batch sequence allocator acquiring FOR UPDATE on projects
CREATE OR REPLACE FUNCTION allocate_issue_sequences(
    p_project_id UUID,
    p_count INTEGER DEFAULT 1,
    p_emit_activity BOOLEAN DEFAULT TRUE
)
RETURNS TABLE (
    allocated_sequences BIGINT[],
    skipped_sequences BIGINT[]
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_ws_id UUID;
    v_identifier TEXT;
    v_curr_seq BIGINT;
    v_skip_loaded BOOLEAN;
    v_allocated BIGINT[];
    v_skipped BIGINT[];
    v_new_counter BIGINT;
BEGIN
    SELECT workspace_id, identifier, issue_seq_counter, skip_loaded_sequence_numbers
      INTO v_ws_id, v_identifier, v_curr_seq, v_skip_loaded
      FROM public.projects
     WHERE id = p_project_id
       FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'PROJECT_NOT_FOUND';
    END IF;

    SELECT b.allocated_sequences, b.skipped_sequences
      INTO v_allocated, v_skipped
      FROM public.compute_agent_safe_sequence_batch(v_curr_seq, p_count, v_skip_loaded) b;

    v_new_counter := v_allocated[cardinality(v_allocated)];

    UPDATE public.projects
       SET issue_seq_counter = v_new_counter
     WHERE id = p_project_id;

    IF COALESCE(p_emit_activity, TRUE) AND cardinality(v_skipped) > 0 THEN
        PERFORM public.append_activity(
            v_ws_id,
            p_project_id,
            'project'::public.object_kind,
            NULL,
            'SEQUENCE_SKIPPED',
            jsonb_build_object(
                'project_key', v_identifier,
                'skipped_sequences', to_jsonb(v_skipped),
                'allocated_sequence', v_allocated[1],
                'reason', 'agent_safe_sequence_numbering'
            )
        );
    END IF;

    allocated_sequences := v_allocated;
    skipped_sequences := v_skipped;
    RETURN NEXT;
END;
$$;

GRANT EXECUTE ON FUNCTION allocate_issue_sequences(UUID, INTEGER, BOOLEAN) TO kanban_app;
ALTER FUNCTION allocate_issue_sequences(UUID, INTEGER, BOOLEAN) OWNER TO kanban_migrator;

-- 4. Backward-compatible delegate
CREATE OR REPLACE FUNCTION allocate_issue_sequence(p_project_id UUID)
RETURNS BIGINT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_allocated BIGINT[];
BEGIN
    SELECT a.allocated_sequences
      INTO v_allocated
      FROM public.allocate_issue_sequences(p_project_id, 1, TRUE) a;

    RETURN v_allocated[1];
END;
$$;

GRANT EXECUTE ON FUNCTION allocate_issue_sequence(UUID) TO kanban_app;
ALTER FUNCTION allocate_issue_sequence(UUID) OWNER TO kanban_migrator;
