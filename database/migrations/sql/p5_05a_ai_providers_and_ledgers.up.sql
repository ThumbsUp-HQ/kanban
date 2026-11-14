-- Phase 5 / Database + Agent: ai_provider_configs and ai_token_ledgers (KB-P5-05a, S10.1, S10.2)

-- 1. Create agent-runtime role for secret unwrap boundary
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agent-runtime') THEN
        CREATE ROLE "agent-runtime" WITH NOLOGIN NOINHERIT NOBYPASSRLS;
    END IF;
    EXECUTE format('GRANT "agent-runtime" TO %I WITH SET TRUE, INHERIT TRUE', CURRENT_USER);
END $$;
GRANT "agent-runtime" TO kanban_app;

-- 2. DDL: ai_provider_configs
CREATE TABLE ai_provider_configs (
    id               UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id     UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    project_id       UUID REFERENCES projects(id) ON DELETE CASCADE,  -- NULL = workspace default
    provider_kind    TEXT NOT NULL CHECK (provider_kind IN ('openai','ollama','gemini','fixture')),
    display_name     TEXT NOT NULL CHECK (char_length(display_name) BETWEEN 1 AND 80),
    base_url         TEXT,
    model_allowlist  TEXT[] NOT NULL CHECK (cardinality(model_allowlist) BETWEEN 1 AND 32),
    residency_tier   TEXT NOT NULL CHECK (residency_tier ~ '^[a-z0-9:._-]{1,64}$'),
    priority         SMALLINT NOT NULL DEFAULT 100,
    settings_json    JSONB NOT NULL DEFAULT '{}'::jsonb,  -- non-secret settings only (CIDRs, region, timeouts)
    wrapped_api_key  BYTEA,          -- AES-256-GCM ciphertext||tag
    api_key_nonce    BYTEA,
    wrapped_dek      BYTEA,          -- DEK wrapped by KMS / MASTER_KEK
    dek_kid          TEXT,
    is_enabled       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CHECK ((wrapped_api_key IS NULL) = (wrapped_dek IS NULL))
);

CREATE INDEX idx_ai_provider_configs_ws_proj ON ai_provider_configs (workspace_id, project_id);
CREATE INDEX idx_ai_provider_configs_ws_prio ON ai_provider_configs (workspace_id, priority);

-- 3. DDL: ai_token_ledgers
CREATE TABLE ai_token_ledgers (
    id                 UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id       UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    project_id         UUID REFERENCES projects(id) ON DELETE CASCADE,
    provider_config_id UUID NOT NULL REFERENCES ai_provider_configs(id) ON DELETE CASCADE,
    period_kind        TEXT NOT NULL CHECK (period_kind IN ('daily','monthly')),
    period_start       DATE NOT NULL,
    token_cap          BIGINT NOT NULL CHECK (token_cap >= 0),
    tokens_reserved    BIGINT NOT NULL DEFAULT 0 CHECK (tokens_reserved >= 0),
    tokens_used        BIGINT NOT NULL DEFAULT 0 CHECK (tokens_used >= 0),
    CHECK (tokens_used + tokens_reserved <= token_cap),
    UNIQUE NULLS NOT DISTINCT (workspace_id, project_id, provider_config_id, period_kind, period_start)
);

CREATE INDEX idx_ai_token_ledgers_lookup ON ai_token_ledgers (workspace_id, provider_config_id, period_kind, period_start);

-- 4. Grants and Privileges
GRANT INSERT, UPDATE, DELETE ON ai_provider_configs TO kanban_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ai_token_ledgers TO kanban_app;
GRANT SELECT ON ai_token_ledgers TO app_rls_reader;

REVOKE SELECT ON ai_provider_configs FROM kanban_app;
REVOKE SELECT ON ai_provider_configs FROM app_rls_reader;

GRANT SELECT (
    id, workspace_id, project_id, provider_kind, display_name,
    base_url, model_allowlist, residency_tier, priority,
    settings_json, dek_kid, is_enabled, created_at, updated_at
) ON ai_provider_configs TO kanban_app;

GRANT SELECT (
    id, workspace_id, project_id, provider_kind, display_name,
    base_url, model_allowlist, residency_tier, priority,
    settings_json, dek_kid, is_enabled, created_at, updated_at
) ON ai_provider_configs TO app_rls_reader;

-- Column-level privilege: REVOKE SELECT (wrapped_api_key, api_key_nonce, wrapped_dek) ON ai_provider_configs FROM kanban_app
REVOKE SELECT (wrapped_api_key, api_key_nonce, wrapped_dek) ON ai_provider_configs FROM kanban_app;
REVOKE SELECT (wrapped_api_key, api_key_nonce, wrapped_dek) ON ai_provider_configs FROM app_rls_reader;

-- 5. Security Definer function ai_provider_secret
CREATE OR REPLACE FUNCTION ai_provider_secret(p_config_id UUID)
RETURNS TABLE (
    wrapped_api_key BYTEA,
    api_key_nonce BYTEA,
    wrapped_dek BYTEA,
    dek_kid TEXT
)
LANGUAGE plpgsql
STABLE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_caller_ws UUID;
BEGIN
    v_caller_ws := NULLIF(current_setting('app.workspace_id', true), '')::UUID;
    IF v_caller_ws IS NULL THEN
        RETURN;
    END IF;

    RETURN QUERY
    SELECT c.wrapped_api_key, c.api_key_nonce, c.wrapped_dek, c.dek_kid
    FROM ai_provider_configs c
    WHERE c.id = p_config_id
      AND c.workspace_id = v_caller_ws
      AND c.is_enabled = TRUE
      AND c.wrapped_api_key IS NOT NULL;
END;
$$;

REVOKE ALL ON FUNCTION ai_provider_secret(UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION ai_provider_secret(UUID) TO "agent-runtime";

-- Helper function to identify svc-agent-runtime principal
CREATE OR REPLACE FUNCTION app_agent_runtime_principal()
RETURNS uuid
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_id uuid;
BEGIN
    SELECT id INTO v_id
    FROM principals
    WHERE principal_type = 'SERVICE_PRINCIPAL'
      AND display_name = 'svc-agent-runtime'
      AND workspace_id = app_current_workspace_id()
    ORDER BY created_at ASC
    LIMIT 1;

    IF v_id IS NOT NULL THEN
        RETURN v_id;
    END IF;

    RETURN NULLIF(current_setting('app.agent_runtime_principal_id', true), '')::uuid;
END;
$$;

GRANT EXECUTE ON FUNCTION app_agent_runtime_principal() TO kanban_app, app_rls_reader, kanban_migrator;

-- 6. Enable and Force Row-Level Security
ALTER TABLE ai_provider_configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_provider_configs FORCE ROW LEVEL SECURITY;

ALTER TABLE ai_token_ledgers ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_token_ledgers FORCE ROW LEVEL SECURITY;

-- 7. RLS Policies on ai_provider_configs
CREATE POLICY ai_provider_configs_select_rls ON ai_provider_configs
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND (
            (project_id IS NULL AND (app_has_object_capability(workspace_id, 64) OR app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])))
            OR
            (project_id IS NOT NULL AND (app_has_object_capability(project_id, 64) OR app_has_object_capability(workspace_id, 64) OR app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN'])))
        )
    );

CREATE POLICY ai_provider_configs_insert_rls ON ai_provider_configs
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND (
            (project_id IS NULL AND (app_has_object_capability(workspace_id, 64) OR app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])))
            OR
            (project_id IS NOT NULL AND (app_has_object_capability(project_id, 64) OR app_has_object_capability(workspace_id, 64) OR app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN'])))
        )
    );

CREATE POLICY ai_provider_configs_update_rls ON ai_provider_configs
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
        AND (
            (project_id IS NULL AND (app_has_object_capability(workspace_id, 64) OR app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])))
            OR
            (project_id IS NOT NULL AND (app_has_object_capability(project_id, 64) OR app_has_object_capability(workspace_id, 64) OR app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN'])))
        )
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND (
            (project_id IS NULL AND (app_has_object_capability(workspace_id, 64) OR app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])))
            OR
            (project_id IS NOT NULL AND (app_has_object_capability(project_id, 64) OR app_has_object_capability(workspace_id, 64) OR app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN'])))
        )
    );

CREATE POLICY ai_provider_configs_delete_rls ON ai_provider_configs
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
        AND (
            (project_id IS NULL AND (app_has_object_capability(workspace_id, 64) OR app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])))
            OR
            (project_id IS NOT NULL AND (app_has_object_capability(project_id, 64) OR app_has_object_capability(workspace_id, 64) OR app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN'])))
        )
    );

-- 8. RLS Policies on ai_token_ledgers
CREATE POLICY ai_token_ledgers_select_rls ON ai_token_ledgers
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND (
            (project_id IS NULL AND (app_has_object_capability(workspace_id, 64) OR app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])))
            OR
            (project_id IS NOT NULL AND (app_has_object_capability(project_id, 64) OR app_has_object_capability(workspace_id, 64) OR app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN'])))
            OR
            (app_current_principal_id() IS NOT NULL AND app_current_principal_id() = app_agent_runtime_principal())
        )
    );

CREATE POLICY ai_token_ledgers_insert_rls ON ai_token_ledgers
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND (
            (project_id IS NULL AND (app_has_object_capability(workspace_id, 64) OR app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])))
            OR
            (project_id IS NOT NULL AND (app_has_object_capability(project_id, 64) OR app_has_object_capability(workspace_id, 64) OR app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN'])))
        )
    );

CREATE POLICY ai_token_ledgers_update_rls ON ai_token_ledgers
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
        AND (
            (project_id IS NULL AND (app_has_object_capability(workspace_id, 64) OR app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])))
            OR
            (project_id IS NOT NULL AND (app_has_object_capability(project_id, 64) OR app_has_object_capability(workspace_id, 64) OR app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN'])))
            OR
            (app_current_principal_id() IS NOT NULL AND app_current_principal_id() = app_agent_runtime_principal())
        )
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND (
            (project_id IS NULL AND (app_has_object_capability(workspace_id, 64) OR app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])))
            OR
            (project_id IS NOT NULL AND (app_has_object_capability(project_id, 64) OR app_has_object_capability(workspace_id, 64) OR app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN'])))
            OR
            (app_current_principal_id() IS NOT NULL AND app_current_principal_id() = app_agent_runtime_principal())
        )
    );

CREATE POLICY ai_token_ledgers_delete_rls ON ai_token_ledgers
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
        AND (
            (project_id IS NULL AND (app_has_object_capability(workspace_id, 64) OR app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])))
            OR
            (project_id IS NOT NULL AND (app_has_object_capability(project_id, 64) OR app_has_object_capability(workspace_id, 64) OR app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN'])))
        )
    );
