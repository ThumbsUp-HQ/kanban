--
-- PostgreSQL database dump
--

\restrict NLPwWjYJfrzrLWL3ZSx3Te1fTDEk2WIhPB8pO3r8EYgEBsoQCAIASq3QFKwasyb

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
-- Name: approved_wasm_modules; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.approved_wasm_modules (
    id uuid DEFAULT public.uuidv7() NOT NULL,
    workspace_id uuid NOT NULL,
    project_id uuid,
    sha256 bytea NOT NULL,
    name text NOT NULL,
    wasm_bytes bytea NOT NULL,
    approved_by_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT approved_wasm_modules_name_check CHECK (((char_length(btrim(name)) >= 1) AND (char_length(btrim(name)) <= 120))),
    CONSTRAINT approved_wasm_modules_sha256_check CHECK ((octet_length(sha256) = 32)),
    CONSTRAINT approved_wasm_modules_wasm_bytes_check CHECK (((octet_length(wasm_bytes) >= 8) AND (octet_length(wasm_bytes) <= 1048576)))
);

ALTER TABLE ONLY public.approved_wasm_modules FORCE ROW LEVEL SECURITY;


ALTER TABLE public.approved_wasm_modules OWNER TO kanban_migrator;

--
-- Name: approved_wasm_modules approved_wasm_modules_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.approved_wasm_modules
    ADD CONSTRAINT approved_wasm_modules_pkey PRIMARY KEY (id);


--
-- Name: approved_wasm_modules approved_wasm_modules_workspace_id_sha256_key; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.approved_wasm_modules
    ADD CONSTRAINT approved_wasm_modules_workspace_id_sha256_key UNIQUE (workspace_id, sha256);


--
-- Name: idx_approved_wasm_modules_lookup; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX idx_approved_wasm_modules_lookup ON public.approved_wasm_modules USING btree (workspace_id, sha256);


--
-- Name: idx_approved_wasm_modules_project; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX idx_approved_wasm_modules_project ON public.approved_wasm_modules USING btree (project_id) WHERE (project_id IS NOT NULL);


--
-- Name: approved_wasm_modules approved_wasm_modules_approved_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.approved_wasm_modules
    ADD CONSTRAINT approved_wasm_modules_approved_by_id_fkey FOREIGN KEY (approved_by_id) REFERENCES public.principals(id);


--
-- Name: approved_wasm_modules approved_wasm_modules_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.approved_wasm_modules
    ADD CONSTRAINT approved_wasm_modules_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: approved_wasm_modules approved_wasm_modules_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.approved_wasm_modules
    ADD CONSTRAINT approved_wasm_modules_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;


--
-- Name: approved_wasm_modules; Type: ROW SECURITY; Schema: public; Owner: kanban_migrator
--

ALTER TABLE public.approved_wasm_modules ENABLE ROW LEVEL SECURITY;

--
-- Name: approved_wasm_modules approved_wasm_modules_delete_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY approved_wasm_modules_delete_rls ON public.approved_wasm_modules FOR DELETE USING (((workspace_id = public.app_current_workspace_id()) AND (((project_id IS NULL) AND public.app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text])) OR ((project_id IS NOT NULL) AND public.app_principal_has_role(project_id, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text, 'PROJECT_ADMIN'::text]))) AND (public.app_current_aal_level() >= 2)));


--
-- Name: approved_wasm_modules approved_wasm_modules_insert_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY approved_wasm_modules_insert_rls ON public.approved_wasm_modules FOR INSERT WITH CHECK (((workspace_id = public.app_current_workspace_id()) AND (((project_id IS NULL) AND public.app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text])) OR ((project_id IS NOT NULL) AND public.app_principal_has_role(project_id, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text, 'PROJECT_ADMIN'::text]))) AND (public.app_current_aal_level() >= 2)));


--
-- Name: approved_wasm_modules approved_wasm_modules_select_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY approved_wasm_modules_select_rls ON public.approved_wasm_modules FOR SELECT USING (((workspace_id = public.app_current_workspace_id()) AND (cardinality(public.app_effective_principal_set()) > 0) AND ((project_id IS NULL) OR public.app_has_object_capability(project_id, 1))));


--
-- Name: approved_wasm_modules approved_wasm_modules_update_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY approved_wasm_modules_update_rls ON public.approved_wasm_modules FOR UPDATE USING ((workspace_id = public.app_current_workspace_id())) WITH CHECK (((workspace_id = public.app_current_workspace_id()) AND (((project_id IS NULL) AND public.app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text])) OR ((project_id IS NOT NULL) AND public.app_principal_has_role(project_id, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text, 'PROJECT_ADMIN'::text]))) AND (public.app_current_aal_level() >= 2)));


--
-- Name: TABLE approved_wasm_modules; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.approved_wasm_modules TO kanban_app;
GRANT SELECT ON TABLE public.approved_wasm_modules TO app_rls_reader;


--
-- PostgreSQL database dump complete
--

\unrestrict NLPwWjYJfrzrLWL3ZSx3Te1fTDEk2WIhPB8pO3r8EYgEBsoQCAIASq3QFKwasyb

