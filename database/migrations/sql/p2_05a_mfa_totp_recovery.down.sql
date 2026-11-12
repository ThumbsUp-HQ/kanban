-- Down migration for p2_05a_mfa_totp_recovery

REVOKE EXECUTE ON FUNCTION kb_auth.mfa_status(UUID) FROM kanban_app;
DROP FUNCTION IF EXISTS kb_auth.mfa_status(UUID);

REVOKE EXECUTE ON FUNCTION kb_auth.recovery_code_consume(UUID, BYTEA) FROM kanban_app;
DROP FUNCTION IF EXISTS kb_auth.recovery_code_consume(UUID, BYTEA);

REVOKE EXECUTE ON FUNCTION kb_auth.recovery_codes_replace(UUID, BYTEA[]) FROM kanban_app;
DROP FUNCTION IF EXISTS kb_auth.recovery_codes_replace(UUID, BYTEA[]);

REVOKE EXECUTE ON FUNCTION kb_auth.totp_delete(UUID) FROM kanban_app;
DROP FUNCTION IF EXISTS kb_auth.totp_delete(UUID);

REVOKE EXECUTE ON FUNCTION kb_auth.totp_update_step(UUID, BIGINT) FROM kanban_app;
DROP FUNCTION IF EXISTS kb_auth.totp_update_step(UUID, BIGINT);

REVOKE EXECUTE ON FUNCTION kb_auth.totp_get_active(UUID) FROM kanban_app;
DROP FUNCTION IF EXISTS kb_auth.totp_get_active(UUID);

REVOKE EXECUTE ON FUNCTION kb_auth.totp_confirm(UUID, BIGINT) FROM kanban_app;
DROP FUNCTION IF EXISTS kb_auth.totp_confirm(UUID, BIGINT);

REVOKE EXECUTE ON FUNCTION kb_auth.totp_get_pending(UUID) FROM kanban_app;
DROP FUNCTION IF EXISTS kb_auth.totp_get_pending(UUID);

REVOKE EXECUTE ON FUNCTION kb_auth.totp_enroll(UUID, BYTEA, BYTEA, TEXT) FROM kanban_app;
DROP FUNCTION IF EXISTS kb_auth.totp_enroll(UUID, BYTEA, BYTEA, TEXT);

DROP TABLE IF EXISTS recovery_codes CASCADE;
DROP TABLE IF EXISTS totp_factors CASCADE;
