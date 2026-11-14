-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.
-- Schema definition and Row-Level Security policies for workspace_settings (KB-P4-09a)

CREATE TABLE workspace_settings (
    workspace_id                  UUID PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,
    display_name                  TEXT NOT NULL CHECK (char_length(display_name) BETWEEN 1 AND 80),
    default_project_visibility    TEXT NOT NULL DEFAULT 'private' CHECK (default_project_visibility IN ('private','workspace')),
    session_idle_timeout_min      INTEGER NOT NULL DEFAULT 60 CHECK (session_idle_timeout_min BETWEEN 5 AND 720),
    session_absolute_timeout_min  INTEGER NOT NULL DEFAULT 720 CHECK (session_absolute_timeout_min BETWEEN 60 AND 10080),
    trash_retention_days          INTEGER NOT NULL DEFAULT 30 CHECK (trash_retention_days BETWEEN 1 AND 365),
    mcp_key_max_ttl_days          INTEGER NOT NULL DEFAULT 90 CHECK (mcp_key_max_ttl_days BETWEEN 1 AND 365),
    air_gap_mode                  BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at                    TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CHECK (session_absolute_timeout_min >= session_idle_timeout_min)
);

-- Grants
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE workspace_settings TO kanban_app;
GRANT SELECT ON TABLE workspace_settings TO app_rls_reader;

-- Row-Level Security (FORCE RLS)
ALTER TABLE workspace_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE workspace_settings FORCE ROW LEVEL SECURITY;

CREATE POLICY workspace_settings_select_rls ON workspace_settings
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND cardinality(app_effective_principal_set()) > 0
    );

CREATE POLICY workspace_settings_insert_rls ON workspace_settings
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
    );

CREATE POLICY workspace_settings_update_rls ON workspace_settings
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
    );

CREATE POLICY workspace_settings_delete_rls ON workspace_settings
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
    );

-- Triggers
CREATE TRIGGER workspace_settings_set_updated_at
    BEFORE UPDATE ON workspace_settings
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE OR REPLACE FUNCTION initialize_workspace_settings()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    INSERT INTO workspace_settings (
        workspace_id,
        display_name,
        default_project_visibility,
        session_idle_timeout_min,
        session_absolute_timeout_min,
        trash_retention_days,
        mcp_key_max_ttl_days,
        air_gap_mode
    )
    VALUES (
        NEW.id,
        substring(NEW.name from 1 for 80),
        'private',
        60,
        720,
        COALESCE(NEW.trash_retention_days, 30),
        90,
        FALSE
    )
    ON CONFLICT (workspace_id) DO NOTHING;
    RETURN NEW;
END;
$$;

CREATE TRIGGER workspaces_init_settings
    AFTER INSERT ON workspaces
    FOR EACH ROW
    EXECUTE FUNCTION initialize_workspace_settings();
