--
-- PostgreSQL database dump
--

\restrict xlBqX6ixeMEuqn9aT3Fe4C5jo3ZsN2MXwOboYwfLm4XHtJgKkSyQ0DEXJQkB3IY

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
-- Name: outbox_events; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.outbox_events (
    id uuid DEFAULT public.uuidv7() NOT NULL,
    seq bigint NOT NULL,
    workspace_id uuid NOT NULL,
    project_id uuid,
    object_id uuid,
    topic text NOT NULL,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    next_attempt_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    published_at timestamp with time zone,
    dead_lettered_at timestamp with time zone,
    attempts integer DEFAULT 0 NOT NULL,
    last_error text,
    CONSTRAINT outbox_events_attempts_check CHECK ((attempts >= 0)),
    CONSTRAINT outbox_events_last_error_check CHECK (((last_error IS NULL) OR (char_length(last_error) <= 1024))),
    CONSTRAINT outbox_events_payload_check CHECK (((jsonb_typeof(payload) = 'object'::text) AND (octet_length((payload)::text) <= 7168))),
    CONSTRAINT outbox_events_topic_check CHECK (((topic ~ '^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$'::text) AND (char_length(topic) <= 128)))
);

ALTER TABLE ONLY public.outbox_events FORCE ROW LEVEL SECURITY;


ALTER TABLE public.outbox_events OWNER TO kanban_migrator;

--
-- Name: outbox_events_seq_seq; Type: SEQUENCE; Schema: public; Owner: kanban_migrator
--

ALTER TABLE public.outbox_events ALTER COLUMN seq ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.outbox_events_seq_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: outbox_events outbox_events_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.outbox_events
    ADD CONSTRAINT outbox_events_pkey PRIMARY KEY (id);


--
-- Name: outbox_events outbox_events_seq_key; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.outbox_events
    ADD CONSTRAINT outbox_events_seq_key UNIQUE (seq);


--
-- Name: outbox_events_pending_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX outbox_events_pending_idx ON public.outbox_events USING btree (next_attempt_at, seq) WHERE ((published_at IS NULL) AND (dead_lettered_at IS NULL));


--
-- Name: outbox_events outbox_events_wakeup_ai; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER outbox_events_wakeup_ai AFTER INSERT ON public.outbox_events FOR EACH STATEMENT EXECUTE FUNCTION public.outbox_events_wakeup_fn();


--
-- Name: outbox_events outbox_events_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.outbox_events
    ADD CONSTRAINT outbox_events_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE SET NULL;


--
-- Name: outbox_events outbox_events_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.outbox_events
    ADD CONSTRAINT outbox_events_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE RESTRICT;


--
-- Name: outbox_events; Type: ROW SECURITY; Schema: public; Owner: kanban_migrator
--

ALTER TABLE public.outbox_events ENABLE ROW LEVEL SECURITY;

--
-- Name: outbox_events outbox_events_insert_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY outbox_events_insert_rls ON public.outbox_events FOR INSERT WITH CHECK (((workspace_id = public.app_current_workspace_id()) AND (public.app_current_principal_id() IS NOT NULL)));


--
-- Name: outbox_events outbox_events_select_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY outbox_events_select_rls ON public.outbox_events FOR SELECT USING (((workspace_id = public.app_current_workspace_id()) AND public.app_principal_has_role(project_id, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text, 'PROJECT_ADMIN'::text])));


--
-- Name: TABLE outbox_events; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.outbox_events TO kanban_app;
GRANT SELECT ON TABLE public.outbox_events TO app_rls_reader;


--
-- PostgreSQL database dump complete
--

\unrestrict xlBqX6ixeMEuqn9aT3Fe4C5jo3ZsN2MXwOboYwfLm4XHtJgKkSyQ0DEXJQkB3IY


-- Function: claim_outbox_batch
CREATE OR REPLACE FUNCTION public.claim_outbox_batch(p_batch_size integer DEFAULT 100, p_now timestamp with time zone DEFAULT clock_timestamp())
 RETURNS SETOF outbox_events
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public'
AS $function$
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
$function$

-- Function: outbox_events_wakeup_fn
CREATE OR REPLACE FUNCTION public.outbox_events_wakeup_fn()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public'
AS $function$
BEGIN
    PERFORM pg_notify('outbox_wakeup', '');
    RETURN NULL;
END;
$function$
