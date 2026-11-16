-- Phase 5 / Database + Workflow Engine: workflow hooks, executions, and invocations (KB-P5-17a, S14.1, S14.2)

CREATE TABLE workflow_transition_hooks (
    id                      UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id            UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    project_id              UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name                    TEXT NOT NULL,
    from_state_id           UUID REFERENCES workflow_states(id) ON DELETE CASCADE, -- NULL = wildcard '*'
    to_state_id             UUID NOT NULL REFERENCES workflow_states(id) ON DELETE CASCADE,
    hook_kind               TEXT NOT NULL CHECK (hook_kind IN ('sync_validator', 'sync_mutator', 'agent_interceptor')),
    sort_rank               TEXT COLLATE "C" NOT NULL,
    is_enabled              BOOLEAN NOT NULL DEFAULT TRUE,
    wasm_module_sha256      BYTEA,
    agent_definition_id     UUID REFERENCES agent_definitions(id) ON DELETE RESTRICT,
    allowed_mutable_fields  TEXT[] NOT NULL DEFAULT '{}', -- Whitelist of fields this hook may auto-update
    failure_policy          TEXT NOT NULL DEFAULT 'fail_closed' CHECK (failure_policy IN ('fail_closed', 'fail_open_warn')),
    manifest_sha256         BYTEA NOT NULL
);

ALTER TABLE workflow_transition_hooks ADD CONSTRAINT ck_workflow_transition_hooks_kind CHECK (
    (hook_kind IN ('sync_validator', 'sync_mutator') AND wasm_module_sha256 IS NOT NULL AND agent_definition_id IS NULL)
    OR
    (hook_kind = 'agent_interceptor' AND agent_definition_id IS NOT NULL AND wasm_module_sha256 IS NULL)
);

ALTER TABLE workflow_transition_hooks ADD CONSTRAINT ck_workflow_transition_hooks_manifest_sha256 CHECK (
    octet_length(manifest_sha256) = 32
);

ALTER TABLE workflow_transition_hooks ADD CONSTRAINT ck_workflow_transition_hooks_wasm_sha256 CHECK (
    wasm_module_sha256 IS NULL OR octet_length(wasm_module_sha256) = 32
);

CREATE INDEX wth_lookup ON workflow_transition_hooks (project_id, to_state_id, sort_rank) WHERE is_enabled;
CREATE INDEX idx_wth_workspace ON workflow_transition_hooks (workspace_id);
CREATE INDEX idx_wth_project ON workflow_transition_hooks (project_id);

CREATE TABLE workflow_transition_executions (
    id                          UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id                UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    project_id                  UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    issue_id                    UUID NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
    invoking_principal_id       UUID NOT NULL REFERENCES principals(id),
    from_state_id               UUID NOT NULL REFERENCES workflow_states(id),
    to_state_id                 UUID NOT NULL REFERENCES workflow_states(id),
    status                      TEXT NOT NULL CHECK (status IN ('running_sync','pending_async','approved','rejected','cancelled','timed_out')),
    hop_depth                   SMALLINT NOT NULL DEFAULT 0 CONSTRAINT ck_workflow_transition_executions_hop_depth CHECK (hop_depth <= 3), -- Infinite-loop breaker
    issue_body_sha256_snapshot  BYTEA NOT NULL CHECK (octet_length(issue_body_sha256_snapshot) = 32), -- Zero-TOCTOU content hash
    verdict_json                JSONB,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    completed_at                TIMESTAMPTZ
);

CREATE UNIQUE INDEX wte_one_pending ON workflow_transition_executions (issue_id) WHERE status IN ('running_sync','pending_async');
CREATE INDEX idx_wte_issue ON workflow_transition_executions (issue_id);
CREATE INDEX idx_wte_workspace ON workflow_transition_executions (workspace_id);

CREATE TABLE workflow_hook_invocations (
    id            UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id  UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    execution_id  UUID NOT NULL REFERENCES workflow_transition_executions(id) ON DELETE CASCADE,
    hook_id       UUID NOT NULL REFERENCES workflow_transition_hooks(id) ON DELETE RESTRICT,
    hook_kind     TEXT NOT NULL CHECK (hook_kind IN ('sync_validator','sync_mutator','agent_interceptor')),
    status        TEXT NOT NULL CHECK (status IN ('running','allowed','rejected','mutated','error','timed_out','skipped')),
    error_code    TEXT,
    output_json   JSONB CHECK (output_json IS NULL OR octet_length(output_json::text) <= 65536), -- bounded <= 64 KiB, scrubbed
    duration_us   INTEGER CHECK (duration_us >= 0),
    started_at    TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    completed_at  TIMESTAMPTZ,
    CONSTRAINT uq_workflow_hook_invocations_exec_hook UNIQUE (execution_id, hook_id)
);

CREATE INDEX idx_whi_execution ON workflow_hook_invocations (execution_id);
CREATE INDEX idx_whi_workspace ON workflow_hook_invocations (workspace_id);

-- Enable and force Row-Level Security
ALTER TABLE workflow_transition_hooks ENABLE ROW LEVEL SECURITY;
ALTER TABLE workflow_transition_hooks FORCE ROW LEVEL SECURITY;

ALTER TABLE workflow_transition_executions ENABLE ROW LEVEL SECURITY;
ALTER TABLE workflow_transition_executions FORCE ROW LEVEL SECURITY;

ALTER TABLE workflow_hook_invocations ENABLE ROW LEVEL SECURITY;
ALTER TABLE workflow_hook_invocations FORCE ROW LEVEL SECURITY;

-- 1. Policies for workflow_transition_hooks
CREATE POLICY workflow_transition_hooks_select_rls ON workflow_transition_hooks
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(project_id, 1)
    );

CREATE POLICY workflow_transition_hooks_insert_rls ON workflow_transition_hooks
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(project_id, ARRAY['PROJECT_ADMIN', 'WORKSPACE_ADMIN', 'SERVER_ADMIN'])
    );

CREATE POLICY workflow_transition_hooks_update_rls ON workflow_transition_hooks
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(project_id, ARRAY['PROJECT_ADMIN', 'WORKSPACE_ADMIN', 'SERVER_ADMIN'])
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(project_id, ARRAY['PROJECT_ADMIN', 'WORKSPACE_ADMIN', 'SERVER_ADMIN'])
    );

CREATE POLICY workflow_transition_hooks_delete_rls ON workflow_transition_hooks
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(project_id, ARRAY['PROJECT_ADMIN', 'WORKSPACE_ADMIN', 'SERVER_ADMIN'])
    );

-- 2. Policies for workflow_transition_executions
CREATE POLICY workflow_transition_executions_select_rls ON workflow_transition_executions
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(issue_id, 1)
    );

CREATE POLICY workflow_transition_executions_insert_rls ON workflow_transition_executions
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(issue_id, 1)
    );

CREATE POLICY workflow_transition_executions_update_rls ON workflow_transition_executions
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(issue_id, 1)
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(issue_id, 1)
    );

CREATE POLICY workflow_transition_executions_delete_rls ON workflow_transition_executions
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(project_id, ARRAY['PROJECT_ADMIN', 'WORKSPACE_ADMIN', 'SERVER_ADMIN'])
    );

-- 3. Policies for workflow_hook_invocations
CREATE POLICY workflow_hook_invocations_select_rls ON workflow_hook_invocations
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND EXISTS (
            SELECT 1 FROM workflow_transition_executions e
            WHERE e.id = workflow_hook_invocations.execution_id
              AND app_has_object_capability(e.issue_id, 1)
        )
    );

CREATE POLICY workflow_hook_invocations_insert_rls ON workflow_hook_invocations
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND EXISTS (
            SELECT 1 FROM workflow_transition_executions e
            WHERE e.id = workflow_hook_invocations.execution_id
              AND app_has_object_capability(e.issue_id, 1)
        )
    );

CREATE POLICY workflow_hook_invocations_update_rls ON workflow_hook_invocations
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
        AND EXISTS (
            SELECT 1 FROM workflow_transition_executions e
            WHERE e.id = workflow_hook_invocations.execution_id
              AND app_has_object_capability(e.issue_id, 1)
        )
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND EXISTS (
            SELECT 1 FROM workflow_transition_executions e
            WHERE e.id = workflow_hook_invocations.execution_id
              AND app_has_object_capability(e.issue_id, 1)
        )
    );

CREATE POLICY workflow_hook_invocations_delete_rls ON workflow_hook_invocations
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
    );

-- Grants
GRANT SELECT, INSERT, UPDATE, DELETE ON workflow_transition_hooks, workflow_transition_executions, workflow_hook_invocations TO kanban_app;
GRANT SELECT ON workflow_transition_hooks, workflow_transition_executions, workflow_hook_invocations TO app_rls_reader;

-- 4. Database guard trigger on issues.state_id
CREATE OR REPLACE FUNCTION check_issues_state_guard() RETURNS trigger AS $$
DECLARE
    v_exec_id_text TEXT;
    v_exec_id UUID;
    v_valid BOOLEAN;
BEGIN
    -- If state_id is unchanged, permit the update without transition engine
    IF NEW.state_id IS NOT DISTINCT FROM OLD.state_id THEN
        RETURN NEW;
    END IF;

    -- Bootstrap fixtures running under superuser or kanban_migrator may seed states directly if no exec id
    IF CURRENT_USER IN ('postgres', 'kanban_migrator') AND current_setting('app.transition_exec_id', true) IS NULL THEN
        RETURN NEW;
    END IF;

    v_exec_id_text := current_setting('app.transition_exec_id', true);
    IF v_exec_id_text IS NULL OR v_exec_id_text = '' THEN
        RAISE EXCEPTION 'STATE_CHANGE_REQUIRES_TRANSITION_ENGINE'
            USING ERRCODE = 'P0001',
                  HINT = 'Issues state changes must pass through TransitionEngine';
    END IF;

    BEGIN
        v_exec_id := v_exec_id_text::uuid;
    EXCEPTION WHEN OTHERS THEN
        RAISE EXCEPTION 'STATE_CHANGE_REQUIRES_TRANSITION_ENGINE'
            USING ERRCODE = 'P0001',
                  HINT = 'app.transition_exec_id is not a valid UUID';
    END;

    SELECT EXISTS (
        SELECT 1
        FROM workflow_transition_executions
        WHERE id = v_exec_id
          AND issue_id = NEW.id
          AND to_state_id = NEW.state_id
          AND status IN ('running_sync', 'pending_async')
    ) INTO v_valid;

    IF NOT v_valid THEN
        RAISE EXCEPTION 'STATE_CHANGE_REQUIRES_TRANSITION_ENGINE'
            USING ERRCODE = 'P0001',
                  HINT = 'No active workflow_transition_executions row matches this state change';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS issues_state_guard ON issues;
CREATE TRIGGER issues_state_guard
    BEFORE UPDATE OF state_id ON issues
    FOR EACH ROW
    EXECUTE FUNCTION check_issues_state_guard();
