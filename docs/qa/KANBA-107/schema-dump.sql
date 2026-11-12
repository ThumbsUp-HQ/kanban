-- Schema dump for custom_field_definitions and custom_field_values (KB-P5-11 / KANBA-107)

--
-- PostgreSQL database dump
--

\restrict kIe9PTl6aNpFfoiS5e51teDnSFVKCTKTXSSY2Z0gxJM6s5mzi40sjffxC54wco0

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
-- Name: custom_field_definitions; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.custom_field_definitions (
    id uuid DEFAULT public.uuidv7() NOT NULL,
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    slug text NOT NULL,
    name text NOT NULL,
    tier text DEFAULT 'wasm'::text NOT NULL,
    output_format text NOT NULL,
    output_format_metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    script_source text NOT NULL,
    wasm_module_sha256 bytea,
    script_version integer DEFAULT 1 NOT NULL,
    target_scope text DEFAULT 'PROJECT'::text NOT NULL,
    credential_mode text DEFAULT 'INVOKING_USER'::text NOT NULL,
    egress_allowlist text[] DEFAULT '{}'::text[] NOT NULL,
    manifest_sha256 bytea NOT NULL,
    is_enabled boolean DEFAULT true NOT NULL,
    created_by_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT custom_field_definitions_credential_mode_check CHECK ((credential_mode = ANY (ARRAY['INVOKING_USER'::text, 'PROJECT_ADMIN_SP'::text, 'SERVER_ADMIN_SP'::text]))),
    CONSTRAINT custom_field_definitions_egress_allowlist_check CHECK ((cardinality(egress_allowlist) <= 16)),
    CONSTRAINT custom_field_definitions_manifest_sha256_check CHECK ((octet_length(manifest_sha256) = 32)),
    CONSTRAINT custom_field_definitions_name_check CHECK (((char_length(btrim(name)) >= 1) AND (char_length(btrim(name)) <= 80))),
    CONSTRAINT custom_field_definitions_output_format_check CHECK ((output_format = ANY (ARRAY['text'::text, 'number'::text, 'badge'::text, 'markdown_snippet'::text, 'url'::text, 'json_table'::text, 'severity_pill'::text]))),
    CONSTRAINT custom_field_definitions_output_format_metadata_check CHECK (((jsonb_typeof(output_format_metadata) = 'object'::text) AND (octet_length((output_format_metadata)::text) <= 16384))),
    CONSTRAINT custom_field_definitions_script_source_check CHECK (((octet_length(script_source) >= 1) AND (octet_length(script_source) <= 131072))),
    CONSTRAINT custom_field_definitions_script_version_check CHECK ((script_version >= 1)),
    CONSTRAINT custom_field_definitions_slug_check CHECK ((slug ~ '^[a-z0-9][a-z0-9-]{1,62}$'::text)),
    CONSTRAINT custom_field_definitions_target_scope_check CHECK ((target_scope = ANY (ARRAY['PROJECT'::text, 'WORKSPACE'::text, 'SERVER'::text]))),
    CONSTRAINT custom_field_definitions_tier_check CHECK ((tier = ANY (ARRAY['wasm'::text, 'nsjail'::text]))),
    CONSTRAINT custom_field_definitions_wasm_module_sha256_check CHECK (((wasm_module_sha256 IS NULL) OR (octet_length(wasm_module_sha256) = 32)))
);

ALTER TABLE ONLY public.custom_field_definitions FORCE ROW LEVEL SECURITY;


ALTER TABLE public.custom_field_definitions OWNER TO kanban_migrator;

--
-- Name: custom_field_values; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.custom_field_values (
    id uuid DEFAULT public.uuidv7() NOT NULL,
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    issue_id uuid NOT NULL,
    field_id uuid NOT NULL,
    script_version integer NOT NULL,
    user_access_hash bytea NOT NULL,
    value_json jsonb NOT NULL,
    last_latency_ms integer NOT NULL,
    computed_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    CONSTRAINT custom_field_values_last_latency_ms_check CHECK ((last_latency_ms >= 0)),
    CONSTRAINT custom_field_values_user_access_hash_check CHECK ((octet_length(user_access_hash) = ANY (ARRAY[0, 32]))),
    CONSTRAINT custom_field_values_value_json_check CHECK ((octet_length((value_json)::text) <= 65536))
);

ALTER TABLE ONLY public.custom_field_values FORCE ROW LEVEL SECURITY;


ALTER TABLE public.custom_field_values OWNER TO kanban_migrator;

--
-- Name: custom_field_definitions custom_field_definitions_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.custom_field_definitions
    ADD CONSTRAINT custom_field_definitions_pkey PRIMARY KEY (id);


--
-- Name: custom_field_definitions custom_field_definitions_project_id_slug_key; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.custom_field_definitions
    ADD CONSTRAINT custom_field_definitions_project_id_slug_key UNIQUE (project_id, slug);


--
-- Name: custom_field_values custom_field_values_issue_id_field_id_script_version_user_a_key; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.custom_field_values
    ADD CONSTRAINT custom_field_values_issue_id_field_id_script_version_user_a_key UNIQUE (issue_id, field_id, script_version, user_access_hash);


--
-- Name: custom_field_values custom_field_values_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.custom_field_values
    ADD CONSTRAINT custom_field_values_pkey PRIMARY KEY (id);


--
-- Name: idx_custom_field_definitions_project; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX idx_custom_field_definitions_project ON public.custom_field_definitions USING btree (project_id);


--
-- Name: idx_custom_field_values_lookup; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX idx_custom_field_values_lookup ON public.custom_field_values USING btree (issue_id, field_id);


--
-- Name: custom_field_definitions custom_field_definitions_created_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.custom_field_definitions
    ADD CONSTRAINT custom_field_definitions_created_by_id_fkey FOREIGN KEY (created_by_id) REFERENCES public.principals(id);


--
-- Name: custom_field_definitions custom_field_definitions_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.custom_field_definitions
    ADD CONSTRAINT custom_field_definitions_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: custom_field_definitions custom_field_definitions_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.custom_field_definitions
    ADD CONSTRAINT custom_field_definitions_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;


--
-- Name: custom_field_values custom_field_values_field_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.custom_field_values
    ADD CONSTRAINT custom_field_values_field_id_fkey FOREIGN KEY (field_id) REFERENCES public.custom_field_definitions(id) ON DELETE CASCADE;


--
-- Name: custom_field_values custom_field_values_issue_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.custom_field_values
    ADD CONSTRAINT custom_field_values_issue_id_fkey FOREIGN KEY (issue_id) REFERENCES public.issues(id) ON DELETE CASCADE;


--
-- Name: custom_field_values custom_field_values_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.custom_field_values
    ADD CONSTRAINT custom_field_values_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: custom_field_values custom_field_values_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.custom_field_values
    ADD CONSTRAINT custom_field_values_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;


--
-- Name: custom_field_definitions; Type: ROW SECURITY; Schema: public; Owner: kanban_migrator
--

ALTER TABLE public.custom_field_definitions ENABLE ROW LEVEL SECURITY;

--
-- Name: custom_field_definitions custom_field_definitions_delete_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY custom_field_definitions_delete_rls ON public.custom_field_definitions FOR DELETE USING (((workspace_id = public.app_current_workspace_id()) AND public.app_principal_has_role(project_id, ARRAY['PROJECT_ADMIN'::text, 'SERVER_ADMIN'::text]) AND (public.app_current_aal_level() >= 2)));


--
-- Name: custom_field_definitions custom_field_definitions_insert_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY custom_field_definitions_insert_rls ON public.custom_field_definitions FOR INSERT WITH CHECK (((workspace_id = public.app_current_workspace_id()) AND public.app_principal_has_role(project_id, ARRAY['PROJECT_ADMIN'::text, 'SERVER_ADMIN'::text]) AND (public.app_current_aal_level() >= 2)));


--
-- Name: custom_field_definitions custom_field_definitions_select_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY custom_field_definitions_select_rls ON public.custom_field_definitions FOR SELECT USING (((workspace_id = public.app_current_workspace_id()) AND public.app_has_object_capability(project_id, 1)));


--
-- Name: custom_field_definitions custom_field_definitions_update_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY custom_field_definitions_update_rls ON public.custom_field_definitions FOR UPDATE USING ((workspace_id = public.app_current_workspace_id())) WITH CHECK (((workspace_id = public.app_current_workspace_id()) AND public.app_principal_has_role(project_id, ARRAY['PROJECT_ADMIN'::text, 'SERVER_ADMIN'::text]) AND (public.app_current_aal_level() >= 2)));


--
-- Name: custom_field_values; Type: ROW SECURITY; Schema: public; Owner: kanban_migrator
--

ALTER TABLE public.custom_field_values ENABLE ROW LEVEL SECURITY;

--
-- Name: custom_field_values custom_field_values_delete_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY custom_field_values_delete_rls ON public.custom_field_values FOR DELETE USING (((workspace_id = public.app_current_workspace_id()) AND public.app_has_object_capability(issue_id, 1) AND (user_access_hash = public.app_caller_access_hash())));


--
-- Name: custom_field_values custom_field_values_insert_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY custom_field_values_insert_rls ON public.custom_field_values FOR INSERT WITH CHECK (((workspace_id = public.app_current_workspace_id()) AND public.app_has_object_capability(issue_id, 1) AND (user_access_hash = public.app_caller_access_hash())));


--
-- Name: custom_field_values custom_field_values_select_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY custom_field_values_select_rls ON public.custom_field_values FOR SELECT USING (((workspace_id = public.app_current_workspace_id()) AND public.app_has_object_capability(issue_id, 1) AND ((user_access_hash = '\x'::bytea) OR (user_access_hash = public.app_caller_access_hash()))));


--
-- Name: custom_field_values custom_field_values_update_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY custom_field_values_update_rls ON public.custom_field_values FOR UPDATE USING (((workspace_id = public.app_current_workspace_id()) AND public.app_has_object_capability(issue_id, 1) AND (user_access_hash = public.app_caller_access_hash()))) WITH CHECK (((workspace_id = public.app_current_workspace_id()) AND public.app_has_object_capability(issue_id, 1) AND (user_access_hash = public.app_caller_access_hash())));


--
-- Name: TABLE custom_field_definitions; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.custom_field_definitions TO kanban_app;
GRANT SELECT ON TABLE public.custom_field_definitions TO app_rls_reader;


--
-- Name: TABLE custom_field_values; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.custom_field_values TO kanban_app;
GRANT SELECT ON TABLE public.custom_field_values TO app_rls_reader;


--
-- PostgreSQL database dump complete
--

\unrestrict kIe9PTl6aNpFfoiS5e51teDnSFVKCTKTXSSY2Z0gxJM6s5mzi40sjffxC54wco0



-- Row-level security settings
         relname          | relrowsecurity | relforcerowsecurity 
--------------------------+----------------+---------------------
 custom_field_definitions | t              | t
 custom_field_values      | t              | t
(2 rows)

 schemaname |        tablename         |             policyname              | permissive |  roles   |  cmd   |                                                                                       qual                                                                                       |                                                                                 with_check                                                                                  
------------+--------------------------+-------------------------------------+------------+----------+--------+----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------
 public     | custom_field_definitions | custom_field_definitions_delete_rls | PERMISSIVE | {public} | DELETE | ((workspace_id = app_current_workspace_id()) AND app_principal_has_role(project_id, ARRAY['PROJECT_ADMIN'::text, 'SERVER_ADMIN'::text]) AND (app_current_aal_level() >= 2))      | 
 public     | custom_field_definitions | custom_field_definitions_insert_rls | PERMISSIVE | {public} | INSERT |                                                                                                                                                                                  | ((workspace_id = app_current_workspace_id()) AND app_principal_has_role(project_id, ARRAY['PROJECT_ADMIN'::text, 'SERVER_ADMIN'::text]) AND (app_current_aal_level() >= 2))
 public     | custom_field_definitions | custom_field_definitions_select_rls | PERMISSIVE | {public} | SELECT | ((workspace_id = app_current_workspace_id()) AND app_has_object_capability(project_id, 1))                                                                                       | 
 public     | custom_field_definitions | custom_field_definitions_update_rls | PERMISSIVE | {public} | UPDATE | (workspace_id = app_current_workspace_id())                                                                                                                                      | ((workspace_id = app_current_workspace_id()) AND app_principal_has_role(project_id, ARRAY['PROJECT_ADMIN'::text, 'SERVER_ADMIN'::text]) AND (app_current_aal_level() >= 2))
 public     | custom_field_values      | custom_field_values_delete_rls      | PERMISSIVE | {public} | DELETE | ((workspace_id = app_current_workspace_id()) AND app_has_object_capability(issue_id, 1) AND (user_access_hash = app_caller_access_hash()))                                       | 
 public     | custom_field_values      | custom_field_values_insert_rls      | PERMISSIVE | {public} | INSERT |                                                                                                                                                                                  | ((workspace_id = app_current_workspace_id()) AND app_has_object_capability(issue_id, 1) AND (user_access_hash = app_caller_access_hash()))
 public     | custom_field_values      | custom_field_values_select_rls      | PERMISSIVE | {public} | SELECT | ((workspace_id = app_current_workspace_id()) AND app_has_object_capability(issue_id, 1) AND ((user_access_hash = '\x'::bytea) OR (user_access_hash = app_caller_access_hash()))) | 
 public     | custom_field_values      | custom_field_values_update_rls      | PERMISSIVE | {public} | UPDATE | ((workspace_id = app_current_workspace_id()) AND app_has_object_capability(issue_id, 1) AND (user_access_hash = app_caller_access_hash()))                                       | ((workspace_id = app_current_workspace_id()) AND app_has_object_capability(issue_id, 1) AND (user_access_hash = app_caller_access_hash()))
(8 rows)

