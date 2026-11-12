-- Phase 2 / Auth: WebAuthn / Passkeys credentials, challenges, and functions (KB-P2-05b)

-- 1. Table: webauthn_credentials
CREATE TABLE webauthn_credentials (
    id                      UUID PRIMARY KEY DEFAULT uuidv7(),
    principal_id            UUID NOT NULL REFERENCES principals(id) ON DELETE CASCADE,
    credential_id           BYTEA NOT NULL UNIQUE CHECK (octet_length(credential_id) BETWEEN 16 AND 1023),
    public_key              BYTEA NOT NULL,
    sign_count              BIGINT NOT NULL,
    aaguid                  UUID,
    transports              TEXT[] NOT NULL DEFAULT '{}',
    nickname                TEXT CHECK (nickname IS NULL OR char_length(nickname) <= 64),
    suspect_clone_at        TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    last_used_at            TIMESTAMPTZ
);

CREATE INDEX webauthn_credentials_principal_id_idx ON webauthn_credentials (principal_id);

-- Ownership and permissions
ALTER TABLE webauthn_credentials OWNER TO kb_auth_owner;
REVOKE ALL ON webauthn_credentials FROM PUBLIC, kanban_app, app_rls_reader;
ALTER TABLE webauthn_credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE webauthn_credentials FORCE ROW LEVEL SECURITY;
CREATE POLICY kb_auth_owner_all ON webauthn_credentials FOR ALL TO kb_auth_owner USING (true) WITH CHECK (true);

-- 2. Table: webauthn_challenges
CREATE TABLE webauthn_challenges (
    id                      UUID PRIMARY KEY DEFAULT uuidv7(),
    session_id              UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    purpose                 TEXT NOT NULL CHECK (purpose IN ('register', 'authenticate')),
    challenge               BYTEA NOT NULL CHECK (octet_length(challenge) = 32),
    expires_at              TIMESTAMPTZ NOT NULL,
    consumed_at             TIMESTAMPTZ
);

CREATE INDEX webauthn_challenges_session_purpose_idx ON webauthn_challenges (session_id, purpose);

-- Ownership and permissions
ALTER TABLE webauthn_challenges OWNER TO kb_auth_owner;
REVOKE ALL ON webauthn_challenges FROM PUBLIC, kanban_app, app_rls_reader;
ALTER TABLE webauthn_challenges ENABLE ROW LEVEL SECURITY;
ALTER TABLE webauthn_challenges FORCE ROW LEVEL SECURITY;
CREATE POLICY kb_auth_owner_all ON webauthn_challenges FOR ALL TO kb_auth_owner USING (true) WITH CHECK (true);

-- 3. Functions in schema kb_auth (owned by kb_auth_owner, SECURITY DEFINER)

-- Function 1: webauthn_challenge_create
CREATE OR REPLACE FUNCTION kb_auth.webauthn_challenge_create(
    p_session_id UUID,
    p_purpose TEXT,
    p_challenge BYTEA,
    p_ttl_seconds INT DEFAULT 300
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_id UUID := uuidv7();
BEGIN
    -- Invalidate any prior unconsumed challenges for this session and purpose
    UPDATE webauthn_challenges
    SET consumed_at = clock_timestamp()
    WHERE session_id = p_session_id
      AND purpose = p_purpose
      AND consumed_at IS NULL;

    INSERT INTO webauthn_challenges (
        id,
        session_id,
        purpose,
        challenge,
        expires_at
    ) VALUES (
        v_id,
        p_session_id,
        p_purpose,
        p_challenge,
        clock_timestamp() + (p_ttl_seconds || ' seconds')::interval
    );

    RETURN v_id;
END;
$$;

ALTER FUNCTION kb_auth.webauthn_challenge_create(UUID, TEXT, BYTEA, INT) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.webauthn_challenge_create(UUID, TEXT, BYTEA, INT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.webauthn_challenge_create(UUID, TEXT, BYTEA, INT) TO kanban_app;

-- Function 2: webauthn_challenge_consume
CREATE OR REPLACE FUNCTION kb_auth.webauthn_challenge_consume(
    p_session_id UUID,
    p_purpose TEXT,
    p_challenge BYTEA
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_id UUID;
BEGIN
    UPDATE webauthn_challenges
    SET consumed_at = clock_timestamp()
    WHERE session_id = p_session_id
      AND purpose = p_purpose
      AND challenge = p_challenge
      AND consumed_at IS NULL
      AND expires_at > clock_timestamp()
    RETURNING id INTO v_id;

    RETURN v_id IS NOT NULL;
END;
$$;

ALTER FUNCTION kb_auth.webauthn_challenge_consume(UUID, TEXT, BYTEA) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.webauthn_challenge_consume(UUID, TEXT, BYTEA) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.webauthn_challenge_consume(UUID, TEXT, BYTEA) TO kanban_app;

-- Function 3: webauthn_credential_create
CREATE OR REPLACE FUNCTION kb_auth.webauthn_credential_create(
    p_principal_id UUID,
    p_credential_id BYTEA,
    p_public_key BYTEA,
    p_sign_count BIGINT,
    p_aaguid UUID,
    p_transports TEXT[],
    p_nickname TEXT
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_count INT;
    v_id UUID := uuidv7();
BEGIN
    SELECT count(*) INTO v_count
    FROM webauthn_credentials
    WHERE principal_id = p_principal_id;

    IF v_count >= 10 THEN
        RAISE EXCEPTION 'CREDENTIAL_LIMIT' USING ERRCODE = 'P0003';
    END IF;

    INSERT INTO webauthn_credentials (
        id,
        principal_id,
        credential_id,
        public_key,
        sign_count,
        aaguid,
        transports,
        nickname
    ) VALUES (
        v_id,
        p_principal_id,
        p_credential_id,
        p_public_key,
        p_sign_count,
        p_aaguid,
        COALESCE(p_transports, '{}'),
        p_nickname
    );

    RETURN v_id;
END;
$$;

ALTER FUNCTION kb_auth.webauthn_credential_create(UUID, BYTEA, BYTEA, BIGINT, UUID, TEXT[], TEXT) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.webauthn_credential_create(UUID, BYTEA, BYTEA, BIGINT, UUID, TEXT[], TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.webauthn_credential_create(UUID, BYTEA, BYTEA, BIGINT, UUID, TEXT[], TEXT) TO kanban_app;

-- Function 4: webauthn_credential_get
CREATE OR REPLACE FUNCTION kb_auth.webauthn_credential_get(p_credential_id BYTEA)
RETURNS TABLE (
    id UUID,
    principal_id UUID,
    credential_id BYTEA,
    public_key BYTEA,
    sign_count BIGINT,
    aaguid UUID,
    transports TEXT[],
    nickname TEXT,
    suspect_clone_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ
)
LANGUAGE plpgsql
STABLE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    RETURN QUERY
    SELECT c.id, c.principal_id, c.credential_id, c.public_key, c.sign_count,
           c.aaguid, c.transports, c.nickname, c.suspect_clone_at, c.created_at, c.last_used_at
    FROM webauthn_credentials c
    WHERE c.credential_id = p_credential_id;
END;
$$;

ALTER FUNCTION kb_auth.webauthn_credential_get(BYTEA) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.webauthn_credential_get(BYTEA) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.webauthn_credential_get(BYTEA) TO kanban_app;

-- Function 5: webauthn_credentials_for_principal
CREATE OR REPLACE FUNCTION kb_auth.webauthn_credentials_for_principal(p_principal_id UUID)
RETURNS TABLE (
    id UUID,
    principal_id UUID,
    credential_id BYTEA,
    public_key BYTEA,
    sign_count BIGINT,
    aaguid UUID,
    transports TEXT[],
    nickname TEXT,
    suspect_clone_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ
)
LANGUAGE plpgsql
STABLE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    RETURN QUERY
    SELECT c.id, c.principal_id, c.credential_id, c.public_key, c.sign_count,
           c.aaguid, c.transports, c.nickname, c.suspect_clone_at, c.created_at, c.last_used_at
    FROM webauthn_credentials c
    WHERE c.principal_id = p_principal_id
    ORDER BY c.created_at DESC;
END;
$$;

ALTER FUNCTION kb_auth.webauthn_credentials_for_principal(UUID) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.webauthn_credentials_for_principal(UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.webauthn_credentials_for_principal(UUID) TO kanban_app;

-- Function 6: webauthn_update_sign_count
CREATE OR REPLACE FUNCTION kb_auth.webauthn_update_sign_count(
    p_credential_id BYTEA,
    p_new_sign_count BIGINT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    UPDATE webauthn_credentials
    SET sign_count = p_new_sign_count,
        last_used_at = clock_timestamp()
    WHERE credential_id = p_credential_id;

    RETURN FOUND;
END;
$$;

ALTER FUNCTION kb_auth.webauthn_update_sign_count(BYTEA, BIGINT) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.webauthn_update_sign_count(BYTEA, BIGINT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.webauthn_update_sign_count(BYTEA, BIGINT) TO kanban_app;

-- Function 7: webauthn_mark_clone
CREATE OR REPLACE FUNCTION kb_auth.webauthn_mark_clone(p_credential_id BYTEA)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    UPDATE webauthn_credentials
    SET suspect_clone_at = clock_timestamp()
    WHERE credential_id = p_credential_id;

    RETURN FOUND;
END;
$$;

ALTER FUNCTION kb_auth.webauthn_mark_clone(BYTEA) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.webauthn_mark_clone(BYTEA) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.webauthn_mark_clone(BYTEA) TO kanban_app;

-- Function 8: webauthn_credential_delete
CREATE OR REPLACE FUNCTION kb_auth.webauthn_credential_delete(
    p_credential_id_uuid UUID,
    p_principal_id UUID
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    DELETE FROM webauthn_credentials
    WHERE id = p_credential_id_uuid
      AND principal_id = p_principal_id;

    RETURN FOUND;
END;
$$;

ALTER FUNCTION kb_auth.webauthn_credential_delete(UUID, UUID) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.webauthn_credential_delete(UUID, UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.webauthn_credential_delete(UUID, UUID) TO kanban_app;

-- Function 9: webauthn_count
CREATE OR REPLACE FUNCTION kb_auth.webauthn_count(p_principal_id UUID)
RETURNS INTEGER
LANGUAGE plpgsql
STABLE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT count(*)::INTEGER INTO v_count
    FROM webauthn_credentials
    WHERE principal_id = p_principal_id;
    RETURN v_count;
END;
$$;

ALTER FUNCTION kb_auth.webauthn_count(UUID) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.webauthn_count(UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.webauthn_count(UUID) TO kanban_app;

-- Function 10: mfa_status (updated to include webauthn_credential_count)
DROP FUNCTION IF EXISTS kb_auth.mfa_status(UUID);

CREATE OR REPLACE FUNCTION kb_auth.mfa_status(p_principal_id UUID)
RETURNS TABLE (
    has_active_totp BOOLEAN,
    unused_recovery_codes INTEGER,
    webauthn_credential_count INTEGER
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
        ) AS unused_recovery_codes,
        (
            SELECT count(*)::INTEGER FROM webauthn_credentials
            WHERE principal_id = p_principal_id
        ) AS webauthn_credential_count;
END;
$$;

ALTER FUNCTION kb_auth.mfa_status(UUID) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.mfa_status(UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.mfa_status(UUID) TO kanban_app;
