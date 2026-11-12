-- Phase 2 / Auth: RFC 6238 TOTP and recovery codes (KB-P2-05a)

-- 1. Table: totp_factors
CREATE TABLE totp_factors (
    id                      UUID PRIMARY KEY DEFAULT uuidv7(),
    principal_id            UUID NOT NULL REFERENCES principals(id) ON DELETE CASCADE,
    status                  TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'ACTIVE', 'REVOKED')),
    encrypted_secret_blob   BYTEA NOT NULL,
    wrapped_dek             BYTEA NOT NULL,
    dek_kid                 TEXT NOT NULL DEFAULT 'kek-v1',
    last_accepted_step      BIGINT NOT NULL DEFAULT 0,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- Table: recovery_codes
CREATE TABLE recovery_codes (
    id                      UUID PRIMARY KEY DEFAULT uuidv7(),
    principal_id            UUID NOT NULL REFERENCES principals(id) ON DELETE CASCADE,
    code_hmac               BYTEA NOT NULL UNIQUE,
    used_at                 TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- Ownership and permissions
ALTER TABLE totp_factors OWNER TO kb_auth_owner;
REVOKE ALL ON totp_factors FROM PUBLIC, kanban_app, app_rls_reader;
ALTER TABLE totp_factors ENABLE ROW LEVEL SECURITY;
ALTER TABLE totp_factors FORCE ROW LEVEL SECURITY;
CREATE POLICY kb_auth_owner_all ON totp_factors FOR ALL TO kb_auth_owner USING (true) WITH CHECK (true);

ALTER TABLE recovery_codes OWNER TO kb_auth_owner;
REVOKE ALL ON recovery_codes FROM PUBLIC, kanban_app, app_rls_reader;
ALTER TABLE recovery_codes ENABLE ROW LEVEL SECURITY;
ALTER TABLE recovery_codes FORCE ROW LEVEL SECURITY;
CREATE POLICY kb_auth_owner_all ON recovery_codes FOR ALL TO kb_auth_owner USING (true) WITH CHECK (true);

-- 2. Functions in schema kb_auth (owned by kb_auth_owner, SECURITY DEFINER)

-- Function 1: totp_enroll
CREATE OR REPLACE FUNCTION kb_auth.totp_enroll(
    p_principal_id UUID,
    p_encrypted_blob BYTEA,
    p_wrapped_dek BYTEA,
    p_dek_kid TEXT
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_id UUID := uuidv7();
BEGIN
    DELETE FROM totp_factors
    WHERE principal_id = p_principal_id
      AND status = 'PENDING';

    INSERT INTO totp_factors (
        id,
        principal_id,
        status,
        encrypted_secret_blob,
        wrapped_dek,
        dek_kid
    ) VALUES (
        v_id,
        p_principal_id,
        'PENDING',
        p_encrypted_blob,
        p_wrapped_dek,
        p_dek_kid
    );

    RETURN v_id;
END;
$$;

ALTER FUNCTION kb_auth.totp_enroll(UUID, BYTEA, BYTEA, TEXT) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.totp_enroll(UUID, BYTEA, BYTEA, TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.totp_enroll(UUID, BYTEA, BYTEA, TEXT) TO kanban_app;

-- Function 2: totp_get_pending
CREATE OR REPLACE FUNCTION kb_auth.totp_get_pending(p_principal_id UUID)
RETURNS TABLE (
    id UUID,
    encrypted_secret_blob BYTEA,
    wrapped_dek BYTEA,
    dek_kid TEXT,
    created_at TIMESTAMPTZ
)
LANGUAGE plpgsql
STABLE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    RETURN QUERY
    SELECT f.id, f.encrypted_secret_blob, f.wrapped_dek, f.dek_kid, f.created_at
    FROM totp_factors f
    WHERE f.principal_id = p_principal_id
      AND f.status = 'PENDING'
      AND f.created_at >= clock_timestamp() - interval '600 seconds'
    ORDER BY f.created_at DESC
    LIMIT 1;
END;
$$;

ALTER FUNCTION kb_auth.totp_get_pending(UUID) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.totp_get_pending(UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.totp_get_pending(UUID) TO kanban_app;

-- Function 3: totp_confirm
CREATE OR REPLACE FUNCTION kb_auth.totp_confirm(p_factor_id UUID, p_step BIGINT)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_principal_id UUID;
BEGIN
    SELECT principal_id INTO v_principal_id
    FROM totp_factors
    WHERE id = p_factor_id
      AND status = 'PENDING'
      AND created_at >= clock_timestamp() - interval '600 seconds';

    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;

    -- Revoke previously active factors
    UPDATE totp_factors
    SET status = 'REVOKED', updated_at = clock_timestamp()
    WHERE principal_id = v_principal_id
      AND id != p_factor_id
      AND status = 'ACTIVE';

    -- Activate confirmed factor
    UPDATE totp_factors
    SET status = 'ACTIVE',
        last_accepted_step = p_step,
        updated_at = clock_timestamp()
    WHERE id = p_factor_id;

    RETURN TRUE;
END;
$$;

ALTER FUNCTION kb_auth.totp_confirm(UUID, BIGINT) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.totp_confirm(UUID, BIGINT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.totp_confirm(UUID, BIGINT) TO kanban_app;

-- Function 4: totp_get_active
CREATE OR REPLACE FUNCTION kb_auth.totp_get_active(p_principal_id UUID)
RETURNS TABLE (
    id UUID,
    encrypted_secret_blob BYTEA,
    wrapped_dek BYTEA,
    dek_kid TEXT,
    last_accepted_step BIGINT
)
LANGUAGE plpgsql
STABLE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    RETURN QUERY
    SELECT f.id, f.encrypted_secret_blob, f.wrapped_dek, f.dek_kid, f.last_accepted_step
    FROM totp_factors f
    WHERE f.principal_id = p_principal_id
      AND f.status = 'ACTIVE'
    ORDER BY f.created_at DESC
    LIMIT 1;
END;
$$;

ALTER FUNCTION kb_auth.totp_get_active(UUID) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.totp_get_active(UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.totp_get_active(UUID) TO kanban_app;

-- Function 5: totp_update_step
CREATE OR REPLACE FUNCTION kb_auth.totp_update_step(p_factor_id UUID, p_step BIGINT)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    UPDATE totp_factors
    SET last_accepted_step = p_step,
        updated_at = clock_timestamp()
    WHERE id = p_factor_id
      AND status = 'ACTIVE'
      AND last_accepted_step < p_step;

    RETURN FOUND;
END;
$$;

ALTER FUNCTION kb_auth.totp_update_step(UUID, BIGINT) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.totp_update_step(UUID, BIGINT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.totp_update_step(UUID, BIGINT) TO kanban_app;

-- Function 6: totp_delete
CREATE OR REPLACE FUNCTION kb_auth.totp_delete(p_principal_id UUID)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    UPDATE totp_factors
    SET status = 'REVOKED',
        updated_at = clock_timestamp()
    WHERE principal_id = p_principal_id
      AND status = 'ACTIVE';

    RETURN FOUND;
END;
$$;

ALTER FUNCTION kb_auth.totp_delete(UUID) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.totp_delete(UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.totp_delete(UUID) TO kanban_app;

-- Function 7: recovery_codes_replace
CREATE OR REPLACE FUNCTION kb_auth.recovery_codes_replace(
    p_principal_id UUID,
    p_code_hmacs BYTEA[]
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    DELETE FROM recovery_codes
    WHERE principal_id = p_principal_id;

    INSERT INTO recovery_codes (
        principal_id,
        code_hmac
    )
    SELECT p_principal_id, unnest(p_code_hmacs);
END;
$$;

ALTER FUNCTION kb_auth.recovery_codes_replace(UUID, BYTEA[]) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.recovery_codes_replace(UUID, BYTEA[]) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.recovery_codes_replace(UUID, BYTEA[]) TO kanban_app;

-- Function 8: recovery_code_consume
CREATE OR REPLACE FUNCTION kb_auth.recovery_code_consume(
    p_principal_id UUID,
    p_code_hmac BYTEA
)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_remaining INTEGER;
BEGIN
    UPDATE recovery_codes
    SET used_at = clock_timestamp()
    WHERE principal_id = p_principal_id
      AND code_hmac = p_code_hmac
      AND used_at IS NULL;

    IF NOT FOUND THEN
        RETURN -1;
    END IF;

    SELECT count(*)::INTEGER INTO v_remaining
    FROM recovery_codes
    WHERE principal_id = p_principal_id
      AND used_at IS NULL;

    RETURN v_remaining;
END;
$$;

ALTER FUNCTION kb_auth.recovery_code_consume(UUID, BYTEA) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.recovery_code_consume(UUID, BYTEA) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.recovery_code_consume(UUID, BYTEA) TO kanban_app;

-- Function 9: mfa_status
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
