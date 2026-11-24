-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

-- 1. Update check constraint to allow confidential OAuth clients
ALTER TABLE oauth_clients DROP CONSTRAINT IF EXISTS oauth_clients_client_type_check;
ALTER TABLE oauth_clients DROP CONSTRAINT IF EXISTS oauth_clients_type_check;
ALTER TABLE oauth_clients ADD CONSTRAINT oauth_clients_type_check CHECK (client_type IN ('public', 'confidential'));

-- 2. Add client secret hash and masked prefix columns
ALTER TABLE oauth_clients ADD COLUMN IF NOT EXISTS client_secret_hash TEXT;
ALTER TABLE oauth_clients ADD COLUMN IF NOT EXISTS client_secret_prefix VARCHAR(16);
