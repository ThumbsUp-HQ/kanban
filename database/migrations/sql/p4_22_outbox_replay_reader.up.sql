-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

-- 1. fetch_replay_outbox_events(): Reads replayable outbox events for a tenant.
-- SECURITY DEFINER allows non-admin members to retrieve historical events for their workspace,
-- which are subsequently filtered strictly through candidate VIEW permissions in OutboxReplayer.
CREATE OR REPLACE FUNCTION fetch_replay_outbox_events(
    p_workspace_id UUID,
    p_last_seq BIGINT,
    p_retention_minutes INT DEFAULT 60,
    p_limit INT DEFAULT 100
)
RETURNS TABLE (
    id UUID,
    seq BIGINT,
    workspace_id UUID,
    project_id UUID,
    object_id UUID,
    topic TEXT,
    payload JSONB,
    created_at TIMESTAMPTZ
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF p_workspace_id IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'NULL_ARGUMENT';
    END IF;

    -- Tenant isolation safeguard: if session has app.workspace_id bound, enforce match.
    IF NULLIF(current_setting('app.workspace_id', true), '') IS NOT NULL THEN
        IF p_workspace_id <> current_setting('app.workspace_id', true)::UUID THEN
            RETURN;
        END IF;
    END IF;

    RETURN QUERY
    SELECT o.id, o.seq, o.workspace_id, o.project_id, o.object_id, o.topic, o.payload, o.created_at
    FROM outbox_events o
    WHERE o.workspace_id = p_workspace_id
      AND o.seq > p_last_seq
      AND o.created_at >= clock_timestamp() - (make_interval(mins => p_retention_minutes))
    ORDER BY o.seq ASC
    LIMIT p_limit;
END;
$$;

-- 2. get_outbox_retention_stats(): Calculates min, max, and overall_max seq for retention check.
CREATE OR REPLACE FUNCTION get_outbox_retention_stats(
    p_workspace_id UUID,
    p_retention_minutes INT DEFAULT 60
)
RETURNS TABLE (
    min_seq BIGINT,
    max_seq BIGINT,
    overall_max BIGINT
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF p_workspace_id IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'NULL_ARGUMENT';
    END IF;

    IF NULLIF(current_setting('app.workspace_id', true), '') IS NOT NULL THEN
        IF p_workspace_id <> current_setting('app.workspace_id', true)::UUID THEN
            RETURN;
        END IF;
    END IF;

    RETURN QUERY
    SELECT
        COALESCE((
            SELECT min(seq)
            FROM outbox_events
            WHERE workspace_id = p_workspace_id
              AND created_at >= clock_timestamp() - (make_interval(mins => p_retention_minutes))
        ), 0::BIGINT) AS min_seq,
        COALESCE((
            SELECT max(seq)
            FROM outbox_events
            WHERE workspace_id = p_workspace_id
              AND created_at >= clock_timestamp() - (make_interval(mins => p_retention_minutes))
        ), 0::BIGINT) AS max_seq,
        COALESCE((
            SELECT max(seq)
            FROM outbox_events
            WHERE workspace_id = p_workspace_id
        ), 0::BIGINT) AS overall_max;
END;
$$;

-- 3. get_outbox_missed_count(): Counts missed events above p_last_seq within retention window.
CREATE OR REPLACE FUNCTION get_outbox_missed_count(
    p_workspace_id UUID,
    p_last_seq BIGINT,
    p_retention_minutes INT DEFAULT 60
)
RETURNS BIGINT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF p_workspace_id IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'NULL_ARGUMENT';
    END IF;

    IF NULLIF(current_setting('app.workspace_id', true), '') IS NOT NULL THEN
        IF p_workspace_id <> current_setting('app.workspace_id', true)::UUID THEN
            RETURN 0::BIGINT;
        END IF;
    END IF;

    RETURN (
        SELECT count(*)::BIGINT
        FROM outbox_events
        WHERE workspace_id = p_workspace_id
          AND seq > p_last_seq
          AND created_at >= clock_timestamp() - (make_interval(mins => p_retention_minutes))
    );
END;
$$;

ALTER FUNCTION fetch_replay_outbox_events(UUID, BIGINT, INT, INT) OWNER TO kanban_migrator;
ALTER FUNCTION get_outbox_retention_stats(UUID, INT) OWNER TO kanban_migrator;
ALTER FUNCTION get_outbox_missed_count(UUID, BIGINT, INT) OWNER TO kanban_migrator;

GRANT EXECUTE ON FUNCTION fetch_replay_outbox_events(UUID, BIGINT, INT, INT) TO kanban_app;
GRANT EXECUTE ON FUNCTION get_outbox_retention_stats(UUID, INT) TO kanban_app;
GRANT EXECUTE ON FUNCTION get_outbox_missed_count(UUID, BIGINT, INT) TO kanban_app;
