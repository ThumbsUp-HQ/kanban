-- Phase 4 / MCP: Ephemeral kb_agt_eph_* read-only MCP tokens (KB-P4-13)

CREATE TABLE mcp_ephemeral_tokens (
    id                      UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id            UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    execution_id            UUID NOT NULL, -- Bound to workflow_transition_executions.id in Phase 5
    invoking_principal_id   UUID NOT NULL REFERENCES principals(id) ON DELETE CASCADE,
    agent_principal_id      UUID NOT NULL REFERENCES principals(id) ON DELETE CASCADE,
    project_id              UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    token_sha256            BYTEA NOT NULL UNIQUE CHECK (octet_length(token_sha256) = 32),
    allowed_tools           TEXT[] NOT NULL
                            CHECK (cardinality(allowed_tools) BETWEEN 1 AND 4
                                   AND allowed_tools <@ ARRAY['search_tickets','read_ticket','search_knowledge','read_doc']::text[]),
    max_calls               SMALLINT NOT NULL DEFAULT 25 CHECK (max_calls BETWEEN 1 AND 25),
    calls_used              SMALLINT NOT NULL DEFAULT 0 CHECK (calls_used >= 0 AND calls_used <= max_calls),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    expires_at              TIMESTAMPTZ NOT NULL,
    revoked_at              TIMESTAMPTZ,
    CHECK (expires_at > created_at AND expires_at <= created_at + interval '120 seconds')
);

CREATE INDEX mcp_eph_execution_idx ON mcp_ephemeral_tokens (execution_id) WHERE revoked_at IS NULL;
CREATE INDEX mcp_eph_token_sha256_idx ON mcp_ephemeral_tokens (token_sha256);
CREATE INDEX mcp_eph_workspace_idx ON mcp_ephemeral_tokens (workspace_id);

ALTER TABLE mcp_ephemeral_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE mcp_ephemeral_tokens FORCE ROW LEVEL SECURITY;

CREATE POLICY mcp_ephemeral_tokens_select_rls ON mcp_ephemeral_tokens
    FOR SELECT USING (
        app_current_workspace_id() IS NULL
        OR workspace_id = app_current_workspace_id()
    );

CREATE POLICY mcp_ephemeral_tokens_insert_rls ON mcp_ephemeral_tokens
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
    );

CREATE POLICY mcp_ephemeral_tokens_update_rls ON mcp_ephemeral_tokens
    FOR UPDATE USING (
        app_current_workspace_id() IS NULL
        OR workspace_id = app_current_workspace_id()
    ) WITH CHECK (
        app_current_workspace_id() IS NULL
        OR workspace_id = app_current_workspace_id()
    );

CREATE POLICY mcp_ephemeral_tokens_delete_rls ON mcp_ephemeral_tokens
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
    );

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE mcp_ephemeral_tokens TO kanban_app;
GRANT SELECT ON TABLE mcp_ephemeral_tokens TO app_rls_reader;

-- Helper function to retrieve effective principal set for any principal
CREATE OR REPLACE FUNCTION app_effective_principal_set_for(p_principal_id uuid)
RETURNS uuid[]
LANGUAGE plpgsql
STABLE PARALLEL SAFE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_ws uuid;
    v_status text;
    v_current_ws uuid;
    v_groups uuid[];
BEGIN
    IF p_principal_id IS NULL THEN
        RETURN '{}'::uuid[];
    END IF;

    v_current_ws := app_current_workspace_id();

    SELECT workspace_id, status
    INTO v_ws, v_status
    FROM principals
    WHERE id = p_principal_id;

    IF NOT FOUND OR v_status <> 'ACTIVE' OR (v_current_ws IS NOT NULL AND v_ws <> v_current_ws) THEN
        RETURN '{}'::uuid[];
    END IF;

    SELECT COALESCE(array_agg(pgc.ancestor_group_id ORDER BY pgc.depth), '{}'::uuid[])
    INTO v_groups
    FROM principal_group_closure pgc
    JOIN principals gp ON gp.id = pgc.ancestor_group_id AND gp.status = 'ACTIVE'
    WHERE pgc.member_id = p_principal_id;

    RETURN ARRAY[p_principal_id] || v_groups;
END;
$$;

GRANT EXECUTE ON FUNCTION app_effective_principal_set_for(uuid) TO kanban_app, app_rls_reader, kanban_migrator;

-- Upgrade app_has_object_capability to enforce ephemeral project pin and agent principal OBO
CREATE OR REPLACE FUNCTION app_has_object_capability(p_object_id uuid, p_mask integer)
RETURNS boolean
LANGUAGE plpgsql
STABLE PARALLEL SAFE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_human_pset uuid[];
    v_agent_pset uuid[];
    v_agent_id_str text;
    v_eph_proj text;
    v_obj_proj uuid;
    v_obj_type text;
BEGIN
    -- Project pin check when app.ephemeral_project_id is set
    v_eph_proj := NULLIF(current_setting('app.ephemeral_project_id', true), '');
    IF v_eph_proj IS NOT NULL THEN
        SELECT project_id, object_type::text INTO v_obj_proj, v_obj_type FROM objects WHERE id = p_object_id;
        IF NOT FOUND THEN
            RETURN FALSE;
        END IF;
        IF v_obj_type = 'project' THEN
            IF p_object_id <> v_eph_proj::uuid THEN
                RETURN FALSE;
            END IF;
        ELSIF v_obj_proj IS NULL OR v_obj_proj <> v_eph_proj::uuid THEN
            RETURN FALSE;
        END IF;
    END IF;

    -- Human principal capability check
    v_human_pset := app_effective_principal_set();
    IF cardinality(v_human_pset) = 0 THEN
        RETURN FALSE;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM effective_resource_access era
        WHERE era.object_id = p_object_id
          AND era.workspace_id = app_current_workspace_id()
          AND era.principal_id = ANY (v_human_pset)
          AND (era.allow_mask & p_mask) = p_mask
          AND (era.deny_mask  & p_mask) = 0
    ) THEN
        RETURN FALSE;
    END IF;

    -- Agent capability check (OBO intersection) when app.agent_principal_id is set
    v_agent_id_str := NULLIF(current_setting('app.agent_principal_id', true), '');
    IF v_agent_id_str IS NOT NULL THEN
        v_agent_pset := app_effective_principal_set_for(v_agent_id_str::uuid);
        IF cardinality(v_agent_pset) = 0 THEN
            RETURN FALSE;
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM effective_resource_access era
            WHERE era.object_id = p_object_id
              AND era.workspace_id = app_current_workspace_id()
              AND era.principal_id = ANY (v_agent_pset)
              AND (era.allow_mask & p_mask) = p_mask
              AND (era.deny_mask  & p_mask) = 0
        ) THEN
            RETURN FALSE;
        END IF;
    END IF;

    RETURN TRUE;
END;
$$;

GRANT EXECUTE ON FUNCTION app_has_object_capability(uuid, integer) TO kanban_app, app_rls_reader, kanban_migrator;
