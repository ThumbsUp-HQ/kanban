-- DDL: import_entity_mappings Table Schema
CREATE TABLE import_entity_mappings (
    workspace_id uuid NOT NULL,
    source_system text NOT NULL,
    source_kind text NOT NULL,
    source_id text NOT NULL,
    target_id uuid NOT NULL,
    source_sha256 bytea NOT NULL,
    imported_at timestamp with time zone NOT NULL DEFAULT clock_timestamp()
);

-- Constraints
ALTER TABLE import_entity_mappings ADD CONSTRAINT import_entity_mappings_pkey PRIMARY KEY (workspace_id, source_system, source_kind, source_id);
ALTER TABLE import_entity_mappings ADD CONSTRAINT import_entity_mappings_source_id_check CHECK (((char_length(source_id) >= 1) AND (char_length(source_id) <= 128)));
ALTER TABLE import_entity_mappings ADD CONSTRAINT import_entity_mappings_source_sha256_check CHECK ((octet_length(source_sha256) = 32));
ALTER TABLE import_entity_mappings ADD CONSTRAINT import_entity_mappings_source_system_check CHECK ((source_system = 'plane'::text));
ALTER TABLE import_entity_mappings ADD CONSTRAINT import_entity_mappings_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE;

-- Indexes
CREATE UNIQUE INDEX import_entity_mappings_pkey ON public.import_entity_mappings USING btree (workspace_id, source_system, source_kind, source_id);
CREATE INDEX import_entity_mappings_target_idx ON public.import_entity_mappings USING btree (workspace_id, target_id);

-- Row-Level Security Status
-- ENABLE ROW LEVEL SECURITY: True
-- FORCE ROW LEVEL SECURITY: True
ALTER TABLE import_entity_mappings ENABLE ROW LEVEL SECURITY;
ALTER TABLE import_entity_mappings FORCE ROW LEVEL SECURITY;

-- Row-Level Security Policies
-- Policy: import_entity_mappings_update_rls (CMD: b'w')
-- USING: (workspace_id = app_current_workspace_id())
-- WITH CHECK: (workspace_id = app_current_workspace_id())
-- Policy: import_entity_mappings_select_rls (CMD: b'r')
-- USING: (workspace_id = app_current_workspace_id())
-- Policy: import_entity_mappings_insert_rls (CMD: b'a')
-- USING: None
-- WITH CHECK: (workspace_id = app_current_workspace_id())
-- Policy: import_entity_mappings_delete_rls (CMD: b'd')
-- USING: (workspace_id = app_current_workspace_id())
