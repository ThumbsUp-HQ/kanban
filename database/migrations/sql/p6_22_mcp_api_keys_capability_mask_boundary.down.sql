-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

ALTER TABLE mcp_api_keys
    DROP CONSTRAINT IF EXISTS mcp_api_keys_capability_mask_check,
    ADD CONSTRAINT mcp_api_keys_capability_mask_check CHECK (capability_mask BETWEEN 1 AND 255);
