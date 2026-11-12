-- DDL and RLS Policies for issue_subscriptions and notifications (KB-P3-06)

-- 1. issue_subscriptions extension
ALTER TABLE issue_subscriptions ADD COLUMN IF NOT EXISTS muted_event_types TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE issue_subscriptions ADD COLUMN IF NOT EXISTS unsubscribed_at TIMESTAMPTZ NULL;

-- 2. notifications table
CREATE TABLE IF NOT EXISTS notifications (
    id                     UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id           UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    recipient_principal_id UUID NOT NULL REFERENCES principals(id) ON DELETE CASCADE,
    issue_id               UUID NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
    activity_record_id     UUID NOT NULL,
    event_type             TEXT NOT NULL,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    read_at                TIMESTAMPTZ,
    UNIQUE (recipient_principal_id, activity_record_id)
);

CREATE INDEX IF NOT EXISTS notifications_unread ON notifications (recipient_principal_id, created_at DESC) WHERE read_at IS NULL;
CREATE INDEX IF NOT EXISTS notifications_recipient_created_idx ON notifications (recipient_principal_id, created_at DESC, id DESC);

-- 3. Row Level Security on notifications
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications FORCE ROW LEVEL SECURITY;

REVOKE ALL ON notifications FROM PUBLIC;
GRANT SELECT, UPDATE, INSERT ON notifications TO kanban_app;
GRANT SELECT ON notifications TO app_rls_reader;

CREATE POLICY notifications_select_rls ON notifications
    FOR SELECT USING (
        recipient_principal_id = app_current_principal_id()
    );

CREATE POLICY notifications_update_rls ON notifications
    FOR UPDATE USING (
        recipient_principal_id = app_current_principal_id()
    ) WITH CHECK (
        recipient_principal_id = app_current_principal_id()
    );

CREATE POLICY notifications_insert_rls ON notifications
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id() OR app_current_workspace_id() IS NULL
    );
