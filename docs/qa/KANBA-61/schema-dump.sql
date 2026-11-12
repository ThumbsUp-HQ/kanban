--
-- Schema dump and permissions audit for KB-P2-18 (KANBA-61)
-- Table: public.rate_limit_buckets
-- Schema: kb_infra
-- Functions: kb_infra.rate_limit_hit, kb_infra.rate_limit_reset
--

-- ============================================================================
-- 1. Table DDL: public.rate_limit_buckets
-- ============================================================================

CREATE TABLE public.rate_limit_buckets (
    policy text NOT NULL,
    key_hash bytea NOT NULL,
    window_start timestamp with time zone NOT NULL,
    count integer DEFAULT 1 NOT NULL,
    CONSTRAINT rate_limit_buckets_count_check CHECK ((count >= 0)),
    CONSTRAINT rate_limit_buckets_key_hash_check CHECK ((octet_length(key_hash) = 32)),
    CONSTRAINT rate_limit_buckets_pkey PRIMARY KEY (policy, key_hash, window_start)
);

ALTER TABLE public.rate_limit_buckets OWNER TO kb_infra_owner;

ALTER TABLE public.rate_limit_buckets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.rate_limit_buckets FORCE ROW LEVEL SECURITY;

CREATE POLICY kb_infra_owner_all ON public.rate_limit_buckets
    TO kb_infra_owner
    USING (true)
    WITH CHECK (true);

REVOKE ALL ON TABLE public.rate_limit_buckets FROM PUBLIC;
REVOKE ALL ON TABLE public.rate_limit_buckets FROM kanban_app;
REVOKE ALL ON TABLE public.rate_limit_buckets FROM app_rls_reader;
GRANT ALL ON TABLE public.rate_limit_buckets TO kb_infra_owner;

-- ============================================================================
-- 2. psql \d+ rate_limit_buckets
-- ============================================================================
--                                                Table "public.rate_limit_buckets"
--     Column    |           Type           | Collation | Nullable | Default | Storage  | Compression | Stats target | Description 
-- --------------+--------------------------+-----------+----------+---------+----------+-------------+--------------+-------------
--  policy       | text                     |           | not null |         | extended |             |              | 
--  key_hash     | bytea                    |           | not null |         | extended |             |              | 
--  window_start | timestamp with time zone |           | not null |         | plain    |             |              | 
--  count        | integer                  |           | not null | 1       | plain    |             |              | 
-- Indexes:
--     "rate_limit_buckets_pkey" PRIMARY KEY, btree (policy, key_hash, window_start)
-- Check constraints:
--     "rate_limit_buckets_count_check" CHECK (count >= 0)
--     "rate_limit_buckets_key_hash_check" CHECK (octet_length(key_hash) = 32)
-- Policies (forced row security enabled):
--     POLICY "kb_infra_owner_all"
--       TO kb_infra_owner
--       USING (true)
--       WITH CHECK (true)
-- Access method: heap

-- ============================================================================
-- 3. Table Access Privileges: \dp rate_limit_buckets
-- ============================================================================
--                                                    Access privileges
--  Schema |        Name        | Type  |           Access privileges           | Column privileges |       Policies       
-- --------+--------------------+-------+---------------------------------------+-------------------+----------------------
--  public | rate_limit_buckets | table | kb_infra_owner=arwdDxt/kb_infra_owner |                   | kb_infra_owner_all: +
--         |                    |       |                                       |                   |   (u): true         +
--         |                    |       |                                       |                   |   (c): true         +
--         |                    |       |                                       |                   |   to: kb_infra_owner

-- ============================================================================
-- 4. Function Inspection: \df+ kb_infra.rate_limit_hit
-- ============================================================================
-- Schema: kb_infra
-- Name: rate_limit_hit
-- Result data type: TABLE(allowed boolean, remaining integer, retry_after integer)
-- Argument data types: p_policy text, p_key bytea, p_limit integer, p_window_s integer, p_now timestamp with time zone DEFAULT clock_timestamp()
-- Type: func
-- Volatility: volatile
-- Owner: kb_infra_owner
-- Security: definer
-- Language: plpgsql
-- Access privileges: kb_infra_owner=X/kb_infra_owner, kanban_app=X/kb_infra_owner

CREATE OR REPLACE FUNCTION kb_infra.rate_limit_hit(
    p_policy text,
    p_key bytea,
    p_limit int,
    p_window_s int,
    p_now timestamptz DEFAULT clock_timestamp()
)
RETURNS TABLE (
    allowed bool,
    remaining int,
    retry_after int
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_epoch double precision;
    v_window_start timestamptz;
    v_prev_window_start timestamptz;
    v_elapsed double precision;
    v_weight double precision;
    v_curr_count int;
    v_prev_count int := 0;
    v_estimated int;
    v_allowed bool;
    v_remaining int;
    v_retry_after int;
BEGIN
    IF octet_length(p_key) <> 32 THEN
        RAISE EXCEPTION 'Key hash must be exactly 32 bytes' USING ERRCODE = '22000';
    END IF;

    v_epoch := extract(epoch FROM p_now);
    v_window_start := to_timestamp(floor(v_epoch / p_window_s) * p_window_s);
    v_prev_window_start := v_window_start - (p_window_s * interval '1 second');

    v_elapsed := v_epoch - extract(epoch FROM v_window_start);
    v_weight := (p_window_s - v_elapsed) / p_window_s::double precision;
    IF v_weight < 0.0 THEN
        v_weight := 0.0;
    ELSIF v_weight > 1.0 THEN
        v_weight := 1.0;
    END IF;

    SELECT coalesce(count, 0)
      INTO v_prev_count
      FROM rate_limit_buckets
     WHERE policy = p_policy
       AND key_hash = p_key
       AND window_start = v_prev_window_start;

    SELECT coalesce(count, 0)
      INTO v_curr_count
      FROM rate_limit_buckets
     WHERE policy = p_policy
       AND key_hash = p_key
       AND window_start = v_window_start;

    v_estimated := floor(v_prev_count * v_weight) + coalesce(v_curr_count, 0);

    IF v_estimated >= p_limit THEN
        v_allowed := false;
        v_remaining := 0;
        v_retry_after := ceil(p_window_s - v_elapsed)::int;
        IF v_retry_after < 1 THEN
            v_retry_after := 1;
        END IF;
    ELSE
        INSERT INTO rate_limit_buckets (policy, key_hash, window_start, count)
        VALUES (p_policy, p_key, v_window_start, 1)
        ON CONFLICT (policy, key_hash, window_start)
        DO UPDATE SET count = rate_limit_buckets.count + 1
        RETURNING rate_limit_buckets.count INTO v_curr_count;

        v_estimated := floor(v_prev_count * v_weight) + v_curr_count;
        v_allowed := true;
        v_remaining := p_limit - v_estimated;
        IF v_remaining < 0 THEN
            v_remaining := 0;
        END IF;
        v_retry_after := 0;

        -- Opportunistic pruning of stale buckets older than 2 windows (bounded to 500 rows)
        DELETE FROM rate_limit_buckets
         WHERE ctid IN (
             SELECT ctid
               FROM rate_limit_buckets
              WHERE window_start < (p_now - (2 * p_window_s * interval '1 second'))
              LIMIT 500
         );
    END IF;

    RETURN QUERY SELECT v_allowed, v_remaining, v_retry_after;
END;
$$;

-- ============================================================================
-- 5. Function Inspection: \df+ kb_infra.rate_limit_reset
-- ============================================================================

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
    IF octet_length(p_key) <> 32 THEN
        RAISE EXCEPTION 'Key hash must be exactly 32 bytes' USING ERRCODE = '22000';
    END IF;

    DELETE FROM rate_limit_buckets
     WHERE policy = p_policy
       AND key_hash = p_key;
END;
$$;
