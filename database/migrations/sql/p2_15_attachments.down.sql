-- Migration: p2_15_attachments (down)
-- Revert attachments table, policies, triggers, and functions.

DROP TRIGGER IF EXISTS attachments_workspace_biu_trg ON attachments;
DROP FUNCTION IF EXISTS attachments_workspace_biu();

DROP POLICY IF EXISTS attachments_delete_rls ON attachments;
DROP POLICY IF EXISTS attachments_update_rls ON attachments;
DROP POLICY IF EXISTS attachments_insert_rls ON attachments;
DROP POLICY IF EXISTS attachments_select_rls ON attachments;

ALTER TABLE IF EXISTS attachments NO FORCE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS attachments DISABLE ROW LEVEL SECURITY;

DROP TABLE IF EXISTS attachments CASCADE;
