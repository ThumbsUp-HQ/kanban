-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

-- 1. Restore append_activity function to 6-arg signature
DROP FUNCTION IF EXISTS append_activity(uuid, uuid, object_kind, uuid, text, jsonb, smallint, bytea, bytea, bytea);
DROP FUNCTION IF EXISTS append_activity(uuid, uuid, object_kind, uuid, text, jsonb, smallint, bytea, bytea, bytea, uuid);

CREATE OR REPLACE FUNCTION append_activity(
    p_workspace_id uuid,
    p_object_id uuid,
    p_object_type object_kind,
    p_actor_id uuid,
    p_event_type text,
    p_payload jsonb DEFAULT '{}'::jsonb
) RETURNS uuid LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE
    v_id uuid;
BEGIN
    INSERT INTO public.activity_records (
        workspace_id, object_id, object_type, actor_id, event_type, payload
    ) VALUES (
        p_workspace_id, p_object_id, p_object_type, p_actor_id, p_event_type, COALESCE(p_payload, '{}'::jsonb)
    ) RETURNING id INTO v_id;

    RETURN v_id;
END $$;

ALTER FUNCTION append_activity(uuid, uuid, object_kind, uuid, text, jsonb) OWNER TO kanban_migrator;
GRANT EXECUTE ON FUNCTION append_activity(uuid, uuid, object_kind, uuid, text, jsonb) TO kanban_app, kb_auth_owner;

-- 2. Restore verify_activity_chain function
CREATE OR REPLACE FUNCTION verify_activity_chain(p_workspace_id uuid)
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

-- 3. Restore activity_records_chain_bi trigger function
CREATE OR REPLACE FUNCTION activity_records_chain_bi()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE
    v_head_seq  bigint;
    v_head_hash bytea;
BEGIN
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

    INSERT INTO public.activity_chain_heads (workspace_id, last_seq, last_hash, updated_at)
    VALUES (NEW.workspace_id, 0, decode(repeat('00', 32), 'hex'), clock_timestamp())
    ON CONFLICT (workspace_id) DO NOTHING;

    SELECT last_seq, last_hash
    INTO v_head_seq, v_head_hash
    FROM public.activity_chain_heads
    WHERE workspace_id = NEW.workspace_id
    FOR UPDATE;

    NEW.id := COALESCE(NEW.id, public.uuidv7());
    NEW.chain_seq := v_head_seq + 1;
    NEW.prev_hash := v_head_hash;
    NEW.recorded_at := date_trunc('microseconds', COALESCE(NEW.recorded_at, clock_timestamp()));
    NEW.payload := COALESCE(NEW.payload, '{}'::jsonb);

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

    UPDATE public.activity_chain_heads
    SET last_seq = NEW.chain_seq,
        last_hash = NEW.row_hash,
        updated_at = clock_timestamp()
    WHERE workspace_id = NEW.workspace_id;

    RETURN NEW;
END $$;

-- 4. Restore compute_activity_row_hash function to 10-arg signature
DROP FUNCTION IF EXISTS compute_activity_row_hash(bytea, uuid, bigint, uuid, uuid, object_kind, uuid, text, timestamptz, jsonb, smallint, bytea, bytea, bytea);

CREATE OR REPLACE FUNCTION compute_activity_row_hash(
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

-- 5. Drop activity_record_keys table
DROP TABLE IF EXISTS activity_record_keys;

-- 6. Drop activity_records added columns
ALTER TABLE activity_records
    DROP COLUMN IF EXISTS payload_aad_sha256,
    DROP COLUMN IF EXISTS payload_nonce,
    DROP COLUMN IF EXISTS payload_ciphertext,
    DROP COLUMN IF EXISTS encryption_ver;
