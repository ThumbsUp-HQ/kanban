-- KB-P5-11: Custom field definitions, Admin-only RBAC/RLS WITH CHECK gate & 7-format output_format_metadata schema

-- 1. Helper function for caller access hash
CREATE OR REPLACE FUNCTION app_caller_access_hash()
RETURNS bytea
LANGUAGE sql
STABLE PARALLEL SAFE
AS $$
    SELECT CASE
        WHEN current_setting('app.user_access_hash', true) IS NOT NULL
             AND current_setting('app.user_access_hash', true) <> ''
        THEN decode(current_setting('app.user_access_hash', true), 'hex')
        ELSE ''::bytea
    END;
$$;

GRANT EXECUTE ON FUNCTION app_caller_access_hash() TO kanban_app, app_rls_reader, kanban_migrator;

-- 2. Custom field definitions table
CREATE TABLE custom_field_definitions (
    id                      UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id            UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    project_id              UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    slug                    TEXT NOT NULL CHECK (slug ~ '^[a-z0-9][a-z0-9-]{1,62}$'),
    name                    TEXT NOT NULL CHECK (char_length(btrim(name)) BETWEEN 1 AND 80),
    tier                    TEXT NOT NULL DEFAULT 'wasm' CHECK (tier IN ('wasm', 'nsjail')),
    output_format           TEXT NOT NULL CHECK (output_format IN (
                                'text', 'number', 'badge', 'markdown_snippet', 'url', 'json_table', 'severity_pill'
                            )),
    output_format_metadata  JSONB NOT NULL DEFAULT '{}'::jsonb
                            CHECK (jsonb_typeof(output_format_metadata) = 'object'
                               AND octet_length(output_format_metadata::text) <= 16384),
    script_source           TEXT NOT NULL CHECK (octet_length(script_source) BETWEEN 1 AND 131072),
    wasm_module_sha256      BYTEA CHECK (wasm_module_sha256 IS NULL OR octet_length(wasm_module_sha256) = 32),
    script_version          INTEGER NOT NULL DEFAULT 1 CHECK (script_version >= 1),
    target_scope            TEXT NOT NULL DEFAULT 'PROJECT'
                            CHECK (target_scope IN ('PROJECT', 'WORKSPACE', 'SERVER')),
    credential_mode         TEXT NOT NULL DEFAULT 'INVOKING_USER'
                            CHECK (credential_mode IN ('INVOKING_USER', 'PROJECT_ADMIN_SP', 'SERVER_ADMIN_SP')),
    egress_allowlist        TEXT[] NOT NULL DEFAULT '{}'
                            CHECK (cardinality(egress_allowlist) <= 16),
    manifest_sha256         BYTEA NOT NULL CHECK (octet_length(manifest_sha256) = 32),
    is_enabled              BOOLEAN NOT NULL DEFAULT TRUE,
    created_by_id           UUID NOT NULL REFERENCES principals(id),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (project_id, slug)
);

CREATE INDEX idx_custom_field_definitions_project ON custom_field_definitions(project_id);

-- 3. Custom field values table
CREATE TABLE custom_field_values (
    id                UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id      UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    project_id        UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    issue_id          UUID NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
    field_id          UUID NOT NULL REFERENCES custom_field_definitions(id) ON DELETE CASCADE,
    script_version    INTEGER NOT NULL,
    user_access_hash  BYTEA NOT NULL CHECK (octet_length(user_access_hash) IN (0, 32)),
    value_json        JSONB NOT NULL CHECK (octet_length(value_json::text) <= 65536),
    last_latency_ms   INTEGER NOT NULL CHECK (last_latency_ms >= 0),
    computed_at       TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    expires_at        TIMESTAMPTZ NOT NULL,
    UNIQUE (issue_id, field_id, script_version, user_access_hash)
);

CREATE INDEX idx_custom_field_values_lookup ON custom_field_values(issue_id, field_id);

-- 4. ENABLE & FORCE ROW LEVEL SECURITY
ALTER TABLE custom_field_definitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE custom_field_definitions FORCE ROW LEVEL SECURITY;

ALTER TABLE custom_field_values ENABLE ROW LEVEL SECURITY;
ALTER TABLE custom_field_values FORCE ROW LEVEL SECURITY;

-- 5. Policies on custom_field_definitions
CREATE POLICY custom_field_definitions_select_rls ON custom_field_definitions
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(project_id, 1)
    );

CREATE POLICY custom_field_definitions_insert_rls ON custom_field_definitions
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(project_id, ARRAY['PROJECT_ADMIN', 'SERVER_ADMIN'])
        AND app_current_aal_level() >= 2
    );

CREATE POLICY custom_field_definitions_update_rls ON custom_field_definitions
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(project_id, ARRAY['PROJECT_ADMIN', 'SERVER_ADMIN'])
        AND app_current_aal_level() >= 2
    );

CREATE POLICY custom_field_definitions_delete_rls ON custom_field_definitions
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(project_id, ARRAY['PROJECT_ADMIN', 'SERVER_ADMIN'])
        AND app_current_aal_level() >= 2
    );

-- 6. Policies on custom_field_values
CREATE POLICY custom_field_values_select_rls ON custom_field_values
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(issue_id, 1)
        AND (user_access_hash = ''::bytea OR user_access_hash = app_caller_access_hash())
    );

CREATE POLICY custom_field_values_insert_rls ON custom_field_values
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(issue_id, 1)
        AND user_access_hash = app_caller_access_hash()
    );

CREATE POLICY custom_field_values_update_rls ON custom_field_values
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(issue_id, 1)
        AND user_access_hash = app_caller_access_hash()
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(issue_id, 1)
        AND user_access_hash = app_caller_access_hash()
    );

CREATE POLICY custom_field_values_delete_rls ON custom_field_values
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(issue_id, 1)
        AND user_access_hash = app_caller_access_hash()
    );

-- 7. Grants
GRANT SELECT, INSERT, UPDATE, DELETE ON custom_field_definitions, custom_field_values TO kanban_app;
GRANT SELECT ON custom_field_definitions, custom_field_values TO app_rls_reader;
