-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

-- 1. Create issue_workpads table
CREATE TABLE IF NOT EXISTS issue_workpads (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    issue_id UUID NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
    principal_id UUID NOT NULL REFERENCES principals(id) ON DELETE CASCADE,
    body_markdown TEXT NOT NULL,
    body_sha256 BYTEA GENERATED ALWAYS AS (digest(body_markdown, 'sha256')) STORED,
    revision BIGINT NOT NULL DEFAULT 1,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (issue_id, principal_id)
);

CREATE INDEX IF NOT EXISTS idx_issue_workpads_ws_proj ON issue_workpads (workspace_id, project_id);
CREATE INDEX IF NOT EXISTS idx_issue_workpads_issue ON issue_workpads (issue_id);
CREATE INDEX IF NOT EXISTS idx_issue_workpads_principal ON issue_workpads (principal_id);

ALTER TABLE issue_workpads ENABLE ROW LEVEL SECURITY;
ALTER TABLE issue_workpads FORCE ROW LEVEL SECURITY;

CREATE POLICY issue_workpads_select_rls ON issue_workpads
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(issue_id, 1)
    );

CREATE POLICY issue_workpads_insert_rls ON issue_workpads
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND (
            principal_id = app_current_principal_id()
            OR app_has_object_capability(issue_id, 4)
            OR app_has_object_capability(issue_id, 64)
        )
        AND (
            app_has_object_capability(issue_id, 4)
            OR app_has_object_capability(issue_id, 2)
            OR app_has_object_capability(issue_id, 1)
        )
    );

CREATE POLICY issue_workpads_update_rls ON issue_workpads
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
        AND (
            principal_id = app_current_principal_id()
            OR app_has_object_capability(issue_id, 4)
            OR app_has_object_capability(issue_id, 64)
        )
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND (
            principal_id = app_current_principal_id()
            OR app_has_object_capability(issue_id, 4)
            OR app_has_object_capability(issue_id, 64)
        )
    );

CREATE POLICY issue_workpads_delete_rls ON issue_workpads
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
        AND (
            principal_id = app_current_principal_id()
            OR app_has_object_capability(issue_id, 4)
            OR app_has_object_capability(issue_id, 64)
        )
    );

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE issue_workpads TO kanban_app;
GRANT SELECT ON TABLE issue_workpads TO app_rls_reader;
ALTER TABLE issue_workpads OWNER TO kanban_migrator;

-- 2. Add rework breaker columns to workflow_transition_hooks and issues
ALTER TABLE workflow_transition_hooks
    ADD COLUMN IF NOT EXISTS max_rework_attempts SMALLINT NOT NULL DEFAULT 3 CHECK (max_rework_attempts BETWEEN 1 AND 20);

ALTER TABLE issues
    ADD COLUMN IF NOT EXISTS rework_rejection_streak SMALLINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS rework_tripped_at TIMESTAMPTZ NULL;
