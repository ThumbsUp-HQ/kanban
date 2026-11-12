-- Phase 4 / MCP: Revert Scoped kb_* API keys (KB-P4-02a)

DROP FUNCTION IF EXISTS introspect_mcp_api_key(BYTEA);
DROP TABLE IF EXISTS mcp_api_keys CASCADE;
