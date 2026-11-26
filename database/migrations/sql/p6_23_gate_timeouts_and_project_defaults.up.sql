-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

-- 1. agent_definitions: raise timeout_ms max from 300000 to 600000 (10 minutes)
ALTER TABLE agent_definitions
    DROP CONSTRAINT IF EXISTS chk_agent_definitions_timeout_ms,
    DROP CONSTRAINT IF EXISTS agent_definitions_timeout_ms_check,
    ADD CONSTRAINT chk_agent_definitions_timeout_ms CHECK (timeout_ms BETWEEN 1000 AND 600000);

-- 2. projects: add optional default_gate_timeout_ms (1000..600000 ms)
ALTER TABLE projects
    ADD COLUMN IF NOT EXISTS default_gate_timeout_ms INTEGER NULL,
    DROP CONSTRAINT IF EXISTS chk_projects_default_gate_timeout_ms,
    ADD CONSTRAINT chk_projects_default_gate_timeout_ms CHECK (default_gate_timeout_ms IS NULL OR default_gate_timeout_ms BETWEEN 1000 AND 600000);

-- 3. workflow_transition_hooks: add optional per-hook timeout_ms override (1000..600000 ms)
ALTER TABLE workflow_transition_hooks
    ADD COLUMN IF NOT EXISTS timeout_ms INTEGER NULL,
    DROP CONSTRAINT IF EXISTS chk_workflow_transition_hooks_timeout_ms,
    ADD CONSTRAINT chk_workflow_transition_hooks_timeout_ms CHECK (timeout_ms IS NULL OR timeout_ms BETWEEN 1000 AND 600000);

-- 4. workflow_hook_invocations: add deadline_at timestamp and partial index for running invocations
ALTER TABLE workflow_hook_invocations
    ADD COLUMN IF NOT EXISTS deadline_at TIMESTAMPTZ NULL;

CREATE INDEX IF NOT EXISTS idx_workflow_hook_invocations_deadline_at_running
    ON workflow_hook_invocations (deadline_at)
    WHERE status = 'running';
