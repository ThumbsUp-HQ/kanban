-- Phase 5 / Database + Workflow Engine: rollback workflow hooks, executions, and invocations (KB-P5-17a)

DROP TRIGGER IF EXISTS issues_state_guard ON issues;
DROP FUNCTION IF EXISTS check_issues_state_guard();
DROP TABLE IF EXISTS workflow_hook_invocations CASCADE;
DROP TABLE IF EXISTS workflow_transition_executions CASCADE;
DROP TABLE IF EXISTS workflow_transition_hooks CASCADE;
