-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

-- 1. Drop issue import/export governance columns from workspace_settings
ALTER TABLE workspace_settings
    DROP COLUMN IF EXISTS issue_export_enabled,
    DROP COLUMN IF EXISTS issue_import_enabled,
    DROP COLUMN IF EXISTS issue_export_allowed_roles;
