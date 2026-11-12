-- Schema dump for custom_field_approvals (KB-P5-12 / KANBA-114)

--
-- PostgreSQL database dump
--

\restrict 9HZyIfXvbadtK4lwfyF4W9LhSbDu0vtj5G9bqR5NsmLxiCEP3mXdbLUtMepYkDq

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
-- Name: custom_field_approvals; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.custom_field_approvals (
    id uuid DEFAULT public.uuidv7() NOT NULL,
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    field_id uuid NOT NULL,
    manifest_sha256 bytea NOT NULL,
    target_scope text NOT NULL,
    credential_mode text NOT NULL,
    required_tier text NOT NULL,
    status text NOT NULL,
    requested_by_id uuid NOT NULL,
    justification text NOT NULL,
    primary_approver_id uuid,
    primary_approver_aal smallint,
    primary_approved_at timestamp with time zone,
    secondary_approver_id uuid,
    secondary_approver_aal smallint,
    secondary_approved_at timestamp with time zone,
    sp_warning_acknowledged boolean DEFAULT false NOT NULL,
    approval_signature_hmac bytea,
    revoked_at timestamp with time zone,
    revoked_reason text,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT custom_field_approvals_approval_signature_hmac_check CHECK (((approval_signature_hmac IS NULL) OR (octet_length(approval_signature_hmac) = 32))),
    CONSTRAINT custom_field_approvals_credential_mode_check CHECK ((credential_mode = ANY (ARRAY['INVOKING_USER'::text, 'PROJECT_ADMIN_SP'::text, 'SERVER_ADMIN_SP'::text]))),
    CONSTRAINT custom_field_approvals_dual_approver_distinct_check CHECK (((secondary_approver_id IS NULL) OR (secondary_approver_id <> primary_approver_id))),
    CONSTRAINT custom_field_approvals_justification_check CHECK (((char_length(btrim(justification)) >= 10) AND (char_length(btrim(justification)) <= 2000))),
    CONSTRAINT custom_field_approvals_manifest_sha256_check CHECK ((octet_length(manifest_sha256) = 32)),
    CONSTRAINT custom_field_approvals_primary_approver_aal_check CHECK (((primary_approver_aal IS NULL) OR (primary_approver_aal >= 2))),
    CONSTRAINT custom_field_approvals_required_tier_check CHECK ((required_tier = ANY (ARRAY['PROJECT_ADMIN'::text, 'WORKSPACE_ADMIN'::text, 'SERVER_ADMIN_DUAL'::text]))),
    CONSTRAINT custom_field_approvals_scope_principal_combo_check CHECK ((((target_scope = 'PROJECT'::text) AND (credential_mode = ANY (ARRAY['INVOKING_USER'::text, 'PROJECT_ADMIN_SP'::text]))) OR ((target_scope = 'WORKSPACE'::text) AND (credential_mode = ANY (ARRAY['INVOKING_USER'::text, 'PROJECT_ADMIN_SP'::text]))) OR ((target_scope = 'SERVER'::text) AND (credential_mode = ANY (ARRAY['INVOKING_USER'::text, 'SERVER_ADMIN_SP'::text]))))),
    CONSTRAINT custom_field_approvals_secondary_approver_aal_check CHECK (((secondary_approver_aal IS NULL) OR (secondary_approver_aal >= 2))),
    CONSTRAINT custom_field_approvals_status_check CHECK ((status = ANY (ARRAY['PENDING'::text, 'PENDING_SECOND_APPROVER'::text, 'APPROVED'::text, 'REVOKED'::text]))),
    CONSTRAINT custom_field_approvals_target_scope_check CHECK ((target_scope = ANY (ARRAY['PROJECT'::text, 'WORKSPACE'::text, 'SERVER'::text])))
);

ALTER TABLE ONLY public.custom_field_approvals FORCE ROW LEVEL SECURITY;


ALTER TABLE public.custom_field_approvals OWNER TO kanban_migrator;

--
-- Name: custom_field_approvals custom_field_approvals_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.custom_field_approvals
    ADD CONSTRAINT custom_field_approvals_pkey PRIMARY KEY (id);


--
-- Name: idx_cfa_field_status; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX idx_cfa_field_status ON public.custom_field_approvals USING btree (field_id, status);


--
-- Name: idx_cfa_project_status; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX idx_cfa_project_status ON public.custom_field_approvals USING btree (project_id, status);


--
-- Name: idx_cfa_workspace_status; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX idx_cfa_workspace_status ON public.custom_field_approvals USING btree (workspace_id, status);


--
-- Name: custom_field_approvals custom_field_approvals_field_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.custom_field_approvals
    ADD CONSTRAINT custom_field_approvals_field_id_fkey FOREIGN KEY (field_id) REFERENCES public.custom_field_definitions(id) ON DELETE CASCADE;


--
-- Name: custom_field_approvals custom_field_approvals_primary_approver_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.custom_field_approvals
    ADD CONSTRAINT custom_field_approvals_primary_approver_id_fkey FOREIGN KEY (primary_approver_id) REFERENCES public.principals(id);


--
-- Name: custom_field_approvals custom_field_approvals_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.custom_field_approvals
    ADD CONSTRAINT custom_field_approvals_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: custom_field_approvals custom_field_approvals_requested_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.custom_field_approvals
    ADD CONSTRAINT custom_field_approvals_requested_by_id_fkey FOREIGN KEY (requested_by_id) REFERENCES public.principals(id);


--
-- Name: custom_field_approvals custom_field_approvals_secondary_approver_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.custom_field_approvals
    ADD CONSTRAINT custom_field_approvals_secondary_approver_id_fkey FOREIGN KEY (secondary_approver_id) REFERENCES public.principals(id);


--
-- Name: custom_field_approvals custom_field_approvals_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.custom_field_approvals
    ADD CONSTRAINT custom_field_approvals_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;


--
-- Name: custom_field_approvals; Type: ROW SECURITY; Schema: public; Owner: kanban_migrator
--

ALTER TABLE public.custom_field_approvals ENABLE ROW LEVEL SECURITY;

--
-- Name: custom_field_approvals custom_field_approvals_delete_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY custom_field_approvals_delete_rls ON public.custom_field_approvals FOR DELETE USING (((workspace_id = public.app_current_workspace_id()) AND public.app_principal_has_role(project_id, ARRAY['PROJECT_ADMIN'::text, 'SERVER_ADMIN'::text]) AND (public.app_current_aal_level() >= 2)));


--
-- Name: custom_field_approvals custom_field_approvals_insert_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY custom_field_approvals_insert_rls ON public.custom_field_approvals FOR INSERT WITH CHECK (((workspace_id = public.app_current_workspace_id()) AND (public.app_current_aal_level() >= 2)));


--
-- Name: custom_field_approvals custom_field_approvals_select_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY custom_field_approvals_select_rls ON public.custom_field_approvals FOR SELECT USING (((workspace_id = public.app_current_workspace_id()) AND (public.app_principal_has_role(project_id, ARRAY['PROJECT_ADMIN'::text, 'SERVER_ADMIN'::text]) OR (EXISTS ( SELECT 1
   FROM public.role_bindings rb
  WHERE ((rb.principal_id = ANY (public.app_effective_principal_set())) AND (rb.workspace_id = custom_field_approvals.workspace_id) AND ((rb.role)::text = ANY (ARRAY['WORKSPACE_ADMIN'::text, 'SERVER_ADMIN'::text]))))))));


--
-- Name: custom_field_approvals custom_field_approvals_update_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY custom_field_approvals_update_rls ON public.custom_field_approvals FOR UPDATE USING ((workspace_id = public.app_current_workspace_id())) WITH CHECK (((workspace_id = public.app_current_workspace_id()) AND (public.app_current_aal_level() >= 2)));


--
-- Name: TABLE custom_field_approvals; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.custom_field_approvals TO kanban_app;
GRANT SELECT ON TABLE public.custom_field_approvals TO app_rls_reader;


--
-- PostgreSQL database dump complete
--

\unrestrict 9HZyIfXvbadtK4lwfyF4W9LhSbDu0vtj5G9bqR5NsmLxiCEP3mXdbLUtMepYkDq


-- Trigger definition on custom_field_definitions:
                                                                                  trigger_definition                                                                                   
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
 CREATE TRIGGER custom_field_manifest_tamper_revoke AFTER UPDATE OF manifest_sha256 ON custom_field_definitions FOR EACH ROW EXECUTE FUNCTION custom_field_manifest_tamper_revoke_tf()
(1 row)


-- RLS catalog status from pg_class:
        relname         | relrowsecurity | relforcerowsecurity 
------------------------+----------------+---------------------
 custom_field_approvals | t              | t
(1 row)

