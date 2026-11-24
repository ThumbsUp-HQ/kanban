-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

-- 1. Revert client secret columns
ALTER TABLE oauth_clients DROP COLUMN IF EXISTS client_secret_prefix;
ALTER TABLE oauth_clients DROP COLUMN IF EXISTS client_secret_hash;

-- 2. Revert check constraint to public only
ALTER TABLE oauth_clients DROP CONSTRAINT IF EXISTS oauth_clients_type_check;
ALTER TABLE oauth_clients DROP CONSTRAINT IF EXISTS oauth_clients_client_type_check;
ALTER TABLE oauth_clients ADD CONSTRAINT oauth_clients_type_check CHECK (client_type = 'public');
