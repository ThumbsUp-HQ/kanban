-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.
-- Migration p5_12_custom_field_approvals.up.sql

CREATE TABLE custom_field_approvals (
    id                        UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id              UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    project_id                UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    field_id                  UUID NOT NULL REFERENCES custom_field_definitions(id) ON DELETE CASCADE,
    manifest_sha256           BYTEA NOT NULL CHECK (octet_length(manifest_sha256) = 32),
    target_scope              TEXT NOT NULL CHECK (target_scope IN ('PROJECT', 'WORKSPACE', 'SERVER')),
    credential_mode           TEXT NOT NULL CHECK (credential_mode IN ('INVOKING_USER', 'PROJECT_ADMIN_SP', 'SERVER_ADMIN_SP')),
    required_tier             TEXT NOT NULL CHECK (required_tier IN ('PROJECT_ADMIN', 'WORKSPACE_ADMIN', 'SERVER_ADMIN_DUAL')),
    status                    TEXT NOT NULL CHECK (status IN ('PENDING', 'PENDING_SECOND_APPROVER', 'APPROVED', 'REVOKED')),
    requested_by_id           UUID NOT NULL REFERENCES principals(id),
    justification             TEXT NOT NULL CHECK (char_length(btrim(justification)) BETWEEN 10 AND 2000),
    primary_approver_id       UUID REFERENCES principals(id),
    primary_approver_aal      SMALLINT CHECK (primary_approver_aal IS NULL OR primary_approver_aal >= 2),
    primary_approved_at       TIMESTAMPTZ,
    secondary_approver_id     UUID REFERENCES principals(id),
    secondary_approver_aal    SMALLINT CHECK (secondary_approver_aal IS NULL OR secondary_approver_aal >= 2),
    secondary_approved_at     TIMESTAMPTZ,
    sp_warning_acknowledged   BOOLEAN NOT NULL DEFAULT FALSE,
    approval_signature_hmac   BYTEA CHECK (approval_signature_hmac IS NULL OR octet_length(approval_signature_hmac) = 32),
    revoked_at                TIMESTAMPTZ,
    revoked_reason            TEXT,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT custom_field_approvals_dual_approver_distinct_check CHECK (secondary_approver_id IS NULL OR secondary_approver_id <> primary_approver_id),
    CONSTRAINT custom_field_approvals_scope_principal_combo_check CHECK (
        (target_scope = 'PROJECT'   AND credential_mode IN ('INVOKING_USER', 'PROJECT_ADMIN_SP')) OR
        (target_scope = 'WORKSPACE' AND credential_mode IN ('INVOKING_USER', 'PROJECT_ADMIN_SP')) OR
        (target_scope = 'SERVER'    AND credential_mode IN ('INVOKING_USER', 'SERVER_ADMIN_SP'))
    )
);

CREATE INDEX idx_cfa_field_status ON custom_field_approvals (field_id, status);
CREATE INDEX idx_cfa_project_status ON custom_field_approvals (project_id, status);
CREATE INDEX idx_cfa_workspace_status ON custom_field_approvals (workspace_id, status);

ALTER TABLE custom_field_approvals ENABLE ROW LEVEL SECURITY;
ALTER TABLE custom_field_approvals FORCE ROW LEVEL SECURITY;

CREATE POLICY custom_field_approvals_select_rls
    ON custom_field_approvals
    FOR SELECT
    USING (
        workspace_id = app_current_workspace_id()
        AND (
            app_principal_has_role(project_id, ARRAY['PROJECT_ADMIN', 'SERVER_ADMIN'])
            OR EXISTS (
                SELECT 1 FROM role_bindings rb
                WHERE rb.principal_id = ANY (app_effective_principal_set())
                  AND rb.workspace_id = custom_field_approvals.workspace_id
                  AND rb.role::text IN ('WORKSPACE_ADMIN', 'SERVER_ADMIN')
            )
        )
    );

CREATE POLICY custom_field_approvals_insert_rls
    ON custom_field_approvals
    FOR INSERT
    WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_current_aal_level() >= 2
    );

CREATE POLICY custom_field_approvals_update_rls
    ON custom_field_approvals
    FOR UPDATE
    USING (
        workspace_id = app_current_workspace_id()
    )
    WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_current_aal_level() >= 2
    );

CREATE POLICY custom_field_approvals_delete_rls
    ON custom_field_approvals
    FOR DELETE
    USING (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(project_id, ARRAY['PROJECT_ADMIN', 'SERVER_ADMIN'])
        AND app_current_aal_level() >= 2
    );

CREATE OR REPLACE FUNCTION custom_field_manifest_tamper_revoke_tf()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF NEW.manifest_sha256 IS DISTINCT FROM OLD.manifest_sha256 THEN
        UPDATE custom_field_approvals
        SET status = 'REVOKED',
            revoked_at = clock_timestamp(),
            revoked_reason = 'MANIFEST_SHA256_CHANGED'
        WHERE field_id = NEW.id
          AND status IN ('PENDING', 'PENDING_SECOND_APPROVER', 'APPROVED');
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER custom_field_manifest_tamper_revoke
AFTER UPDATE OF manifest_sha256 ON custom_field_definitions
FOR EACH ROW
EXECUTE FUNCTION custom_field_manifest_tamper_revoke_tf();

GRANT SELECT, INSERT, UPDATE, DELETE ON custom_field_approvals TO kanban_app;
GRANT SELECT ON custom_field_approvals TO app_rls_reader;
