-- ============================================================================
-- 👍kanban Schema Dump: mcp_api_keys (KB-P4-14 / KANBA-106)
-- Hierarchical Scopable Keys (Global, Workspace, Project, Personal User)
-- & Granular Capability / Tool Narrowing with Friction Unlimited Expiry
-- ============================================================================

-- Table Definition
CREATE TABLE public.mcp_api_keys (
    id                    UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id          UUID REFERENCES public.workspaces(id) ON DELETE CASCADE,
    principal_id          UUID NOT NULL REFERENCES public.principals(id) ON DELETE RESTRICT,
    surface               TEXT NOT NULL CHECK (surface IN ('agent', 'docs', 'admin')),
    key_prefix            TEXT NOT NULL CHECK (key_prefix IN ('kb_agt_', 'kb_doc_', 'kb_adm_')),
    key_sha256            BYTEA NOT NULL UNIQUE CHECK (octet_length(key_sha256) = 32),
    display_hint          TEXT NOT NULL CHECK (char_length(display_hint) = 4),
    scopes                TEXT[] NOT NULL,
    created_by_id         UUID NOT NULL REFERENCES public.principals(id),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    expires_at            TIMESTAMPTZ,
    revoked_at            TIMESTAMPTZ,
    last_used_at          TIMESTAMPTZ,
    label                 TEXT,
    scope_tier            TEXT NOT NULL DEFAULT 'workspace'
                          CHECK (scope_tier IN ('global', 'workspace', 'project')),
    owner_kind            TEXT NOT NULL DEFAULT 'service_bot'
                          CHECK (owner_kind IN ('personal_user', 'service_bot')),
    project_id            UUID REFERENCES public.projects(id) ON DELETE CASCADE,
    allowed_workspace_ids UUID[],
    allowed_project_ids   UUID[],
    capability_mask       INTEGER NOT NULL DEFAULT 7
                          CHECK (capability_mask BETWEEN 1 AND 255),
    allowed_tools         TEXT[],
    disabled_tools        TEXT[] NOT NULL DEFAULT '{}'::TEXT[],
    allowed_cidrs         CIDR[],

    -- Constraints
    CONSTRAINT mcp_api_keys_surface_prefix_check
        CHECK ((surface, key_prefix) IN (
            ('agent', 'kb_agt_'),
            ('docs',  'kb_doc_'),
            ('admin', 'kb_adm_')
        )),
    CONSTRAINT mcp_api_keys_expires_at_check
        CHECK (expires_at IS NULL OR expires_at <= created_at + interval '365 days'),
    CONSTRAINT mcp_keys_tier_shape_chk
        CHECK (
            (scope_tier = 'global'    AND workspace_id IS NULL AND project_id IS NULL) OR
            (scope_tier = 'workspace' AND workspace_id IS NOT NULL AND project_id IS NULL) OR
            (scope_tier = 'project'   AND workspace_id IS NOT NULL AND project_id IS NOT NULL)
        )
);

-- Indexes
CREATE INDEX mcp_api_keys_workspace_idx   ON public.mcp_api_keys (workspace_id);
CREATE INDEX mcp_api_keys_principal_idx   ON public.mcp_api_keys (principal_id);
CREATE INDEX mcp_api_keys_key_sha256_idx  ON public.mcp_api_keys (key_sha256);
CREATE INDEX mcp_api_keys_project_idx     ON public.mcp_api_keys (project_id);
CREATE INDEX mcp_api_keys_scope_tier_idx  ON public.mcp_api_keys (scope_tier);
CREATE INDEX mcp_api_keys_owner_kind_idx  ON public.mcp_api_keys (owner_kind);

-- Row-Level Security
ALTER TABLE public.mcp_api_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.mcp_api_keys FORCE ROW LEVEL SECURITY;

-- RLS Policies
CREATE POLICY mcp_api_keys_select_rls ON public.mcp_api_keys
    FOR SELECT USING (
        (scope_tier = 'global' AND (app_current_workspace_id() IS NULL OR app_principal_has_role(NULL, ARRAY['SERVER_ADMIN'])))
        OR
        (scope_tier = 'workspace' AND (app_current_workspace_id() IS NULL OR workspace_id = app_current_workspace_id()) AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN']))
        OR
        (scope_tier = 'project' AND (app_current_workspace_id() IS NULL OR workspace_id = app_current_workspace_id()) AND app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN']))
        OR
        (owner_kind = 'personal_user' AND principal_id = app_current_principal_id() AND (workspace_id IS NULL OR app_current_workspace_id() IS NULL OR workspace_id = app_current_workspace_id()))
    );

CREATE POLICY mcp_api_keys_insert_rls ON public.mcp_api_keys
    FOR INSERT WITH CHECK (
        (scope_tier = 'global' AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN']))
        OR
        (scope_tier = 'workspace' AND (app_current_workspace_id() IS NULL OR workspace_id = app_current_workspace_id()) AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN']))
        OR
        (scope_tier = 'project' AND (app_current_workspace_id() IS NULL OR workspace_id = app_current_workspace_id()) AND app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN']))
        OR
        (owner_kind = 'personal_user' AND principal_id = app_current_principal_id())
    );

CREATE POLICY mcp_api_keys_update_rls ON public.mcp_api_keys
    FOR UPDATE USING (
        (scope_tier = 'global' AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN']))
        OR
        (scope_tier = 'workspace' AND (app_current_workspace_id() IS NULL OR workspace_id = app_current_workspace_id()) AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN']))
        OR
        (scope_tier = 'project' AND (app_current_workspace_id() IS NULL OR workspace_id = app_current_workspace_id()) AND app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN']))
        OR
        (owner_kind = 'personal_user' AND principal_id = app_current_principal_id())
    ) WITH CHECK (
        (scope_tier = 'global' AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN']))
        OR
        (scope_tier = 'workspace' AND (app_current_workspace_id() IS NULL OR workspace_id = app_current_workspace_id()) AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN']))
        OR
        (scope_tier = 'project' AND (app_current_workspace_id() IS NULL OR workspace_id = app_current_workspace_id()) AND app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN']))
        OR
        (owner_kind = 'personal_user' AND principal_id = app_current_principal_id())
    );

CREATE POLICY mcp_api_keys_delete_rls ON public.mcp_api_keys
    FOR DELETE USING (
        (scope_tier = 'global' AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN']))
        OR
        (scope_tier = 'workspace' AND (app_current_workspace_id() IS NULL OR workspace_id = app_current_workspace_id()) AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN']))
        OR
        (scope_tier = 'project' AND (app_current_workspace_id() IS NULL OR workspace_id = app_current_workspace_id()) AND app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN']))
        OR
        (owner_kind = 'personal_user' AND principal_id = app_current_principal_id())
    );

-- Introspection Function (20 columns returned)
CREATE OR REPLACE FUNCTION public.introspect_mcp_api_key(p_key_sha256 BYTEA)
RETURNS TABLE (
    id UUID,
    workspace_id UUID,
    principal_id UUID,
    surface TEXT,
    scopes TEXT[],
    created_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ,
    is_active BOOLEAN,
    scope_tier TEXT,
    owner_kind TEXT,
    project_id UUID,
    allowed_workspace_ids UUID[],
    allowed_project_ids UUID[],
    capability_mask INTEGER,
    allowed_tools TEXT[],
    disabled_tools TEXT[],
    allowed_cidrs TEXT[],
    label TEXT
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
    RETURN QUERY
    SELECT
        k.id,
        k.workspace_id,
        k.principal_id,
        k.surface,
        k.scopes,
        k.created_at,
        k.expires_at,
        k.revoked_at,
        k.last_used_at,
        (k.revoked_at IS NULL AND (k.expires_at IS NULL OR k.expires_at > clock_timestamp())) AS is_active,
        k.scope_tier,
        k.owner_kind,
        k.project_id,
        k.allowed_workspace_ids,
        k.allowed_project_ids,
        k.capability_mask,
        k.allowed_tools,
        k.disabled_tools,
        ARRAY(SELECT host(c) FROM unnest(k.allowed_cidrs) AS c)::TEXT[] AS allowed_cidrs,
        k.label
    FROM mcp_api_keys k
    WHERE k.key_sha256 = p_key_sha256;
END;
$$;
