-- Phase 6 / DevSecOps Bus: SCM webhooks, artifacts, and outbound webhook bus (KB-DEVSECOPS-BUS-01)

-- 1. Enum expansions
ALTER TYPE object_kind ADD VALUE IF NOT EXISTS 'scm_artifact';
ALTER TYPE link_kind ADD VALUE IF NOT EXISTS 'IMPLEMENTED_IN_PR';
ALTER TYPE link_kind ADD VALUE IF NOT EXISTS 'REFERENCED_BY_COMMIT';
ALTER TYPE link_kind ADD VALUE IF NOT EXISTS 'TRACKED_ON_BRANCH';

COMMIT;
BEGIN;

-- 2. Alter project_repo_bindings
ALTER TABLE project_repo_bindings
    ADD COLUMN IF NOT EXISTS ssh_known_hosts TEXT,
    ADD COLUMN IF NOT EXISTS wrapped_webhook_secret BYTEA,
    ADD COLUMN IF NOT EXISTS webhook_secret_dek_kid TEXT;

-- 3. Link type matrix allowlist for SCM artifacts
INSERT INTO link_type_matrix (source_type, link_type, target_type, is_user_creatable) VALUES
('issue', 'IMPLEMENTED_IN_PR', 'scm_artifact', FALSE),
('scm_artifact', 'IMPLEMENTED_IN_PR', 'issue', FALSE),
('issue', 'REFERENCED_BY_COMMIT', 'scm_artifact', FALSE),
('scm_artifact', 'REFERENCED_BY_COMMIT', 'issue', FALSE),
('issue', 'TRACKED_ON_BRANCH', 'scm_artifact', FALSE),
('scm_artifact', 'TRACKED_ON_BRANCH', 'issue', FALSE)
ON CONFLICT DO NOTHING;

-- 4. scm_artifacts table
CREATE TABLE scm_artifacts (
    id                UUID PRIMARY KEY DEFAULT uuidv7(),
    object_id         UUID UNIQUE REFERENCES objects(id) ON DELETE CASCADE,
    workspace_id      UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    project_id        UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    repo_binding_id   UUID NOT NULL REFERENCES project_repo_bindings(id) ON DELETE CASCADE,
    artifact_kind     TEXT NOT NULL CHECK (artifact_kind IN ('branch', 'commit', 'pull_request', 'ci_run')),
    external_id       TEXT NOT NULL,
    title             TEXT NOT NULL,
    url               TEXT NOT NULL,
    state             TEXT,
    head_sha          TEXT,
    metadata_json     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX idx_scm_artifacts_ws_proj ON scm_artifacts (workspace_id, project_id);
CREATE INDEX idx_scm_artifacts_repo ON scm_artifacts (repo_binding_id);
CREATE INDEX idx_scm_artifacts_obj ON scm_artifacts (object_id);
CREATE UNIQUE INDEX uq_scm_artifacts_repo_kind_ext ON scm_artifacts (repo_binding_id, artifact_kind, external_id);

ALTER TABLE scm_artifacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE scm_artifacts FORCE ROW LEVEL SECURITY;

CREATE POLICY scm_artifacts_select_rls ON scm_artifacts
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND cardinality(app_effective_principal_set()) > 0
        AND app_has_object_capability(project_id, 1)
    );

CREATE POLICY scm_artifacts_insert_rls ON scm_artifacts
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND (
            app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN'])
            OR app_has_object_capability(project_id, 64)
            OR app_has_object_capability(project_id, 4)
        )
    );

CREATE POLICY scm_artifacts_update_rls ON scm_artifacts
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
        AND (
            app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN'])
            OR app_has_object_capability(project_id, 64)
            OR app_has_object_capability(project_id, 4)
        )
    );

CREATE POLICY scm_artifacts_delete_rls ON scm_artifacts
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
        AND (
            app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN'])
            OR app_has_object_capability(project_id, 64)
        )
    );

GRANT SELECT, INSERT, UPDATE, DELETE ON scm_artifacts TO kanban_app;
GRANT SELECT ON scm_artifacts TO app_rls_reader;

-- 5. scm_webhook_deliveries table
CREATE TABLE scm_webhook_deliveries (
    id                UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id      UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    repo_binding_id   UUID NOT NULL REFERENCES project_repo_bindings(id) ON DELETE CASCADE,
    provider          TEXT NOT NULL CHECK (provider IN ('github', 'gitlab', 'forgejo')),
    delivery_id       TEXT NOT NULL,
    event_type        TEXT NOT NULL,
    payload_sha256    TEXT NOT NULL,
    processed_at      TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (repo_binding_id, delivery_id)
);

CREATE INDEX idx_scm_webhook_deliveries_ws ON scm_webhook_deliveries (workspace_id);
CREATE INDEX idx_scm_webhook_deliveries_repo ON scm_webhook_deliveries (repo_binding_id);

ALTER TABLE scm_webhook_deliveries ENABLE ROW LEVEL SECURITY;
ALTER TABLE scm_webhook_deliveries FORCE ROW LEVEL SECURITY;

CREATE POLICY scm_webhook_deliveries_select_rls ON scm_webhook_deliveries
    FOR SELECT USING (workspace_id = app_current_workspace_id());

CREATE POLICY scm_webhook_deliveries_insert_rls ON scm_webhook_deliveries
    FOR INSERT WITH CHECK (workspace_id = app_current_workspace_id());

CREATE POLICY scm_webhook_deliveries_delete_rls ON scm_webhook_deliveries
    FOR DELETE USING (workspace_id = app_current_workspace_id());

GRANT SELECT, INSERT, UPDATE, DELETE ON scm_webhook_deliveries TO kanban_app;
GRANT SELECT ON scm_webhook_deliveries TO app_rls_reader;

-- 6. webhook_subscriptions table
CREATE TABLE webhook_subscriptions (
    id                UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id      UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    project_id        UUID REFERENCES projects(id) ON DELETE CASCADE,
    target_url        TEXT NOT NULL CHECK (char_length(target_url) <= 2048),
    events            TEXT[] NOT NULL DEFAULT '{}',
    secret_ciphertext BYTEA,
    secret_dek_kid    TEXT,
    is_active         BOOLEAN NOT NULL DEFAULT TRUE,
    created_by        UUID NOT NULL REFERENCES principals(id),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX idx_webhook_subscriptions_ws ON webhook_subscriptions (workspace_id);
CREATE INDEX idx_webhook_subscriptions_proj ON webhook_subscriptions (project_id);

ALTER TABLE webhook_subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE webhook_subscriptions FORCE ROW LEVEL SECURITY;

CREATE POLICY webhook_subscriptions_select_rls ON webhook_subscriptions
    FOR SELECT USING (workspace_id = app_current_workspace_id());

CREATE POLICY webhook_subscriptions_insert_rls ON webhook_subscriptions
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND (
            project_id IS NULL
            OR app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN'])
            OR app_has_object_capability(project_id, 64)
        )
    );

CREATE POLICY webhook_subscriptions_update_rls ON webhook_subscriptions
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
        AND (
            project_id IS NULL
            OR app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN'])
            OR app_has_object_capability(project_id, 64)
        )
    );

CREATE POLICY webhook_subscriptions_delete_rls ON webhook_subscriptions
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
        AND (
            project_id IS NULL
            OR app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN'])
            OR app_has_object_capability(project_id, 64)
        )
    );

GRANT SELECT, INSERT, UPDATE, DELETE ON webhook_subscriptions TO kanban_app;
GRANT SELECT ON webhook_subscriptions TO app_rls_reader;

-- 7. webhook_deliveries table
CREATE TABLE webhook_deliveries (
    id                UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id      UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    subscription_id   UUID NOT NULL REFERENCES webhook_subscriptions(id) ON DELETE CASCADE,
    event_id          UUID,
    event_topic       TEXT NOT NULL,
    payload_json      JSONB NOT NULL DEFAULT '{}'::jsonb,
    attempt_count     INT NOT NULL DEFAULT 0,
    status            TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'delivered', 'failed', 'dead_letter')),
    status_code       INT,
    error_message     TEXT,
    next_retry_at     TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    delivered_at      TIMESTAMPTZ
);

CREATE INDEX idx_webhook_deliveries_ws ON webhook_deliveries (workspace_id);
CREATE INDEX idx_webhook_deliveries_sub ON webhook_deliveries (subscription_id);
CREATE INDEX idx_webhook_deliveries_status ON webhook_deliveries (status);

ALTER TABLE webhook_deliveries ENABLE ROW LEVEL SECURITY;
ALTER TABLE webhook_deliveries FORCE ROW LEVEL SECURITY;

CREATE POLICY webhook_deliveries_select_rls ON webhook_deliveries
    FOR SELECT USING (workspace_id = app_current_workspace_id());

CREATE POLICY webhook_deliveries_insert_rls ON webhook_deliveries
    FOR INSERT WITH CHECK (workspace_id = app_current_workspace_id());

CREATE POLICY webhook_deliveries_update_rls ON webhook_deliveries
    FOR UPDATE USING (workspace_id = app_current_workspace_id());

CREATE POLICY webhook_deliveries_delete_rls ON webhook_deliveries
    FOR DELETE USING (workspace_id = app_current_workspace_id());

GRANT SELECT, INSERT, UPDATE, DELETE ON webhook_deliveries TO kanban_app;
GRANT SELECT ON webhook_deliveries TO app_rls_reader;

-- 8. Helper routines for unauthenticated SCM inbound webhooks
CREATE OR REPLACE FUNCTION get_repo_binding_for_webhook(p_binding_id UUID)
RETURNS TABLE (
    id UUID,
    workspace_id UUID,
    project_id UUID,
    slug TEXT,
    remote_url TEXT,
    default_ref TEXT,
    access_mode TEXT,
    credential_dek_kid TEXT,
    wrapped_webhook_secret BYTEA,
    webhook_secret_dek_kid TEXT,
    ssh_known_hosts TEXT,
    created_by UUID
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    RETURN QUERY
    SELECT b.id, b.workspace_id, b.project_id, b.slug, b.remote_url, b.default_ref,
           b.access_mode, b.credential_dek_kid, b.wrapped_webhook_secret,
           b.webhook_secret_dek_kid, b.ssh_known_hosts, b.created_by
    FROM project_repo_bindings b
    WHERE b.id = p_binding_id;
END;
$$;

CREATE OR REPLACE FUNCTION find_repo_binding_by_url_for_webhook(p_url_pattern TEXT)
RETURNS TABLE (
    id UUID,
    workspace_id UUID,
    project_id UUID,
    slug TEXT,
    remote_url TEXT,
    default_ref TEXT,
    access_mode TEXT,
    credential_dek_kid TEXT,
    wrapped_webhook_secret BYTEA,
    webhook_secret_dek_kid TEXT,
    ssh_known_hosts TEXT,
    created_by UUID
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    RETURN QUERY
    SELECT b.id, b.workspace_id, b.project_id, b.slug, b.remote_url, b.default_ref,
           b.access_mode, b.credential_dek_kid, b.wrapped_webhook_secret,
           b.webhook_secret_dek_kid, b.ssh_known_hosts, b.created_by
    FROM project_repo_bindings b
    WHERE b.remote_url ILIKE '%' || p_url_pattern || '%'
    LIMIT 1;
END;
$$;

ALTER FUNCTION get_repo_binding_for_webhook(UUID) OWNER TO kanban_migrator;
ALTER FUNCTION find_repo_binding_by_url_for_webhook(TEXT) OWNER TO kanban_migrator;

GRANT EXECUTE ON FUNCTION get_repo_binding_for_webhook(UUID) TO kanban_app;
GRANT EXECUTE ON FUNCTION find_repo_binding_by_url_for_webhook(TEXT) TO kanban_app;

