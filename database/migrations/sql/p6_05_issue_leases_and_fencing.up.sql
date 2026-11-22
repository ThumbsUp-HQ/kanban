-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

-- 1. Add fencing_token and row_version to issues
ALTER TABLE issues ADD COLUMN IF NOT EXISTS fencing_token BIGINT NOT NULL DEFAULT 0;
ALTER TABLE issues ADD COLUMN IF NOT EXISTS row_version BIGINT NOT NULL DEFAULT 1;

-- 2. Create issue_leases table
CREATE TABLE IF NOT EXISTS issue_leases (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    issue_id UUID NOT NULL UNIQUE REFERENCES issues(id) ON DELETE CASCADE,
    principal_id UUID NOT NULL REFERENCES principals(id) ON DELETE CASCADE,
    fencing_token BIGINT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX IF NOT EXISTS idx_issue_leases_ws ON issue_leases (workspace_id);
CREATE INDEX IF NOT EXISTS idx_issue_leases_expires_at ON issue_leases (expires_at);
CREATE INDEX IF NOT EXISTS idx_issue_leases_principal ON issue_leases (principal_id);

ALTER TABLE issue_leases ENABLE ROW LEVEL SECURITY;
ALTER TABLE issue_leases FORCE ROW LEVEL SECURITY;

CREATE POLICY issue_leases_select_rls ON issue_leases
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(issue_id, 1)
    );

CREATE POLICY issue_leases_insert_rls ON issue_leases
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND (app_has_object_capability(issue_id, 4) OR app_has_object_capability(issue_id, 8))
    );

CREATE POLICY issue_leases_update_rls ON issue_leases
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
        AND (app_has_object_capability(issue_id, 4) OR app_has_object_capability(issue_id, 8))
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND (app_has_object_capability(issue_id, 4) OR app_has_object_capability(issue_id, 8))
    );

CREATE POLICY issue_leases_delete_rls ON issue_leases
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
        AND (
            app_has_object_capability(issue_id, 4)
            OR app_has_object_capability(issue_id, 8)
            OR principal_id = ANY(app_effective_principal_set())
            OR app_principal_has_role(workspace_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
        )
    );

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE issue_leases TO kanban_app;
GRANT SELECT ON TABLE issue_leases TO app_rls_reader;
ALTER TABLE issue_leases OWNER TO kanban_migrator;

-- 3. Add worker claim support to workflow_hook_invocations
ALTER TABLE workflow_hook_invocations ADD COLUMN IF NOT EXISTS claimed_by_worker TEXT;
ALTER TABLE workflow_hook_invocations ADD COLUMN IF NOT EXISTS claim_expires_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_workflow_hook_invocations_worker_claim
    ON workflow_hook_invocations (status, claim_expires_at)
    WHERE hook_kind = 'agent_interceptor';

-- 4. BEFORE UPDATE PL/pgSQL guard on issues
CREATE OR REPLACE FUNCTION check_issues_concurrency_guard()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_lease_principal_id uuid;
    v_lease_fencing_token bigint;
    v_lease_expires_at timestamptz;
    v_caller_pid uuid;
    v_is_admin_override boolean;
    v_guc_fencing text;
BEGIN
    -- 1. Automatically increment row_version
    NEW.row_version := OLD.row_version + 1;

    -- 2. Reject stale fencing token writes
    IF NEW.fencing_token < OLD.fencing_token THEN
        RAISE EXCEPTION 'FENCING_TOKEN_STALE'
            USING ERRCODE = 'P0001',
                  HINT = 'Supplied fencing_token is older than current issue fencing_token';
    END IF;

    v_guc_fencing := NULLIF(current_setting('app.fencing_token', true), '');
    IF v_guc_fencing IS NOT NULL AND v_guc_fencing::bigint < OLD.fencing_token THEN
        RAISE EXCEPTION 'FENCING_TOKEN_STALE'
            USING ERRCODE = 'P0001',
                  HINT = 'GUC app.fencing_token is older than current issue fencing_token';
    END IF;

    -- 3. Check for admin override GUC
    v_is_admin_override := (
        COALESCE(current_setting('app.admin_override', true), '') IN ('on', 'true', '1')
        OR COALESCE(current_setting('kanban.admin_override', true), '') IN ('on', 'true', '1')
        OR COALESCE(current_setting('app.lease_override', true), '') IN ('on', 'true', '1')
        OR CURRENT_USER IN ('postgres', 'kanban_migrator')
    );

    IF NOT v_is_admin_override THEN
        -- Check if an unexpired lease exists on this issue
        SELECT principal_id, fencing_token, expires_at
        INTO v_lease_principal_id, v_lease_fencing_token, v_lease_expires_at
        FROM issue_leases
        WHERE issue_id = NEW.id;

        IF FOUND AND v_lease_expires_at > clock_timestamp() THEN
            v_caller_pid := app_current_principal_id();
            IF v_caller_pid IS NULL OR v_caller_pid <> v_lease_principal_id THEN
                RAISE EXCEPTION 'LEASE_HELD'
                    USING ERRCODE = 'P0001',
                          HINT = 'Issue is actively leased by another principal';
            END IF;
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS issues_concurrency_guard ON issues;
CREATE TRIGGER issues_concurrency_guard
    BEFORE UPDATE ON issues
    FOR EACH ROW
    EXECUTE FUNCTION check_issues_concurrency_guard();

ALTER FUNCTION check_issues_concurrency_guard() OWNER TO kanban_migrator;
