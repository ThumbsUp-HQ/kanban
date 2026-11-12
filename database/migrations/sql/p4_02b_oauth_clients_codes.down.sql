-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

ALTER FUNCTION append_activity(uuid, uuid, object_kind, uuid, text, jsonb) SECURITY INVOKER;
DROP FUNCTION IF EXISTS check_oauth_token_status(UUID, UUID, UUID);
DROP TABLE IF EXISTS oauth_revoked_jtis CASCADE;
DROP TABLE IF EXISTS oauth_refresh_tokens CASCADE;
DROP TABLE IF EXISTS oauth_authorization_codes CASCADE;
DROP TABLE IF EXISTS oauth_grants CASCADE;
DROP TABLE IF EXISTS oauth_clients CASCADE;
