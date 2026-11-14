-- Phase 5 / Sandbox: approved_wasm_modules (KB-P5-13, S13.3)

CREATE TABLE approved_wasm_modules (
    id              UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    project_id      UUID REFERENCES projects(id) ON DELETE CASCADE,
    sha256          BYTEA NOT NULL CHECK (octet_length(sha256) = 32),
    name            TEXT NOT NULL CHECK (char_length(btrim(name)) BETWEEN 1 AND 120),
    wasm_bytes      BYTEA NOT NULL CHECK (octet_length(wasm_bytes) BETWEEN 8 AND 1048576),
    approved_by_id  UUID NOT NULL REFERENCES principals(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (workspace_id, sha256)
);

CREATE INDEX idx_approved_wasm_modules_lookup ON approved_wasm_modules (workspace_id, sha256);
CREATE INDEX idx_approved_wasm_modules_project ON approved_wasm_modules (project_id) WHERE project_id IS NOT NULL;

ALTER TABLE approved_wasm_modules ENABLE ROW LEVEL SECURITY;
ALTER TABLE approved_wasm_modules FORCE ROW LEVEL SECURITY;

-- SELECT policy: Workspace-scoped read with VIEW access on project when project_id is present
CREATE POLICY approved_wasm_modules_select_rls ON approved_wasm_modules
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND cardinality(app_effective_principal_set()) > 0
        AND (
            project_id IS NULL
            OR app_has_object_capability(project_id, 1)
        )
    );

-- INSERT policy: WORKSPACE_ADMIN for workspace-scoped; PROJECT_ADMIN for project-scoped; requires AAL2
CREATE POLICY approved_wasm_modules_insert_rls ON approved_wasm_modules
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND (
            (project_id IS NULL AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN']))
            OR (project_id IS NOT NULL AND app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN']))
        )
        AND app_current_aal_level() >= 2
    );

-- UPDATE policy: WORKSPACE_ADMIN for workspace-scoped; PROJECT_ADMIN for project-scoped; requires AAL2
CREATE POLICY approved_wasm_modules_update_rls ON approved_wasm_modules
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND (
            (project_id IS NULL AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN']))
            OR (project_id IS NOT NULL AND app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN']))
        )
        AND app_current_aal_level() >= 2
    );

-- DELETE policy: WORKSPACE_ADMIN for workspace-scoped; PROJECT_ADMIN for project-scoped; requires AAL2
CREATE POLICY approved_wasm_modules_delete_rls ON approved_wasm_modules
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
        AND (
            (project_id IS NULL AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN']))
            OR (project_id IS NOT NULL AND app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN']))
        )
        AND app_current_aal_level() >= 2
    );

GRANT SELECT, INSERT, UPDATE, DELETE ON approved_wasm_modules TO kanban_app;
GRANT SELECT ON approved_wasm_modules TO app_rls_reader;
