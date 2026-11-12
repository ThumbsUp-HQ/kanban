-- Revert Phase 2 / Auth: WebAuthn credentials, challenges, and functions (KB-P2-05b)

-- 1. Revert mfa_status to 2-column signature
DROP FUNCTION IF EXISTS kb_auth.mfa_status(UUID);

CREATE OR REPLACE FUNCTION kb_auth.mfa_status(p_principal_id UUID)
RETURNS TABLE (
    has_active_totp BOOLEAN,
    unused_recovery_codes INTEGER
)
LANGUAGE plpgsql
STABLE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    RETURN QUERY
    SELECT
        EXISTS (
            SELECT 1 FROM totp_factors
            WHERE principal_id = p_principal_id AND status = 'ACTIVE'
        ) AS has_active_totp,
        (
            SELECT count(*)::INTEGER FROM recovery_codes
            WHERE principal_id = p_principal_id AND used_at IS NULL
        ) AS unused_recovery_codes;
END;
$$;

ALTER FUNCTION kb_auth.mfa_status(UUID) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.mfa_status(UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.mfa_status(UUID) TO kanban_app;

-- 2. Revoke and drop WebAuthn functions
REVOKE EXECUTE ON FUNCTION kb_auth.webauthn_count(UUID) FROM kanban_app;
DROP FUNCTION IF EXISTS kb_auth.webauthn_count(UUID);

REVOKE EXECUTE ON FUNCTION kb_auth.webauthn_credential_delete(UUID, UUID) FROM kanban_app;
DROP FUNCTION IF EXISTS kb_auth.webauthn_credential_delete(UUID, UUID);

REVOKE EXECUTE ON FUNCTION kb_auth.webauthn_mark_clone(BYTEA) FROM kanban_app;
DROP FUNCTION IF EXISTS kb_auth.webauthn_mark_clone(BYTEA);

REVOKE EXECUTE ON FUNCTION kb_auth.webauthn_update_sign_count(BYTEA, BIGINT) FROM kanban_app;
DROP FUNCTION IF EXISTS kb_auth.webauthn_update_sign_count(BYTEA, BIGINT);

REVOKE EXECUTE ON FUNCTION kb_auth.webauthn_credentials_for_principal(UUID) FROM kanban_app;
DROP FUNCTION IF EXISTS kb_auth.webauthn_credentials_for_principal(UUID);

REVOKE EXECUTE ON FUNCTION kb_auth.webauthn_credential_get(BYTEA) FROM kanban_app;
DROP FUNCTION IF EXISTS kb_auth.webauthn_credential_get(BYTEA);

REVOKE EXECUTE ON FUNCTION kb_auth.webauthn_credential_create(UUID, BYTEA, BYTEA, BIGINT, UUID, TEXT[], TEXT) FROM kanban_app;
DROP FUNCTION IF EXISTS kb_auth.webauthn_credential_create(UUID, BYTEA, BYTEA, BIGINT, UUID, TEXT[], TEXT);

REVOKE EXECUTE ON FUNCTION kb_auth.webauthn_challenge_consume(UUID, TEXT, BYTEA) FROM kanban_app;
DROP FUNCTION IF EXISTS kb_auth.webauthn_challenge_consume(UUID, TEXT, BYTEA);

REVOKE EXECUTE ON FUNCTION kb_auth.webauthn_challenge_create(UUID, TEXT, BYTEA, INT) FROM kanban_app;
DROP FUNCTION IF EXISTS kb_auth.webauthn_challenge_create(UUID, TEXT, BYTEA, INT);

-- 3. Drop tables
DROP TABLE IF EXISTS webauthn_challenges;
DROP TABLE IF EXISTS webauthn_credentials;
