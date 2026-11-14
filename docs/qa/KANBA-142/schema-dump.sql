--
-- PostgreSQL database dump
--

\restrict N9qHZbywB5Y8Sk1M3whQCatoZrVfBZYX4hE3oLthEZdIo92WOcPADChuKgBV32g

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
-- Name: ai_provider_configs; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.ai_provider_configs (
    id uuid DEFAULT public.uuidv7() NOT NULL,
    workspace_id uuid NOT NULL,
    project_id uuid,
    provider_kind text NOT NULL,
    display_name text NOT NULL,
    base_url text,
    model_allowlist text[] NOT NULL,
    residency_tier text NOT NULL,
    priority smallint DEFAULT 100 NOT NULL,
    settings_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    wrapped_api_key bytea,
    api_key_nonce bytea,
    wrapped_dek bytea,
    dek_kid text,
    is_enabled boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT ai_provider_configs_check CHECK (((wrapped_api_key IS NULL) = (wrapped_dek IS NULL))),
    CONSTRAINT ai_provider_configs_display_name_check CHECK (((char_length(display_name) >= 1) AND (char_length(display_name) <= 80))),
    CONSTRAINT ai_provider_configs_model_allowlist_check CHECK (((cardinality(model_allowlist) >= 1) AND (cardinality(model_allowlist) <= 32))),
    CONSTRAINT ai_provider_configs_provider_kind_check CHECK ((provider_kind = ANY (ARRAY['openai'::text, 'ollama'::text, 'gemini'::text, 'fixture'::text]))),
    CONSTRAINT ai_provider_configs_residency_tier_check CHECK ((residency_tier ~ '^[a-z0-9:._-]{1,64}$'::text))
);

ALTER TABLE ONLY public.ai_provider_configs FORCE ROW LEVEL SECURITY;


ALTER TABLE public.ai_provider_configs OWNER TO kanban_migrator;

--
-- Name: ai_token_ledgers; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.ai_token_ledgers (
    id uuid DEFAULT public.uuidv7() NOT NULL,
    workspace_id uuid NOT NULL,
    project_id uuid,
    provider_config_id uuid NOT NULL,
    period_kind text NOT NULL,
    period_start date NOT NULL,
    token_cap bigint NOT NULL,
    tokens_reserved bigint DEFAULT 0 NOT NULL,
    tokens_used bigint DEFAULT 0 NOT NULL,
    CONSTRAINT ai_token_ledgers_check CHECK (((tokens_used + tokens_reserved) <= token_cap)),
    CONSTRAINT ai_token_ledgers_period_kind_check CHECK ((period_kind = ANY (ARRAY['daily'::text, 'monthly'::text]))),
    CONSTRAINT ai_token_ledgers_token_cap_check CHECK ((token_cap >= 0)),
    CONSTRAINT ai_token_ledgers_tokens_reserved_check CHECK ((tokens_reserved >= 0)),
    CONSTRAINT ai_token_ledgers_tokens_used_check CHECK ((tokens_used >= 0))
);

ALTER TABLE ONLY public.ai_token_ledgers FORCE ROW LEVEL SECURITY;


ALTER TABLE public.ai_token_ledgers OWNER TO kanban_migrator;

--
-- Name: ai_provider_configs ai_provider_configs_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.ai_provider_configs
    ADD CONSTRAINT ai_provider_configs_pkey PRIMARY KEY (id);


--
-- Name: ai_token_ledgers ai_token_ledgers_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.ai_token_ledgers
    ADD CONSTRAINT ai_token_ledgers_pkey PRIMARY KEY (id);


--
-- Name: ai_token_ledgers ai_token_ledgers_workspace_id_project_id_provider_config_id_key; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.ai_token_ledgers
    ADD CONSTRAINT ai_token_ledgers_workspace_id_project_id_provider_config_id_key UNIQUE NULLS NOT DISTINCT (workspace_id, project_id, provider_config_id, period_kind, period_start);


--
-- Name: idx_ai_provider_configs_ws_prio; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX idx_ai_provider_configs_ws_prio ON public.ai_provider_configs USING btree (workspace_id, priority);


--
-- Name: idx_ai_provider_configs_ws_proj; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX idx_ai_provider_configs_ws_proj ON public.ai_provider_configs USING btree (workspace_id, project_id);


--
-- Name: idx_ai_token_ledgers_lookup; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX idx_ai_token_ledgers_lookup ON public.ai_token_ledgers USING btree (workspace_id, provider_config_id, period_kind, period_start);


--
-- Name: ai_provider_configs ai_provider_configs_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.ai_provider_configs
    ADD CONSTRAINT ai_provider_configs_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: ai_provider_configs ai_provider_configs_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.ai_provider_configs
    ADD CONSTRAINT ai_provider_configs_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;


--
-- Name: ai_token_ledgers ai_token_ledgers_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.ai_token_ledgers
    ADD CONSTRAINT ai_token_ledgers_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: ai_token_ledgers ai_token_ledgers_provider_config_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.ai_token_ledgers
    ADD CONSTRAINT ai_token_ledgers_provider_config_id_fkey FOREIGN KEY (provider_config_id) REFERENCES public.ai_provider_configs(id) ON DELETE CASCADE;


--
-- Name: ai_token_ledgers ai_token_ledgers_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.ai_token_ledgers
    ADD CONSTRAINT ai_token_ledgers_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;


--
-- Name: ai_provider_configs; Type: ROW SECURITY; Schema: public; Owner: kanban_migrator
--

ALTER TABLE public.ai_provider_configs ENABLE ROW LEVEL SECURITY;

--
-- Name: ai_provider_configs ai_provider_configs_delete_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY ai_provider_configs_delete_rls ON public.ai_provider_configs FOR DELETE USING (((workspace_id = public.app_current_workspace_id()) AND (((project_id IS NULL) AND (public.app_has_object_capability(workspace_id, 64) OR public.app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text]))) OR ((project_id IS NOT NULL) AND (public.app_has_object_capability(project_id, 64) OR public.app_has_object_capability(workspace_id, 64) OR public.app_principal_has_role(project_id, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text, 'PROJECT_ADMIN'::text]))))));


--
-- Name: ai_provider_configs ai_provider_configs_insert_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY ai_provider_configs_insert_rls ON public.ai_provider_configs FOR INSERT WITH CHECK (((workspace_id = public.app_current_workspace_id()) AND (((project_id IS NULL) AND (public.app_has_object_capability(workspace_id, 64) OR public.app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text]))) OR ((project_id IS NOT NULL) AND (public.app_has_object_capability(project_id, 64) OR public.app_has_object_capability(workspace_id, 64) OR public.app_principal_has_role(project_id, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text, 'PROJECT_ADMIN'::text]))))));


--
-- Name: ai_provider_configs ai_provider_configs_select_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY ai_provider_configs_select_rls ON public.ai_provider_configs FOR SELECT USING (((workspace_id = public.app_current_workspace_id()) AND (((project_id IS NULL) AND (public.app_has_object_capability(workspace_id, 64) OR public.app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text]))) OR ((project_id IS NOT NULL) AND (public.app_has_object_capability(project_id, 64) OR public.app_has_object_capability(workspace_id, 64) OR public.app_principal_has_role(project_id, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text, 'PROJECT_ADMIN'::text]))))));


--
-- Name: ai_provider_configs ai_provider_configs_update_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY ai_provider_configs_update_rls ON public.ai_provider_configs FOR UPDATE USING (((workspace_id = public.app_current_workspace_id()) AND (((project_id IS NULL) AND (public.app_has_object_capability(workspace_id, 64) OR public.app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text]))) OR ((project_id IS NOT NULL) AND (public.app_has_object_capability(project_id, 64) OR public.app_has_object_capability(workspace_id, 64) OR public.app_principal_has_role(project_id, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text, 'PROJECT_ADMIN'::text])))))) WITH CHECK (((workspace_id = public.app_current_workspace_id()) AND (((project_id IS NULL) AND (public.app_has_object_capability(workspace_id, 64) OR public.app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text]))) OR ((project_id IS NOT NULL) AND (public.app_has_object_capability(project_id, 64) OR public.app_has_object_capability(workspace_id, 64) OR public.app_principal_has_role(project_id, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text, 'PROJECT_ADMIN'::text]))))));


--
-- Name: ai_token_ledgers; Type: ROW SECURITY; Schema: public; Owner: kanban_migrator
--

ALTER TABLE public.ai_token_ledgers ENABLE ROW LEVEL SECURITY;

--
-- Name: ai_token_ledgers ai_token_ledgers_delete_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY ai_token_ledgers_delete_rls ON public.ai_token_ledgers FOR DELETE USING (((workspace_id = public.app_current_workspace_id()) AND (((project_id IS NULL) AND (public.app_has_object_capability(workspace_id, 64) OR public.app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text]))) OR ((project_id IS NOT NULL) AND (public.app_has_object_capability(project_id, 64) OR public.app_has_object_capability(workspace_id, 64) OR public.app_principal_has_role(project_id, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text, 'PROJECT_ADMIN'::text]))))));


--
-- Name: ai_token_ledgers ai_token_ledgers_insert_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY ai_token_ledgers_insert_rls ON public.ai_token_ledgers FOR INSERT WITH CHECK (((workspace_id = public.app_current_workspace_id()) AND (((project_id IS NULL) AND (public.app_has_object_capability(workspace_id, 64) OR public.app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text]))) OR ((project_id IS NOT NULL) AND (public.app_has_object_capability(project_id, 64) OR public.app_has_object_capability(workspace_id, 64) OR public.app_principal_has_role(project_id, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text, 'PROJECT_ADMIN'::text]))))));


--
-- Name: ai_token_ledgers ai_token_ledgers_select_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY ai_token_ledgers_select_rls ON public.ai_token_ledgers FOR SELECT USING (((workspace_id = public.app_current_workspace_id()) AND (((project_id IS NULL) AND (public.app_has_object_capability(workspace_id, 64) OR public.app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text]))) OR ((project_id IS NOT NULL) AND (public.app_has_object_capability(project_id, 64) OR public.app_has_object_capability(workspace_id, 64) OR public.app_principal_has_role(project_id, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text, 'PROJECT_ADMIN'::text]))) OR ((public.app_current_principal_id() IS NOT NULL) AND (public.app_current_principal_id() = public.app_agent_runtime_principal())))));


--
-- Name: ai_token_ledgers ai_token_ledgers_update_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY ai_token_ledgers_update_rls ON public.ai_token_ledgers FOR UPDATE USING (((workspace_id = public.app_current_workspace_id()) AND (((project_id IS NULL) AND (public.app_has_object_capability(workspace_id, 64) OR public.app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text]))) OR ((project_id IS NOT NULL) AND (public.app_has_object_capability(project_id, 64) OR public.app_has_object_capability(workspace_id, 64) OR public.app_principal_has_role(project_id, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text, 'PROJECT_ADMIN'::text]))) OR ((public.app_current_principal_id() IS NOT NULL) AND (public.app_current_principal_id() = public.app_agent_runtime_principal()))))) WITH CHECK (((workspace_id = public.app_current_workspace_id()) AND (((project_id IS NULL) AND (public.app_has_object_capability(workspace_id, 64) OR public.app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text]))) OR ((project_id IS NOT NULL) AND (public.app_has_object_capability(project_id, 64) OR public.app_has_object_capability(workspace_id, 64) OR public.app_principal_has_role(project_id, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text, 'PROJECT_ADMIN'::text]))) OR ((public.app_current_principal_id() IS NOT NULL) AND (public.app_current_principal_id() = public.app_agent_runtime_principal())))));


--
-- Name: TABLE ai_provider_configs; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT INSERT,DELETE,UPDATE ON TABLE public.ai_provider_configs TO kanban_app;


--
-- Name: COLUMN ai_provider_configs.id; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT(id) ON TABLE public.ai_provider_configs TO kanban_app;
GRANT SELECT(id) ON TABLE public.ai_provider_configs TO app_rls_reader;


--
-- Name: COLUMN ai_provider_configs.workspace_id; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT(workspace_id) ON TABLE public.ai_provider_configs TO kanban_app;
GRANT SELECT(workspace_id) ON TABLE public.ai_provider_configs TO app_rls_reader;


--
-- Name: COLUMN ai_provider_configs.project_id; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT(project_id) ON TABLE public.ai_provider_configs TO kanban_app;
GRANT SELECT(project_id) ON TABLE public.ai_provider_configs TO app_rls_reader;


--
-- Name: COLUMN ai_provider_configs.provider_kind; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT(provider_kind) ON TABLE public.ai_provider_configs TO kanban_app;
GRANT SELECT(provider_kind) ON TABLE public.ai_provider_configs TO app_rls_reader;


--
-- Name: COLUMN ai_provider_configs.display_name; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT(display_name) ON TABLE public.ai_provider_configs TO kanban_app;
GRANT SELECT(display_name) ON TABLE public.ai_provider_configs TO app_rls_reader;


--
-- Name: COLUMN ai_provider_configs.base_url; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT(base_url) ON TABLE public.ai_provider_configs TO kanban_app;
GRANT SELECT(base_url) ON TABLE public.ai_provider_configs TO app_rls_reader;


--
-- Name: COLUMN ai_provider_configs.model_allowlist; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT(model_allowlist) ON TABLE public.ai_provider_configs TO kanban_app;
GRANT SELECT(model_allowlist) ON TABLE public.ai_provider_configs TO app_rls_reader;


--
-- Name: COLUMN ai_provider_configs.residency_tier; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT(residency_tier) ON TABLE public.ai_provider_configs TO kanban_app;
GRANT SELECT(residency_tier) ON TABLE public.ai_provider_configs TO app_rls_reader;


--
-- Name: COLUMN ai_provider_configs.priority; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT(priority) ON TABLE public.ai_provider_configs TO kanban_app;
GRANT SELECT(priority) ON TABLE public.ai_provider_configs TO app_rls_reader;


--
-- Name: COLUMN ai_provider_configs.settings_json; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT(settings_json) ON TABLE public.ai_provider_configs TO kanban_app;
GRANT SELECT(settings_json) ON TABLE public.ai_provider_configs TO app_rls_reader;


--
-- Name: COLUMN ai_provider_configs.is_enabled; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT(is_enabled) ON TABLE public.ai_provider_configs TO kanban_app;
GRANT SELECT(is_enabled) ON TABLE public.ai_provider_configs TO app_rls_reader;


--
-- Name: COLUMN ai_provider_configs.created_at; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT(created_at) ON TABLE public.ai_provider_configs TO kanban_app;
GRANT SELECT(created_at) ON TABLE public.ai_provider_configs TO app_rls_reader;


--
-- Name: COLUMN ai_provider_configs.updated_at; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT(updated_at) ON TABLE public.ai_provider_configs TO kanban_app;
GRANT SELECT(updated_at) ON TABLE public.ai_provider_configs TO app_rls_reader;


--
-- Name: TABLE ai_token_ledgers; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.ai_token_ledgers TO kanban_app;
GRANT SELECT ON TABLE public.ai_token_ledgers TO app_rls_reader;


--
-- PostgreSQL database dump complete
--

\unrestrict N9qHZbywB5Y8Sk1M3whQCatoZrVfBZYX4hE3oLthEZdIo92WOcPADChuKgBV32g


-- Function ai_provider_secret definition:
                                                                                                                                List of functions
 Schema |        Name        |                                  Result data type                                  | Argument data types | Type | Volatility | Parallel |      Owner      | Security |         Access privileges         | Language | Internal name | Description 
--------+--------------------+------------------------------------------------------------------------------------+---------------------+------+------------+----------+-----------------+----------+-----------------------------------+----------+---------------+-------------
 public | ai_provider_secret | TABLE(wrapped_api_key bytea, api_key_nonce bytea, wrapped_dek bytea, dek_kid text) | p_config_id uuid    | func | stable     | unsafe   | kanban_migrator | definer  | kanban_migrator=X/kanban_migrator+| plpgsql  |               | 
        |                    |                                                                                    |                     |      |            |          |                 |          | "agent-runtime"=X/kanban_migrator |          |               | 
(1 row)

