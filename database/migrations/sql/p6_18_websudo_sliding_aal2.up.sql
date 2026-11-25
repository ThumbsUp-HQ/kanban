-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

-- 1. Table schema alterations
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS aal2_last_active_at TIMESTAMPTZ;

-- Backfill active aal_level = 2 rows
UPDATE sessions
SET aal2_last_active_at = aal2_verified_at
WHERE aal_level = 2
  AND aal2_verified_at IS NOT NULL
  AND aal2_last_active_at IS NULL;

-- 2. Drop existing functions whose signatures or return types are changing
DROP FUNCTION IF EXISTS kb_auth.session_create(UUID, BYTEA, UUID, UUID, UUID, SMALLINT, TIMESTAMPTZ, BOOLEAN, TIMESTAMPTZ, TIMESTAMPTZ, UUID, BOOLEAN);
DROP FUNCTION IF EXISTS kb_auth.session_create(UUID, BYTEA, UUID, UUID, UUID, SMALLINT, TIMESTAMPTZ, BOOLEAN, TIMESTAMPTZ, TIMESTAMPTZ, UUID, BOOLEAN, TIMESTAMPTZ);
DROP FUNCTION IF EXISTS kb_auth.session_resolve(BYTEA);
DROP FUNCTION IF EXISTS kb_auth.session_rotate(UUID, BYTEA, SMALLINT);
DROP FUNCTION IF EXISTS kb_auth.session_get_metadata(UUID);
DROP FUNCTION IF EXISTS kb_auth.session_touch_aal2(UUID, INT, INT, BOOLEAN);
DROP FUNCTION IF EXISTS kb_auth.session_drop_aal2(UUID);

-- 3. Function kb_auth.session_create carrying aal2_last_active_at
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
    p_rotated_from_id UUID DEFAULT NULL,
    p_is_persistent BOOLEAN DEFAULT TRUE,
    p_aal2_last_active_at TIMESTAMPTZ DEFAULT NULL
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_id UUID;
    v_last_active TIMESTAMPTZ;
BEGIN
    v_id := COALESCE(p_id, uuidv7());
    IF p_aal_level = 2 THEN
        v_last_active := COALESCE(p_aal2_last_active_at, p_aal2_verified_at, clock_timestamp());
    ELSE
        v_last_active := p_aal2_last_active_at;
    END IF;

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
        rotated_from_id,
        is_persistent,
        aal2_last_active_at
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
        p_rotated_from_id,
        COALESCE(p_is_persistent, TRUE),
        v_last_active
    );
    RETURN v_id;
END;
$$;

ALTER FUNCTION kb_auth.session_create(UUID, BYTEA, UUID, UUID, UUID, SMALLINT, TIMESTAMPTZ, BOOLEAN, TIMESTAMPTZ, TIMESTAMPTZ, UUID, BOOLEAN, TIMESTAMPTZ) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.session_create(UUID, BYTEA, UUID, UUID, UUID, SMALLINT, TIMESTAMPTZ, BOOLEAN, TIMESTAMPTZ, TIMESTAMPTZ, UUID, BOOLEAN, TIMESTAMPTZ) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.session_create(UUID, BYTEA, UUID, UUID, UUID, SMALLINT, TIMESTAMPTZ, BOOLEAN, TIMESTAMPTZ, TIMESTAMPTZ, UUID, BOOLEAN, TIMESTAMPTZ) TO kanban_app;

-- 4. Function kb_auth.session_resolve carrying aal2_last_active_at (DO NOT slide inside session_resolve)
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
    rotated_from_id UUID,
    is_persistent BOOLEAN,
    aal2_last_active_at TIMESTAMPTZ
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
    -- (aal2_last_active_at is NOT slided inside session_resolve)
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
        v_session.rotated_from_id,
        v_session.is_persistent,
        v_session.aal2_last_active_at;
END;
$$;

ALTER FUNCTION kb_auth.session_resolve(BYTEA) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.session_resolve(BYTEA) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.session_resolve(BYTEA) TO kanban_app;

-- 5. Function kb_auth.session_rotate carrying aal2_last_active_at
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
    v_aal2_last_active TIMESTAMPTZ := NULL;
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
        v_aal2_last_active := v_now;
    ELSE
        v_aal2_at := v_old.aal2_verified_at;
        v_aal2_last_active := v_old.aal2_last_active_at;
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
        rotated_from_id,
        is_persistent,
        aal2_last_active_at
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
        p_old_id,
        v_old.is_persistent,
        v_aal2_last_active
    );

    RETURN v_new_id;
END;
$$;

ALTER FUNCTION kb_auth.session_rotate(UUID, BYTEA, SMALLINT) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.session_rotate(UUID, BYTEA, SMALLINT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.session_rotate(UUID, BYTEA, SMALLINT) TO kanban_app;

-- 6. Function kb_auth.session_get_metadata carrying aal2_last_active_at
CREATE OR REPLACE FUNCTION kb_auth.session_get_metadata(p_id UUID)
RETURNS TABLE (
    id UUID,
    idle_expires_at TIMESTAMPTZ,
    absolute_expires_at TIMESTAMPTZ,
    is_persistent BOOLEAN,
    aal2_last_active_at TIMESTAMPTZ,
    aal2_verified_at TIMESTAMPTZ,
    aal_level SMALLINT
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    RETURN QUERY
    SELECT s.id, s.idle_expires_at, s.absolute_expires_at, s.is_persistent,
           s.aal2_last_active_at, s.aal2_verified_at, s.aal_level
    FROM sessions s
    WHERE s.id = p_id
      AND s.revoked_at IS NULL;
END;
$$;

ALTER FUNCTION kb_auth.session_get_metadata(UUID) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.session_get_metadata(UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.session_get_metadata(UUID) TO kanban_app;

-- 7. Function kb_auth.session_touch_aal2 (sliding window touch with 30s write throttling)
CREATE OR REPLACE FUNCTION kb_auth.session_touch_aal2(
    p_session_id UUID,
    p_idle_seconds INT DEFAULT 900,
    p_abs_seconds INT DEFAULT 14400,
    p_force BOOLEAN DEFAULT FALSE
)
RETURNS TABLE (
    aal2_active BOOLEAN,
    aal2_expires_at TIMESTAMPTZ
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_now TIMESTAMPTZ := clock_timestamp();
    v_session sessions%ROWTYPE;
    v_idle_sec INT := COALESCE(p_idle_seconds, 900);
    v_abs_sec INT := COALESCE(p_abs_seconds, 14400);
    v_effective_active_at TIMESTAMPTZ;
    v_expires_at TIMESTAMPTZ;
BEGIN
    SELECT * INTO v_session
    FROM sessions s
    WHERE s.id = p_session_id
      AND s.revoked_at IS NULL
      AND v_now < s.idle_expires_at
      AND v_now < s.absolute_expires_at;

    IF NOT FOUND OR v_session.aal_level < 2 OR v_session.aal2_verified_at IS NULL THEN
        RETURN QUERY SELECT FALSE, NULL::TIMESTAMPTZ;
        RETURN;
    END IF;

    v_effective_active_at := COALESCE(v_session.aal2_last_active_at, v_session.aal2_verified_at);

    -- Check if idle timeout has expired or absolute cap has been exceeded
    IF v_now >= (v_effective_active_at + (v_idle_sec * interval '1 second'))
       OR v_now >= (v_session.aal2_verified_at + (v_abs_sec * interval '1 second')) THEN
        RETURN QUERY SELECT FALSE, NULL::TIMESTAMPTZ;
        RETURN;
    END IF;

    -- Still active: compute new aal2_expires_at
    v_expires_at := LEAST(
        v_now + (v_idle_sec * interval '1 second'),
        v_session.aal2_verified_at + (v_abs_sec * interval '1 second'),
        v_session.idle_expires_at,
        v_session.absolute_expires_at
    );

    -- Throttle DB writes: only update aal2_last_active_at if forced or if > 30s elapsed since last update
    IF p_force OR v_session.aal2_last_active_at IS NULL OR v_session.aal2_last_active_at < (v_now - interval '30 seconds') THEN
        UPDATE sessions
        SET aal2_last_active_at = v_now
        WHERE id = v_session.id;
    END IF;

    RETURN QUERY SELECT TRUE, v_expires_at;
END;
$$;

ALTER FUNCTION kb_auth.session_touch_aal2(UUID, INT, INT, BOOLEAN) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.session_touch_aal2(UUID, INT, INT, BOOLEAN) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.session_touch_aal2(UUID, INT, INT, BOOLEAN) TO kanban_app;

-- 8. Function kb_auth.session_drop_aal2 (drop active AAL2 WebSudo elevation)
CREATE OR REPLACE FUNCTION kb_auth.session_drop_aal2(p_session_id UUID)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_updated INT;
BEGIN
    UPDATE sessions
    SET aal_level = 1,
        aal2_last_active_at = NULL,
        aal2_verified_at = NULL
    WHERE id = p_session_id
      AND revoked_at IS NULL;
    GET DIAGNOSTICS v_updated = ROW_COUNT;
    RETURN v_updated > 0;
END;
$$;

ALTER FUNCTION kb_auth.session_drop_aal2(UUID) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.session_drop_aal2(UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.session_drop_aal2(UUID) TO kanban_app;
