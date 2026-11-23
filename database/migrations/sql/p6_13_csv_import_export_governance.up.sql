-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

-- 1. Add issue import/export governance columns to workspace_settings
ALTER TABLE workspace_settings
    ADD COLUMN IF NOT EXISTS issue_export_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS issue_import_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS issue_export_allowed_roles TEXT[] NOT NULL DEFAULT ARRAY['workspace_admin', 'project_admin', 'member']::text[];
