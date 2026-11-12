-- Migration: p3_08_issue_copy (up)
-- SECURITY DEFINER function to collect issue descendant subtree for issue copying

CREATE OR REPLACE FUNCTION issues_get_copy_subtrees(
    p_root_id uuid
)
RETURNS TABLE (
    issue_id uuid,
    parent_issue_id uuid,
    rel_depth integer,
    summary text,
    description_markdown text,
    priority_id uuid,
    board_rank text,
    canonical_key text,
    is_readable boolean,
    is_skipped boolean
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_root_path ltree;
    r RECORD;
    v_skipped_ids uuid[] := '{}';
    v_can_view boolean;
    v_is_parent_skipped boolean;
BEGIN
    SELECT ancestry_path
      INTO v_root_path
      FROM issues
     WHERE id = p_root_id AND deleted_at IS NULL;

    IF NOT FOUND THEN
        RETURN;
    END IF;

    FOR r IN
        SELECT i.id,
               i.parent_issue_id,
               (nlevel(i.ancestry_path) - nlevel(v_root_path)) AS depth,
               i.summary,
               i.description_markdown,
               i.priority_id,
               i.board_rank,
               o.canonical_key
          FROM issues i
          JOIN objects o ON o.id = i.id
         WHERE i.ancestry_path <@ v_root_path
           AND i.id <> p_root_id
           AND i.deleted_at IS NULL
           AND (nlevel(i.ancestry_path) - nlevel(v_root_path)) <= 6
         ORDER BY nlevel(i.ancestry_path) ASC, i.board_rank ASC, i.sequence_id ASC
    LOOP
        v_is_parent_skipped := (r.parent_issue_id = ANY(v_skipped_ids));

        IF v_is_parent_skipped THEN
            v_skipped_ids := array_append(v_skipped_ids, r.id);
            issue_id := r.id;
            parent_issue_id := r.parent_issue_id;
            rel_depth := r.depth;
            summary := NULL;
            description_markdown := NULL;
            priority_id := NULL;
            board_rank := NULL;
            canonical_key := NULL;
            is_readable := FALSE;
            is_skipped := TRUE;
            RETURN NEXT;
        ELSE
            v_can_view := app_has_object_capability(r.id, 1);

            IF v_can_view THEN
                issue_id := r.id;
                parent_issue_id := r.parent_issue_id;
                rel_depth := r.depth;
                summary := r.summary;
                description_markdown := r.description_markdown;
                priority_id := r.priority_id;
                board_rank := r.board_rank;
                canonical_key := r.canonical_key;
                is_readable := TRUE;
                is_skipped := FALSE;
                RETURN NEXT;
            ELSE
                v_skipped_ids := array_append(v_skipped_ids, r.id);
                issue_id := r.id;
                parent_issue_id := r.parent_issue_id;
                rel_depth := r.depth;
                summary := NULL;
                description_markdown := NULL;
                priority_id := NULL;
                board_rank := NULL;
                canonical_key := NULL;
                is_readable := FALSE;
                is_skipped := TRUE;
                RETURN NEXT;
            END IF;
        END IF;
    END LOOP;
END;
$$;

GRANT EXECUTE ON FUNCTION issues_get_copy_subtrees(uuid) TO kanban_app, app_rls_reader;
