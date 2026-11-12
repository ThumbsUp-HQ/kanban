-- Migration: p3_01b_workflow_state_wip_limits (KB-P3-01b)
-- Add soft/hard WIP limits and ordering constraint to workflow_states.
-- Update project_labels INSERT policy to permit EDIT capability (mask 4) per S7.2 item 8i.

ALTER TABLE workflow_states
  ADD COLUMN wip_soft_limit INTEGER CHECK (wip_soft_limit IS NULL OR wip_soft_limit BETWEEN 1 AND 999),
  ADD COLUMN wip_hard_limit INTEGER CHECK (wip_hard_limit IS NULL OR wip_hard_limit BETWEEN 1 AND 999),
  ADD CONSTRAINT wip_soft_le_hard CHECK (wip_soft_limit IS NULL OR wip_hard_limit IS NULL OR wip_soft_limit <= wip_hard_limit);

DROP POLICY IF EXISTS project_labels_insert_rls ON project_labels;
CREATE POLICY project_labels_insert_rls ON project_labels
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(project_id, 4)
    );
