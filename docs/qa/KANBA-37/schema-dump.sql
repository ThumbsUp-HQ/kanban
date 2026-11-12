--
-- PostgreSQL database dump
--

\restrict g8LuFmocvwDC2Qg2uZvlby2M9St6I4FuwlJU40abuqBErE2XtR4tJCGR3OizhOq

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
-- Name: link_type_matrix; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.link_type_matrix (
    source_type public.object_kind NOT NULL,
    link_type public.link_kind NOT NULL,
    target_type public.object_kind NOT NULL,
    is_user_creatable boolean DEFAULT false NOT NULL
);


ALTER TABLE public.link_type_matrix OWNER TO kanban_migrator;

--
-- Name: object_links; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.object_links (
    id uuid DEFAULT public.uuidv7() NOT NULL,
    workspace_id uuid NOT NULL,
    source_id uuid NOT NULL,
    source_type public.object_kind NOT NULL,
    target_id uuid NOT NULL,
    target_type public.object_kind NOT NULL,
    link_type public.link_kind NOT NULL,
    link_state text DEFAULT 'ACTIVE'::text NOT NULL,
    source_key_snapshot text NOT NULL,
    target_key_snapshot text NOT NULL,
    created_by_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT object_links_check CHECK ((source_id <> target_id)),
    CONSTRAINT object_links_link_state_check CHECK ((link_state = ANY (ARRAY['ACTIVE'::text, 'FLAGGED_INVALID'::text])))
);


ALTER TABLE public.object_links OWNER TO kanban_migrator;

--
-- Name: link_type_matrix link_type_matrix_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.link_type_matrix
    ADD CONSTRAINT link_type_matrix_pkey PRIMARY KEY (source_type, link_type, target_type);


--
-- Name: object_links object_links_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.object_links
    ADD CONSTRAINT object_links_pkey PRIMARY KEY (id);


--
-- Name: object_links object_links_source_id_target_id_link_type_key; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.object_links
    ADD CONSTRAINT object_links_source_id_target_id_link_type_key UNIQUE (source_id, target_id, link_type);


--
-- Name: object_links_source_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX object_links_source_idx ON public.object_links USING btree (source_id, link_state);


--
-- Name: object_links_target_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX object_links_target_idx ON public.object_links USING btree (target_id, link_state);


--
-- Name: object_links_ws_state_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX object_links_ws_state_idx ON public.object_links USING btree (workspace_id, link_state);


--
-- Name: object_links object_links_guard_bu_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER object_links_guard_bu_trg BEFORE UPDATE ON public.object_links FOR EACH ROW EXECUTE FUNCTION public.object_links_guard_bu();


--
-- Name: object_links object_links_validate_bi_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER object_links_validate_bi_trg BEFORE INSERT ON public.object_links FOR EACH ROW EXECUTE FUNCTION public.object_links_validate_bi();


--
-- Name: object_links object_links_source_id_source_type_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.object_links
    ADD CONSTRAINT object_links_source_id_source_type_fkey FOREIGN KEY (source_id, source_type) REFERENCES public.objects(id, object_type) ON DELETE RESTRICT;


--
-- Name: object_links object_links_target_id_target_type_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.object_links
    ADD CONSTRAINT object_links_target_id_target_type_fkey FOREIGN KEY (target_id, target_type) REFERENCES public.objects(id, object_type) ON DELETE RESTRICT;


--
-- Name: object_links object_links_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.object_links
    ADD CONSTRAINT object_links_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE RESTRICT;


--
-- Name: TABLE link_type_matrix; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT ON TABLE public.link_type_matrix TO kanban_app;
GRANT SELECT ON TABLE public.link_type_matrix TO app_rls_reader;


--
-- Name: TABLE object_links; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.object_links TO kanban_app;
GRANT SELECT ON TABLE public.object_links TO app_rls_reader;


--
-- PostgreSQL database dump complete
--

\unrestrict g8LuFmocvwDC2Qg2uZvlby2M9St6I4FuwlJU40abuqBErE2XtR4tJCGR3OizhOq

                                                 List of data types
 Schema |   Name    | Internal name | Size |      Elements       |      Owner      | Access privileges | Description 
--------+-----------+---------------+------+---------------------+-----------------+-------------------+-------------
 public | link_kind | link_kind     | 4    | BLOCKS             +| kanban_migrator |                   | 
        |           |               |      | BLOCKED_BY         +|                 |                   | 
        |           |               |      | RELATES_TO         +|                 |                   | 
        |           |               |      | DUPLICATES         +|                 |                   | 
        |           |               |      | PARENT_OF          +|                 |                   | 
        |           |               |      | ASSIGNED_TO        +|                 |                   | 
        |           |               |      | IN_CYCLE           +|                 |                   | 
        |           |               |      | IN_MODULE          +|                 |                   | 
        |           |               |      | PROMOTED_TO_DOC    +|                 |                   | 
        |           |               |      | VERIFIED_BY_DOC    +|                 |                   | 
        |           |               |      | DERIVED_FROM_STICKY+|                 |                   | 
        |           |               |      | EMBEDS_OBJECT      +|                 |                   | 
        |           |               |      | GOVERNED_BY_VIEW    |                 |                   | 
(1 row)

