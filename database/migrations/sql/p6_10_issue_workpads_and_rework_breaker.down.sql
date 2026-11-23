-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

ALTER TABLE issues
    DROP COLUMN IF EXISTS rework_tripped_at,
    DROP COLUMN IF EXISTS rework_rejection_streak;

ALTER TABLE workflow_transition_hooks
    DROP COLUMN IF EXISTS max_rework_attempts;

DROP TABLE IF EXISTS issue_workpads CASCADE;
