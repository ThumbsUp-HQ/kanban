--
-- PostgreSQL database dump
--

\restrict nV0VymgXEKSEXcLvteXxuSRoOjtTTAc8MpeDU9EAHWxOTUIr09v1nypDDdBYNyg

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
-- Name: destructive_confirmation_tokens; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.destructive_confirmation_tokens (
    id uuid DEFAULT public.uuidv7() NOT NULL,
    workspace_id uuid NOT NULL,
    token_sha256 bytea NOT NULL,
    caller_principal_id uuid NOT NULL,
    target_object_id uuid NOT NULL,
    target_object_type public.object_kind NOT NULL,
    mode text NOT NULL,
    blast_hash text NOT NULL,
    confirm_phrase text NOT NULL,
    blast_summary_json jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    consumed_at timestamp with time zone,
    CONSTRAINT destructive_confirmation_tokens_blast_hash_check CHECK ((char_length(blast_hash) = 64)),
    CONSTRAINT destructive_confirmation_tokens_check CHECK ((expires_at <= (created_at + '00:05:00'::interval))),
    CONSTRAINT destructive_confirmation_tokens_mode_check CHECK ((mode = ANY (ARRAY['trash'::text, 'permanent_purge'::text, 'restore'::text]))),
    CONSTRAINT destructive_confirmation_tokens_token_sha256_check CHECK ((octet_length(token_sha256) = 32))
);

ALTER TABLE ONLY public.destructive_confirmation_tokens FORCE ROW LEVEL SECURITY;


ALTER TABLE public.destructive_confirmation_tokens OWNER TO kanban_migrator;

--
-- Name: destructive_confirmation_tokens destructive_confirmation_tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.destructive_confirmation_tokens
    ADD CONSTRAINT destructive_confirmation_tokens_pkey PRIMARY KEY (id);


--
-- Name: destructive_confirmation_tokens destructive_confirmation_tokens_token_sha256_key; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.destructive_confirmation_tokens
    ADD CONSTRAINT destructive_confirmation_tokens_token_sha256_key UNIQUE (token_sha256);


--
-- Name: destructive_tokens_lookup_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX destructive_tokens_lookup_idx ON public.destructive_confirmation_tokens USING btree (token_sha256) WHERE (consumed_at IS NULL);


--
-- Name: destructive_tokens_ws_target_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX destructive_tokens_ws_target_idx ON public.destructive_confirmation_tokens USING btree (workspace_id, target_object_id);


--
-- Name: destructive_confirmation_tokens destructive_confirmation_toke_target_object_id_target_obje_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.destructive_confirmation_tokens
    ADD CONSTRAINT destructive_confirmation_toke_target_object_id_target_obje_fkey FOREIGN KEY (target_object_id, target_object_type) REFERENCES public.objects(id, object_type) ON DELETE CASCADE;


--
-- Name: destructive_confirmation_tokens destructive_confirmation_tokens_caller_principal_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.destructive_confirmation_tokens
    ADD CONSTRAINT destructive_confirmation_tokens_caller_principal_id_fkey FOREIGN KEY (caller_principal_id) REFERENCES public.principals(id) ON DELETE CASCADE;


--
-- Name: destructive_confirmation_tokens destructive_confirmation_tokens_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.destructive_confirmation_tokens
    ADD CONSTRAINT destructive_confirmation_tokens_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;


--
-- Name: destructive_confirmation_tokens; Type: ROW SECURITY; Schema: public; Owner: kanban_migrator
--

ALTER TABLE public.destructive_confirmation_tokens ENABLE ROW LEVEL SECURITY;

--
-- Name: destructive_confirmation_tokens destructive_tokens_delete_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY destructive_tokens_delete_rls ON public.destructive_confirmation_tokens FOR DELETE USING ((workspace_id = public.app_current_workspace_id()));


--
-- Name: destructive_confirmation_tokens destructive_tokens_insert_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY destructive_tokens_insert_rls ON public.destructive_confirmation_tokens FOR INSERT WITH CHECK ((workspace_id = public.app_current_workspace_id()));


--
-- Name: destructive_confirmation_tokens destructive_tokens_select_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY destructive_tokens_select_rls ON public.destructive_confirmation_tokens FOR SELECT USING ((workspace_id = public.app_current_workspace_id()));


--
-- Name: destructive_confirmation_tokens destructive_tokens_update_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY destructive_tokens_update_rls ON public.destructive_confirmation_tokens FOR UPDATE USING ((workspace_id = public.app_current_workspace_id())) WITH CHECK ((workspace_id = public.app_current_workspace_id()));


--
-- Name: TABLE destructive_confirmation_tokens; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.destructive_confirmation_tokens TO kanban_app;
GRANT SELECT ON TABLE public.destructive_confirmation_tokens TO app_rls_reader;


--
-- PostgreSQL database dump complete
--

\unrestrict nV0VymgXEKSEXcLvteXxuSRoOjtTTAc8MpeDU9EAHWxOTUIr09v1nypDDdBYNyg

