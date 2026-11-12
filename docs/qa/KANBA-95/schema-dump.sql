--
-- PostgreSQL database dump
--

\restrict 1qi0GAmEORqz696OuAMrtkXyjHZdPPTNrwrQAj1PJqwe9BgSu6h4Pow57uceef2

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
-- Name: mcp_api_keys; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.mcp_api_keys (
    id uuid DEFAULT public.uuidv7() NOT NULL,
    workspace_id uuid NOT NULL,
    principal_id uuid NOT NULL,
    surface text NOT NULL,
    key_prefix text NOT NULL,
    key_sha256 bytea NOT NULL,
    display_hint text NOT NULL,
    scopes text[] NOT NULL,
    created_by_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    revoked_at timestamp with time zone,
    last_used_at timestamp with time zone,
    CONSTRAINT mcp_api_keys_check CHECK ((expires_at <= (created_at + '365 days'::interval))),
    CONSTRAINT mcp_api_keys_check1 CHECK (((((surface = 'agent'::text) AND (key_prefix = 'kb_agt_'::text)) OR ((surface = 'docs'::text) AND (key_prefix = 'kb_doc_'::text))) OR ((surface = 'admin'::text) AND (key_prefix = 'kb_adm_'::text)))),
    CONSTRAINT mcp_api_keys_display_hint_check CHECK ((char_length(display_hint) = 4)),
    CONSTRAINT mcp_api_keys_key_prefix_check CHECK ((key_prefix = ANY (ARRAY['kb_agt_'::text, 'kb_doc_'::text, 'kb_adm_'::text]))),
    CONSTRAINT mcp_api_keys_key_sha256_check CHECK ((octet_length(key_sha256) = 32)),
    CONSTRAINT mcp_api_keys_surface_check CHECK ((surface = ANY (ARRAY['agent'::text, 'docs'::text, 'admin'::text])))
);

ALTER TABLE ONLY public.mcp_api_keys FORCE ROW LEVEL SECURITY;


ALTER TABLE public.mcp_api_keys OWNER TO kanban_migrator;

--
-- Name: mcp_api_keys mcp_api_keys_key_sha256_key; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.mcp_api_keys
    ADD CONSTRAINT mcp_api_keys_key_sha256_key UNIQUE (key_sha256);


--
-- Name: mcp_api_keys mcp_api_keys_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.mcp_api_keys
    ADD CONSTRAINT mcp_api_keys_pkey PRIMARY KEY (id);


--
-- Name: mcp_api_keys_key_sha256_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX mcp_api_keys_key_sha256_idx ON public.mcp_api_keys USING btree (key_sha256);


--
-- Name: mcp_api_keys_principal_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX mcp_api_keys_principal_idx ON public.mcp_api_keys USING btree (principal_id);


--
-- Name: mcp_api_keys_workspace_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX mcp_api_keys_workspace_idx ON public.mcp_api_keys USING btree (workspace_id);


--
-- Name: mcp_api_keys mcp_api_keys_created_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.mcp_api_keys
    ADD CONSTRAINT mcp_api_keys_created_by_id_fkey FOREIGN KEY (created_by_id) REFERENCES public.principals(id);


--
-- Name: mcp_api_keys mcp_api_keys_principal_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.mcp_api_keys
    ADD CONSTRAINT mcp_api_keys_principal_id_fkey FOREIGN KEY (principal_id) REFERENCES public.principals(id) ON DELETE RESTRICT;


--
-- Name: mcp_api_keys mcp_api_keys_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.mcp_api_keys
    ADD CONSTRAINT mcp_api_keys_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;


--
-- Name: mcp_api_keys; Type: ROW SECURITY; Schema: public; Owner: kanban_migrator
--

ALTER TABLE public.mcp_api_keys ENABLE ROW LEVEL SECURITY;

--
-- Name: mcp_api_keys mcp_api_keys_delete_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY mcp_api_keys_delete_rls ON public.mcp_api_keys FOR DELETE USING ((workspace_id = public.app_current_workspace_id()));


--
-- Name: mcp_api_keys mcp_api_keys_insert_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY mcp_api_keys_insert_rls ON public.mcp_api_keys FOR INSERT WITH CHECK ((workspace_id = public.app_current_workspace_id()));


--
-- Name: mcp_api_keys mcp_api_keys_select_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY mcp_api_keys_select_rls ON public.mcp_api_keys FOR SELECT USING (((public.app_current_workspace_id() IS NULL) OR (workspace_id = public.app_current_workspace_id())));


--
-- Name: mcp_api_keys mcp_api_keys_update_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY mcp_api_keys_update_rls ON public.mcp_api_keys FOR UPDATE USING (((public.app_current_workspace_id() IS NULL) OR (workspace_id = public.app_current_workspace_id()))) WITH CHECK (((public.app_current_workspace_id() IS NULL) OR (workspace_id = public.app_current_workspace_id())));


--
-- Name: TABLE mcp_api_keys; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.mcp_api_keys TO kanban_app;
GRANT SELECT ON TABLE public.mcp_api_keys TO app_rls_reader;


--
-- PostgreSQL database dump complete
--

\unrestrict 1qi0GAmEORqz696OuAMrtkXyjHZdPPTNrwrQAj1PJqwe9BgSu6h4Pow57uceef2

