-- Migration: p3_09b_issue_delete_blast_radius (down)
-- Drop Security Definer helpers for issue blast radius calculation and child unparenting under RLS (KB-P3-09b)

REVOKE EXECUTE ON FUNCTION unparent_issue_children_privileged(uuid, uuid) FROM kanban_app;
REVOKE EXECUTE ON FUNCTION get_issue_blast_radius_privileged(uuid, uuid) FROM kanban_app;

DROP FUNCTION IF EXISTS unparent_issue_children_privileged(uuid, uuid);
DROP FUNCTION IF EXISTS get_issue_blast_radius_privileged(uuid, uuid);
