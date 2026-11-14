-- Revert Phase 5 / Database + Agent: ai_provider_configs and ai_token_ledgers (KB-P5-05a)

DROP POLICY IF EXISTS ai_token_ledgers_delete_rls ON ai_token_ledgers;
DROP POLICY IF EXISTS ai_token_ledgers_update_rls ON ai_token_ledgers;
DROP POLICY IF EXISTS ai_token_ledgers_insert_rls ON ai_token_ledgers;
DROP POLICY IF EXISTS ai_token_ledgers_select_rls ON ai_token_ledgers;

DROP POLICY IF EXISTS ai_provider_configs_delete_rls ON ai_provider_configs;
DROP POLICY IF EXISTS ai_provider_configs_update_rls ON ai_provider_configs;
DROP POLICY IF EXISTS ai_provider_configs_insert_rls ON ai_provider_configs;
DROP POLICY IF EXISTS ai_provider_configs_select_rls ON ai_provider_configs;

DROP TABLE IF EXISTS ai_token_ledgers CASCADE;
DROP TABLE IF EXISTS ai_provider_configs CASCADE;

DROP FUNCTION IF EXISTS ai_provider_secret(UUID);
DROP FUNCTION IF EXISTS app_agent_runtime_principal();
