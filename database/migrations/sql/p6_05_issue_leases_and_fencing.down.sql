-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

DROP TRIGGER IF EXISTS issues_concurrency_guard ON issues;
DROP FUNCTION IF EXISTS check_issues_concurrency_guard();
DROP INDEX IF EXISTS idx_workflow_hook_invocations_worker_claim;
ALTER TABLE workflow_hook_invocations DROP COLUMN IF EXISTS claim_expires_at;
ALTER TABLE workflow_hook_invocations DROP COLUMN IF EXISTS claimed_by_worker;
DROP TABLE IF EXISTS issue_leases CASCADE;
ALTER TABLE issues DROP COLUMN IF EXISTS row_version;
ALTER TABLE issues DROP COLUMN IF EXISTS fencing_token;
