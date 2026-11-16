-- Phase 4 / MCP: Session read-taint exfiltration guard (KB-P4-07, S3.5, S11.2)

CREATE TABLE mcp_read_taint (
    workspace_id   UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    taint_key      BYTEA NOT NULL CHECK (octet_length(taint_key) = 32),
    key_kind       TEXT NOT NULL CHECK (key_kind IN ('session', 'credential')),
    project_id     UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    first_read_at  TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    expires_at     TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (taint_key, project_id)
);

CREATE INDEX mcp_read_taint_workspace_idx ON mcp_read_taint (workspace_id);
CREATE INDEX mcp_read_taint_expires_idx ON mcp_read_taint (expires_at);

ALTER TABLE mcp_read_taint ENABLE ROW LEVEL SECURITY;
ALTER TABLE mcp_read_taint FORCE ROW LEVEL SECURITY;

CREATE POLICY mcp_read_taint_select_rls ON mcp_read_taint
    FOR SELECT USING (
        app_current_workspace_id() IS NULL
        OR workspace_id = app_current_workspace_id()
    );

CREATE POLICY mcp_read_taint_insert_rls ON mcp_read_taint
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
    );

CREATE POLICY mcp_read_taint_update_rls ON mcp_read_taint
    FOR UPDATE USING (
        app_current_workspace_id() IS NULL
        OR workspace_id = app_current_workspace_id()
    ) WITH CHECK (
        app_current_workspace_id() IS NULL
        OR workspace_id = app_current_workspace_id()
    );

CREATE POLICY mcp_read_taint_delete_rls ON mcp_read_taint
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
    );

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE mcp_read_taint TO kanban_app;
GRANT SELECT ON TABLE mcp_read_taint TO app_rls_reader;
