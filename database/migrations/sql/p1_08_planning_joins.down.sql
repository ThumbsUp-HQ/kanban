-- Revert KB-P1-08: cycles, modules, assignees, labels & subscriptions join tables

DROP TRIGGER IF EXISTS issue_assignees_autosubscribe_ai_trg ON issue_assignees;
DROP FUNCTION IF EXISTS issue_assignees_autosubscribe_ai();

DROP TRIGGER IF EXISTS issues_autosubscribe_creator_ai_trg ON issues;
DROP FUNCTION IF EXISTS issues_autosubscribe_creator_ai();

DROP TRIGGER IF EXISTS issue_labels_exclusive_bi_trg ON issue_labels;
DROP FUNCTION IF EXISTS issue_labels_exclusive_bi();

DROP TRIGGER IF EXISTS issue_assignees_guard_bi_trg ON issue_assignees;
DROP FUNCTION IF EXISTS issue_assignees_guard_bi();

DROP TRIGGER IF EXISTS issues_apply_module_defaults_ai_trg ON issues;
DROP FUNCTION IF EXISTS issues_apply_module_defaults_ai();

DROP TRIGGER IF EXISTS project_module_defaults_guard_bi_trg ON project_module_defaults;
DROP FUNCTION IF EXISTS project_module_defaults_guard_bi();

DROP TRIGGER IF EXISTS issue_modules_guard_bi_trg ON issue_modules;
DROP FUNCTION IF EXISTS issue_modules_guard_bi();

DROP TRIGGER IF EXISTS issue_subscriptions_guard_bi_trg ON issue_subscriptions;
DROP FUNCTION IF EXISTS issue_subscriptions_guard_bi();

DROP TRIGGER IF EXISTS issues_cycle_project_biu_trg ON issues;
DROP FUNCTION IF EXISTS issues_cycle_project_biu();

DROP TRIGGER IF EXISTS modules_spine_match_biu_trg ON modules;
DROP FUNCTION IF EXISTS modules_spine_match_biu();

DROP TRIGGER IF EXISTS cycles_spine_match_biu_trg ON cycles;
DROP FUNCTION IF EXISTS cycles_spine_match_biu();

DROP TABLE IF EXISTS issue_subscriptions CASCADE;
DROP TABLE IF EXISTS issue_labels CASCADE;
DROP TABLE IF EXISTS issue_assignees CASCADE;
DROP TABLE IF EXISTS issue_modules CASCADE;
DROP TABLE IF EXISTS project_module_defaults CASCADE;

ALTER TABLE issues DROP CONSTRAINT IF EXISTS issues_cycle_fk;

DROP TABLE IF EXISTS modules CASCADE;
DROP TABLE IF EXISTS cycles CASCADE;
