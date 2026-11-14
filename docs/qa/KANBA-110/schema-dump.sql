--
-- PostgreSQL database dump
--

\restrict 6p9kEGc9pa7Pvhw8n9yHNifUVfI5LbWeTtQj97J3EM46lIW5e7kiBLXeCZM1Y28

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
-- Name: docs; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.docs (
    id uuid NOT NULL,
    object_type public.object_kind DEFAULT 'doc'::public.object_kind NOT NULL,
    workspace_id uuid NOT NULL,
    project_id uuid,
    title text NOT NULL,
    body_markdown text DEFAULT ''::text NOT NULL,
    body_sha256 bytea GENERATED ALWAYS AS (public.digest(body_markdown, 'sha256'::text)) STORED,
    hierarchy_path public.ltree NOT NULL,
    version_seq integer DEFAULT 1 NOT NULL,
    search_tsv tsvector GENERATED ALWAYS AS ((setweight(to_tsvector('english'::regconfig, COALESCE(title, ''::text)), 'A'::"char") || setweight(public.build_markdown_tsvector(body_markdown), 'B'::"char"))) STORED,
    CONSTRAINT docs_body_markdown_check CHECK ((octet_length(body_markdown) <= 1048576)),
    CONSTRAINT docs_object_type_check CHECK ((object_type = 'doc'::public.object_kind)),
    CONSTRAINT docs_title_check CHECK (((char_length(btrim(title)) >= 1) AND (char_length(btrim(title)) <= 500)))
);

ALTER TABLE ONLY public.docs FORCE ROW LEVEL SECURITY;


ALTER TABLE public.docs OWNER TO kanban_migrator;

--
-- Name: issues; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.issues (
    id uuid NOT NULL,
    object_type public.object_kind DEFAULT 'issue'::public.object_kind NOT NULL,
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    sequence_id bigint NOT NULL,
    summary text NOT NULL,
    description_markdown text DEFAULT ''::text NOT NULL,
    description_sha256 bytea GENERATED ALWAYS AS (public.digest(description_markdown, 'sha256'::text)) STORED,
    state_id uuid NOT NULL,
    pending_transition_exec_id uuid,
    priority_id uuid NOT NULL,
    created_by_id uuid NOT NULL,
    original_created_by_id uuid NOT NULL,
    creator_modified_by_id uuid,
    creator_modified_at timestamp with time zone,
    start_date date,
    due_date date,
    cycle_id uuid,
    parent_issue_id uuid,
    ancestry_path public.ltree NOT NULL,
    board_rank text NOT NULL COLLATE pg_catalog."C",
    search_tsv tsvector GENERATED ALWAYS AS ((setweight(to_tsvector('english'::regconfig, COALESCE(summary, ''::text)), 'A'::"char") || setweight(public.build_markdown_tsvector(description_markdown), 'B'::"char"))) STORED,
    CONSTRAINT issues_ancestry_depth_chk CHECK (((public.nlevel(ancestry_path) >= 1) AND (public.nlevel(ancestry_path) <= 6))),
    CONSTRAINT issues_check CHECK (((due_date IS NULL) OR (start_date IS NULL) OR (due_date >= start_date))),
    CONSTRAINT issues_description_markdown_check CHECK ((octet_length(description_markdown) <= 1048576)),
    CONSTRAINT issues_object_type_check CHECK ((object_type = 'issue'::public.object_kind)),
    CONSTRAINT issues_summary_check CHECK (((char_length(btrim(summary)) >= 1) AND (char_length(btrim(summary)) <= 500)))
);

ALTER TABLE ONLY public.issues FORCE ROW LEVEL SECURITY;


ALTER TABLE public.issues OWNER TO kanban_migrator;

--
-- Name: pages; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.pages (
    id uuid NOT NULL,
    object_type public.object_kind DEFAULT 'page'::public.object_kind NOT NULL,
    workspace_id uuid NOT NULL,
    doc_id uuid NOT NULL,
    parent_page_id uuid,
    title text NOT NULL,
    body_markdown text DEFAULT ''::text NOT NULL,
    body_sha256 bytea GENERATED ALWAYS AS (public.digest(body_markdown, 'sha256'::text)) STORED,
    hierarchy_path public.ltree NOT NULL,
    version_seq integer DEFAULT 1 NOT NULL,
    sort_rank text DEFAULT 'a0'::text NOT NULL COLLATE pg_catalog."C",
    search_tsv tsvector GENERATED ALWAYS AS ((setweight(to_tsvector('english'::regconfig, COALESCE(title, ''::text)), 'A'::"char") || setweight(public.build_markdown_tsvector(body_markdown), 'B'::"char"))) STORED,
    CONSTRAINT pages_body_markdown_check CHECK ((octet_length(body_markdown) <= 1048576)),
    CONSTRAINT pages_hierarchy_path_check CHECK (((public.nlevel(hierarchy_path) >= 2) AND (public.nlevel(hierarchy_path) <= 11))),
    CONSTRAINT pages_object_type_check CHECK ((object_type = 'page'::public.object_kind)),
    CONSTRAINT pages_title_check CHECK (((char_length(btrim(title)) >= 1) AND (char_length(btrim(title)) <= 500)))
);

ALTER TABLE ONLY public.pages FORCE ROW LEVEL SECURITY;


ALTER TABLE public.pages OWNER TO kanban_migrator;

--
-- Name: stickies; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.stickies (
    id uuid NOT NULL,
    object_type public.object_kind DEFAULT 'sticky'::public.object_kind NOT NULL,
    workspace_id uuid NOT NULL,
    project_id uuid,
    body_markdown text DEFAULT ''::text NOT NULL,
    body_sha256 bytea GENERATED ALWAYS AS (public.digest(body_markdown, 'sha256'::text)) STORED,
    color_token text DEFAULT 'amber'::text NOT NULL,
    promotion_recommended boolean DEFAULT false NOT NULL,
    promotion_snoozed_at_length integer,
    promoted_to_doc_id uuid,
    sort_rank text DEFAULT 'a0'::text NOT NULL COLLATE pg_catalog."C",
    search_tsv tsvector GENERATED ALWAYS AS (public.build_markdown_tsvector(body_markdown)) STORED,
    CONSTRAINT stickies_body_markdown_check CHECK ((octet_length(body_markdown) <= 65536)),
    CONSTRAINT stickies_color_token_check CHECK ((color_token = ANY (ARRAY['amber'::text, 'mint'::text, 'sky'::text, 'lavender'::text, 'coral'::text, 'slate'::text]))),
    CONSTRAINT stickies_object_type_check CHECK ((object_type = 'sticky'::public.object_kind)),
    CONSTRAINT stickies_promotion_snoozed_at_length_check CHECK (((promotion_snoozed_at_length IS NULL) OR (promotion_snoozed_at_length >= 0)))
);

ALTER TABLE ONLY public.stickies FORCE ROW LEVEL SECURITY;


ALTER TABLE public.stickies OWNER TO kanban_migrator;

--
-- Name: docs docs_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.docs
    ADD CONSTRAINT docs_pkey PRIMARY KEY (id);


--
-- Name: issues issues_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.issues
    ADD CONSTRAINT issues_pkey PRIMARY KEY (id);


--
-- Name: issues issues_project_id_sequence_id_key; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.issues
    ADD CONSTRAINT issues_project_id_sequence_id_key UNIQUE (project_id, sequence_id);


--
-- Name: pages pages_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.pages
    ADD CONSTRAINT pages_pkey PRIMARY KEY (id);


--
-- Name: stickies stickies_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.stickies
    ADD CONSTRAINT stickies_pkey PRIMARY KEY (id);


--
-- Name: docs_hierarchy_gist; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX docs_hierarchy_gist ON public.docs USING gist (hierarchy_path);


--
-- Name: docs_project_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX docs_project_idx ON public.docs USING btree (project_id) WHERE (project_id IS NOT NULL);


--
-- Name: docs_search_tsv_gin; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX docs_search_tsv_gin ON public.docs USING gin (search_tsv);


--
-- Name: docs_title_trgm_gin; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX docs_title_trgm_gin ON public.docs USING gin (title public.gin_trgm_ops);


--
-- Name: docs_workspace_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX docs_workspace_idx ON public.docs USING btree (workspace_id);


--
-- Name: issues_ancestry_gist; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX issues_ancestry_gist ON public.issues USING gist (ancestry_path);


--
-- Name: issues_parent_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX issues_parent_idx ON public.issues USING btree (parent_issue_id) WHERE (parent_issue_id IS NOT NULL);


--
-- Name: issues_project_rank_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX issues_project_rank_idx ON public.issues USING btree (project_id, state_id, board_rank);


--
-- Name: issues_search_tsv_gin; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX issues_search_tsv_gin ON public.issues USING gin (search_tsv);


--
-- Name: issues_summary_trgm_gin; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX issues_summary_trgm_gin ON public.issues USING gin (summary public.gin_trgm_ops);


--
-- Name: pages_doc_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX pages_doc_idx ON public.pages USING btree (doc_id);


--
-- Name: pages_hierarchy_gist; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX pages_hierarchy_gist ON public.pages USING gist (hierarchy_path);


--
-- Name: pages_parent_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX pages_parent_idx ON public.pages USING btree (parent_page_id) WHERE (parent_page_id IS NOT NULL);


--
-- Name: pages_search_tsv_gin; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX pages_search_tsv_gin ON public.pages USING gin (search_tsv);


--
-- Name: pages_title_trgm_gin; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX pages_title_trgm_gin ON public.pages USING gin (title public.gin_trgm_ops);


--
-- Name: pages_workspace_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX pages_workspace_idx ON public.pages USING btree (workspace_id);


--
-- Name: stickies_body_trgm_gin; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX stickies_body_trgm_gin ON public.stickies USING gin (body_markdown public.gin_trgm_ops);


--
-- Name: stickies_project_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX stickies_project_idx ON public.stickies USING btree (project_id) WHERE (project_id IS NOT NULL);


--
-- Name: stickies_promoted_doc_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX stickies_promoted_doc_idx ON public.stickies USING btree (promoted_to_doc_id) WHERE (promoted_to_doc_id IS NOT NULL);


--
-- Name: stickies_search_tsv_gin; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX stickies_search_tsv_gin ON public.stickies USING gin (search_tsv);


--
-- Name: stickies_workspace_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX stickies_workspace_idx ON public.stickies USING btree (workspace_id);


--
-- Name: docs docs_hierarchy_bi_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER docs_hierarchy_bi_trg BEFORE INSERT ON public.docs FOR EACH ROW EXECUTE FUNCTION public.docs_hierarchy_bi();


--
-- Name: docs docs_spine_match_biu_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER docs_spine_match_biu_trg BEFORE INSERT OR UPDATE ON public.docs FOR EACH ROW EXECUTE FUNCTION public.docs_spine_match_biu();


--
-- Name: docs docs_versioning_bu_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER docs_versioning_bu_trg BEFORE UPDATE ON public.docs FOR EACH ROW EXECUTE FUNCTION public.docs_versioning_bu();


--
-- Name: issues issues_apply_module_defaults_ai_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER issues_apply_module_defaults_ai_trg AFTER INSERT ON public.issues FOR EACH ROW EXECUTE FUNCTION public.issues_apply_module_defaults_ai();


--
-- Name: issues issues_autosubscribe_creator_ai_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER issues_autosubscribe_creator_ai_trg AFTER INSERT ON public.issues FOR EACH ROW EXECUTE FUNCTION public.issues_autosubscribe_creator_ai();


--
-- Name: issues issues_creator_insert_bi_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER issues_creator_insert_bi_trg BEFORE INSERT ON public.issues FOR EACH ROW EXECUTE FUNCTION public.issues_creator_insert_bi();


--
-- Name: issues issues_creator_provenance_bu_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER issues_creator_provenance_bu_trg BEFORE UPDATE OF created_by_id, original_created_by_id, creator_modified_by_id, creator_modified_at ON public.issues FOR EACH ROW EXECUTE FUNCTION public.issues_creator_provenance_bu();


--
-- Name: issues issues_cycle_project_biu_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER issues_cycle_project_biu_trg BEFORE INSERT OR UPDATE OF cycle_id ON public.issues FOR EACH ROW EXECUTE FUNCTION public.issues_cycle_project_biu();


--
-- Name: issues issues_parent_dag_au_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER issues_parent_dag_au_trg AFTER UPDATE OF parent_issue_id ON public.issues FOR EACH ROW WHEN ((old.parent_issue_id IS DISTINCT FROM new.parent_issue_id)) EXECUTE FUNCTION public.issues_parent_dag_au();


--
-- Name: issues issues_parent_dag_biu_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER issues_parent_dag_biu_trg BEFORE INSERT OR UPDATE OF parent_issue_id ON public.issues FOR EACH ROW EXECUTE FUNCTION public.issues_parent_dag_biu();


--
-- Name: TRIGGER issues_parent_dag_biu_trg ON issues; Type: COMMENT; Schema: public; Owner: kanban_migrator
--

COMMENT ON TRIGGER issues_parent_dag_biu_trg ON public.issues IS 'Enforces tree hierarchy, acquires top-down FOR UPDATE ancestor locks, and rejects cycles and depths > 6. Concurrent opposite reparenting may raise 40P01 deadlock_detected which safely aborts one transaction.';


--
-- Name: issues issues_validate_biu_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER issues_validate_biu_trg BEFORE INSERT OR UPDATE ON public.issues FOR EACH ROW EXECUTE FUNCTION public.issues_validate_biu();


--
-- Name: pages pages_hierarchy_au_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER pages_hierarchy_au_trg AFTER UPDATE OF parent_page_id, doc_id ON public.pages FOR EACH ROW WHEN (((old.parent_page_id IS DISTINCT FROM new.parent_page_id) OR (old.doc_id IS DISTINCT FROM new.doc_id))) EXECUTE FUNCTION public.pages_hierarchy_au();


--
-- Name: pages pages_hierarchy_biu_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER pages_hierarchy_biu_trg BEFORE INSERT OR UPDATE OF parent_page_id, doc_id ON public.pages FOR EACH ROW EXECUTE FUNCTION public.pages_hierarchy_biu();


--
-- Name: pages pages_spine_match_biu_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER pages_spine_match_biu_trg BEFORE INSERT OR UPDATE ON public.pages FOR EACH ROW EXECUTE FUNCTION public.pages_spine_match_biu();


--
-- Name: pages pages_versioning_bu_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER pages_versioning_bu_trg BEFORE UPDATE ON public.pages FOR EACH ROW EXECUTE FUNCTION public.pages_versioning_bu();


--
-- Name: stickies stickies_promotion_guard_bu_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER stickies_promotion_guard_bu_trg BEFORE UPDATE ON public.stickies FOR EACH ROW EXECUTE FUNCTION public.stickies_promotion_guard_bu();


--
-- Name: stickies stickies_spine_match_biu_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER stickies_spine_match_biu_trg BEFORE INSERT OR UPDATE ON public.stickies FOR EACH ROW EXECUTE FUNCTION public.stickies_spine_match_biu();


--
-- Name: docs docs_id_object_type_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.docs
    ADD CONSTRAINT docs_id_object_type_fkey FOREIGN KEY (id, object_type) REFERENCES public.objects(id, object_type) ON DELETE RESTRICT;


--
-- Name: docs docs_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.docs
    ADD CONSTRAINT docs_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE RESTRICT;


--
-- Name: docs docs_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.docs
    ADD CONSTRAINT docs_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE RESTRICT;


--
-- Name: issues issues_created_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.issues
    ADD CONSTRAINT issues_created_by_id_fkey FOREIGN KEY (created_by_id) REFERENCES public.users(id);


--
-- Name: issues issues_creator_modified_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.issues
    ADD CONSTRAINT issues_creator_modified_by_id_fkey FOREIGN KEY (creator_modified_by_id) REFERENCES public.users(id);


--
-- Name: issues issues_cycle_fk; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.issues
    ADD CONSTRAINT issues_cycle_fk FOREIGN KEY (cycle_id) REFERENCES public.cycles(id) ON DELETE SET NULL;


--
-- Name: issues issues_id_object_type_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.issues
    ADD CONSTRAINT issues_id_object_type_fkey FOREIGN KEY (id, object_type) REFERENCES public.objects(id, object_type) ON DELETE RESTRICT;


--
-- Name: issues issues_original_created_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.issues
    ADD CONSTRAINT issues_original_created_by_id_fkey FOREIGN KEY (original_created_by_id) REFERENCES public.users(id);


--
-- Name: issues issues_parent_issue_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.issues
    ADD CONSTRAINT issues_parent_issue_id_fkey FOREIGN KEY (parent_issue_id) REFERENCES public.issues(id) ON DELETE SET NULL;


--
-- Name: issues issues_priority_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.issues
    ADD CONSTRAINT issues_priority_id_fkey FOREIGN KEY (priority_id) REFERENCES public.project_priorities(id);


--
-- Name: issues issues_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.issues
    ADD CONSTRAINT issues_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE RESTRICT;


--
-- Name: issues issues_state_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.issues
    ADD CONSTRAINT issues_state_id_fkey FOREIGN KEY (state_id) REFERENCES public.workflow_states(id);


--
-- Name: pages pages_doc_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.pages
    ADD CONSTRAINT pages_doc_id_fkey FOREIGN KEY (doc_id) REFERENCES public.docs(id) ON DELETE RESTRICT;


--
-- Name: pages pages_id_object_type_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.pages
    ADD CONSTRAINT pages_id_object_type_fkey FOREIGN KEY (id, object_type) REFERENCES public.objects(id, object_type) ON DELETE RESTRICT;


--
-- Name: pages pages_parent_page_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.pages
    ADD CONSTRAINT pages_parent_page_id_fkey FOREIGN KEY (parent_page_id) REFERENCES public.pages(id) ON DELETE RESTRICT;


--
-- Name: pages pages_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.pages
    ADD CONSTRAINT pages_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE RESTRICT;


--
-- Name: stickies stickies_id_object_type_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.stickies
    ADD CONSTRAINT stickies_id_object_type_fkey FOREIGN KEY (id, object_type) REFERENCES public.objects(id, object_type) ON DELETE RESTRICT;


--
-- Name: stickies stickies_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.stickies
    ADD CONSTRAINT stickies_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE RESTRICT;


--
-- Name: stickies stickies_promoted_to_doc_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.stickies
    ADD CONSTRAINT stickies_promoted_to_doc_id_fkey FOREIGN KEY (promoted_to_doc_id) REFERENCES public.docs(id) ON DELETE SET NULL;


--
-- Name: stickies stickies_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.stickies
    ADD CONSTRAINT stickies_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE RESTRICT;


--
-- Name: docs; Type: ROW SECURITY; Schema: public; Owner: kanban_migrator
--

ALTER TABLE public.docs ENABLE ROW LEVEL SECURITY;

--
-- Name: docs docs_delete_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY docs_delete_rls ON public.docs FOR DELETE USING (((workspace_id = public.app_current_workspace_id()) AND public.app_has_object_capability(id, 128)));


--
-- Name: docs docs_insert_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY docs_insert_rls ON public.docs FOR INSERT WITH CHECK (((workspace_id = public.app_current_workspace_id()) AND ((project_id IS NULL) OR public.app_has_object_capability(project_id, 4))));


--
-- Name: docs docs_select_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY docs_select_rls ON public.docs FOR SELECT USING (((workspace_id = public.app_current_workspace_id()) AND public.app_has_object_capability(id, 1)));


--
-- Name: docs docs_update_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY docs_update_rls ON public.docs FOR UPDATE USING (((workspace_id = public.app_current_workspace_id()) AND public.app_has_object_capability(id, 4))) WITH CHECK (((workspace_id = public.app_current_workspace_id()) AND public.app_has_object_capability(id, 4)));


--
-- Name: issues; Type: ROW SECURITY; Schema: public; Owner: kanban_migrator
--

ALTER TABLE public.issues ENABLE ROW LEVEL SECURITY;

--
-- Name: issues issues_delete_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY issues_delete_rls ON public.issues FOR DELETE USING (((workspace_id = public.app_current_workspace_id()) AND public.app_has_object_capability(id, 128)));


--
-- Name: issues issues_insert_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY issues_insert_rls ON public.issues FOR INSERT WITH CHECK (((workspace_id = public.app_current_workspace_id()) AND public.app_has_object_capability(project_id, 4)));


--
-- Name: issues issues_select_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY issues_select_rls ON public.issues FOR SELECT USING (((workspace_id = public.app_current_workspace_id()) AND public.app_has_object_capability(id, 1)));


--
-- Name: issues issues_update_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY issues_update_rls ON public.issues FOR UPDATE USING (((workspace_id = public.app_current_workspace_id()) AND public.app_has_object_capability(id, 1))) WITH CHECK (((workspace_id = public.app_current_workspace_id()) AND (public.app_has_object_capability(id, 4) OR public.app_has_object_capability(id, 8))));


--
-- Name: pages; Type: ROW SECURITY; Schema: public; Owner: kanban_migrator
--

ALTER TABLE public.pages ENABLE ROW LEVEL SECURITY;

--
-- Name: pages pages_delete_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY pages_delete_rls ON public.pages FOR DELETE USING (((workspace_id = public.app_current_workspace_id()) AND public.app_has_object_capability(id, 128)));


--
-- Name: pages pages_insert_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY pages_insert_rls ON public.pages FOR INSERT WITH CHECK (((workspace_id = public.app_current_workspace_id()) AND public.app_has_object_capability(doc_id, 4)));


--
-- Name: pages pages_select_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY pages_select_rls ON public.pages FOR SELECT USING (((workspace_id = public.app_current_workspace_id()) AND public.app_has_object_capability(id, 1)));


--
-- Name: pages pages_update_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY pages_update_rls ON public.pages FOR UPDATE USING (((workspace_id = public.app_current_workspace_id()) AND public.app_has_object_capability(id, 4))) WITH CHECK (((workspace_id = public.app_current_workspace_id()) AND public.app_has_object_capability(id, 4)));


--
-- Name: stickies; Type: ROW SECURITY; Schema: public; Owner: kanban_migrator
--

ALTER TABLE public.stickies ENABLE ROW LEVEL SECURITY;

--
-- Name: stickies stickies_delete_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY stickies_delete_rls ON public.stickies FOR DELETE USING (((workspace_id = public.app_current_workspace_id()) AND public.app_has_object_capability(id, 128)));


--
-- Name: stickies stickies_insert_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY stickies_insert_rls ON public.stickies FOR INSERT WITH CHECK (((workspace_id = public.app_current_workspace_id()) AND ((project_id IS NULL) OR public.app_has_object_capability(project_id, 4))));


--
-- Name: stickies stickies_select_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY stickies_select_rls ON public.stickies FOR SELECT USING (((workspace_id = public.app_current_workspace_id()) AND public.app_has_object_capability(id, 1)));


--
-- Name: stickies stickies_update_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY stickies_update_rls ON public.stickies FOR UPDATE USING (((workspace_id = public.app_current_workspace_id()) AND public.app_has_object_capability(id, 4))) WITH CHECK (((workspace_id = public.app_current_workspace_id()) AND public.app_has_object_capability(id, 4)));


--
-- Name: TABLE docs; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.docs TO kanban_app;
GRANT SELECT ON TABLE public.docs TO app_rls_reader;


--
-- Name: TABLE issues; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.issues TO kanban_app;
GRANT SELECT ON TABLE public.issues TO app_rls_reader;


--
-- Name: TABLE pages; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.pages TO kanban_app;
GRANT SELECT ON TABLE public.pages TO app_rls_reader;


--
-- Name: TABLE stickies; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.stickies TO kanban_app;
GRANT SELECT ON TABLE public.stickies TO app_rls_reader;


--
-- PostgreSQL database dump complete
--

\unrestrict 6p9kEGc9pa7Pvhw8n9yHNifUVfI5LbWeTtQj97J3EM46lIW5e7kiBLXeCZM1Y28

