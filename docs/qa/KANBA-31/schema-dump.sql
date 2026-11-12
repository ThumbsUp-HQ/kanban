--
-- PostgreSQL database dump
--

\restrict 3gSk5TMSZvDhRHiZVPNiDUSIEeaNJCnY4Ot22NqWHVbKRE17zZeEqd1LkWbWi1m

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
-- Name: objects; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.objects (
    id uuid DEFAULT public.uuidv7() NOT NULL,
    object_type public.object_kind NOT NULL,
    workspace_id uuid NOT NULL,
    project_id uuid,
    canonical_key text NOT NULL,
    display_title text NOT NULL,
    created_by_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    archived_at timestamp with time zone,
    deleted_at timestamp with time zone,
    CONSTRAINT objects_canonical_key_check CHECK (((char_length(canonical_key) >= 1) AND (char_length(canonical_key) <= 200))),
    CONSTRAINT objects_display_title_check CHECK (((char_length(display_title) >= 1) AND (char_length(display_title) <= 500)))
);


ALTER TABLE public.objects OWNER TO kanban_migrator;

--
-- Name: workspaces; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.workspaces (
    id uuid DEFAULT public.uuidv7() NOT NULL,
    slug text NOT NULL,
    name text NOT NULL,
    trash_retention_days integer DEFAULT 30 NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT workspaces_name_check CHECK (((char_length(btrim(name)) >= 1) AND (char_length(btrim(name)) <= 200))),
    CONSTRAINT workspaces_slug_check CHECK ((slug ~ '^[a-z0-9][a-z0-9-]{1,62}$'::text)),
    CONSTRAINT workspaces_trash_retention_days_check CHECK (((trash_retention_days >= 1) AND (trash_retention_days <= 3650)))
);


ALTER TABLE public.workspaces OWNER TO kanban_migrator;

--
-- Name: objects objects_id_object_type_key; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.objects
    ADD CONSTRAINT objects_id_object_type_key UNIQUE (id, object_type);


--
-- Name: objects objects_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.objects
    ADD CONSTRAINT objects_pkey PRIMARY KEY (id);


--
-- Name: objects objects_workspace_id_object_type_canonical_key_key; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.objects
    ADD CONSTRAINT objects_workspace_id_object_type_canonical_key_key UNIQUE (workspace_id, object_type, canonical_key);


--
-- Name: workspaces workspaces_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.workspaces
    ADD CONSTRAINT workspaces_pkey PRIMARY KEY (id);


--
-- Name: workspaces workspaces_slug_key; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.workspaces
    ADD CONSTRAINT workspaces_slug_key UNIQUE (slug);


--
-- Name: objects_project_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX objects_project_idx ON public.objects USING btree (project_id) WHERE (project_id IS NOT NULL);


--
-- Name: objects_ws_type_live_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX objects_ws_type_live_idx ON public.objects USING btree (workspace_id, object_type) WHERE (deleted_at IS NULL);


--
-- Name: objects objects_guard_bu_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER objects_guard_bu_trg BEFORE UPDATE ON public.objects FOR EACH ROW EXECUTE FUNCTION public.objects_guard_bu();


--
-- Name: objects objects_set_updated_at; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER objects_set_updated_at BEFORE UPDATE ON public.objects FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: workspaces workspaces_set_updated_at; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER workspaces_set_updated_at BEFORE UPDATE ON public.workspaces FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: objects objects_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.objects
    ADD CONSTRAINT objects_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE RESTRICT;


--
-- Name: TABLE objects; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.objects TO kanban_app;
GRANT SELECT ON TABLE public.objects TO app_rls_reader;


--
-- Name: TABLE workspaces; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.workspaces TO kanban_app;
GRANT SELECT ON TABLE public.workspaces TO app_rls_reader;


--
-- PostgreSQL database dump complete
--

\unrestrict 3gSk5TMSZvDhRHiZVPNiDUSIEeaNJCnY4Ot22NqWHVbKRE17zZeEqd1LkWbWi1m


-- \dT+ object_kind
                                             List of data types
 Schema |    Name     | Internal name | Size | Elements |      Owner      | Access privileges | Description 
--------+-------------+---------------+------+----------+-----------------+-------------------+-------------
 public | object_kind | object_kind   | 4    | issue   +| kanban_migrator |                   | 
        |             |               |      | sticky  +|                 |                   | 
        |             |               |      | doc     +|                 |                   | 
        |             |               |      | user    +|                 |                   | 
        |             |               |      | project +|                 |                   | 
        |             |               |      | cycle   +|                 |                   | 
        |             |               |      | module  +|                 |                   | 
        |             |               |      | view    +|                 |                   | 
        |             |               |      | page     |                 |                   | 
(1 row)

