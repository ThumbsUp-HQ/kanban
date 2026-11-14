-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

CREATE TABLE oauth_device_codes (
    id                      UUID PRIMARY KEY DEFAULT uuidv7(),
    device_code_sha256      BYTEA NOT NULL UNIQUE CHECK (octet_length(device_code_sha256) = 32),
    user_code               TEXT NOT NULL UNIQUE CHECK (user_code ~ '^[BCDFGHJKLMNPQRSTVWXZ]{4}-[BCDFGHJKLMNPQRSTVWXZ]{4}$'),
    client_id               UUID NOT NULL REFERENCES oauth_clients(id) ON DELETE CASCADE,
    workspace_id            UUID REFERENCES workspaces(id) ON DELETE CASCADE,
    resource                TEXT NOT NULL,
    surface                 TEXT NOT NULL CHECK (surface IN ('agent', 'docs', 'admin')),
    requested_scopes        TEXT[] NOT NULL,
    allowed_projects        UUID[],
    approved_grant_id       UUID REFERENCES oauth_grants(id) ON DELETE CASCADE,
    approved_by_user_id     UUID REFERENCES principals(id) ON DELETE SET NULL,
    approved_scopes         TEXT[],
    status                  TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'denied', 'expired')),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    expires_at              TIMESTAMPTZ NOT NULL,
    last_polled_at          TIMESTAMPTZ,
    interval_sec            INTEGER NOT NULL DEFAULT 5 CHECK (interval_sec >= 1)
);

-- Indexes for rapid lookup
CREATE INDEX idx_oauth_device_codes_user_code ON oauth_device_codes (user_code);
CREATE INDEX idx_oauth_device_codes_client_id ON oauth_device_codes (client_id);
CREATE INDEX idx_oauth_device_codes_workspace_id ON oauth_device_codes (workspace_id);
CREATE INDEX idx_oauth_device_codes_grant_id ON oauth_device_codes (approved_grant_id);

-- RLS Enforcement
ALTER TABLE oauth_device_codes ENABLE ROW LEVEL SECURITY;
ALTER TABLE oauth_device_codes FORCE ROW LEVEL SECURITY;

CREATE POLICY oauth_device_codes_workspace_policy ON oauth_device_codes
    FOR ALL
    USING (
        workspace_id IS NULL OR
        app_current_workspace_id() IS NULL OR
        workspace_id = app_current_workspace_id()
    )
    WITH CHECK (
        workspace_id IS NULL OR
        app_current_workspace_id() IS NULL OR
        workspace_id = app_current_workspace_id()
    );

-- Table Grants
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE oauth_device_codes TO kanban_app;
GRANT SELECT ON TABLE oauth_device_codes TO app_rls_reader;
