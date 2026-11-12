--
-- PostgreSQL database dump
--

\restrict iLV1k2zMLcj8U9muDRMXHSQud5R3x88YagfrCHztMctnoqJnRgaEPUYKB2GrMin

-- Dumped from database version 16.15 (Debian 16.15-1.pgdg12+2)
-- Dumped by pg_dump version 16.15 (Debian 16.15-1.pgdg12+2)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: activity_chain_heads; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.activity_chain_heads (
    workspace_id uuid NOT NULL,
    last_seq bigint NOT NULL,
    last_hash bytea NOT NULL,
    updated_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT activity_chain_heads_last_hash_check CHECK ((octet_length(last_hash) = 32)),
    CONSTRAINT activity_chain_heads_last_seq_check CHECK ((last_seq >= 0))
);


ALTER TABLE public.activity_chain_heads OWNER TO kanban_migrator;

--
-- Name: activity_records; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.activity_records (
    id uuid DEFAULT public.uuidv7() NOT NULL,
    workspace_id uuid NOT NULL,
    chain_seq bigint NOT NULL,
    object_id uuid,
    object_type public.object_kind,
    actor_id uuid,
    event_type text NOT NULL,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    recorded_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    prev_hash bytea NOT NULL,
    row_hash bytea NOT NULL,
    CONSTRAINT activity_records_check CHECK (((object_id IS NULL) = (object_type IS NULL))),
    CONSTRAINT activity_records_event_type_check CHECK ((event_type ~ '^[A-Z][A-Z0-9_]{2,63}$'::text)),
    CONSTRAINT activity_records_payload_check CHECK (((jsonb_typeof(payload) = 'object'::text) AND (octet_length((payload)::text) <= 16384))),
    CONSTRAINT activity_records_prev_hash_check CHECK ((octet_length(prev_hash) = 32)),
    CONSTRAINT activity_records_row_hash_check CHECK ((octet_length(row_hash) = 32))
)
PARTITION BY RANGE (recorded_at);


ALTER TABLE public.activity_records OWNER TO kanban_migrator;

--
-- Name: activity_chain_heads activity_chain_heads_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.activity_chain_heads
    ADD CONSTRAINT activity_chain_heads_pkey PRIMARY KEY (workspace_id);


--
-- Name: activity_records activity_records_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.activity_records
    ADD CONSTRAINT activity_records_pkey PRIMARY KEY (id, recorded_at);


--
-- Name: activity_records_object_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX activity_records_object_idx ON ONLY public.activity_records USING btree (object_id, recorded_at DESC) WHERE (object_id IS NOT NULL);


--
-- Name: activity_records_ws_seq_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX activity_records_ws_seq_idx ON ONLY public.activity_records USING btree (workspace_id, chain_seq DESC);


--
-- Name: activity_records_ws_seq_recorded_uq; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE UNIQUE INDEX activity_records_ws_seq_recorded_uq ON ONLY public.activity_records USING btree (workspace_id, chain_seq, recorded_at);


--
-- Name: activity_records activity_records_chain_bi_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER activity_records_chain_bi_trg BEFORE INSERT ON public.activity_records FOR EACH ROW EXECUTE FUNCTION public.activity_records_chain_bi();


--
-- Name: activity_records activity_records_immutable_bud_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER activity_records_immutable_bud_trg BEFORE DELETE OR UPDATE ON public.activity_records FOR EACH ROW EXECUTE FUNCTION public.activity_records_immutable_bud();


--
-- Name: activity_chain_heads activity_chain_heads_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.activity_chain_heads
    ADD CONSTRAINT activity_chain_heads_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE RESTRICT;


--
-- Name: activity_records activity_records_actor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE public.activity_records
    ADD CONSTRAINT activity_records_actor_id_fkey FOREIGN KEY (actor_id) REFERENCES public.principals(id) ON DELETE RESTRICT;


--
-- Name: activity_records activity_records_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE public.activity_records
    ADD CONSTRAINT activity_records_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE RESTRICT;


--
-- Name: TABLE activity_chain_heads; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT ON TABLE public.activity_chain_heads TO kanban_app;
GRANT SELECT ON TABLE public.activity_chain_heads TO app_rls_reader;


--
-- Name: TABLE activity_records; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT ON TABLE public.activity_records TO kanban_app;
GRANT SELECT ON TABLE public.activity_records TO app_rls_reader;


--
-- PostgreSQL database dump complete
--

\unrestrict iLV1k2zMLcj8U9muDRMXHSQud5R3x88YagfrCHztMctnoqJnRgaEPUYKB2GrMin

CREATE OR REPLACE FUNCTION public.verify_activity_chain(p_workspace_id uuid)
 RETURNS TABLE(is_valid boolean, checked_rows bigint, first_broken_seq bigint, first_broken_id uuid, failure_reason text)
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public'
AS $function$
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
END $function$
CREATE OR REPLACE FUNCTION public.append_activity(p_workspace_id uuid, p_object_id uuid, p_object_type object_kind, p_actor_id uuid, p_event_type text, p_payload jsonb DEFAULT '{}'::jsonb)
 RETURNS uuid
 LANGUAGE plpgsql
AS $function$
DECLARE
    v_id uuid;
BEGIN
    INSERT INTO activity_records (
        workspace_id, object_id, object_type, actor_id, event_type, payload
    ) VALUES (
        p_workspace_id, p_object_id, p_object_type, p_actor_id, p_event_type, COALESCE(p_payload, '{}'::jsonb)
    ) RETURNING id INTO v_id;

    RETURN v_id;
END $function$
