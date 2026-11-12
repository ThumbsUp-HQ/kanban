-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

-- Revert Migration: p3_06_notifications

DROP POLICY IF EXISTS notifications_insert_rls ON notifications;
DROP POLICY IF EXISTS notifications_update_rls ON notifications;
DROP POLICY IF EXISTS notifications_select_rls ON notifications;

ALTER TABLE notifications NO FORCE ROW LEVEL SECURITY;
ALTER TABLE notifications DISABLE ROW LEVEL SECURITY;

DROP TABLE IF EXISTS notifications CASCADE;

ALTER TABLE issue_subscriptions DROP COLUMN IF EXISTS muted_event_types;
ALTER TABLE issue_subscriptions DROP COLUMN IF EXISTS unsubscribed_at;
