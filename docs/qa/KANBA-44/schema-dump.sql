-- === PG_DUMP ROLE_BINDINGS, RESOURCE_ACL_ENTRIES, EFFECTIVE_RESOURCE_ACCESS ===
--
-- PostgreSQL database dump
--

\restrict xjhstQxBgcPy4fPG0KCdscIUYgoew4AzcAMUh3d2RMTBuRohVLiw9jhkiLVhidy

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
-- Name: effective_resource_access; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.effective_resource_access (
    object_id uuid NOT NULL,
    principal_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    allow_mask integer NOT NULL,
    deny_mask integer NOT NULL,
    effective_mask integer GENERATED ALWAYS AS ((allow_mask & (~ deny_mask))) STORED,
    CONSTRAINT effective_resource_access_allow_mask_check CHECK (((allow_mask >= 0) AND (allow_mask <= 255))),
    CONSTRAINT effective_resource_access_deny_mask_check CHECK (((deny_mask >= 0) AND (deny_mask <= 255)))
);


ALTER TABLE public.effective_resource_access OWNER TO kanban_migrator;

--
-- Name: resource_acl_entries; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.resource_acl_entries (
    id uuid DEFAULT public.uuidv7() NOT NULL,
    workspace_id uuid NOT NULL,
    object_id uuid NOT NULL,
    principal_id uuid NOT NULL,
    effect text NOT NULL,
    capability_mask integer NOT NULL,
    created_by_id uuid,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT resource_acl_entries_capability_mask_check CHECK (((capability_mask >= 1) AND (capability_mask <= 255))),
    CONSTRAINT resource_acl_entries_effect_check CHECK ((effect = ANY (ARRAY['ALLOW'::text, 'DENY'::text])))
);


ALTER TABLE public.resource_acl_entries OWNER TO kanban_migrator;

--
-- Name: role_bindings; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.role_bindings (
    id uuid DEFAULT public.uuidv7() NOT NULL,
    workspace_id uuid NOT NULL,
    principal_id uuid NOT NULL,
    role public.rbac_role NOT NULL,
    scope_type text NOT NULL,
    project_id uuid,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT role_bindings_check CHECK ((((scope_type = 'server'::text) AND (role = 'SERVER_ADMIN'::public.rbac_role) AND (project_id IS NULL)) OR ((scope_type = 'workspace'::text) AND (role = ANY (ARRAY['WORKSPACE_ADMIN'::public.rbac_role, 'WORKSPACE_MEMBER'::public.rbac_role, 'WORKSPACE_GUEST'::public.rbac_role])) AND (project_id IS NULL)) OR ((scope_type = 'project'::text) AND (role = ANY (ARRAY['PROJECT_ADMIN'::public.rbac_role, 'MEMBER'::public.rbac_role, 'VIEWER'::public.rbac_role])) AND (project_id IS NOT NULL)))),
    CONSTRAINT role_bindings_scope_type_check CHECK ((scope_type = ANY (ARRAY['server'::text, 'workspace'::text, 'project'::text])))
);


ALTER TABLE public.role_bindings OWNER TO kanban_migrator;

--
-- Name: effective_resource_access effective_resource_access_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.effective_resource_access
    ADD CONSTRAINT effective_resource_access_pkey PRIMARY KEY (object_id, principal_id);


--
-- Name: resource_acl_entries resource_acl_entries_object_id_principal_id_effect_key; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.resource_acl_entries
    ADD CONSTRAINT resource_acl_entries_object_id_principal_id_effect_key UNIQUE (object_id, principal_id, effect);


--
-- Name: resource_acl_entries resource_acl_entries_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.resource_acl_entries
    ADD CONSTRAINT resource_acl_entries_pkey PRIMARY KEY (id);


--
-- Name: role_bindings role_bindings_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.role_bindings
    ADD CONSTRAINT role_bindings_pkey PRIMARY KEY (id);


--
-- Name: role_bindings role_bindings_workspace_id_principal_id_role_scope_type_pro_key; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.role_bindings
    ADD CONSTRAINT role_bindings_workspace_id_principal_id_role_scope_type_pro_key UNIQUE NULLS NOT DISTINCT (workspace_id, principal_id, role, scope_type, project_id);


--
-- Name: era_principal_obj_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX era_principal_obj_idx ON public.effective_resource_access USING btree (principal_id, object_id);


--
-- Name: resource_acl_object_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX resource_acl_object_idx ON public.resource_acl_entries USING btree (object_id);


--
-- Name: role_bindings_principal_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX role_bindings_principal_idx ON public.role_bindings USING btree (principal_id, workspace_id);


--
-- Name: role_bindings_project_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX role_bindings_project_idx ON public.role_bindings USING btree (project_id) WHERE (project_id IS NOT NULL);


--
-- Name: resource_acl_entries resource_acl_era_refresh_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER resource_acl_era_refresh_trg AFTER INSERT OR DELETE OR UPDATE ON public.resource_acl_entries FOR EACH ROW EXECUTE FUNCTION public.resource_acl_era_refresh_aiud();


--
-- Name: resource_acl_entries resource_acl_guard_biu_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER resource_acl_guard_biu_trg BEFORE INSERT OR UPDATE ON public.resource_acl_entries FOR EACH ROW EXECUTE FUNCTION public.resource_acl_guard_biu();


--
-- Name: role_bindings role_bindings_era_refresh_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER role_bindings_era_refresh_trg AFTER INSERT OR DELETE OR UPDATE ON public.role_bindings FOR EACH ROW EXECUTE FUNCTION public.role_bindings_era_refresh_aiud();


--
-- Name: role_bindings role_bindings_guard_biu_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER role_bindings_guard_biu_trg BEFORE INSERT OR UPDATE ON public.role_bindings FOR EACH ROW EXECUTE FUNCTION public.role_bindings_guard_biu();


--
-- Name: effective_resource_access effective_resource_access_object_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.effective_resource_access
    ADD CONSTRAINT effective_resource_access_object_id_fkey FOREIGN KEY (object_id) REFERENCES public.objects(id) ON DELETE CASCADE;


--
-- Name: effective_resource_access effective_resource_access_principal_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.effective_resource_access
    ADD CONSTRAINT effective_resource_access_principal_id_fkey FOREIGN KEY (principal_id) REFERENCES public.principals(id) ON DELETE CASCADE;


--
-- Name: resource_acl_entries resource_acl_entries_created_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.resource_acl_entries
    ADD CONSTRAINT resource_acl_entries_created_by_id_fkey FOREIGN KEY (created_by_id) REFERENCES public.principals(id) ON DELETE SET NULL;


--
-- Name: resource_acl_entries resource_acl_entries_object_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.resource_acl_entries
    ADD CONSTRAINT resource_acl_entries_object_id_fkey FOREIGN KEY (object_id) REFERENCES public.objects(id) ON DELETE CASCADE;


--
-- Name: resource_acl_entries resource_acl_entries_principal_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.resource_acl_entries
    ADD CONSTRAINT resource_acl_entries_principal_id_fkey FOREIGN KEY (principal_id) REFERENCES public.principals(id) ON DELETE CASCADE;


--
-- Name: resource_acl_entries resource_acl_entries_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.resource_acl_entries
    ADD CONSTRAINT resource_acl_entries_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE RESTRICT;


--
-- Name: role_bindings role_bindings_principal_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.role_bindings
    ADD CONSTRAINT role_bindings_principal_id_fkey FOREIGN KEY (principal_id) REFERENCES public.principals(id) ON DELETE CASCADE;


--
-- Name: role_bindings role_bindings_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.role_bindings
    ADD CONSTRAINT role_bindings_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: role_bindings role_bindings_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.role_bindings
    ADD CONSTRAINT role_bindings_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE RESTRICT;


--
-- Name: TABLE effective_resource_access; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT ON TABLE public.effective_resource_access TO kanban_app;
GRANT SELECT ON TABLE public.effective_resource_access TO app_rls_reader;


--
-- Name: TABLE resource_acl_entries; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.resource_acl_entries TO kanban_app;
GRANT SELECT ON TABLE public.resource_acl_entries TO app_rls_reader;


--
-- Name: TABLE role_bindings; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.role_bindings TO kanban_app;
GRANT SELECT ON TABLE public.role_bindings TO app_rls_reader;


--
-- PostgreSQL database dump complete
--

\unrestrict xjhstQxBgcPy4fPG0KCdscIUYgoew4AzcAMUh3d2RMTBuRohVLiw9jhkiLVhidy


-- === FUNCTION: app_effective_principal_set ===
CREATE OR REPLACE FUNCTION public.app_effective_principal_set()
 RETURNS uuid[]
 LANGUAGE plpgsql
 STABLE PARALLEL SAFE SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public'
AS $function$
DECLARE
    v_p uuid;
    v_ws uuid;
    v_status text;
    v_current_ws uuid;
    v_groups uuid[];
BEGIN
    v_p := app_current_principal_id();
    IF v_p IS NULL THEN
        RETURN '{}'::uuid[];
    END IF;

    v_current_ws := app_current_workspace_id();

    SELECT workspace_id, status
    INTO v_ws, v_status
    FROM principals
    WHERE id = v_p;

    IF NOT FOUND OR v_status <> 'ACTIVE' OR (v_current_ws IS NOT NULL AND v_ws <> v_current_ws) THEN
        RETURN '{}'::uuid[];
    END IF;

    SELECT COALESCE(array_agg(pgc.ancestor_group_id ORDER BY pgc.depth), '{}'::uuid[])
    INTO v_groups
    FROM principal_group_closure pgc
    JOIN principals gp ON gp.id = pgc.ancestor_group_id AND gp.status = 'ACTIVE'
    WHERE pgc.member_id = v_p;

    RETURN ARRAY[v_p] || v_groups;
END;
$function$

-- === FUNCTION: app_principal_has_role ===
CREATE OR REPLACE FUNCTION public.app_principal_has_role(p_project_id uuid, p_roles text[])
 RETURNS boolean
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public'
AS $function$
DECLARE
    v_pset uuid[];
    v_ws uuid;
BEGIN
    v_pset := app_effective_principal_set();
    IF cardinality(v_pset) = 0 THEN
        RETURN FALSE;
    END IF;

    v_ws := app_current_workspace_id();
    IF v_ws IS NULL THEN
        RETURN FALSE;
    END IF;

    RETURN EXISTS (
        SELECT 1
        FROM role_bindings rb
        WHERE rb.principal_id = ANY (v_pset)
          AND rb.workspace_id = v_ws
          AND rb.role::text = ANY (p_roles)
          AND (
              rb.scope_type = 'server'
              OR rb.scope_type = 'workspace'
              OR (rb.scope_type = 'project' AND rb.project_id = p_project_id AND p_project_id IS NOT NULL)
          )
    );
END;
$function$
