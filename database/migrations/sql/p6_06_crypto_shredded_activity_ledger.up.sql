-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

-- 1. Upgrade activity_records columns for envelope-encrypted payloads
ALTER TABLE activity_records
    ADD COLUMN IF NOT EXISTS encryption_ver SMALLINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS payload_ciphertext BYTEA NULL,
    ADD COLUMN IF NOT EXISTS payload_nonce BYTEA NULL,
    ADD COLUMN IF NOT EXISTS payload_aad_sha256 BYTEA NULL;

-- 2. Dedicated activity_record_keys table for wrapped DEKs and crypto-shredding
CREATE TABLE IF NOT EXISTS activity_record_keys (
    activity_id UUID NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    object_id UUID NULL,
    actor_id UUID NULL,
    wrapped_dek BYTEA NULL,
    dek_nonce BYTEA NULL,
    dek_kid TEXT NOT NULL,
    shredded_at TIMESTAMPTZ NULL,
    shredded_by_id UUID NULL,
    shred_reason TEXT NULL,
    PRIMARY KEY (workspace_id, activity_id)
);

CREATE INDEX IF NOT EXISTS idx_activity_record_keys_object ON activity_record_keys (workspace_id, object_id) WHERE object_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_activity_record_keys_actor ON activity_record_keys (workspace_id, actor_id) WHERE actor_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_activity_record_keys_recorded ON activity_record_keys (workspace_id, recorded_at DESC);

ALTER TABLE activity_record_keys OWNER TO kanban_migrator;

ALTER TABLE activity_record_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE activity_record_keys FORCE ROW LEVEL SECURITY;

CREATE POLICY activity_record_keys_select_rls ON activity_record_keys
    FOR SELECT USING (
        app_current_workspace_id() IS NULL
        OR (
            workspace_id = app_current_workspace_id()
            AND (
                object_id IS NULL
                OR app_has_object_capability(object_id, 1)
                OR app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
            )
        )
    );

CREATE POLICY activity_record_keys_insert_rls ON activity_record_keys
    FOR INSERT WITH CHECK (
        app_current_workspace_id() IS NULL
        OR workspace_id = app_current_workspace_id()
    );

CREATE POLICY activity_record_keys_update_rls ON activity_record_keys
    FOR UPDATE USING (
        app_current_workspace_id() IS NULL
        OR (
            workspace_id = app_current_workspace_id()
            AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
        )
    ) WITH CHECK (
        app_current_workspace_id() IS NULL
        OR workspace_id = app_current_workspace_id()
    );

GRANT SELECT, INSERT, UPDATE ON activity_record_keys TO kanban_app;
GRANT SELECT ON activity_record_keys TO app_rls_reader;
REVOKE DELETE, TRUNCATE ON activity_record_keys FROM kanban_app, app_rls_reader;

-- 3. Update compute_activity_row_hash to support encryption_ver = 1
DROP FUNCTION IF EXISTS compute_activity_row_hash(bytea, uuid, bigint, uuid, uuid, object_kind, uuid, text, timestamptz, jsonb);

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
    p_payload jsonb,
    p_encryption_ver smallint DEFAULT 0,
    p_payload_ciphertext bytea DEFAULT NULL,
    p_payload_nonce bytea DEFAULT NULL,
    p_payload_aad_sha256 bytea DEFAULT NULL
) RETURNS bytea LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT CASE
        WHEN coalesce(p_encryption_ver, 0) = 0 THEN
            digest(
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
            )
        ELSE
            digest(
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
                        encode(digest(coalesce(p_payload_ciphertext, ''::bytea) || coalesce(p_payload_nonce, ''::bytea) || coalesce(p_payload_aad_sha256, ''::bytea), 'sha256'), 'hex')
                    ),
                    'UTF8'
                ),
                'sha256'
            )
    END;
$$;

GRANT EXECUTE ON FUNCTION compute_activity_row_hash(bytea, uuid, bigint, uuid, uuid, object_kind, uuid, text, timestamptz, jsonb, smallint, bytea, bytea, bytea) TO kanban_app, app_rls_reader;

-- 4. Update activity_records_chain_bi trigger function
CREATE OR REPLACE FUNCTION activity_records_chain_bi()
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
    NEW.encryption_ver := COALESCE(NEW.encryption_ver, 0::smallint);

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
        NEW.payload,
        NEW.encryption_ver,
        NEW.payload_ciphertext,
        NEW.payload_nonce,
        NEW.payload_aad_sha256
    );

    -- 5. Update chain head
    UPDATE public.activity_chain_heads
    SET last_seq = NEW.chain_seq,
        last_hash = NEW.row_hash,
        updated_at = clock_timestamp()
    WHERE workspace_id = NEW.workspace_id;

    RETURN NEW;
END $$;

-- 5. Update verify_activity_chain function
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
            event_type, payload, recorded_at, prev_hash, row_hash,
            encryption_ver, payload_ciphertext, payload_nonce, payload_aad_sha256
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
            r.payload,
            r.encryption_ver,
            r.payload_ciphertext,
            r.payload_nonce,
            r.payload_aad_sha256
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

-- 6. Update append_activity function to accept encryption parameters and optional id
DROP FUNCTION IF EXISTS append_activity(uuid, uuid, object_kind, uuid, text, jsonb);

CREATE OR REPLACE FUNCTION append_activity(
    p_workspace_id uuid,
    p_object_id uuid,
    p_object_type object_kind,
    p_actor_id uuid,
    p_event_type text,
    p_payload jsonb DEFAULT '{}'::jsonb,
    p_encryption_ver smallint DEFAULT 0,
    p_payload_ciphertext bytea DEFAULT NULL,
    p_payload_nonce bytea DEFAULT NULL,
    p_payload_aad_sha256 bytea DEFAULT NULL,
    p_id uuid DEFAULT NULL
) RETURNS uuid LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE
    v_id uuid;
BEGIN
    INSERT INTO public.activity_records (
        id, workspace_id, object_id, object_type, actor_id, event_type, payload,
        encryption_ver, payload_ciphertext, payload_nonce, payload_aad_sha256
    ) VALUES (
        COALESCE(p_id, public.uuidv7()),
        p_workspace_id, p_object_id, p_object_type, p_actor_id, p_event_type, COALESCE(p_payload, '{}'::jsonb),
        COALESCE(p_encryption_ver, 0::smallint), p_payload_ciphertext, p_payload_nonce, p_payload_aad_sha256
    ) RETURNING id INTO v_id;

    RETURN v_id;
END $$;

ALTER FUNCTION compute_activity_row_hash(bytea, uuid, bigint, uuid, uuid, object_kind, uuid, text, timestamptz, jsonb, smallint, bytea, bytea, bytea) OWNER TO kanban_migrator;
ALTER FUNCTION activity_records_chain_bi() OWNER TO kanban_migrator;
ALTER FUNCTION verify_activity_chain(uuid) OWNER TO kanban_migrator;
ALTER FUNCTION append_activity(uuid, uuid, object_kind, uuid, text, jsonb, smallint, bytea, bytea, bytea, uuid) OWNER TO kanban_migrator;
GRANT EXECUTE ON FUNCTION append_activity(uuid, uuid, object_kind, uuid, text, jsonb, smallint, bytea, bytea, bytea, uuid) TO kanban_app, kb_auth_owner;
