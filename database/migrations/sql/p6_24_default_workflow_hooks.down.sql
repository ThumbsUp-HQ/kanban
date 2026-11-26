-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

-- 2. Drop inherited_from_template_id column and index on workflow_transition_hooks
DROP INDEX IF EXISTS idx_workflow_transition_hooks_inherited_from_template_id;
ALTER TABLE workflow_transition_hooks DROP COLUMN IF EXISTS inherited_from_template_id;

-- 1. Drop default_workflow_hooks table and index
DROP INDEX IF EXISTS uq_default_workflow_hooks_scope_ws_name;
DROP TABLE IF EXISTS default_workflow_hooks CASCADE;
