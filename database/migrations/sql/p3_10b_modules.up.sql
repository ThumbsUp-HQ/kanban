-- Migration: p3_10b_modules (KB-P3-10b)
-- Add description_markdown, lead_principal_id, status to modules.
-- Enforce case-insensitive uniqueness on (project_id, lower(name)).
-- Add added_at and added_by_id to issue_modules and expose module_issues view.

ALTER TABLE modules
  ADD COLUMN IF NOT EXISTS description_markdown TEXT NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS lead_principal_id UUID REFERENCES principals(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('backlog', 'planned', 'in_progress', 'paused', 'completed', 'cancelled'));

CREATE UNIQUE INDEX IF NOT EXISTS modules_project_lower_name_uq ON modules (project_id, lower(name));
CREATE INDEX IF NOT EXISTS modules_lead_idx ON modules (lead_principal_id);

ALTER TABLE issue_modules
  ADD COLUMN IF NOT EXISTS added_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  ADD COLUMN IF NOT EXISTS added_by_id UUID REFERENCES principals(id) ON DELETE SET NULL;

CREATE OR REPLACE VIEW module_issues AS
  SELECT module_id, issue_id, workspace_id, added_at, added_by_id
  FROM issue_modules;
