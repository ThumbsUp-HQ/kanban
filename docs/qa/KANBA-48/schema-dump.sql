--
-- PostgreSQL database dump
--

\restrict al2vlAaeFlFQ0qwLAwQhV7cMbZ8GFtnr0UC5QOaD4ve4EzDkycx6UlLfqNjfFoo

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
-- Name: cycles; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.cycles (
    id uuid NOT NULL,
    object_type public.object_kind DEFAULT 'cycle'::public.object_kind NOT NULL,
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    name text NOT NULL,
    status text DEFAULT 'upcoming'::text NOT NULL,
    start_date date,
    end_date date,
    CONSTRAINT cycles_check CHECK (((end_date IS NULL) OR (start_date IS NULL) OR (end_date >= start_date))),
    CONSTRAINT cycles_name_check CHECK (((char_length(btrim(name)) >= 1) AND (char_length(btrim(name)) <= 200))),
    CONSTRAINT cycles_object_type_check CHECK ((object_type = 'cycle'::public.object_kind)),
    CONSTRAINT cycles_status_check CHECK ((status = ANY (ARRAY['upcoming'::text, 'active'::text, 'completed'::text])))
);


ALTER TABLE public.cycles OWNER TO kanban_migrator;

--
-- Name: issue_assignees; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.issue_assignees (
    id uuid DEFAULT public.uuidv7() NOT NULL,
    workspace_id uuid NOT NULL,
    issue_id uuid NOT NULL,
    principal_id uuid,
    free_text_assignee text,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT issue_assignees_check CHECK ((num_nonnulls(principal_id, free_text_assignee) = 1)),
    CONSTRAINT issue_assignees_free_text_assignee_check CHECK (((free_text_assignee IS NULL) OR ((char_length(btrim(free_text_assignee)) >= 1) AND (char_length(btrim(free_text_assignee)) <= 120))))
);


ALTER TABLE public.issue_assignees OWNER TO kanban_migrator;

--
-- Name: COLUMN issue_assignees.free_text_assignee; Type: COMMENT; Schema: public; Owner: kanban_migrator
--

COMMENT ON COLUMN public.issue_assignees.free_text_assignee IS 'Vendor or external assignee; grants zero system access and is omitted from effective_resource_access computation.';


--
-- Name: issue_labels; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.issue_labels (
    issue_id uuid NOT NULL,
    label_id uuid NOT NULL,
    workspace_id uuid NOT NULL
);


ALTER TABLE public.issue_labels OWNER TO kanban_migrator;

--
-- Name: issue_modules; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.issue_modules (
    issue_id uuid NOT NULL,
    module_id uuid NOT NULL,
    workspace_id uuid NOT NULL
);


ALTER TABLE public.issue_modules OWNER TO kanban_migrator;

--
-- Name: issue_subscriptions; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.issue_subscriptions (
    issue_id uuid NOT NULL,
    principal_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    source text NOT NULL,
    is_muted boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT issue_subscriptions_source_check CHECK ((source = ANY (ARRAY['MANUAL'::text, 'CREATOR'::text, 'ASSIGNEE'::text, 'MENTION'::text])))
);


ALTER TABLE public.issue_subscriptions OWNER TO kanban_migrator;

--
-- Name: modules; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.modules (
    id uuid NOT NULL,
    object_type public.object_kind DEFAULT 'module'::public.object_kind NOT NULL,
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    name text NOT NULL,
    start_date date,
    target_date date,
    CONSTRAINT modules_check CHECK (((target_date IS NULL) OR (start_date IS NULL) OR (target_date >= start_date))),
    CONSTRAINT modules_name_check CHECK (((char_length(btrim(name)) >= 1) AND (char_length(btrim(name)) <= 200))),
    CONSTRAINT modules_object_type_check CHECK ((object_type = 'module'::public.object_kind))
);


ALTER TABLE public.modules OWNER TO kanban_migrator;

--
-- Name: project_module_defaults; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.project_module_defaults (
    project_id uuid NOT NULL,
    module_id uuid NOT NULL,
    workspace_id uuid NOT NULL
);


ALTER TABLE public.project_module_defaults OWNER TO kanban_migrator;

--
-- Name: cycles cycles_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.cycles
    ADD CONSTRAINT cycles_pkey PRIMARY KEY (id);


--
-- Name: cycles cycles_project_id_daterange_excl; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.cycles
    ADD CONSTRAINT cycles_project_id_daterange_excl EXCLUDE USING gist (project_id WITH =, daterange(start_date, end_date, '[]'::text) WITH &&) WHERE (((start_date IS NOT NULL) AND (end_date IS NOT NULL)));


--
-- Name: issue_assignees issue_assignees_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.issue_assignees
    ADD CONSTRAINT issue_assignees_pkey PRIMARY KEY (id);


--
-- Name: issue_labels issue_labels_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.issue_labels
    ADD CONSTRAINT issue_labels_pkey PRIMARY KEY (issue_id, label_id);


--
-- Name: issue_modules issue_modules_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.issue_modules
    ADD CONSTRAINT issue_modules_pkey PRIMARY KEY (issue_id, module_id);


--
-- Name: issue_subscriptions issue_subscriptions_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.issue_subscriptions
    ADD CONSTRAINT issue_subscriptions_pkey PRIMARY KEY (issue_id, principal_id);


--
-- Name: modules modules_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.modules
    ADD CONSTRAINT modules_pkey PRIMARY KEY (id);


--
-- Name: modules modules_project_id_name_key; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.modules
    ADD CONSTRAINT modules_project_id_name_key UNIQUE (project_id, name);


--
-- Name: project_module_defaults project_module_defaults_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.project_module_defaults
    ADD CONSTRAINT project_module_defaults_pkey PRIMARY KEY (project_id, module_id);


--
-- Name: cycles_one_active_per_project; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE UNIQUE INDEX cycles_one_active_per_project ON public.cycles USING btree (project_id) WHERE (status = 'active'::text);


--
-- Name: cycles_project_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX cycles_project_idx ON public.cycles USING btree (project_id);


--
-- Name: issue_assignees_issue_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX issue_assignees_issue_idx ON public.issue_assignees USING btree (issue_id);


--
-- Name: issue_assignees_principal_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX issue_assignees_principal_idx ON public.issue_assignees USING btree (principal_id) WHERE (principal_id IS NOT NULL);


--
-- Name: issue_assignees_principal_uq; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE UNIQUE INDEX issue_assignees_principal_uq ON public.issue_assignees USING btree (issue_id, principal_id) WHERE (principal_id IS NOT NULL);


--
-- Name: issue_assignees_text_uq; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE UNIQUE INDEX issue_assignees_text_uq ON public.issue_assignees USING btree (issue_id, lower(free_text_assignee)) WHERE (free_text_assignee IS NOT NULL);


--
-- Name: issue_labels_label_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX issue_labels_label_idx ON public.issue_labels USING btree (label_id);


--
-- Name: issue_modules_module_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX issue_modules_module_idx ON public.issue_modules USING btree (module_id);


--
-- Name: issue_subscriptions_principal_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX issue_subscriptions_principal_idx ON public.issue_subscriptions USING btree (principal_id);


--
-- Name: modules_project_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX modules_project_idx ON public.modules USING btree (project_id);


--
-- Name: cycles cycles_spine_match_biu_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER cycles_spine_match_biu_trg BEFORE INSERT OR UPDATE ON public.cycles FOR EACH ROW EXECUTE FUNCTION public.cycles_spine_match_biu();


--
-- Name: issue_assignees issue_assignees_autosubscribe_ai_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER issue_assignees_autosubscribe_ai_trg AFTER INSERT ON public.issue_assignees FOR EACH ROW EXECUTE FUNCTION public.issue_assignees_autosubscribe_ai();


--
-- Name: issue_assignees issue_assignees_guard_bi_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER issue_assignees_guard_bi_trg BEFORE INSERT ON public.issue_assignees FOR EACH ROW EXECUTE FUNCTION public.issue_assignees_guard_bi();


--
-- Name: issue_labels issue_labels_exclusive_bi_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER issue_labels_exclusive_bi_trg BEFORE INSERT ON public.issue_labels FOR EACH ROW EXECUTE FUNCTION public.issue_labels_exclusive_bi();


--
-- Name: issue_modules issue_modules_guard_bi_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER issue_modules_guard_bi_trg BEFORE INSERT ON public.issue_modules FOR EACH ROW EXECUTE FUNCTION public.issue_modules_guard_bi();


--
-- Name: issue_subscriptions issue_subscriptions_guard_bi_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER issue_subscriptions_guard_bi_trg BEFORE INSERT ON public.issue_subscriptions FOR EACH ROW EXECUTE FUNCTION public.issue_subscriptions_guard_bi();


--
-- Name: modules modules_spine_match_biu_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER modules_spine_match_biu_trg BEFORE INSERT OR UPDATE ON public.modules FOR EACH ROW EXECUTE FUNCTION public.modules_spine_match_biu();


--
-- Name: project_module_defaults project_module_defaults_guard_bi_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER project_module_defaults_guard_bi_trg BEFORE INSERT ON public.project_module_defaults FOR EACH ROW EXECUTE FUNCTION public.project_module_defaults_guard_bi();


--
-- Name: cycles cycles_id_object_type_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.cycles
    ADD CONSTRAINT cycles_id_object_type_fkey FOREIGN KEY (id, object_type) REFERENCES public.objects(id, object_type) ON DELETE RESTRICT;


--
-- Name: cycles cycles_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.cycles
    ADD CONSTRAINT cycles_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE RESTRICT;


--
-- Name: issue_assignees issue_assignees_issue_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.issue_assignees
    ADD CONSTRAINT issue_assignees_issue_id_fkey FOREIGN KEY (issue_id) REFERENCES public.issues(id) ON DELETE CASCADE;


--
-- Name: issue_assignees issue_assignees_principal_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.issue_assignees
    ADD CONSTRAINT issue_assignees_principal_id_fkey FOREIGN KEY (principal_id) REFERENCES public.principals(id) ON DELETE RESTRICT;


--
-- Name: issue_labels issue_labels_issue_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.issue_labels
    ADD CONSTRAINT issue_labels_issue_id_fkey FOREIGN KEY (issue_id) REFERENCES public.issues(id) ON DELETE CASCADE;


--
-- Name: issue_labels issue_labels_label_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.issue_labels
    ADD CONSTRAINT issue_labels_label_id_fkey FOREIGN KEY (label_id) REFERENCES public.project_labels(id) ON DELETE CASCADE;


--
-- Name: issue_modules issue_modules_issue_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.issue_modules
    ADD CONSTRAINT issue_modules_issue_id_fkey FOREIGN KEY (issue_id) REFERENCES public.issues(id) ON DELETE CASCADE;


--
-- Name: issue_modules issue_modules_module_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.issue_modules
    ADD CONSTRAINT issue_modules_module_id_fkey FOREIGN KEY (module_id) REFERENCES public.modules(id) ON DELETE CASCADE;


--
-- Name: issue_subscriptions issue_subscriptions_issue_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.issue_subscriptions
    ADD CONSTRAINT issue_subscriptions_issue_id_fkey FOREIGN KEY (issue_id) REFERENCES public.issues(id) ON DELETE CASCADE;


--
-- Name: issue_subscriptions issue_subscriptions_principal_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.issue_subscriptions
    ADD CONSTRAINT issue_subscriptions_principal_id_fkey FOREIGN KEY (principal_id) REFERENCES public.principals(id) ON DELETE CASCADE;


--
-- Name: modules modules_id_object_type_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.modules
    ADD CONSTRAINT modules_id_object_type_fkey FOREIGN KEY (id, object_type) REFERENCES public.objects(id, object_type) ON DELETE RESTRICT;


--
-- Name: modules modules_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.modules
    ADD CONSTRAINT modules_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE RESTRICT;


--
-- Name: project_module_defaults project_module_defaults_module_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.project_module_defaults
    ADD CONSTRAINT project_module_defaults_module_id_fkey FOREIGN KEY (module_id) REFERENCES public.modules(id) ON DELETE CASCADE;


--
-- Name: project_module_defaults project_module_defaults_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.project_module_defaults
    ADD CONSTRAINT project_module_defaults_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE RESTRICT;


--
-- Name: TABLE cycles; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.cycles TO kanban_app;
GRANT SELECT ON TABLE public.cycles TO app_rls_reader;


--
-- Name: TABLE issue_assignees; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.issue_assignees TO kanban_app;
GRANT SELECT ON TABLE public.issue_assignees TO app_rls_reader;


--
-- Name: TABLE issue_labels; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.issue_labels TO kanban_app;
GRANT SELECT ON TABLE public.issue_labels TO app_rls_reader;


--
-- Name: TABLE issue_modules; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.issue_modules TO kanban_app;
GRANT SELECT ON TABLE public.issue_modules TO app_rls_reader;


--
-- Name: TABLE issue_subscriptions; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.issue_subscriptions TO kanban_app;
GRANT SELECT ON TABLE public.issue_subscriptions TO app_rls_reader;


--
-- Name: TABLE modules; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.modules TO kanban_app;
GRANT SELECT ON TABLE public.modules TO app_rls_reader;


--
-- Name: TABLE project_module_defaults; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.project_module_defaults TO kanban_app;
GRANT SELECT ON TABLE public.project_module_defaults TO app_rls_reader;


--
-- PostgreSQL database dump complete
--

\unrestrict al2vlAaeFlFQ0qwLAwQhV7cMbZ8GFtnr0UC5QOaD4ve4EzDkycx6UlLfqNjfFoo

