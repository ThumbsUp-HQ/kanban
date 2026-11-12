-- Phase 5 / Database + API: agent_definitions registry (KB-P5-16)

CREATE TABLE agent_definitions (
    id                      UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id            UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    project_id              UUID REFERENCES projects(id) ON DELETE CASCADE,
    principal_id            UUID NOT NULL REFERENCES principals(id) ON DELETE RESTRICT,
    slug                    TEXT NOT NULL CHECK (slug ~ '^[a-z0-9][a-z0-9-]{1,62}$'),
    display_name            TEXT NOT NULL,
    harness_kind            TEXT NOT NULL CHECK (harness_kind IN ('in_app_sdk', 'cli_pipe', 'remote_runner')),
    provider_kind           TEXT CHECK (provider_kind IN ('openai', 'ollama', 'gemini', 'fixture')),
    model_id                TEXT,
    cli_binary_allowlist_id TEXT CHECK (cli_binary_allowlist_id IN ('agy', 'codex', 'gemini-cli', 'claude-code')),
    cli_args_json           JSONB NOT NULL DEFAULT '[]'::jsonb, -- Validated argv array; NEVER sh -c
    remote_runner_pool_slug TEXT,
    repo_access_mode        TEXT NOT NULL DEFAULT 'none' CHECK (repo_access_mode IN ('none', 'bare_git_tools', 'ro_vfs_mount')),
    mcp_allowed_tools       TEXT[] NOT NULL DEFAULT ARRAY['search_tickets','read_ticket','search_knowledge','read_doc'],
    system_instructions_md  TEXT NOT NULL DEFAULT '',
    timeout_ms              INTEGER NOT NULL DEFAULT 60000 CHECK (timeout_ms BETWEEN 1000 AND 300000),
    UNIQUE (workspace_id, slug)
);

ALTER TABLE agent_definitions ADD CONSTRAINT agent_def_harness_fields CHECK (
  (harness_kind = 'in_app_sdk'    AND provider_kind IS NOT NULL AND model_id IS NOT NULL AND cli_binary_allowlist_id IS NULL AND remote_runner_pool_slug IS NULL) OR
  (harness_kind = 'cli_pipe'      AND cli_binary_allowlist_id IS NOT NULL AND remote_runner_pool_slug IS NULL) OR
  (harness_kind = 'remote_runner' AND remote_runner_pool_slug IS NOT NULL)
);

ALTER TABLE agent_definitions ADD CONSTRAINT agent_def_mcp_tools_subset CHECK (
  mcp_allowed_tools <@ ARRAY['search_tickets','read_ticket','search_knowledge','read_doc']::text[]
);

ALTER TABLE agent_definitions ADD CONSTRAINT agent_def_args_is_array CHECK (jsonb_typeof(cli_args_json) = 'array');

ALTER TABLE agent_definitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_definitions FORCE ROW LEVEL SECURITY;

-- SELECT policy: Workspace-scoped read with VIEW access on project when project_id is present
CREATE POLICY agent_definitions_select_rls ON agent_definitions
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND cardinality(app_effective_principal_set()) > 0
        AND (
            project_id IS NULL
            OR app_has_object_capability(project_id, 1)
        )
    );

-- INSERT policy: WORKSPACE_ADMIN for workspace-scoped; PROJECT_ADMIN for project-scoped
CREATE POLICY agent_definitions_insert_rls ON agent_definitions
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND (
            (project_id IS NULL AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN']))
            OR (project_id IS NOT NULL AND app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN']))
        )
    );

-- UPDATE policy: WORKSPACE_ADMIN for workspace-scoped; PROJECT_ADMIN for project-scoped
CREATE POLICY agent_definitions_update_rls ON agent_definitions
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
        AND (
            (project_id IS NULL AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN']))
            OR (project_id IS NOT NULL AND app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN']))
        )
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND (
            (project_id IS NULL AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN']))
            OR (project_id IS NOT NULL AND app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN']))
        )
    );

-- DELETE policy: WORKSPACE_ADMIN for workspace-scoped; PROJECT_ADMIN for project-scoped
CREATE POLICY agent_definitions_delete_rls ON agent_definitions
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
        AND (
            (project_id IS NULL AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN']))
            OR (project_id IS NOT NULL AND app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN']))
        )
    );

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE agent_definitions TO kanban_app;
GRANT SELECT ON TABLE agent_definitions TO app_rls_reader;
