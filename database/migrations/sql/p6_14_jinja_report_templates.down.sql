-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.
-- Revert Phase 6 / Jinja2 Reports: report_templates table, 3-tier governance on workspace_settings, and built-in templates (KAN-317)

DROP TRIGGER IF EXISTS trg_seed_workspace_report_templates ON workspaces;
DROP FUNCTION IF EXISTS trigger_seed_workspace_report_templates();
DROP FUNCTION IF EXISTS seed_builtin_report_templates(UUID);

DROP TRIGGER IF EXISTS report_templates_set_updated_at ON report_templates;
DROP POLICY IF EXISTS report_templates_delete_rls ON report_templates;
DROP POLICY IF EXISTS report_templates_update_rls ON report_templates;
DROP POLICY IF EXISTS report_templates_insert_rls ON report_templates;
DROP POLICY IF EXISTS report_templates_select_rls ON report_templates;

DROP TABLE IF EXISTS report_templates CASCADE;

ALTER TABLE workspace_settings
    DROP COLUMN IF EXISTS report_export_allowed_roles,
    DROP COLUMN IF EXISTS report_export_enabled;
