-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

ALTER TABLE oauth_clients DROP CONSTRAINT IF EXISTS oauth_clients_status_check;
ALTER TABLE oauth_clients ADD CONSTRAINT oauth_clients_status_check
    CHECK (status IN ('active', 'pending_admin_approval', 'disabled', 'suspended', 'revoked'));
