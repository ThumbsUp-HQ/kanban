-- Phase 2 / Kanban: Sliding-window rate limiting service (KB-P2-18)
-- Authoritative Specification: S2.2, S2.4, Requirements #3, #6

-- 1. Create NOLOGIN infrastructure owner role
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'kb_infra_owner') THEN
        BEGIN
            CREATE ROLE kb_infra_owner WITH NOLOGIN NOINHERIT NOBYPASSRLS;
        EXCEPTION WHEN insufficient_privilege THEN
            RAISE NOTICE 'Role kb_infra_owner must be created by bootstrap';
        END;
    END IF;
END
$$;

-- 2. Create kb_infra schema owned by kb_infra_owner
CREATE SCHEMA IF NOT EXISTS kb_infra AUTHORIZATION kb_infra_owner;
GRANT USAGE ON SCHEMA kb_infra TO kanban_app;

-- 3. Create rate_limit_buckets table in public schema
CREATE TABLE rate_limit_buckets (
    policy       TEXT        NOT NULL,
    key_hash     BYTEA       NOT NULL CHECK (octet_length(key_hash) = 32),
    window_start TIMESTAMPTZ NOT NULL,
    count        INTEGER     NOT NULL DEFAULT 1 CHECK (count >= 0),
    PRIMARY KEY (policy, key_hash, window_start)
);

ALTER TABLE rate_limit_buckets OWNER TO kb_infra_owner;
ALTER TABLE rate_limit_buckets ENABLE ROW LEVEL SECURITY;
ALTER TABLE rate_limit_buckets FORCE ROW LEVEL SECURITY;

REVOKE ALL ON rate_limit_buckets FROM PUBLIC, kanban_app, app_rls_reader;
GRANT ALL ON rate_limit_buckets TO kb_infra_owner;

CREATE POLICY kb_infra_owner_all ON rate_limit_buckets
    FOR ALL TO kb_infra_owner
    USING (true)
    WITH CHECK (true);

-- 4. Create SECURITY DEFINER rate_limit_hit function
CREATE OR REPLACE FUNCTION kb_infra.rate_limit_hit(
    p_policy text,
    p_key bytea,
    p_limit integer,
    p_window_s integer,
    p_now timestamptz DEFAULT clock_timestamp()
)
RETURNS TABLE(allowed boolean, remaining integer, retry_after integer)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_now timestamptz := COALESCE(p_now, clock_timestamp());
    v_epoch double precision := extract(epoch FROM v_now);
    v_window_start_epoch double precision := floor(v_epoch / p_window_s) * p_window_s;
    v_window_start timestamptz := to_timestamp(v_window_start_epoch);
    v_prev_window_start timestamptz := to_timestamp(v_window_start_epoch - p_window_s);
    v_elapsed double precision := v_epoch - v_window_start_epoch;
    v_weight double precision;
    v_curr_count integer;
    v_prev_count integer := 0;
    v_total integer;
    v_allowed boolean;
    v_remaining integer;
    v_retry_after integer;
BEGIN
    IF octet_length(p_key) <> 32 THEN
        RAISE EXCEPTION 'p_key must be exactly 32 bytes' USING ERRCODE = '22023';
    END IF;
    IF p_limit < 1 THEN
        RAISE EXCEPTION 'p_limit must be >= 1' USING ERRCODE = '22023';
    END IF;
    IF p_window_s < 1 THEN
        RAISE EXCEPTION 'p_window_s must be >= 1' USING ERRCODE = '22023';
    END IF;

    -- Weight for remaining overlap of previous window: (window_s - elapsed) / window_s
    v_weight := (p_window_s - v_elapsed) / p_window_s;
    IF v_weight < 0.0 THEN
        v_weight := 0.0;
    ELSIF v_weight > 1.0 THEN
        v_weight := 1.0;
    END IF;

    -- Increment or insert current window bucket
    INSERT INTO rate_limit_buckets (policy, key_hash, window_start, count)
    VALUES (p_policy, p_key, v_window_start, 1)
    ON CONFLICT (policy, key_hash, window_start)
    DO UPDATE SET count = rate_limit_buckets.count + 1
    RETURNING rate_limit_buckets.count INTO v_curr_count;

    -- Fetch count from immediately preceding window
    SELECT COALESCE(b.count, 0) INTO v_prev_count
    FROM rate_limit_buckets b
    WHERE b.policy = p_policy
      AND b.key_hash = p_key
      AND b.window_start = v_prev_window_start;

    IF v_prev_count IS NULL THEN
        v_prev_count := 0;
    END IF;

    -- Compute sliding-window estimated count
    v_total := floor(v_prev_count * v_weight)::integer + v_curr_count;

    IF v_total <= p_limit THEN
        v_allowed := true;
        v_remaining := p_limit - v_total;
        v_retry_after := 0;
    ELSE
        v_allowed := false;
        v_remaining := 0;
        v_retry_after := ceil(p_window_s - v_elapsed)::integer;
        IF v_retry_after < 1 THEN
            v_retry_after := 1;
        END IF;
    END IF;

    -- Opportunistic cleanup of rows older than 2 * window (max 500 rows)
    DELETE FROM rate_limit_buckets
    WHERE ctid IN (
        SELECT ctid
        FROM rate_limit_buckets
        WHERE window_start < v_window_start - make_interval(secs => p_window_s)
        LIMIT 500
    );

    RETURN QUERY SELECT v_allowed, v_remaining, v_retry_after;
END;
$$;

ALTER FUNCTION kb_infra.rate_limit_hit(text, bytea, integer, integer, timestamptz) OWNER TO kb_infra_owner;
GRANT EXECUTE ON FUNCTION kb_infra.rate_limit_hit(text, bytea, integer, integer, timestamptz) TO kanban_app;

-- 5. Create SECURITY DEFINER rate_limit_reset function
CREATE OR REPLACE FUNCTION kb_infra.rate_limit_reset(
    p_policy text,
    p_key bytea
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    DELETE FROM rate_limit_buckets
    WHERE policy = p_policy
      AND key_hash = p_key;
END;
$$;

ALTER FUNCTION kb_infra.rate_limit_reset(text, bytea) OWNER TO kb_infra_owner;
GRANT EXECUTE ON FUNCTION kb_infra.rate_limit_reset(text, bytea) TO kanban_app;
