--
-- PostgreSQL database dump
--

\restrict iSNPrGq4ZVckBNefYbUuxuKjbkFBva2D6tdg2PlU2rTVTnZchfTfMlE8fgIGZGD

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
-- Name: groups; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.groups (
    id uuid NOT NULL,
    principal_type text DEFAULT 'GROUP'::text NOT NULL,
    workspace_id uuid NOT NULL,
    name text NOT NULL,
    external_source text,
    external_id text,
    CONSTRAINT groups_external_id_check CHECK (((external_id IS NULL) OR (char_length(external_id) <= 1024))),
    CONSTRAINT groups_external_source_check CHECK ((external_source = ANY (ARRAY['LDAP'::text, 'OIDC'::text]))),
    CONSTRAINT groups_name_check CHECK (((char_length(btrim(name)) >= 1) AND (char_length(btrim(name)) <= 200))),
    CONSTRAINT groups_principal_type_check CHECK ((principal_type = 'GROUP'::text))
);


ALTER TABLE public.groups OWNER TO kanban_migrator;

--
-- Name: principal_group_closure; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.principal_group_closure (
    member_id uuid NOT NULL,
    ancestor_group_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    depth smallint NOT NULL,
    CONSTRAINT principal_group_closure_depth_check CHECK (((depth >= 1) AND (depth <= 8)))
);


ALTER TABLE public.principal_group_closure OWNER TO kanban_migrator;

--
-- Name: principal_group_edges; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.principal_group_edges (
    member_id uuid NOT NULL,
    group_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT principal_group_edges_check CHECK ((member_id <> group_id))
);


ALTER TABLE public.principal_group_edges OWNER TO kanban_migrator;

--
-- Name: principals; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.principals (
    id uuid DEFAULT public.uuidv7() NOT NULL,
    principal_type text NOT NULL,
    workspace_id uuid NOT NULL,
    status text DEFAULT 'ACTIVE'::text NOT NULL,
    display_name text NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT principals_display_name_check CHECK (((char_length(btrim(display_name)) >= 1) AND (char_length(btrim(display_name)) <= 200))),
    CONSTRAINT principals_principal_type_check CHECK ((principal_type = ANY (ARRAY['USER'::text, 'GROUP'::text, 'AGENT'::text, 'SCRIPT_EPHEMERAL'::text, 'SERVICE_PRINCIPAL'::text]))),
    CONSTRAINT principals_status_check CHECK ((status = ANY (ARRAY['ACTIVE'::text, 'DISABLED'::text])))
);


ALTER TABLE public.principals OWNER TO kanban_migrator;

--
-- Name: users; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.users (
    id uuid NOT NULL,
    object_type public.object_kind DEFAULT 'user'::public.object_kind NOT NULL,
    principal_type text DEFAULT 'USER'::text NOT NULL,
    workspace_id uuid NOT NULL,
    email text NOT NULL,
    CONSTRAINT users_email_check CHECK ((((char_length(email) >= 3) AND (char_length(email) <= 320)) AND (email ~ '^[^@\s]+@[^@\s]+$'::text))),
    CONSTRAINT users_object_type_check CHECK ((object_type = 'user'::public.object_kind)),
    CONSTRAINT users_principal_type_check CHECK ((principal_type = 'USER'::text))
);


ALTER TABLE public.users OWNER TO kanban_migrator;

--
-- Name: groups groups_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.groups
    ADD CONSTRAINT groups_pkey PRIMARY KEY (id);


--
-- Name: groups groups_workspace_id_name_key; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.groups
    ADD CONSTRAINT groups_workspace_id_name_key UNIQUE (workspace_id, name);


--
-- Name: principal_group_closure principal_group_closure_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.principal_group_closure
    ADD CONSTRAINT principal_group_closure_pkey PRIMARY KEY (member_id, ancestor_group_id);


--
-- Name: principal_group_edges principal_group_edges_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.principal_group_edges
    ADD CONSTRAINT principal_group_edges_pkey PRIMARY KEY (member_id, group_id);


--
-- Name: principals principals_id_principal_type_key; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.principals
    ADD CONSTRAINT principals_id_principal_type_key UNIQUE (id, principal_type);


--
-- Name: principals principals_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.principals
    ADD CONSTRAINT principals_pkey PRIMARY KEY (id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: pgc_ancestor_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX pgc_ancestor_idx ON public.principal_group_closure USING btree (ancestor_group_id, member_id);


--
-- Name: pgc_workspace_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX pgc_workspace_idx ON public.principal_group_closure USING btree (workspace_id);


--
-- Name: pge_workspace_group_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX pge_workspace_group_idx ON public.principal_group_edges USING btree (workspace_id, group_id);


--
-- Name: users_ws_email_uq; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE UNIQUE INDEX users_ws_email_uq ON public.users USING btree (workspace_id, lower(email));


--
-- Name: groups groups_workspace_match_biu_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER groups_workspace_match_biu_trg BEFORE INSERT OR UPDATE ON public.groups FOR EACH ROW EXECUTE FUNCTION public.groups_workspace_match_biu();


--
-- Name: principal_group_edges principal_group_edges_closure_aiud_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER principal_group_edges_closure_aiud_trg AFTER INSERT OR DELETE OR UPDATE ON public.principal_group_edges FOR EACH ROW EXECUTE FUNCTION public.principal_group_edges_closure_aiud();


--
-- Name: principal_group_edges principal_group_edges_guard_biu_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER principal_group_edges_guard_biu_trg BEFORE INSERT OR UPDATE ON public.principal_group_edges FOR EACH ROW EXECUTE FUNCTION public.principal_group_edges_guard_biu();


--
-- Name: users users_workspace_match_biu_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER users_workspace_match_biu_trg BEFORE INSERT OR UPDATE ON public.users FOR EACH ROW EXECUTE FUNCTION public.users_workspace_match_biu();


--
-- Name: groups groups_id_principal_type_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.groups
    ADD CONSTRAINT groups_id_principal_type_fkey FOREIGN KEY (id, principal_type) REFERENCES public.principals(id, principal_type) ON DELETE RESTRICT;


--
-- Name: groups groups_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.groups
    ADD CONSTRAINT groups_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE RESTRICT;


--
-- Name: principal_group_closure principal_group_closure_ancestor_group_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.principal_group_closure
    ADD CONSTRAINT principal_group_closure_ancestor_group_id_fkey FOREIGN KEY (ancestor_group_id) REFERENCES public.groups(id) ON DELETE CASCADE;


--
-- Name: principal_group_closure principal_group_closure_member_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.principal_group_closure
    ADD CONSTRAINT principal_group_closure_member_id_fkey FOREIGN KEY (member_id) REFERENCES public.principals(id) ON DELETE CASCADE;


--
-- Name: principal_group_closure principal_group_closure_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.principal_group_closure
    ADD CONSTRAINT principal_group_closure_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;


--
-- Name: principal_group_edges principal_group_edges_group_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.principal_group_edges
    ADD CONSTRAINT principal_group_edges_group_id_fkey FOREIGN KEY (group_id) REFERENCES public.groups(id) ON DELETE RESTRICT;


--
-- Name: principal_group_edges principal_group_edges_member_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.principal_group_edges
    ADD CONSTRAINT principal_group_edges_member_id_fkey FOREIGN KEY (member_id) REFERENCES public.principals(id) ON DELETE RESTRICT;


--
-- Name: principal_group_edges principal_group_edges_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.principal_group_edges
    ADD CONSTRAINT principal_group_edges_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE RESTRICT;


--
-- Name: principals principals_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.principals
    ADD CONSTRAINT principals_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE RESTRICT;


--
-- Name: users users_id_object_type_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_id_object_type_fkey FOREIGN KEY (id, object_type) REFERENCES public.objects(id, object_type) ON DELETE RESTRICT;


--
-- Name: users users_id_principal_type_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_id_principal_type_fkey FOREIGN KEY (id, principal_type) REFERENCES public.principals(id, principal_type) ON DELETE RESTRICT;


--
-- Name: users users_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE RESTRICT;


--
-- Name: TABLE groups; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.groups TO kanban_app;
GRANT SELECT ON TABLE public.groups TO app_rls_reader;


--
-- Name: TABLE principal_group_closure; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT ON TABLE public.principal_group_closure TO kanban_app;
GRANT SELECT ON TABLE public.principal_group_closure TO app_rls_reader;


--
-- Name: TABLE principal_group_edges; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.principal_group_edges TO kanban_app;
GRANT SELECT ON TABLE public.principal_group_edges TO app_rls_reader;


--
-- Name: TABLE principals; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.principals TO kanban_app;
GRANT SELECT ON TABLE public.principals TO app_rls_reader;


--
-- Name: TABLE users; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.users TO kanban_app;
GRANT SELECT ON TABLE public.users TO app_rls_reader;


--
-- PostgreSQL database dump complete
--

\unrestrict iSNPrGq4ZVckBNefYbUuxuKjbkFBva2D6tdg2PlU2rTVTnZchfTfMlE8fgIGZGD



-- Functions --
CREATE OR REPLACE FUNCTION public.groups_workspace_match_biu()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
DECLARE
    v_principal_ws uuid;
BEGIN
    SELECT workspace_id INTO v_principal_ws FROM principals WHERE id = NEW.id;
    IF v_principal_ws IS NULL OR NEW.workspace_id <> v_principal_ws THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'PRINCIPAL_WORKSPACE_MISMATCH';
    END IF;

    RETURN NEW;
END $function$
;

CREATE OR REPLACE FUNCTION public.principal_group_edges_closure_aiud()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
BEGIN
    IF TG_OP = 'DELETE' THEN
        PERFORM rebuild_group_closure(OLD.workspace_id);
        RETURN OLD;
    ELSIF TG_OP = 'UPDATE' THEN
        IF OLD.workspace_id <> NEW.workspace_id THEN
            PERFORM rebuild_group_closure(OLD.workspace_id);
        END IF;
        PERFORM rebuild_group_closure(NEW.workspace_id);
        RETURN NEW;
    ELSE
        PERFORM rebuild_group_closure(NEW.workspace_id);
        RETURN NEW;
    END IF;
END $function$
;

CREATE OR REPLACE FUNCTION public.principal_group_edges_guard_biu()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
DECLARE
    v_member_ws uuid;
    v_group_ws uuid;
BEGIN
    SELECT workspace_id INTO v_member_ws FROM principals WHERE id = NEW.member_id;
    SELECT workspace_id INTO v_group_ws FROM groups WHERE id = NEW.group_id;

    IF v_member_ws IS NULL OR v_group_ws IS NULL OR v_member_ws <> NEW.workspace_id OR v_group_ws <> NEW.workspace_id THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'GROUP_EDGE_WORKSPACE_MISMATCH';
    END IF;

    IF EXISTS (
        SELECT 1 FROM principal_group_closure
        WHERE member_id = NEW.group_id AND ancestor_group_id = NEW.member_id
    ) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'GROUP_CYCLE_REJECTED';
    END IF;

    RETURN NEW;
END $function$
;

CREATE OR REPLACE FUNCTION public.rebuild_group_closure(p_workspace_id uuid)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    v_has_cycle boolean;
    v_max_depth int;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended('group_closure:' || p_workspace_id::text, 0));

    WITH RECURSIVE walk(member_id, ancestor_group_id, depth) AS (
        SELECT e.member_id, e.group_id, 1
        FROM principal_group_edges e
        WHERE e.workspace_id = p_workspace_id
      UNION ALL
        SELECT e.member_id, w.ancestor_group_id, w.depth + 1
        FROM walk w
        JOIN principal_group_edges e ON e.group_id = w.member_id
        WHERE e.workspace_id = p_workspace_id
          AND w.depth <= 8
    )
    CYCLE member_id SET is_cycle USING path
    SELECT
        coalesce(bool_or(is_cycle), false),
        coalesce(max(depth), 0)
    INTO v_has_cycle, v_max_depth
    FROM walk;

    IF v_has_cycle THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'GROUP_CYCLE_REJECTED';
    END IF;

    IF v_max_depth > 8 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'GROUP_DEPTH_EXCEEDED';
    END IF;

    DELETE FROM principal_group_closure WHERE workspace_id = p_workspace_id;

    WITH RECURSIVE walk(member_id, ancestor_group_id, depth) AS (
        SELECT e.member_id, e.group_id, 1
        FROM principal_group_edges e
        WHERE e.workspace_id = p_workspace_id
      UNION ALL
        SELECT e.member_id, w.ancestor_group_id, w.depth + 1
        FROM walk w
        JOIN principal_group_edges e ON e.group_id = w.member_id
        WHERE e.workspace_id = p_workspace_id
          AND w.depth <= 8
    )
    CYCLE member_id SET is_cycle USING path
    INSERT INTO principal_group_closure (member_id, ancestor_group_id, workspace_id, depth)
    SELECT member_id, ancestor_group_id, p_workspace_id, min(depth)::smallint
    FROM walk
    GROUP BY member_id, ancestor_group_id;
END $function$
;

CREATE OR REPLACE FUNCTION public.users_workspace_match_biu()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
DECLARE
    v_principal_ws uuid;
    v_object_ws uuid;
BEGIN
    SELECT workspace_id INTO v_principal_ws FROM principals WHERE id = NEW.id;
    IF v_principal_ws IS NULL OR NEW.workspace_id <> v_principal_ws THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'PRINCIPAL_WORKSPACE_MISMATCH';
    END IF;

    SELECT workspace_id INTO v_object_ws FROM objects WHERE id = NEW.id;
    IF v_object_ws IS NULL OR NEW.workspace_id <> v_object_ws THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'PRINCIPAL_WORKSPACE_MISMATCH';
    END IF;

    RETURN NEW;
END $function$
;
