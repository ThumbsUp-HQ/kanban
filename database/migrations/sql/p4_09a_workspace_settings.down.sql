-- Revert Phase 4 / MCP: workspace_settings DDL, FORCE RLS, defaults & triggers (KB-P4-09a)

DROP TRIGGER IF EXISTS workspaces_init_settings ON workspaces;
DROP FUNCTION IF EXISTS initialize_workspace_settings();
DROP TRIGGER IF EXISTS workspace_settings_set_updated_at ON workspace_settings;
DROP POLICY IF EXISTS workspace_settings_delete_rls ON workspace_settings;
DROP POLICY IF EXISTS workspace_settings_update_rls ON workspace_settings;
DROP POLICY IF EXISTS workspace_settings_insert_rls ON workspace_settings;
DROP POLICY IF EXISTS workspace_settings_select_rls ON workspace_settings;
DROP TABLE IF EXISTS workspace_settings CASCADE;
