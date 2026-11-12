--
-- PostgreSQL database dump
--

\restrict AU7yIJqN97tVRL5Zsu7iLd2g5jycjd77aIjYOCgpzIW7jgwIImgfqECKcOXRk42

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
-- Name: project_labels; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.project_labels (
    id uuid DEFAULT public.uuidv7() NOT NULL,
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    name text NOT NULL,
    color_hex text NOT NULL,
    exclusive_group text,
    CONSTRAINT project_labels_color_hex_check CHECK ((color_hex ~ '^#[0-9A-Fa-f]{6}$'::text)),
    CONSTRAINT project_labels_exclusive_group_check CHECK (((exclusive_group IS NULL) OR (exclusive_group ~ '^[a-z][a-z0-9_-]{0,31}$'::text))),
    CONSTRAINT project_labels_name_check CHECK (((char_length(btrim(name)) >= 1) AND (char_length(btrim(name)) <= 100)))
);


ALTER TABLE public.project_labels OWNER TO kanban_migrator;

--
-- Name: project_priorities; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.project_priorities (
    id uuid DEFAULT public.uuidv7() NOT NULL,
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    slug text NOT NULL,
    label text NOT NULL,
    emoji text,
    color_hex text NOT NULL,
    sort_order integer NOT NULL,
    is_default boolean DEFAULT false NOT NULL,
    CONSTRAINT project_priorities_color_hex_check CHECK ((color_hex ~ '^#[0-9A-Fa-f]{6}$'::text)),
    CONSTRAINT project_priorities_emoji_check CHECK (((emoji IS NULL) OR ((char_length(emoji) >= 1) AND (char_length(emoji) <= 8)))),
    CONSTRAINT project_priorities_label_check CHECK (((char_length(btrim(label)) >= 1) AND (char_length(btrim(label)) <= 50))),
    CONSTRAINT project_priorities_slug_check CHECK ((slug ~ '^[a-z][a-z0-9_-]{0,31}$'::text))
);


ALTER TABLE public.project_priorities OWNER TO kanban_migrator;

--
-- Name: projects; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.projects (
    id uuid NOT NULL,
    object_type public.object_kind DEFAULT 'project'::public.object_kind NOT NULL,
    workspace_id uuid NOT NULL,
    identifier text NOT NULL,
    name text NOT NULL,
    description_markdown text DEFAULT ''::text NOT NULL,
    modules_enabled boolean DEFAULT false NOT NULL,
    issue_seq_counter bigint DEFAULT 0 NOT NULL,
    auto_archive_days integer,
    CONSTRAINT projects_auto_archive_days_check CHECK (((auto_archive_days IS NULL) OR ((auto_archive_days >= 1) AND (auto_archive_days <= 365)))),
    CONSTRAINT projects_description_markdown_check CHECK ((octet_length(description_markdown) <= 524288)),
    CONSTRAINT projects_identifier_check CHECK ((identifier ~ '^[A-Z][A-Z0-9]{1,9}$'::text)),
    CONSTRAINT projects_object_type_check CHECK ((object_type = 'project'::public.object_kind))
);


ALTER TABLE public.projects OWNER TO kanban_migrator;

--
-- Name: workflow_states; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.workflow_states (
    id uuid DEFAULT public.uuidv7() NOT NULL,
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    name text NOT NULL,
    state_group text NOT NULL,
    color_hex text NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    is_default boolean DEFAULT false NOT NULL,
    CONSTRAINT workflow_states_color_hex_check CHECK ((color_hex ~ '^#[0-9A-Fa-f]{6}$'::text)),
    CONSTRAINT workflow_states_name_check CHECK (((char_length(btrim(name)) >= 1) AND (char_length(btrim(name)) <= 100))),
    CONSTRAINT workflow_states_state_group_check CHECK ((state_group = ANY (ARRAY['backlog'::text, 'unstarted'::text, 'started'::text, 'completed'::text, 'cancelled'::text])))
);


ALTER TABLE public.workflow_states OWNER TO kanban_migrator;

--
-- Name: project_labels project_labels_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.project_labels
    ADD CONSTRAINT project_labels_pkey PRIMARY KEY (id);


--
-- Name: project_labels project_labels_project_id_name_key; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.project_labels
    ADD CONSTRAINT project_labels_project_id_name_key UNIQUE (project_id, name);


--
-- Name: project_priorities project_priorities_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.project_priorities
    ADD CONSTRAINT project_priorities_pkey PRIMARY KEY (id);


--
-- Name: project_priorities project_priorities_project_id_slug_key; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.project_priorities
    ADD CONSTRAINT project_priorities_project_id_slug_key UNIQUE (project_id, slug);


--
-- Name: projects projects_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT projects_pkey PRIMARY KEY (id);


--
-- Name: projects projects_workspace_id_identifier_key; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT projects_workspace_id_identifier_key UNIQUE (workspace_id, identifier);


--
-- Name: workflow_states workflow_states_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.workflow_states
    ADD CONSTRAINT workflow_states_pkey PRIMARY KEY (id);


--
-- Name: workflow_states workflow_states_project_id_name_key; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.workflow_states
    ADD CONSTRAINT workflow_states_project_id_name_key UNIQUE (project_id, name);


--
-- Name: project_priorities_one_default; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE UNIQUE INDEX project_priorities_one_default ON public.project_priorities USING btree (project_id) WHERE is_default;


--
-- Name: workflow_states_one_default; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE UNIQUE INDEX workflow_states_one_default ON public.workflow_states USING btree (project_id) WHERE is_default;


--
-- Name: project_labels project_labels_workspace_match_biu_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER project_labels_workspace_match_biu_trg BEFORE INSERT OR UPDATE ON public.project_labels FOR EACH ROW EXECUTE FUNCTION public.project_labels_workspace_match_biu();


--
-- Name: project_priorities project_priorities_workspace_match_biu_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER project_priorities_workspace_match_biu_trg BEFORE INSERT OR UPDATE ON public.project_priorities FOR EACH ROW EXECUTE FUNCTION public.project_priorities_workspace_match_biu();


--
-- Name: projects projects_seed_defaults_ai_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER projects_seed_defaults_ai_trg AFTER INSERT ON public.projects FOR EACH ROW EXECUTE FUNCTION public.projects_seed_defaults_ai();


--
-- Name: projects projects_seq_guard_bu_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER projects_seq_guard_bu_trg BEFORE UPDATE ON public.projects FOR EACH ROW EXECUTE FUNCTION public.projects_seq_guard_bu();


--
-- Name: projects projects_spine_match_biu_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER projects_spine_match_biu_trg BEFORE INSERT OR UPDATE ON public.projects FOR EACH ROW EXECUTE FUNCTION public.projects_spine_match_biu();


--
-- Name: workflow_states workflow_states_group_guard_bd_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER workflow_states_group_guard_bd_trg BEFORE DELETE ON public.workflow_states FOR EACH ROW EXECUTE FUNCTION public.workflow_states_group_guard_bd();


--
-- Name: workflow_states workflow_states_workspace_match_biu_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER workflow_states_workspace_match_biu_trg BEFORE INSERT OR UPDATE ON public.workflow_states FOR EACH ROW EXECUTE FUNCTION public.workflow_states_workspace_match_biu();


--
-- Name: project_labels project_labels_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.project_labels
    ADD CONSTRAINT project_labels_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE RESTRICT;


--
-- Name: project_labels project_labels_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.project_labels
    ADD CONSTRAINT project_labels_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE RESTRICT;


--
-- Name: project_priorities project_priorities_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.project_priorities
    ADD CONSTRAINT project_priorities_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE RESTRICT;


--
-- Name: project_priorities project_priorities_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.project_priorities
    ADD CONSTRAINT project_priorities_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE RESTRICT;


--
-- Name: projects projects_id_object_type_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT projects_id_object_type_fkey FOREIGN KEY (id, object_type) REFERENCES public.objects(id, object_type) ON DELETE RESTRICT;


--
-- Name: projects projects_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT projects_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE RESTRICT;


--
-- Name: workflow_states workflow_states_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.workflow_states
    ADD CONSTRAINT workflow_states_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE RESTRICT;


--
-- Name: workflow_states workflow_states_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.workflow_states
    ADD CONSTRAINT workflow_states_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE RESTRICT;


--
-- Name: TABLE project_labels; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.project_labels TO kanban_app;
GRANT SELECT ON TABLE public.project_labels TO app_rls_reader;


--
-- Name: TABLE project_priorities; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.project_priorities TO kanban_app;
GRANT SELECT ON TABLE public.project_priorities TO app_rls_reader;


--
-- Name: TABLE projects; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.projects TO kanban_app;
GRANT SELECT ON TABLE public.projects TO app_rls_reader;


--
-- Name: TABLE workflow_states; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.workflow_states TO kanban_app;
GRANT SELECT ON TABLE public.workflow_states TO app_rls_reader;


--
-- PostgreSQL database dump complete
--

\unrestrict AU7yIJqN97tVRL5Zsu7iLd2g5jycjd77aIjYOCgpzIW7jgwIImgfqECKcOXRk42

