-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

-- 1. Alter project_repo_bindings to add git truststore columns
ALTER TABLE project_repo_bindings
    ADD COLUMN IF NOT EXISTS ssh_allowed_signers TEXT NULL,
    ADD COLUMN IF NOT EXISTS gpg_trusted_armored_keys TEXT NULL,
    ADD COLUMN IF NOT EXISTS sigstore_trusted_identities_json JSONB NOT NULL DEFAULT '[]'::jsonb;

-- 2. Create commit_attestations table
CREATE TABLE IF NOT EXISTS commit_attestations (
    id                UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id      UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    repo_binding_id   UUID NOT NULL REFERENCES project_repo_bindings(id) ON DELETE CASCADE,
    commit_sha        TEXT NOT NULL,
    sig_scheme        TEXT NOT NULL,
    signer_identity   TEXT NOT NULL,
    key_fingerprint   TEXT NOT NULL,
    verified          BOOLEAN NOT NULL DEFAULT TRUE,
    verified_at       TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX IF NOT EXISTS idx_commit_attestations_ws ON commit_attestations (workspace_id);
CREATE INDEX IF NOT EXISTS idx_commit_attestations_repo_sha ON commit_attestations (repo_binding_id, commit_sha);

ALTER TABLE commit_attestations ENABLE ROW LEVEL SECURITY;
ALTER TABLE commit_attestations FORCE ROW LEVEL SECURITY;

CREATE POLICY commit_attestations_select_rls ON commit_attestations
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
    );

CREATE POLICY commit_attestations_insert_rls ON commit_attestations
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
    );

CREATE POLICY commit_attestations_update_rls ON commit_attestations
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
    );

CREATE POLICY commit_attestations_delete_rls ON commit_attestations
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
    );

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE commit_attestations TO kanban_app;
GRANT SELECT ON TABLE commit_attestations TO app_rls_reader;

ALTER TABLE commit_attestations OWNER TO kanban_migrator;

-- 3. Expand workflow_transition_hooks constraints to include deterministic gate types
ALTER TABLE workflow_transition_hooks DROP CONSTRAINT IF EXISTS ck_workflow_transition_hooks_kind;
ALTER TABLE workflow_transition_hooks DROP CONSTRAINT IF EXISTS workflow_transition_hooks_hook_kind_check;
ALTER TABLE workflow_transition_hooks ADD CONSTRAINT ck_workflow_transition_hooks_kind CHECK (
    (hook_kind IN ('sync_validator', 'sync_mutator') AND wasm_module_sha256 IS NOT NULL AND agent_definition_id IS NULL)
    OR
    (hook_kind = 'agent_interceptor' AND agent_definition_id IS NOT NULL AND wasm_module_sha256 IS NULL)
    OR
    (hook_kind IN ('commit_signature', 'ci_check_run', 'slsa_provenance') AND wasm_module_sha256 IS NULL AND agent_definition_id IS NULL)
);

ALTER TABLE workflow_hook_invocations DROP CONSTRAINT IF EXISTS ck_workflow_hook_invocations_kind;
ALTER TABLE workflow_hook_invocations DROP CONSTRAINT IF EXISTS workflow_hook_invocations_hook_kind_check;
ALTER TABLE workflow_hook_invocations ADD CONSTRAINT ck_workflow_hook_invocations_kind CHECK (
    hook_kind IN ('sync_validator', 'sync_mutator', 'agent_interceptor', 'commit_signature', 'ci_check_run', 'slsa_provenance')
);
