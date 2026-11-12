-- Migration Downgrade: p3_01b_workflow_state_wip_limits (KB-P3-01b)
-- Revert soft/hard WIP limits and ordering constraint from workflow_states.
-- Restore project_labels INSERT policy to ADMIN capability (mask 64).

DROP POLICY IF EXISTS project_labels_insert_rls ON project_labels;
CREATE POLICY project_labels_insert_rls ON project_labels
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(project_id, 64)
    );

ALTER TABLE workflow_states
  DROP CONSTRAINT IF EXISTS wip_soft_le_hard,
  DROP COLUMN IF EXISTS wip_hard_limit,
  DROP COLUMN IF EXISTS wip_soft_limit;
