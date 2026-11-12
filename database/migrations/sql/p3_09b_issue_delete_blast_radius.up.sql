-- Migration: p3_09b_issue_delete_blast_radius (up)
-- Security Definer helpers for issue blast radius calculation and child unparenting under RLS (KB-P3-09b)

CREATE OR REPLACE FUNCTION get_issue_blast_radius_privileged(
    p_issue_id uuid,
    p_workspace_id uuid DEFAULT NULL
)
RETURNS TABLE (
    child_ids uuid[],
    inbound_link_ids uuid[],
    outbound_link_ids uuid[],
    comment_count integer,
    attachment_count integer
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
#variable_conflict use_column
DECLARE
    v_ws uuid;
    v_children uuid[];
    v_inbound uuid[];
    v_outbound uuid[];
    v_comments integer;
    v_attachments integer;
BEGIN
    SELECT workspace_id INTO v_ws
    FROM objects
    WHERE id = p_issue_id AND deleted_at IS NULL;

    IF v_ws IS NULL THEN
        RETURN;
    END IF;

    IF p_workspace_id IS NOT NULL AND v_ws <> p_workspace_id THEN
        RETURN;
    END IF;

    -- Direct active child issues in the workspace
    SELECT coalesce(array_agg(i.id ORDER BY i.id), ARRAY[]::uuid[])
    INTO v_children
    FROM issues i
    JOIN objects o ON o.id = i.id
    WHERE i.parent_issue_id = p_issue_id
      AND o.workspace_id = v_ws
      AND o.deleted_at IS NULL;

    -- Inbound active object links
    SELECT coalesce(array_agg(l.id ORDER BY l.id), ARRAY[]::uuid[])
    INTO v_inbound
    FROM object_links l
    WHERE l.target_id = p_issue_id
      AND l.workspace_id = v_ws
      AND l.link_state = 'ACTIVE';

    -- Outbound active object links
    SELECT coalesce(array_agg(l.id ORDER BY l.id), ARRAY[]::uuid[])
    INTO v_outbound
    FROM object_links l
    WHERE l.source_id = p_issue_id
      AND l.workspace_id = v_ws
      AND l.link_state = 'ACTIVE';

    -- Comments (active/not deleted)
    SELECT count(*)::integer
    INTO v_comments
    FROM issue_comments c
    JOIN objects o ON o.id = c.id
    WHERE c.issue_id = p_issue_id
      AND o.workspace_id = v_ws
      AND o.deleted_at IS NULL;

    -- Attachments
    SELECT count(*)::integer
    INTO v_attachments
    FROM attachments a
    WHERE a.issue_id = p_issue_id
      AND a.workspace_id = v_ws;

    RETURN QUERY SELECT
        v_children,
        v_inbound,
        v_outbound,
        v_comments,
        v_attachments;
END;
$$;

CREATE OR REPLACE FUNCTION unparent_issue_children_privileged(
    p_issue_id uuid,
    p_workspace_id uuid DEFAULT NULL
)
RETURNS uuid[]
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
#variable_conflict use_column
DECLARE
    v_ws uuid;
    v_unparented_ids uuid[];
BEGIN
    SELECT workspace_id INTO v_ws
    FROM objects
    WHERE id = p_issue_id;

    IF v_ws IS NULL THEN
        RETURN ARRAY[]::uuid[];
    END IF;

    IF p_workspace_id IS NOT NULL AND v_ws <> p_workspace_id THEN
        RETURN ARRAY[]::uuid[];
    END IF;

    WITH updated AS (
        UPDATE issues i
        SET parent_issue_id = NULL
        FROM objects o
        WHERE i.id = o.id
          AND i.parent_issue_id = p_issue_id
          AND o.workspace_id = v_ws
          AND o.deleted_at IS NULL
        RETURNING i.id
    )
    SELECT coalesce(array_agg(id ORDER BY id), ARRAY[]::uuid[])
    INTO v_unparented_ids
    FROM updated;

    RETURN v_unparented_ids;
END;
$$;

GRANT EXECUTE ON FUNCTION get_issue_blast_radius_privileged(uuid, uuid) TO kanban_app;
GRANT EXECUTE ON FUNCTION unparent_issue_children_privileged(uuid, uuid) TO kanban_app;
