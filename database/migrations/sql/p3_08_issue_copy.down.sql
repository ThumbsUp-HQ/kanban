-- Migration: p3_08_issue_copy (down)
-- Drop issues_get_copy_subtrees function

DROP FUNCTION IF EXISTS issues_get_copy_subtrees(uuid);
