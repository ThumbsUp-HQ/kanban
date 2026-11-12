-- Migration rollback: p3_10b_modules (KB-P3-10b)

DROP VIEW IF EXISTS module_issues;

ALTER TABLE issue_modules
  DROP COLUMN IF EXISTS added_by_id,
  DROP COLUMN IF EXISTS added_at;

DROP INDEX IF EXISTS modules_lead_idx;
DROP INDEX IF EXISTS modules_project_lower_name_uq;

ALTER TABLE modules
  DROP COLUMN IF EXISTS status,
  DROP COLUMN IF EXISTS lead_principal_id,
  DROP COLUMN IF EXISTS description_markdown;
