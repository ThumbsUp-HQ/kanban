-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

ALTER TABLE import_entity_mappings
    DROP CONSTRAINT IF EXISTS import_entity_mappings_source_system_check;

ALTER TABLE import_entity_mappings
    ADD CONSTRAINT import_entity_mappings_source_system_check
    CHECK (source_system IN ('plane', 'jira', 'github', 'linear'));

CREATE TABLE IF NOT EXISTS issue_key_aliases (
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    legacy_key TEXT NOT NULL CHECK (legacy_key ~ '^[A-Z][A-Z0-9_-]{1,24}-[0-9]{1,18}$'),
    issue_id UUID NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
    source_system TEXT NOT NULL CHECK (source_system IN ('plane', 'jira', 'github', 'linear')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (workspace_id, legacy_key)
);

CREATE INDEX IF NOT EXISTS idx_issue_key_aliases_workspace_issue
    ON issue_key_aliases (workspace_id, issue_id);

ALTER TABLE issue_key_aliases OWNER TO kanban_migrator;

ALTER TABLE issue_key_aliases ENABLE ROW LEVEL SECURITY;
ALTER TABLE issue_key_aliases FORCE ROW LEVEL SECURITY;

CREATE POLICY issue_key_aliases_select_rls ON issue_key_aliases
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
    );

CREATE POLICY issue_key_aliases_insert_rls ON issue_key_aliases
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
    );

CREATE POLICY issue_key_aliases_update_rls ON issue_key_aliases
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
    );

CREATE POLICY issue_key_aliases_delete_rls ON issue_key_aliases
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
    );

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE issue_key_aliases TO kanban_app;
GRANT SELECT ON TABLE issue_key_aliases TO app_rls_reader;
