--
-- PostgreSQL database dump
--

\restrict D1xNgqOUBgjcvVn9CZkDRSZezdffu6zwMJfU3racDz6mIEwZGeNBln9wVhFj8Lc

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
-- Name: agent_definitions; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.agent_definitions (
    id uuid DEFAULT public.uuidv7() NOT NULL,
    workspace_id uuid NOT NULL,
    project_id uuid,
    principal_id uuid NOT NULL,
    slug text NOT NULL,
    display_name text NOT NULL,
    harness_kind text NOT NULL,
    provider_kind text,
    model_id text,
    cli_binary_allowlist_id text,
    cli_args_json jsonb DEFAULT '[]'::jsonb NOT NULL,
    remote_runner_pool_slug text,
    repo_access_mode text DEFAULT 'none'::text NOT NULL,
    mcp_allowed_tools text[] DEFAULT ARRAY['search_tickets'::text, 'read_ticket'::text, 'search_knowledge'::text, 'read_doc'::text] NOT NULL,
    system_instructions_md text DEFAULT ''::text NOT NULL,
    timeout_ms integer DEFAULT 60000 NOT NULL,
    CONSTRAINT agent_def_args_is_array CHECK ((jsonb_typeof(cli_args_json) = 'array'::text)),
    CONSTRAINT agent_def_harness_fields CHECK ((((harness_kind = 'in_app_sdk'::text) AND (provider_kind IS NOT NULL) AND (model_id IS NOT NULL) AND (cli_binary_allowlist_id IS NULL) AND (remote_runner_pool_slug IS NULL)) OR ((harness_kind = 'cli_pipe'::text) AND (cli_binary_allowlist_id IS NOT NULL) AND (remote_runner_pool_slug IS NULL)) OR ((harness_kind = 'remote_runner'::text) AND (remote_runner_pool_slug IS NOT NULL)))),
    CONSTRAINT agent_def_mcp_tools_subset CHECK ((mcp_allowed_tools <@ ARRAY['search_tickets'::text, 'read_ticket'::text, 'search_knowledge'::text, 'read_doc'::text])),
    CONSTRAINT agent_definitions_cli_binary_allowlist_id_check CHECK ((cli_binary_allowlist_id = ANY (ARRAY['agy'::text, 'codex'::text, 'gemini-cli'::text, 'claude-code'::text]))),
    CONSTRAINT agent_definitions_harness_kind_check CHECK ((harness_kind = ANY (ARRAY['in_app_sdk'::text, 'cli_pipe'::text, 'remote_runner'::text]))),
    CONSTRAINT agent_definitions_provider_kind_check CHECK ((provider_kind = ANY (ARRAY['openai'::text, 'ollama'::text, 'gemini'::text, 'fixture'::text]))),
    CONSTRAINT agent_definitions_repo_access_mode_check CHECK ((repo_access_mode = ANY (ARRAY['none'::text, 'bare_git_tools'::text, 'ro_vfs_mount'::text]))),
    CONSTRAINT agent_definitions_slug_check CHECK ((slug ~ '^[a-z0-9][a-z0-9-]{1,62}$'::text)),
    CONSTRAINT agent_definitions_timeout_ms_check CHECK (((timeout_ms >= 1000) AND (timeout_ms <= 300000)))
);

ALTER TABLE ONLY public.agent_definitions FORCE ROW LEVEL SECURITY;


ALTER TABLE public.agent_definitions OWNER TO kanban_migrator;

--
-- Name: agent_definitions agent_definitions_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.agent_definitions
    ADD CONSTRAINT agent_definitions_pkey PRIMARY KEY (id);


--
-- Name: agent_definitions agent_definitions_workspace_id_slug_key; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.agent_definitions
    ADD CONSTRAINT agent_definitions_workspace_id_slug_key UNIQUE (workspace_id, slug);


--
-- Name: agent_definitions agent_definitions_principal_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.agent_definitions
    ADD CONSTRAINT agent_definitions_principal_id_fkey FOREIGN KEY (principal_id) REFERENCES public.principals(id) ON DELETE RESTRICT;


--
-- Name: agent_definitions agent_definitions_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.agent_definitions
    ADD CONSTRAINT agent_definitions_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: agent_definitions agent_definitions_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.agent_definitions
    ADD CONSTRAINT agent_definitions_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;


--
-- Name: agent_definitions; Type: ROW SECURITY; Schema: public; Owner: kanban_migrator
--

ALTER TABLE public.agent_definitions ENABLE ROW LEVEL SECURITY;

--
-- Name: agent_definitions agent_definitions_delete_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY agent_definitions_delete_rls ON public.agent_definitions FOR DELETE USING (((workspace_id = public.app_current_workspace_id()) AND (((project_id IS NULL) AND public.app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text])) OR ((project_id IS NOT NULL) AND public.app_principal_has_role(project_id, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text, 'PROJECT_ADMIN'::text])))));


--
-- Name: agent_definitions agent_definitions_insert_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY agent_definitions_insert_rls ON public.agent_definitions FOR INSERT WITH CHECK (((workspace_id = public.app_current_workspace_id()) AND (((project_id IS NULL) AND public.app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text])) OR ((project_id IS NOT NULL) AND public.app_principal_has_role(project_id, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text, 'PROJECT_ADMIN'::text])))));


--
-- Name: agent_definitions agent_definitions_select_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY agent_definitions_select_rls ON public.agent_definitions FOR SELECT USING (((workspace_id = public.app_current_workspace_id()) AND (cardinality(public.app_effective_principal_set()) > 0) AND ((project_id IS NULL) OR public.app_has_object_capability(project_id, 1))));


--
-- Name: agent_definitions agent_definitions_update_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY agent_definitions_update_rls ON public.agent_definitions FOR UPDATE USING (((workspace_id = public.app_current_workspace_id()) AND (((project_id IS NULL) AND public.app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text])) OR ((project_id IS NOT NULL) AND public.app_principal_has_role(project_id, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text, 'PROJECT_ADMIN'::text]))))) WITH CHECK (((workspace_id = public.app_current_workspace_id()) AND (((project_id IS NULL) AND public.app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text])) OR ((project_id IS NOT NULL) AND public.app_principal_has_role(project_id, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text, 'PROJECT_ADMIN'::text])))));


--
-- Name: TABLE agent_definitions; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.agent_definitions TO kanban_app;
GRANT SELECT ON TABLE public.agent_definitions TO app_rls_reader;


--
-- PostgreSQL database dump complete
--

\unrestrict D1xNgqOUBgjcvVn9CZkDRSZezdffu6zwMJfU3racDz6mIEwZGeNBln9wVhFj8Lc


-- Verification of relrowsecurity and relforcerowsecurity in pg_class:
      relname      | relrowsecurity | relforcerowsecurity 
-------------------+----------------+---------------------
 agent_definitions | t              | t
(1 row)

