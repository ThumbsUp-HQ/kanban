-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

-- 1. Revert workflow_hook_invocations constraint
ALTER TABLE workflow_hook_invocations DROP CONSTRAINT IF EXISTS ck_workflow_hook_invocations_kind;
ALTER TABLE workflow_hook_invocations ADD CONSTRAINT ck_workflow_hook_invocations_kind CHECK (
    hook_kind IN ('sync_validator', 'sync_mutator', 'agent_interceptor')
);

-- 2. Revert workflow_transition_hooks constraint
ALTER TABLE workflow_transition_hooks DROP CONSTRAINT IF EXISTS ck_workflow_transition_hooks_kind;
ALTER TABLE workflow_transition_hooks ADD CONSTRAINT ck_workflow_transition_hooks_kind CHECK (
    (hook_kind IN ('sync_validator', 'sync_mutator') AND wasm_module_sha256 IS NOT NULL AND agent_definition_id IS NULL)
    OR
    (hook_kind = 'agent_interceptor' AND agent_definition_id IS NOT NULL AND wasm_module_sha256 IS NULL)
);

-- 3. Drop commit_attestations table
DROP TABLE IF EXISTS commit_attestations CASCADE;

-- 4. Drop columns from project_repo_bindings
ALTER TABLE project_repo_bindings
    DROP COLUMN IF EXISTS ssh_allowed_signers,
    DROP COLUMN IF EXISTS gpg_trusted_armored_keys,
    DROP COLUMN IF EXISTS sigstore_trusted_identities_json;
