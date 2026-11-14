-- Revert Phase 4 / MCP: Ephemeral kb_agt_eph_* read-only MCP tokens (KB-P4-13)

DROP TABLE IF EXISTS mcp_ephemeral_tokens CASCADE;

CREATE OR REPLACE FUNCTION app_has_object_capability(p_object_id uuid, p_mask integer)
RETURNS boolean
LANGUAGE sql
STABLE PARALLEL SAFE SECURITY INVOKER
AS $$
    SELECT EXISTS (
        SELECT 1 FROM effective_resource_access era
        WHERE era.object_id = p_object_id
          AND era.workspace_id = app_current_workspace_id()
          AND era.principal_id = ANY (app_effective_principal_set())
          AND (era.allow_mask & p_mask) = p_mask
          AND (era.deny_mask  & p_mask) = 0
    );
$$;

GRANT EXECUTE ON FUNCTION app_has_object_capability(uuid, integer) TO kanban_app, app_rls_reader, kanban_migrator;

DROP FUNCTION IF EXISTS app_effective_principal_set_for(uuid);
