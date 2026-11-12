-- Schema dump for invalid_object_link_audits
--
-- PostgreSQL database dump
--

\restrict LsAEg2xLmCrs8UWryRxUZLOfYUDfIeSV6fCn1Zk7Y3HYSW3h21gbFGMbe4bucRe

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
-- Name: invalid_object_link_audits; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.invalid_object_link_audits (
    id uuid DEFAULT public.uuidv7() NOT NULL,
    workspace_id uuid NOT NULL,
    link_id uuid NOT NULL,
    reason public.invalid_link_reason NOT NULL,
    link_snapshot jsonb NOT NULL,
    source_snapshot jsonb,
    target_snapshot jsonb,
    detected_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    resolved_at timestamp with time zone,
    purged_at timestamp with time zone,
    purged_by_id uuid,
    purge_reason text,
    CONSTRAINT invalid_object_link_audits_link_snapshot_check CHECK ((jsonb_typeof(link_snapshot) = 'object'::text)),
    CONSTRAINT invalid_object_link_audits_purge_reason_check CHECK (((purge_reason IS NULL) OR ((char_length(btrim(purge_reason)) >= 3) AND (char_length(btrim(purge_reason)) <= 1000)))),
    CONSTRAINT invalid_object_link_audits_source_snapshot_check CHECK (((source_snapshot IS NULL) OR (jsonb_typeof(source_snapshot) = 'object'::text))),
    CONSTRAINT invalid_object_link_audits_target_snapshot_check CHECK (((target_snapshot IS NULL) OR (jsonb_typeof(target_snapshot) = 'object'::text)))
);

ALTER TABLE ONLY public.invalid_object_link_audits FORCE ROW LEVEL SECURITY;


ALTER TABLE public.invalid_object_link_audits OWNER TO kanban_migrator;

--
-- Name: invalid_object_link_audits invalid_object_link_audits_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.invalid_object_link_audits
    ADD CONSTRAINT invalid_object_link_audits_pkey PRIMARY KEY (id);


--
-- Name: invalid_link_audits_open_uq; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE UNIQUE INDEX invalid_link_audits_open_uq ON public.invalid_object_link_audits USING btree (link_id, reason) WHERE ((purged_at IS NULL) AND (resolved_at IS NULL));


--
-- Name: invalid_link_audits_ws_open_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX invalid_link_audits_ws_open_idx ON public.invalid_object_link_audits USING btree (workspace_id, detected_at DESC) WHERE ((purged_at IS NULL) AND (resolved_at IS NULL));


--
-- Name: invalid_object_link_audits invalid_link_audits_guard_bud_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER invalid_link_audits_guard_bud_trg BEFORE DELETE OR UPDATE ON public.invalid_object_link_audits FOR EACH ROW EXECUTE FUNCTION public.invalid_link_audits_guard_bud();


--
-- Name: invalid_object_link_audits invalid_object_link_audits_purged_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.invalid_object_link_audits
    ADD CONSTRAINT invalid_object_link_audits_purged_by_id_fkey FOREIGN KEY (purged_by_id) REFERENCES public.principals(id) ON DELETE RESTRICT;


--
-- Name: invalid_object_link_audits invalid_object_link_audits_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.invalid_object_link_audits
    ADD CONSTRAINT invalid_object_link_audits_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE RESTRICT;


--
-- Name: invalid_object_link_audits invalid_link_audits_select_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY invalid_link_audits_select_rls ON public.invalid_object_link_audits FOR SELECT TO kanban_app, app_rls_reader USING (((workspace_id = public.app_current_workspace_id()) AND (public.app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text]) OR (((source_snapshot ->> 'project_id'::text) IS NOT NULL) AND public.app_principal_has_role(((source_snapshot ->> 'project_id'::text))::uuid, ARRAY['PROJECT_ADMIN'::text])) OR (((target_snapshot ->> 'project_id'::text) IS NOT NULL) AND public.app_principal_has_role(((target_snapshot ->> 'project_id'::text))::uuid, ARRAY['PROJECT_ADMIN'::text])))));


--
-- Name: invalid_object_link_audits; Type: ROW SECURITY; Schema: public; Owner: kanban_migrator
--

ALTER TABLE public.invalid_object_link_audits ENABLE ROW LEVEL SECURITY;

--
-- Name: TABLE invalid_object_link_audits; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT ON TABLE public.invalid_object_link_audits TO kanban_app;
GRANT SELECT ON TABLE public.invalid_object_link_audits TO app_rls_reader;


--
-- PostgreSQL database dump complete
--

\unrestrict LsAEg2xLmCrs8UWryRxUZLOfYUDfIeSV6fCn1Zk7Y3HYSW3h21gbFGMbe4bucRe



-- Function definition for audit_object_links
CREATE OR REPLACE FUNCTION public.audit_object_links(p_workspace_id uuid, p_as_of timestamp with time zone DEFAULT clock_timestamp())
 RETURNS TABLE(audit_id uuid, link_id uuid, reason invalid_link_reason)
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public'
AS $function$
#variable_conflict use_column
DECLARE
    v_lid uuid;
BEGIN
    -- Permission check
    IF pg_trigger_depth() = 0 THEN
        IF session_user IN ('kanban_app', 'app_rls_reader') OR current_user IN ('kanban_app', 'app_rls_reader') THEN
            IF app_current_workspace_id() IS DISTINCT FROM p_workspace_id
               OR NOT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN']) THEN
                RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'AUDIT_LINKS_FORBIDDEN';
            END IF;
        END IF;
    END IF;

    FOR v_lid IN
        SELECT id FROM object_links WHERE workspace_id = p_workspace_id AND link_state <> 'PURGED'
    LOOP
        RETURN QUERY
        SELECT * FROM audit_single_object_link(v_lid, p_as_of);
    END LOOP;

    RETURN;
END;
$function$
