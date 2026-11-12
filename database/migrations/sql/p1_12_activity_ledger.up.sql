CREATE TABLE activity_chain_heads (
    workspace_id  UUID PRIMARY KEY REFERENCES workspaces(id) ON DELETE RESTRICT,
    last_seq      BIGINT NOT NULL CHECK (last_seq >= 0),
    last_hash     BYTEA  NOT NULL CHECK (octet_length(last_hash) = 32),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

REVOKE INSERT, UPDATE, DELETE ON activity_chain_heads FROM kanban_app, app_rls_reader;

CREATE TABLE activity_records (
    id           UUID        NOT NULL DEFAULT uuidv7(),
    workspace_id UUID        NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    chain_seq    BIGINT      NOT NULL,
    object_id    UUID,
    object_type  object_kind,
    actor_id     UUID        REFERENCES principals(id) ON DELETE RESTRICT,
    event_type   TEXT        NOT NULL CHECK (event_type ~ '^[A-Z][A-Z0-9_]{2,63}$'),
    payload      JSONB       NOT NULL DEFAULT '{}'::jsonb
                             CHECK (jsonb_typeof(payload) = 'object' AND octet_length(payload::text) <= 16384),
    recorded_at  TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    prev_hash    BYTEA       NOT NULL CHECK (octet_length(prev_hash) = 32),
    row_hash     BYTEA       NOT NULL CHECK (octet_length(row_hash) = 32),
    CHECK ((object_id IS NULL) = (object_type IS NULL)),
    PRIMARY KEY (id, recorded_at)
) PARTITION BY RANGE (recorded_at);

CREATE UNIQUE INDEX activity_records_ws_seq_recorded_uq ON activity_records (workspace_id, chain_seq, recorded_at);
CREATE INDEX activity_records_ws_seq_idx ON activity_records (workspace_id, chain_seq DESC);
CREATE INDEX activity_records_object_idx ON activity_records (object_id, recorded_at DESC) WHERE object_id IS NOT NULL;

REVOKE UPDATE, DELETE, TRUNCATE ON activity_records FROM kanban_app, app_rls_reader;

CREATE FUNCTION compute_activity_row_hash(
    p_prev_hash bytea,
    p_workspace_id uuid,
    p_chain_seq bigint,
    p_id uuid,
    p_object_id uuid,
    p_object_type object_kind,
    p_actor_id uuid,
    p_event_type text,
    p_recorded_at timestamptz,
    p_payload jsonb
) RETURNS bytea LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT digest(
        p_prev_hash || convert_to(
            concat_ws(
                '|',
                p_workspace_id::text,
                p_chain_seq::text,
                p_id::text,
                coalesce(p_object_id::text, ''),
                coalesce(p_object_type::text, ''),
                coalesce(p_actor_id::text, ''),
                p_event_type,
                to_char(date_trunc('microseconds', p_recorded_at) AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
                p_payload::text
            ),
            'UTF8'
        ),
        'sha256'
    );
$$;

GRANT EXECUTE ON FUNCTION compute_activity_row_hash(bytea, uuid, bigint, uuid, uuid, object_kind, uuid, text, timestamptz, jsonb) TO kanban_app, app_rls_reader;

CREATE FUNCTION ensure_activity_partitions(
    p_ref timestamptz DEFAULT clock_timestamp(),
    p_months_back int DEFAULT 1,
    p_months_ahead int DEFAULT 6
) RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE
    v_created_count integer := 0;
    v_i integer;
    v_ref_utc timestamp without time zone;
    v_start_ts timestamp with time zone;
    v_end_ts timestamp with time zone;
    v_part_name text;
    v_start_str text;
    v_end_str text;
BEGIN
    IF p_months_back < 0 OR p_months_back > 24 OR p_months_ahead < 0 OR p_months_ahead > 36 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'PARTITION_RANGE_INVALID';
    END IF;

    PERFORM pg_advisory_xact_lock(hashtextextended('activity_partitions', 0));

    v_ref_utc := date_trunc('month', p_ref AT TIME ZONE 'UTC');

    FOR v_i IN (-p_months_back)..p_months_ahead LOOP
        v_start_ts := (v_ref_utc + (v_i || ' month')::interval) AT TIME ZONE 'UTC';
        v_end_ts := (v_ref_utc + ((v_i + 1) || ' month')::interval) AT TIME ZONE 'UTC';

        v_part_name := 'activity_records_y' || to_char(v_start_ts, 'YYYY') || 'm' || to_char(v_start_ts, 'MM');
        v_start_str := to_char(v_start_ts, 'YYYY-MM-DD 00:00:00+00');
        v_end_str := to_char(v_end_ts, 'YYYY-MM-DD 00:00:00+00');

        IF NOT EXISTS (
            SELECT 1 FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relname = v_part_name
        ) THEN
            EXECUTE format(
                'CREATE TABLE public.%I PARTITION OF public.activity_records FOR VALUES FROM (%L) TO (%L)',
                v_part_name,
                v_start_str,
                v_end_str
            );
            EXECUTE format(
                'REVOKE UPDATE, DELETE, TRUNCATE ON public.%I FROM kanban_app, app_rls_reader',
                v_part_name
            );
            v_created_count := v_created_count + 1;
        END IF;
    END LOOP;

    RETURN v_created_count;
END $$;

GRANT EXECUTE ON FUNCTION ensure_activity_partitions(timestamptz, int, int) TO kanban_app;

-- Pre-create partitions for -1..+6 months around current timestamp
SELECT ensure_activity_partitions(clock_timestamp(), 1, 6);

CREATE FUNCTION activity_records_chain_bi()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE
    v_head_seq  bigint;
    v_head_hash bytea;
BEGIN
    -- 1. If object_id and object_type are both present, verify object belongs to workspace
    IF NEW.object_id IS NOT NULL AND NEW.object_type IS NOT NULL THEN
        IF NOT EXISTS (
            SELECT 1 FROM public.objects
            WHERE id = NEW.object_id
              AND object_type = NEW.object_type
              AND workspace_id = NEW.workspace_id
        ) THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'ACTIVITY_OBJECT_MISMATCH';
        END IF;
    END IF;

    -- 2. Lock / fetch chain head for workspace
    INSERT INTO public.activity_chain_heads (workspace_id, last_seq, last_hash, updated_at)
    VALUES (NEW.workspace_id, 0, decode(repeat('00', 32), 'hex'), clock_timestamp())
    ON CONFLICT (workspace_id) DO NOTHING;

    SELECT last_seq, last_hash
    INTO v_head_seq, v_head_hash
    FROM public.activity_chain_heads
    WHERE workspace_id = NEW.workspace_id
    FOR UPDATE;

    -- 3. Set chain attributes
    NEW.id := COALESCE(NEW.id, public.uuidv7());
    NEW.chain_seq := v_head_seq + 1;
    NEW.prev_hash := v_head_hash;
    NEW.recorded_at := date_trunc('microseconds', COALESCE(NEW.recorded_at, clock_timestamp()));
    NEW.payload := COALESCE(NEW.payload, '{}'::jsonb);

    -- 4. Compute row hash
    NEW.row_hash := public.compute_activity_row_hash(
        NEW.prev_hash,
        NEW.workspace_id,
        NEW.chain_seq,
        NEW.id,
        NEW.object_id,
        NEW.object_type,
        NEW.actor_id,
        NEW.event_type,
        NEW.recorded_at,
        NEW.payload
    );

    -- 5. Update chain head
    UPDATE public.activity_chain_heads
    SET last_seq = NEW.chain_seq,
        last_hash = NEW.row_hash,
        updated_at = clock_timestamp()
    WHERE workspace_id = NEW.workspace_id;

    RETURN NEW;
END $$;

CREATE TRIGGER activity_records_chain_bi_trg
BEFORE INSERT ON activity_records
FOR EACH ROW EXECUTE FUNCTION activity_records_chain_bi();

CREATE FUNCTION activity_records_immutable_bud()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'ACTIVITY_LEDGER_IMMUTABLE';
END $$;

CREATE TRIGGER activity_records_immutable_bud_trg
BEFORE UPDATE OR DELETE ON activity_records
FOR EACH ROW EXECUTE FUNCTION activity_records_immutable_bud();

CREATE FUNCTION append_activity(
    p_workspace_id uuid,
    p_object_id uuid,
    p_object_type object_kind,
    p_actor_id uuid,
    p_event_type text,
    p_payload jsonb DEFAULT '{}'::jsonb
) RETURNS uuid LANGUAGE plpgsql VOLATILE SECURITY INVOKER AS $$
DECLARE
    v_id uuid;
BEGIN
    INSERT INTO activity_records (
        workspace_id, object_id, object_type, actor_id, event_type, payload
    ) VALUES (
        p_workspace_id, p_object_id, p_object_type, p_actor_id, p_event_type, COALESCE(p_payload, '{}'::jsonb)
    ) RETURNING id INTO v_id;

    RETURN v_id;
END $$;

GRANT EXECUTE ON FUNCTION append_activity(uuid, uuid, object_kind, uuid, text, jsonb) TO kanban_app;

CREATE FUNCTION verify_activity_chain(p_workspace_id uuid)
RETURNS TABLE(
    is_valid boolean,
    checked_rows bigint,
    first_broken_seq bigint,
    first_broken_id uuid,
    failure_reason text
) LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE
    r RECORD;
    v_expected_seq bigint := 1;
    v_expected_prev_hash bytea := decode(repeat('00', 32), 'hex');
    v_computed_hash bytea;
    v_checked bigint := 0;
    v_head_seq bigint;
    v_head_hash bytea;
    v_has_head boolean := false;
BEGIN
    SELECT last_seq, last_hash INTO v_head_seq, v_head_hash
    FROM public.activity_chain_heads
    WHERE workspace_id = p_workspace_id;

    IF FOUND THEN
        v_has_head := true;
    END IF;

    FOR r IN
        SELECT
            id, workspace_id, chain_seq, object_id, object_type, actor_id,
            event_type, payload, recorded_at, prev_hash, row_hash
        FROM public.activity_records
        WHERE workspace_id = p_workspace_id
        ORDER BY chain_seq ASC, recorded_at ASC
    LOOP
        -- Check 1: SEQ_GAP
        IF r.chain_seq <> v_expected_seq THEN
            RETURN QUERY SELECT false, v_checked, r.chain_seq, r.id, 'SEQ_GAP'::text;
            RETURN;
        END IF;

        -- Check 2: PREV_HASH_MISMATCH
        IF r.prev_hash <> v_expected_prev_hash THEN
            RETURN QUERY SELECT false, v_checked, r.chain_seq, r.id, 'PREV_HASH_MISMATCH'::text;
            RETURN;
        END IF;

        -- Check 3: ROW_HASH_MISMATCH
        v_computed_hash := public.compute_activity_row_hash(
            r.prev_hash,
            r.workspace_id,
            r.chain_seq,
            r.id,
            r.object_id,
            r.object_type,
            r.actor_id,
            r.event_type,
            r.recorded_at,
            r.payload
        );

        IF r.row_hash <> v_computed_hash THEN
            RETURN QUERY SELECT false, v_checked, r.chain_seq, r.id, 'ROW_HASH_MISMATCH'::text;
            RETURN;
        END IF;

        v_checked := v_checked + 1;
        v_expected_seq := v_expected_seq + 1;
        v_expected_prev_hash := r.row_hash;
    END LOOP;

    -- If no rows
    IF v_checked = 0 THEN
        IF v_has_head AND v_head_seq > 0 THEN
            RETURN QUERY SELECT false, 0::bigint, 1::bigint, NULL::uuid, 'HEAD_MISMATCH'::text;
            RETURN;
        END IF;
        RETURN QUERY SELECT true, 0::bigint, NULL::bigint, NULL::uuid, NULL::text;
        RETURN;
    END IF;

    -- Check 4: HEAD_MISMATCH
    IF NOT v_has_head OR v_head_seq <> (v_expected_seq - 1) OR v_head_hash <> v_expected_prev_hash THEN
        RETURN QUERY SELECT false, v_checked, (v_expected_seq - 1), NULL::uuid, 'HEAD_MISMATCH'::text;
        RETURN;
    END IF;

    RETURN QUERY SELECT true, v_checked, NULL::bigint, NULL::uuid, NULL::text;
    RETURN;
END $$;

GRANT EXECUTE ON FUNCTION verify_activity_chain(uuid) TO kanban_app;
