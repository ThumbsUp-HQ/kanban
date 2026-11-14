-- KB-P4-12: Destructive confirmation tokens table (S11.4, S7.2, S12.3)

CREATE TABLE destructive_confirmation_tokens (
    id                    UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id          UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    token_sha256          BYTEA NOT NULL UNIQUE CHECK (octet_length(token_sha256) = 32),
    caller_principal_id   UUID NOT NULL REFERENCES principals(id) ON DELETE CASCADE,
    target_object_id      UUID NOT NULL,
    target_object_type    object_kind NOT NULL,
    mode                  TEXT NOT NULL CHECK (mode IN ('trash', 'permanent_purge', 'restore')),
    blast_hash            TEXT NOT NULL CHECK (char_length(blast_hash) = 64),
    confirm_phrase        TEXT NOT NULL,
    blast_summary_json    JSONB NOT NULL,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    expires_at            TIMESTAMPTZ NOT NULL,
    consumed_at           TIMESTAMPTZ,
    CHECK (expires_at <= created_at + interval '300 seconds'),
    FOREIGN KEY (target_object_id, target_object_type) REFERENCES objects (id, object_type) ON DELETE CASCADE
);

CREATE INDEX destructive_tokens_lookup_idx
    ON destructive_confirmation_tokens (token_sha256)
    WHERE consumed_at IS NULL;

CREATE INDEX destructive_tokens_ws_target_idx
    ON destructive_confirmation_tokens (workspace_id, target_object_id);

ALTER TABLE destructive_confirmation_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE destructive_confirmation_tokens FORCE ROW LEVEL SECURITY;

CREATE POLICY destructive_tokens_select_rls ON destructive_confirmation_tokens
    FOR SELECT
    USING (workspace_id = app_current_workspace_id());

CREATE POLICY destructive_tokens_insert_rls ON destructive_confirmation_tokens
    FOR INSERT
    WITH CHECK (workspace_id = app_current_workspace_id());

CREATE POLICY destructive_tokens_update_rls ON destructive_confirmation_tokens
    FOR UPDATE
    USING (workspace_id = app_current_workspace_id())
    WITH CHECK (workspace_id = app_current_workspace_id());

CREATE POLICY destructive_tokens_delete_rls ON destructive_confirmation_tokens
    FOR DELETE
    USING (workspace_id = app_current_workspace_id());

GRANT SELECT, INSERT, UPDATE, DELETE ON destructive_confirmation_tokens TO kanban_app;
GRANT SELECT ON destructive_confirmation_tokens TO app_rls_reader;
