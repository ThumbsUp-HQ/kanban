-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

-- 1. Create default_workflow_hooks table
CREATE TABLE default_workflow_hooks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scope_kind TEXT NOT NULL CHECK (scope_kind IN ('system', 'workspace')),
    workspace_id UUID NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name TEXT NOT NULL CHECK (char_length(name) BETWEEN 1 AND 120),
    from_state_name TEXT NULL CHECK (from_state_name IS NULL OR char_length(from_state_name) BETWEEN 1 AND 80),
    to_state_name TEXT NOT NULL CHECK (char_length(to_state_name) BETWEEN 1 AND 80),
    hook_kind TEXT NOT NULL CHECK (hook_kind IN ('wasm_sync', 'agent_async', 'builtin')),
    sort_rank INTEGER NOT NULL DEFAULT 100 CHECK (sort_rank >= 0),
    is_enabled BOOLEAN NOT NULL DEFAULT true,
    wasm_module_sha256 BYTEA NULL,
    agent_definition_id UUID NULL REFERENCES agent_definitions(id) ON DELETE RESTRICT,
    agent_slug TEXT NULL CHECK (agent_slug IS NULL OR char_length(agent_slug) BETWEEN 1 AND 80),
    allowed_mutable_fields JSONB NOT NULL DEFAULT '[]'::jsonb,
    failure_policy TEXT NOT NULL DEFAULT 'fail_closed' CHECK (failure_policy IN ('fail_closed', 'fail_open_warn')),
    timeout_ms INTEGER NULL CHECK (timeout_ms IS NULL OR timeout_ms BETWEEN 1000 AND 600000),
    max_rework_attempts INTEGER NOT NULL DEFAULT 3 CHECK (max_rework_attempts BETWEEN 0 AND 20),
    created_by UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_default_workflow_hooks_scope CHECK (
        (scope_kind = 'system' AND workspace_id IS NULL) OR
        (scope_kind = 'workspace' AND workspace_id IS NOT NULL)
    )
);

CREATE INDEX idx_default_workflow_hooks_scope ON default_workflow_hooks (scope_kind, workspace_id);
CREATE INDEX idx_default_workflow_hooks_workspace_id ON default_workflow_hooks (workspace_id);

ALTER TABLE default_workflow_hooks ENABLE ROW LEVEL SECURITY;
ALTER TABLE default_workflow_hooks FORCE ROW LEVEL SECURITY;

CREATE POLICY default_workflow_hooks_select_rls ON default_workflow_hooks
    FOR SELECT USING (
        scope_kind = 'system' OR (scope_kind = 'workspace' AND workspace_id = app_current_workspace_id())
    );

CREATE POLICY default_workflow_hooks_insert_rls ON default_workflow_hooks
    FOR INSERT WITH CHECK (
        (scope_kind = 'workspace' AND workspace_id = app_current_workspace_id()) OR
        (scope_kind = 'system' AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN']))
    );

CREATE POLICY default_workflow_hooks_update_rls ON default_workflow_hooks
    FOR UPDATE USING (
        (scope_kind = 'workspace' AND workspace_id = app_current_workspace_id()) OR
        (scope_kind = 'system' AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN']))
    ) WITH CHECK (
        (scope_kind = 'workspace' AND workspace_id = app_current_workspace_id()) OR
        (scope_kind = 'system' AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN']))
    );

CREATE POLICY default_workflow_hooks_delete_rls ON default_workflow_hooks
    FOR DELETE USING (
        (scope_kind = 'workspace' AND workspace_id = app_current_workspace_id()) OR
        (scope_kind = 'system' AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN']))
    );

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE default_workflow_hooks TO kanban_app;
GRANT SELECT ON TABLE default_workflow_hooks TO app_rls_reader;
ALTER TABLE default_workflow_hooks OWNER TO kanban_migrator;

-- 2. Add inherited_from_template_id on workflow_transition_hooks
ALTER TABLE workflow_transition_hooks
    ADD COLUMN IF NOT EXISTS inherited_from_template_id UUID NULL REFERENCES default_workflow_hooks(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_workflow_transition_hooks_inherited_from_template_id
    ON workflow_transition_hooks (inherited_from_template_id);
