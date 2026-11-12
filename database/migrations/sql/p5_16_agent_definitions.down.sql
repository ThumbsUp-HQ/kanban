-- Revert Phase 5 / Database + API: agent_definitions registry (KB-P5-16)

REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLE agent_definitions FROM kanban_app;
REVOKE SELECT ON TABLE agent_definitions FROM app_rls_reader;

DROP POLICY IF EXISTS agent_definitions_delete_rls ON agent_definitions;
DROP POLICY IF EXISTS agent_definitions_update_rls ON agent_definitions;
DROP POLICY IF EXISTS agent_definitions_insert_rls ON agent_definitions;
DROP POLICY IF EXISTS agent_definitions_select_rls ON agent_definitions;

DROP TABLE IF EXISTS agent_definitions CASCADE;
