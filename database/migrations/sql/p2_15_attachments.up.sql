-- Migration: p2_15_attachments (up)
-- Table: attachments with FORCE RLS, integrity triggers, and indices.

CREATE TABLE attachments (
    id                 UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id       UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    project_id         UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    issue_id           UUID REFERENCES issues(id) ON DELETE SET NULL,
    uploaded_by_id     UUID NOT NULL REFERENCES principals(id) ON DELETE RESTRICT,
    original_filename  TEXT NOT NULL CHECK (char_length(btrim(original_filename)) BETWEEN 1 AND 255),
    content_type       TEXT NOT NULL CHECK (content_type IN (
                           'image/png','image/jpeg','image/webp','image/avif','image/gif','image/svg+xml')),
    byte_size          INTEGER NOT NULL CHECK (byte_size BETWEEN 1 AND 26214400),
    pixel_width        INTEGER CHECK (pixel_width IS NULL OR pixel_width > 0),
    pixel_height       INTEGER CHECK (pixel_height IS NULL OR pixel_height > 0),
    blob_sha256        BYTEA NOT NULL CHECK (octet_length(blob_sha256) = 32),
    storage_key        TEXT NOT NULL CHECK (storage_key ~ '^sha256/[0-9a-f]{2}/[0-9a-f]{2}/[0-9a-f]{64}$'),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX attachments_workspace_project_idx ON attachments (workspace_id, project_id);
CREATE INDEX attachments_issue_id_idx ON attachments (issue_id) WHERE issue_id IS NOT NULL;
CREATE INDEX attachments_uploaded_by_idx ON attachments (uploaded_by_id);
CREATE INDEX attachments_storage_key_idx ON attachments (storage_key);
CREATE INDEX attachments_blob_sha256_idx ON attachments (blob_sha256);

CREATE OR REPLACE FUNCTION attachments_workspace_biu() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_proj_ws uuid;
    v_issue_ws uuid;
    v_issue_proj uuid;
BEGIN
    SELECT workspace_id INTO v_proj_ws FROM projects WHERE id = NEW.project_id;
    IF v_proj_ws IS NULL THEN
        RAISE EXCEPTION 'PROJECT_NOT_FOUND' USING ERRCODE = 'P0001';
    END IF;
    NEW.workspace_id := v_proj_ws;

    IF NEW.issue_id IS NOT NULL THEN
        SELECT workspace_id, project_id INTO v_issue_ws, v_issue_proj FROM issues WHERE id = NEW.issue_id;
        IF v_issue_ws IS NULL OR v_issue_ws <> NEW.workspace_id OR v_issue_proj <> NEW.project_id THEN
            RAISE EXCEPTION 'ATTACHMENT_ISSUE_MISMATCH' USING ERRCODE = 'P0001';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER attachments_workspace_biu_trg
BEFORE INSERT OR UPDATE ON attachments
FOR EACH ROW EXECUTE FUNCTION attachments_workspace_biu();

ALTER TABLE attachments ENABLE ROW LEVEL SECURITY;
ALTER TABLE attachments FORCE ROW LEVEL SECURITY;

CREATE POLICY attachments_select_rls ON attachments
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND app_has_object_capability(COALESCE(issue_id, project_id), 1)
    );

CREATE POLICY attachments_insert_rls ON attachments
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND uploaded_by_id = app_current_principal_id()
        AND (
            app_has_object_capability(COALESCE(issue_id, project_id), 2)
            OR app_has_object_capability(COALESCE(issue_id, project_id), 4)
        )
    );

CREATE POLICY attachments_update_rls ON attachments
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
        AND (
            (uploaded_by_id = app_current_principal_id() AND (
                app_has_object_capability(COALESCE(issue_id, project_id), 2)
                OR app_has_object_capability(COALESCE(issue_id, project_id), 4)
            ))
            OR app_has_object_capability(COALESCE(issue_id, project_id), 64)
        )
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND (
            (uploaded_by_id = app_current_principal_id() AND (
                app_has_object_capability(COALESCE(issue_id, project_id), 2)
                OR app_has_object_capability(COALESCE(issue_id, project_id), 4)
            ))
            OR app_has_object_capability(COALESCE(issue_id, project_id), 64)
        )
    );

CREATE POLICY attachments_delete_rls ON attachments
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
        AND (
            (uploaded_by_id = app_current_principal_id() AND (
                app_has_object_capability(COALESCE(issue_id, project_id), 2)
                OR app_has_object_capability(COALESCE(issue_id, project_id), 4)
            ))
            OR app_has_object_capability(COALESCE(issue_id, project_id), 64)
            OR app_has_object_capability(COALESCE(issue_id, project_id), 128)
        )
    );

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE attachments TO kanban_app;
GRANT SELECT ON TABLE attachments TO app_rls_reader;
GRANT EXECUTE ON FUNCTION attachments_workspace_biu() TO kanban_app, kanban_migrator;
