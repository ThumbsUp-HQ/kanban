-- Phase 1 / Database: Transactional outbox_events, OutboxRelay (SKIP LOCKED) and RealtimeBroker
-- Authoritative Specification: S2.2, S2.4, Requirement #3, KB-P1-18

-- 1. Create outbox_events table
CREATE TABLE outbox_events (
    id                UUID        PRIMARY KEY DEFAULT uuidv7(),
    seq               BIGINT      GENERATED ALWAYS AS IDENTITY UNIQUE,
    workspace_id      UUID        NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    project_id        UUID        REFERENCES projects(id) ON DELETE SET NULL,
    object_id         UUID,
    topic             TEXT        NOT NULL CHECK (topic ~ '^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$'
                                                  AND char_length(topic) <= 128),
    payload           JSONB       NOT NULL DEFAULT '{}'::jsonb
                                  CHECK (jsonb_typeof(payload) = 'object'
                                         AND octet_length(payload::text) <= 7168),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    next_attempt_at   TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    published_at      TIMESTAMPTZ,
    dead_lettered_at  TIMESTAMPTZ,
    attempts          INTEGER     NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    last_error        TEXT        CHECK (last_error IS NULL OR char_length(last_error) <= 1024)
);

CREATE INDEX outbox_events_pending_idx
    ON outbox_events (next_attempt_at, seq)
    WHERE published_at IS NULL AND dead_lettered_at IS NULL;

-- 2. Row Level Security
ALTER TABLE outbox_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE outbox_events FORCE ROW LEVEL SECURITY;

REVOKE ALL ON outbox_events FROM PUBLIC;
GRANT SELECT, INSERT ON outbox_events TO kanban_app;
GRANT SELECT ON outbox_events TO app_rls_reader;

CREATE POLICY outbox_events_insert_rls ON outbox_events
    FOR INSERT
    WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_current_principal_id() IS NOT NULL
    );

CREATE POLICY outbox_events_select_rls ON outbox_events
    FOR SELECT
    USING (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN'])
    );

-- 3. Statement-level wakeup trigger
CREATE OR REPLACE FUNCTION outbox_events_wakeup_fn()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    PERFORM pg_notify('outbox_wakeup', '');
    RETURN NULL;
END;
$$;

CREATE TRIGGER outbox_events_wakeup_ai
    AFTER INSERT ON outbox_events
    FOR EACH STATEMENT
    EXECUTE FUNCTION outbox_events_wakeup_fn();

-- 4. claim_outbox_batch() FOR UPDATE SKIP LOCKED
CREATE OR REPLACE FUNCTION claim_outbox_batch(
    p_batch_size integer DEFAULT 100,
    p_now timestamptz DEFAULT clock_timestamp()
)
RETURNS SETOF outbox_events
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF p_batch_size < 1 OR p_batch_size > 500 THEN
        RAISE EXCEPTION USING ERRCODE = '22023',
            MESSAGE = 'p_batch_size must be between 1 and 500';
    END IF;

    RETURN QUERY
    WITH locked AS (
        SELECT id
        FROM outbox_events
        WHERE published_at IS NULL
          AND dead_lettered_at IS NULL
          AND next_attempt_at <= p_now
        ORDER BY seq ASC
        LIMIT p_batch_size
        FOR UPDATE SKIP LOCKED
    )
    UPDATE outbox_events o
    SET attempts = o.attempts + 1,
        next_attempt_at = p_now + interval '30 seconds'
    FROM locked
    WHERE o.id = locked.id
    RETURNING o.*;
END;
$$;

-- 5. mark_outbox_published()
CREATE OR REPLACE FUNCTION mark_outbox_published(
    p_ids uuid[],
    p_now timestamptz DEFAULT clock_timestamp()
)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_count integer;
BEGIN
    UPDATE outbox_events
    SET published_at = p_now,
        last_error = NULL
    WHERE id = ANY(p_ids)
      AND published_at IS NULL;

    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$;

-- 6. mark_outbox_failed() with exponential backoff and dead-lettering
CREATE OR REPLACE FUNCTION mark_outbox_failed(
    p_id uuid,
    p_error text,
    p_max_attempts integer DEFAULT 5,
    p_now timestamptz DEFAULT clock_timestamp()
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_attempts integer;
    v_truncated_error text;
    v_dead_lettered boolean := false;
BEGIN
    v_truncated_error := substr(p_error, 1, 1024);

    SELECT attempts INTO v_attempts
    FROM outbox_events
    WHERE id = p_id;

    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;

    IF v_attempts >= p_max_attempts THEN
        UPDATE outbox_events
        SET dead_lettered_at = p_now,
            last_error = v_truncated_error
        WHERE id = p_id;
        v_dead_lettered := true;
    ELSE
        UPDATE outbox_events
        SET next_attempt_at = p_now + make_interval(secs => least(300, power(2, v_attempts)::int)),
            last_error = v_truncated_error
        WHERE id = p_id;
        v_dead_lettered := false;
    END IF;

    RETURN v_dead_lettered;
END;
$$;

GRANT EXECUTE ON FUNCTION claim_outbox_batch(integer, timestamptz) TO kanban_app;
GRANT EXECUTE ON FUNCTION mark_outbox_published(uuid[], timestamptz) TO kanban_app;
GRANT EXECUTE ON FUNCTION mark_outbox_failed(uuid, text, integer, timestamptz) TO kanban_app;
