-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

-- 1. Table: comment_reactions
CREATE TABLE comment_reactions (
    comment_id   UUID NOT NULL REFERENCES issue_comments(id) ON DELETE CASCADE,
    principal_id UUID NOT NULL REFERENCES principals(id) ON DELETE CASCADE,
    emoji        TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (comment_id, principal_id, emoji)
);

CREATE INDEX comment_reactions_comment_idx ON comment_reactions (comment_id);
CREATE INDEX comment_reactions_principal_idx ON comment_reactions (principal_id);

-- 2. Grants
GRANT SELECT, INSERT, UPDATE, DELETE ON comment_reactions TO kanban_app;
GRANT SELECT ON comment_reactions TO app_rls_reader;

-- 3. Row-Level Security
ALTER TABLE comment_reactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE comment_reactions FORCE ROW LEVEL SECURITY;

CREATE POLICY comment_reactions_select_rls ON comment_reactions
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM issue_comments ic
            WHERE ic.id = comment_reactions.comment_id
              AND ic.workspace_id = app_current_workspace_id()
              AND app_has_object_capability(ic.issue_id, 1)
        )
    );

CREATE POLICY comment_reactions_insert_rls ON comment_reactions
    FOR INSERT WITH CHECK (
        principal_id = COALESCE(NULLIF(current_setting('app.principal_id', true), '')::uuid, app_current_principal_id())
        AND EXISTS (
            SELECT 1 FROM issue_comments ic
            WHERE ic.id = comment_reactions.comment_id
              AND ic.workspace_id = app_current_workspace_id()
              AND app_has_object_capability(ic.issue_id, 1)
        )
    );

CREATE POLICY comment_reactions_delete_rls ON comment_reactions
    FOR DELETE USING (
        principal_id = COALESCE(NULLIF(current_setting('app.principal_id', true), '')::uuid, app_current_principal_id())
        AND EXISTS (
            SELECT 1 FROM issue_comments ic
            WHERE ic.id = comment_reactions.comment_id
              AND ic.workspace_id = app_current_workspace_id()
              AND app_has_object_capability(ic.issue_id, 1)
        )
    );
