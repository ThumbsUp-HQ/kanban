-- KB-P6-01: Lossless Plane importer entity mappings table (S1.3, S15.5)

CREATE TABLE import_entity_mappings (
    workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    source_system   TEXT NOT NULL CHECK (source_system = 'plane'),
    source_kind     TEXT NOT NULL,
    source_id       TEXT NOT NULL CHECK (char_length(source_id) BETWEEN 1 AND 128),
    target_id       UUID NOT NULL,
    source_sha256   BYTEA NOT NULL CHECK (octet_length(source_sha256) = 32),
    imported_at     TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (workspace_id, source_system, source_kind, source_id)
);

CREATE INDEX import_entity_mappings_target_idx
    ON import_entity_mappings (workspace_id, target_id);

ALTER TABLE import_entity_mappings ENABLE ROW LEVEL SECURITY;
ALTER TABLE import_entity_mappings FORCE ROW LEVEL SECURITY;

CREATE POLICY import_entity_mappings_select_rls ON import_entity_mappings
    FOR SELECT
    USING (workspace_id = app_current_workspace_id());

CREATE POLICY import_entity_mappings_insert_rls ON import_entity_mappings
    FOR INSERT
    WITH CHECK (workspace_id = app_current_workspace_id());

CREATE POLICY import_entity_mappings_update_rls ON import_entity_mappings
    FOR UPDATE
    USING (workspace_id = app_current_workspace_id())
    WITH CHECK (workspace_id = app_current_workspace_id());

CREATE POLICY import_entity_mappings_delete_rls ON import_entity_mappings
    FOR DELETE
    USING (workspace_id = app_current_workspace_id());

GRANT SELECT, INSERT, UPDATE, DELETE ON import_entity_mappings TO kanban_app;
GRANT SELECT ON import_entity_mappings TO app_rls_reader;
