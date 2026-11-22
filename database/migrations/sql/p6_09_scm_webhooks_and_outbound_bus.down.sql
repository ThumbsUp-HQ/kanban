-- Revert Phase 6 / DevSecOps Bus: SCM webhooks, artifacts, and outbound webhook bus (KB-DEVSECOPS-BUS-01)

DROP FUNCTION IF EXISTS find_repo_binding_by_url_for_webhook(TEXT);
DROP FUNCTION IF EXISTS get_repo_binding_for_webhook(UUID);

DROP TABLE IF EXISTS webhook_deliveries CASCADE;
DROP TABLE IF EXISTS webhook_subscriptions CASCADE;
DROP TABLE IF EXISTS scm_webhook_deliveries CASCADE;
DROP TABLE IF EXISTS scm_artifacts CASCADE;

ALTER TABLE project_repo_bindings
    DROP COLUMN IF EXISTS ssh_known_hosts,
    DROP COLUMN IF EXISTS wrapped_webhook_secret,
    DROP COLUMN IF EXISTS webhook_secret_dek_kid;

DELETE FROM link_type_matrix
WHERE link_type IN ('IMPLEMENTED_IN_PR', 'REFERENCED_BY_COMMIT', 'TRACKED_ON_BRANCH');
