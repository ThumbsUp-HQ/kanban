-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

-- Allow capability_mask 0 for deny-all MCP keys boundary (KB-SEC-05 / KAN-418)
ALTER TABLE mcp_api_keys
    DROP CONSTRAINT IF EXISTS mcp_api_keys_capability_mask_check,
    ADD CONSTRAINT mcp_api_keys_capability_mask_check CHECK (capability_mask BETWEEN 0 AND 255);
