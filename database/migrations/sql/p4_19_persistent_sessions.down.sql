-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

-- 1. Drop updated functions
DROP FUNCTION IF EXISTS kb_auth.session_create(UUID, BYTEA, UUID, UUID, UUID, SMALLINT, TIMESTAMPTZ, BOOLEAN, TIMESTAMPTZ, TIMESTAMPTZ, UUID, BOOLEAN);
DROP FUNCTION IF EXISTS kb_auth.session_resolve(BYTEA);
DROP FUNCTION IF EXISTS kb_auth.session_get_metadata(UUID);
DROP FUNCTION IF EXISTS kb_auth.oidc_request_create(UUID, BYTEA, BYTEA, BYTEA, BYTEA, TEXT, UUID, TIMESTAMPTZ, UUID, BOOLEAN);
DROP FUNCTION IF EXISTS kb_auth.oidc_request_consume(BYTEA, BYTEA);

-- 2. Restore p2_02 session_create (11 parameters)
CREATE OR REPLACE FUNCTION kb_auth.session_create(
    p_id UUID,
    p_token_sha256 BYTEA,
    p_principal_id UUID,
    p_workspace_id UUID,
    p_auth_card_id UUID,
    p_aal_level SMALLINT,
    p_aal2_verified_at TIMESTAMPTZ,
    p_mfa_pending BOOLEAN,
    p_idle_expires_at TIMESTAMPTZ,
    p_absolute_expires_at TIMESTAMPTZ,
    p_rotated_from_id UUID DEFAULT NULL
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_id UUID;
BEGIN
    v_id := COALESCE(p_id, uuidv7());
    INSERT INTO sessions (
        id,
        token_sha256,
        principal_id,
        workspace_id,
        auth_card_id,
        aal_level,
        aal2_verified_at,
        mfa_pending,
        created_at,
        last_seen_at,
        idle_expires_at,
        absolute_expires_at,
        rotated_from_id
    ) VALUES (
        v_id,
        p_token_sha256,
        p_principal_id,
        p_workspace_id,
        p_auth_card_id,
        p_aal_level,
        p_aal2_verified_at,
        COALESCE(p_mfa_pending, FALSE),
        clock_timestamp(),
        clock_timestamp(),
        p_idle_expires_at,
        p_absolute_expires_at,
        p_rotated_from_id
    );
    RETURN v_id;
END;
$$;

ALTER FUNCTION kb_auth.session_create(UUID, BYTEA, UUID, UUID, UUID, SMALLINT, TIMESTAMPTZ, BOOLEAN, TIMESTAMPTZ, TIMESTAMPTZ, UUID) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.session_create(UUID, BYTEA, UUID, UUID, UUID, SMALLINT, TIMESTAMPTZ, BOOLEAN, TIMESTAMPTZ, TIMESTAMPTZ, UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.session_create(UUID, BYTEA, UUID, UUID, UUID, SMALLINT, TIMESTAMPTZ, BOOLEAN, TIMESTAMPTZ, TIMESTAMPTZ, UUID) TO kanban_app;

-- 3. Restore p2_02 session_resolve (13 columns)
CREATE OR REPLACE FUNCTION kb_auth.session_resolve(p_token_sha256 BYTEA)
RETURNS TABLE (
    id UUID,
    principal_id UUID,
    workspace_id UUID,
    auth_card_id UUID,
    aal_level SMALLINT,
    aal2_verified_at TIMESTAMPTZ,
    mfa_pending BOOLEAN,
    created_at TIMESTAMPTZ,
    last_seen_at TIMESTAMPTZ,
    idle_expires_at TIMESTAMPTZ,
    absolute_expires_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    rotated_from_id UUID
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_now TIMESTAMPTZ := clock_timestamp();
    v_session sessions%ROWTYPE;
    v_idle_interval INTERVAL;
BEGIN
    SELECT * INTO v_session
    FROM sessions s
    WHERE s.token_sha256 = p_token_sha256
      AND s.revoked_at IS NULL
      AND v_now < s.idle_expires_at
      AND v_now < s.absolute_expires_at;

    IF NOT FOUND THEN
        RETURN;
    END IF;

    IF v_session.last_seen_at < (v_now - interval '60 seconds') THEN
        v_idle_interval := v_session.idle_expires_at - v_session.last_seen_at;
        UPDATE sessions
        SET last_seen_at = v_now,
            idle_expires_at = LEAST(v_now + v_idle_interval, v_session.absolute_expires_at)
        WHERE sessions.id = v_session.id
        RETURNING * INTO v_session;
    END IF;

    RETURN QUERY
    SELECT
        v_session.id,
        v_session.principal_id,
        v_session.workspace_id,
        v_session.auth_card_id,
        v_session.aal_level,
        v_session.aal2_verified_at,
        v_session.mfa_pending,
        v_session.created_at,
        v_session.last_seen_at,
        v_session.idle_expires_at,
        v_session.absolute_expires_at,
        v_session.revoked_at,
        v_session.rotated_from_id;
END;
$$;

ALTER FUNCTION kb_auth.session_resolve(BYTEA) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.session_resolve(BYTEA) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.session_resolve(BYTEA) TO kanban_app;

-- 4. Restore p2_02 session_rotate
CREATE OR REPLACE FUNCTION kb_auth.session_rotate(
    p_old_id UUID,
    p_new_token_sha256 BYTEA,
    p_aal SMALLINT
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_now TIMESTAMPTZ := clock_timestamp();
    v_old sessions%ROWTYPE;
    v_new_id UUID := uuidv7();
    v_aal2_at TIMESTAMPTZ := NULL;
    v_idle_interval INTERVAL;
BEGIN
    UPDATE sessions
    SET revoked_at = v_now
    WHERE id = p_old_id
      AND revoked_at IS NULL
    RETURNING * INTO v_old;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'session_not_found_or_revoked: %', p_old_id
            USING ERRCODE = 'P0002';
    END IF;

    IF p_aal = 2 THEN
        v_aal2_at := v_now;
    END IF;

    v_idle_interval := v_old.idle_expires_at - v_old.last_seen_at;

    INSERT INTO sessions (
        id,
        token_sha256,
        principal_id,
        workspace_id,
        auth_card_id,
        aal_level,
        aal2_verified_at,
        mfa_pending,
        created_at,
        last_seen_at,
        idle_expires_at,
        absolute_expires_at,
        rotated_from_id
    ) VALUES (
        v_new_id,
        p_new_token_sha256,
        v_old.principal_id,
        v_old.workspace_id,
        v_old.auth_card_id,
        p_aal,
        COALESCE(v_aal2_at, v_old.aal2_verified_at),
        FALSE,
        v_now,
        v_now,
        LEAST(v_now + v_idle_interval, v_old.absolute_expires_at),
        v_old.absolute_expires_at,
        p_old_id
    );

    RETURN v_new_id;
END;
$$;

ALTER FUNCTION kb_auth.session_rotate(UUID, BYTEA, SMALLINT) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.session_rotate(UUID, BYTEA, SMALLINT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.session_rotate(UUID, BYTEA, SMALLINT) TO kanban_app;

-- 5. Restore p2_06 oidc_request_create (9 parameters)
CREATE OR REPLACE FUNCTION kb_auth.oidc_request_create(
    p_card_id UUID,
    p_state_hash BYTEA,
    p_nonce BYTEA,
    p_code_verifier_sealed BYTEA,
    p_browser_binding_hash BYTEA,
    p_return_to TEXT,
    p_link_intent_id UUID,
    p_expires_at TIMESTAMPTZ,
    p_id UUID DEFAULT NULL
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_id UUID;
BEGIN
    v_id := COALESCE(p_id, uuidv7());
    INSERT INTO oidc_auth_requests (
        id,
        card_id,
        state_hash,
        nonce,
        code_verifier_sealed,
        browser_binding_hash,
        return_to,
        link_intent_id,
        expires_at,
        consumed_at,
        created_at
    ) VALUES (
        v_id,
        p_card_id,
        p_state_hash,
        p_nonce,
        p_code_verifier_sealed,
        p_browser_binding_hash,
        COALESCE(p_return_to, '/'),
        p_link_intent_id,
        p_expires_at,
        NULL,
        clock_timestamp()
    );
    RETURN v_id;
END;
$$;

ALTER FUNCTION kb_auth.oidc_request_create(UUID, BYTEA, BYTEA, BYTEA, BYTEA, TEXT, UUID, TIMESTAMPTZ, UUID) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.oidc_request_create(UUID, BYTEA, BYTEA, BYTEA, BYTEA, TEXT, UUID, TIMESTAMPTZ, UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.oidc_request_create(UUID, BYTEA, BYTEA, BYTEA, BYTEA, TEXT, UUID, TIMESTAMPTZ, UUID) TO kanban_app;

-- 6. Restore p2_06 oidc_request_consume (7 columns)
CREATE OR REPLACE FUNCTION kb_auth.oidc_request_consume(
    p_state_hash BYTEA,
    p_browser_binding_hash BYTEA
)
RETURNS TABLE (
    id UUID,
    card_id UUID,
    nonce BYTEA,
    code_verifier_sealed BYTEA,
    return_to TEXT,
    link_intent_id UUID,
    status TEXT
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_rec RECORD;
BEGIN
    SELECT r.id, r.card_id, r.nonce, r.code_verifier_sealed, r.browser_binding_hash,
           r.return_to, r.link_intent_id, r.expires_at, r.consumed_at
    INTO v_rec
    FROM oidc_auth_requests r
    WHERE r.state_hash = p_state_hash
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN QUERY SELECT NULL::UUID, NULL::UUID, NULL::BYTEA, NULL::BYTEA, NULL::TEXT, NULL::UUID, 'NOT_FOUND'::TEXT;
        RETURN;
    END IF;

    IF v_rec.consumed_at IS NOT NULL THEN
        RETURN QUERY SELECT NULL::UUID, NULL::UUID, NULL::BYTEA, NULL::BYTEA, NULL::TEXT, NULL::UUID, 'ALREADY_CONSUMED'::TEXT;
        RETURN;
    END IF;

    IF v_rec.expires_at <= clock_timestamp() THEN
        RETURN QUERY SELECT NULL::UUID, NULL::UUID, NULL::BYTEA, NULL::BYTEA, NULL::TEXT, NULL::UUID, 'EXPIRED'::TEXT;
        RETURN;
    END IF;

    IF v_rec.browser_binding_hash != p_browser_binding_hash THEN
        RETURN QUERY SELECT NULL::UUID, NULL::UUID, NULL::BYTEA, NULL::BYTEA, NULL::TEXT, NULL::UUID, 'BINDING_MISMATCH'::TEXT;
        RETURN;
    END IF;

    UPDATE oidc_auth_requests
    SET consumed_at = clock_timestamp()
    WHERE oidc_auth_requests.id = v_rec.id;

    RETURN QUERY SELECT v_rec.id, v_rec.card_id, v_rec.nonce, v_rec.code_verifier_sealed,
                        v_rec.return_to, v_rec.link_intent_id, 'OK'::TEXT;
END;
$$;

ALTER FUNCTION kb_auth.oidc_request_consume(BYTEA, BYTEA) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.oidc_request_consume(BYTEA, BYTEA) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.oidc_request_consume(BYTEA, BYTEA) TO kanban_app;

-- 7. Drop columns
ALTER TABLE oidc_auth_requests DROP COLUMN IF EXISTS remember_me;
ALTER TABLE sessions DROP COLUMN IF EXISTS is_persistent;
