-- Phase 5 / API + MCP: project_repo_bindings (KB-P5-19b, S14.2, S14.3, S11.4)

CREATE TABLE project_repo_bindings (
    id                    UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id          UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    project_id            UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    slug                  TEXT NOT NULL CHECK (slug ~ '^[a-z0-9][a-z0-9-]{1,62}$'),
    remote_url            TEXT NOT NULL CHECK (char_length(remote_url) <= 2048),
    default_ref           TEXT NOT NULL DEFAULT 'main' CHECK (default_ref ~ '^[A-Za-z0-9._/-]{1,200}$' AND default_ref !~ '\.\.'),
    access_mode           TEXT NOT NULL CHECK (access_mode IN ('bare_git_tools','ro_vfs_mount')),
    credential_ciphertext BYTEA,           -- optional deploy key / token, envelope-encrypted via KB-P2-03
    credential_dek_kid    TEXT,
    last_fetched_commit   TEXT CHECK (last_fetched_commit ~ '^[0-9a-f]{40}([0-9a-f]{24})?$'),
    last_fetched_at       TIMESTAMPTZ,
    last_fetch_error      TEXT,
    created_by            UUID NOT NULL REFERENCES principals(id),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (project_id, slug)
);

CREATE INDEX idx_project_repo_bindings_ws ON project_repo_bindings (workspace_id);
CREATE INDEX idx_project_repo_bindings_proj ON project_repo_bindings (project_id);

ALTER TABLE project_repo_bindings ENABLE ROW LEVEL SECURITY;
ALTER TABLE project_repo_bindings FORCE ROW LEVEL SECURITY;

-- SELECT: workspace-scoped, requires VIEW capability (1) on project
CREATE POLICY project_repo_bindings_select_rls ON project_repo_bindings
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND cardinality(app_effective_principal_set()) > 0
        AND app_has_object_capability(project_id, 1)
    );

-- INSERT: workspace-scoped, requires PROJECT_ADMIN or capability ADMIN (64)
CREATE POLICY project_repo_bindings_insert_rls ON project_repo_bindings
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND (
            app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN'])
            OR app_has_object_capability(project_id, 64)
        )
    );

-- UPDATE: workspace-scoped, requires PROJECT_ADMIN or capability ADMIN (64)
CREATE POLICY project_repo_bindings_update_rls ON project_repo_bindings
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
        AND (
            app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN'])
            OR app_has_object_capability(project_id, 64)
        )
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND (
            app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN'])
            OR app_has_object_capability(project_id, 64)
        )
    );

-- DELETE: workspace-scoped, requires PROJECT_ADMIN or capability ADMIN (64)
CREATE POLICY project_repo_bindings_delete_rls ON project_repo_bindings
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
        AND (
            app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN'])
            OR app_has_object_capability(project_id, 64)
        )
    );

GRANT SELECT, INSERT, UPDATE, DELETE ON project_repo_bindings TO kanban_app;
GRANT SELECT ON project_repo_bindings TO app_rls_reader;
