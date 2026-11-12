-- Phase 2 / Auth: Server-side sessions, timeouts and security definer functions (KB-P2-02)

-- 1. Table: sessions
CREATE TABLE sessions (
    id                  UUID PRIMARY KEY DEFAULT uuidv7(),
    token_sha256        BYTEA NOT NULL UNIQUE CHECK (octet_length(token_sha256) = 32),
    principal_id        UUID NOT NULL REFERENCES principals(id) ON DELETE CASCADE,
    workspace_id        UUID NOT NULL,
    auth_card_id        UUID REFERENCES auth_provider_cards(id) ON DELETE CASCADE,
    aal_level           SMALLINT NOT NULL CHECK (aal_level IN (1, 2)),
    aal2_verified_at    TIMESTAMPTZ,
    mfa_pending         BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    last_seen_at        TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    idle_expires_at     TIMESTAMPTZ NOT NULL,
    absolute_expires_at TIMESTAMPTZ NOT NULL,
    revoked_at          TIMESTAMPTZ,
    rotated_from_id     UUID
);

CREATE INDEX sessions_principal_id_idx ON sessions (principal_id);

-- Ownership and permissions
ALTER TABLE sessions OWNER TO kb_auth_owner;
REVOKE ALL ON sessions FROM PUBLIC, kanban_app, app_rls_reader;

-- RLS
ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE sessions FORCE ROW LEVEL SECURITY;
CREATE POLICY kb_auth_owner_all ON sessions
    FOR ALL TO kb_auth_owner USING (true) WITH CHECK (true);

-- 2. Functions in schema kb_auth (owned by kb_auth_owner, SECURITY DEFINER)

-- Function 1: session_create
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

-- Function 2: session_resolve(p_token_sha256 bytea)
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

    -- Slide idle_expires_at and last_seen_at only when last_seen_at < v_now - interval '60 seconds'
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

-- Function 3: session_revoke(p_id uuid)
CREATE OR REPLACE FUNCTION kb_auth.session_revoke(p_id UUID)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_count INT;
BEGIN
    UPDATE sessions
    SET revoked_at = clock_timestamp()
    WHERE id = p_id
      AND revoked_at IS NULL;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count > 0;
END;
$$;

ALTER FUNCTION kb_auth.session_revoke(UUID) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.session_revoke(UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.session_revoke(UUID) TO kanban_app;

-- Function 4: session_rotate(p_old_id uuid, p_new_token_sha256 bytea, p_aal smallint)
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

-- Function 5: session_revoke_all_for_principal(p_principal uuid)
CREATE OR REPLACE FUNCTION kb_auth.session_revoke_all_for_principal(p_principal_id UUID)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_count INT;
BEGIN
    UPDATE sessions
    SET revoked_at = clock_timestamp()
    WHERE principal_id = p_principal_id
      AND revoked_at IS NULL;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$;

ALTER FUNCTION kb_auth.session_revoke_all_for_principal(UUID) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.session_revoke_all_for_principal(UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.session_revoke_all_for_principal(UUID) TO kanban_app;
