-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

-- 1. Create workload_identity_policies table
CREATE TABLE IF NOT EXISTS workload_identity_policies (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name TEXT NOT NULL CHECK (char_length(btrim(name)) BETWEEN 1 AND 120),
    description TEXT,
    issuer TEXT NOT NULL CHECK (char_length(btrim(issuer)) BETWEEN 1 AND 500),
    client_id TEXT NOT NULL CHECK (char_length(btrim(client_id)) BETWEEN 1 AND 255),
    subject_pattern TEXT NOT NULL CHECK (char_length(btrim(subject_pattern)) BETWEEN 1 AND 500),
    required_claims_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    surface TEXT NOT NULL CHECK (surface IN ('agent', 'docs')),
    scopes TEXT[] NOT NULL DEFAULT '{}'::text[],
    allowed_project_ids UUID[] DEFAULT '{}'::uuid[],
    capability_mask INTEGER NOT NULL DEFAULT 255 CHECK (capability_mask BETWEEN 0 AND 255),
    allowed_cidrs TEXT[] DEFAULT '{}'::text[],
    max_ttl_seconds INTEGER NOT NULL DEFAULT 3600 CHECK (max_ttl_seconds BETWEEN 60 AND 86400),
    is_enabled BOOLEAN NOT NULL DEFAULT true,
    created_by_id UUID REFERENCES principals(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX IF NOT EXISTS idx_workload_identity_policies_ws ON workload_identity_policies (workspace_id);
CREATE INDEX IF NOT EXISTS idx_workload_identity_policies_issuer ON workload_identity_policies (issuer);

ALTER TABLE workload_identity_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE workload_identity_policies FORCE ROW LEVEL SECURITY;

CREATE POLICY workload_identity_policies_select_rls ON workload_identity_policies
    FOR SELECT USING (
        app_current_workspace_id() IS NULL
        OR workspace_id = app_current_workspace_id()
    );

CREATE POLICY workload_identity_policies_insert_rls ON workload_identity_policies
    FOR INSERT WITH CHECK (
        app_current_workspace_id() IS NULL
        OR workspace_id = app_current_workspace_id()
    );

CREATE POLICY workload_identity_policies_update_rls ON workload_identity_policies
    FOR UPDATE USING (
        app_current_workspace_id() IS NULL
        OR workspace_id = app_current_workspace_id()
    ) WITH CHECK (
        app_current_workspace_id() IS NULL
        OR workspace_id = app_current_workspace_id()
    );

CREATE POLICY workload_identity_policies_delete_rls ON workload_identity_policies
    FOR DELETE USING (
        app_current_workspace_id() IS NULL
        OR workspace_id = app_current_workspace_id()
    );

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE workload_identity_policies TO kanban_app;
GRANT SELECT ON TABLE workload_identity_policies TO app_rls_reader;
ALTER TABLE workload_identity_policies OWNER TO kanban_migrator;

-- 2. Create workload_jti_replays table
CREATE TABLE IF NOT EXISTS workload_jti_replays (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    policy_id UUID NOT NULL REFERENCES workload_identity_policies(id) ON DELETE CASCADE,
    jti TEXT NOT NULL CHECK (char_length(btrim(jti)) BETWEEN 1 AND 500),
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT uq_workload_jti_replays_policy_jti UNIQUE (policy_id, jti)
);

CREATE INDEX IF NOT EXISTS idx_workload_jti_replays_expires_at ON workload_jti_replays (expires_at);

ALTER TABLE workload_jti_replays ENABLE ROW LEVEL SECURITY;
ALTER TABLE workload_jti_replays FORCE ROW LEVEL SECURITY;

CREATE POLICY workload_jti_replays_select_rls ON workload_jti_replays
    FOR SELECT USING (
        app_current_workspace_id() IS NULL
        OR workspace_id = app_current_workspace_id()
    );

CREATE POLICY workload_jti_replays_insert_rls ON workload_jti_replays
    FOR INSERT WITH CHECK (
        app_current_workspace_id() IS NULL
        OR workspace_id = app_current_workspace_id()
    );

CREATE POLICY workload_jti_replays_delete_rls ON workload_jti_replays
    FOR DELETE USING (
        app_current_workspace_id() IS NULL
        OR workspace_id = app_current_workspace_id()
    );

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE workload_jti_replays TO kanban_app;
GRANT SELECT ON TABLE workload_jti_replays TO app_rls_reader;
ALTER TABLE workload_jti_replays OWNER TO kanban_migrator;
