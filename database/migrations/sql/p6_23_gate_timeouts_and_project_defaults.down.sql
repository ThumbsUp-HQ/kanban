-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

-- 4. workflow_hook_invocations: drop index and deadline_at column
DROP INDEX IF EXISTS idx_workflow_hook_invocations_deadline_at_running;
ALTER TABLE workflow_hook_invocations DROP COLUMN IF EXISTS deadline_at;

-- 3. workflow_transition_hooks: drop constraint and timeout_ms column
ALTER TABLE workflow_transition_hooks DROP CONSTRAINT IF EXISTS chk_workflow_transition_hooks_timeout_ms;
ALTER TABLE workflow_transition_hooks DROP COLUMN IF EXISTS timeout_ms;

-- 2. projects: drop constraint and default_gate_timeout_ms column
ALTER TABLE projects DROP CONSTRAINT IF EXISTS chk_projects_default_gate_timeout_ms;
ALTER TABLE projects DROP COLUMN IF EXISTS default_gate_timeout_ms;

-- 1. agent_definitions: clamp timeout_ms > 300000 to 300000, restore 1000..300000 constraint
UPDATE agent_definitions SET timeout_ms = 300000 WHERE timeout_ms > 300000;
ALTER TABLE agent_definitions
    DROP CONSTRAINT IF EXISTS chk_agent_definitions_timeout_ms,
    DROP CONSTRAINT IF EXISTS agent_definitions_timeout_ms_check,
    ADD CONSTRAINT agent_definitions_timeout_ms_check CHECK (timeout_ms BETWEEN 1000 AND 300000);
