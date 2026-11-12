--
-- PostgreSQL database dump
--

\restrict zEWdQMdE4jFLfbHP2MKQccVLtGZv5SGqNvaivNOHH9gK7OiJSrar6PEzSOQlERK

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
    CONSTRAINT docs_body_markdown_check CHECK ((octet_length(body_markdown) <= 1048576)),
    CONSTRAINT docs_object_type_check CHECK ((object_type = 'doc'::public.object_kind)),
    CONSTRAINT docs_title_check CHECK (((char_length(btrim(title)) >= 1) AND (char_length(btrim(title)) <= 500)))
);


ALTER TABLE public.docs OWNER TO kanban_migrator;

--
-- Name: issue_comments; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.issue_comments (
    id uuid DEFAULT public.uuidv7() NOT NULL,
    workspace_id uuid NOT NULL,
    issue_id uuid NOT NULL,
    parent_comment_id uuid,
    author_id uuid NOT NULL,
    body_markdown text NOT NULL,
    body_sha256 bytea GENERATED ALWAYS AS (public.digest(body_markdown, 'sha256'::text)) STORED,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    edited_at timestamp with time zone,
    deleted_at timestamp with time zone,
    CONSTRAINT issue_comments_body_markdown_check CHECK (((octet_length(body_markdown) >= 1) AND (octet_length(body_markdown) <= 262144)))
);


ALTER TABLE public.issue_comments OWNER TO kanban_migrator;

--
-- Name: page_versions; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.page_versions (
    page_id uuid NOT NULL,
    version_seq integer NOT NULL,
    workspace_id uuid NOT NULL,
    title text NOT NULL,
    body_markdown text NOT NULL,
    body_sha256 bytea GENERATED ALWAYS AS (public.digest(body_markdown, 'sha256'::text)) STORED,
    created_by_id uuid,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT page_versions_body_markdown_check CHECK ((octet_length(body_markdown) <= 1048576))
);


ALTER TABLE public.page_versions OWNER TO kanban_migrator;

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
    CONSTRAINT pages_body_markdown_check CHECK ((octet_length(body_markdown) <= 1048576)),
    CONSTRAINT pages_hierarchy_path_check CHECK (((public.nlevel(hierarchy_path) >= 2) AND (public.nlevel(hierarchy_path) <= 11))),
    CONSTRAINT pages_object_type_check CHECK ((object_type = 'page'::public.object_kind)),
    CONSTRAINT pages_title_check CHECK (((char_length(btrim(title)) >= 1) AND (char_length(btrim(title)) <= 500)))
);


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
    CONSTRAINT stickies_body_markdown_check CHECK ((octet_length(body_markdown) <= 65536)),
    CONSTRAINT stickies_color_token_check CHECK ((color_token = ANY (ARRAY['amber'::text, 'mint'::text, 'sky'::text, 'lavender'::text, 'coral'::text, 'slate'::text]))),
    CONSTRAINT stickies_object_type_check CHECK ((object_type = 'sticky'::public.object_kind)),
    CONSTRAINT stickies_promotion_snoozed_at_length_check CHECK (((promotion_snoozed_at_length IS NULL) OR (promotion_snoozed_at_length >= 0)))
);


ALTER TABLE public.stickies OWNER TO kanban_migrator;

--
-- Name: docs docs_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.docs
    ADD CONSTRAINT docs_pkey PRIMARY KEY (id);


--
-- Name: issue_comments issue_comments_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.issue_comments
    ADD CONSTRAINT issue_comments_pkey PRIMARY KEY (id);


--
-- Name: page_versions page_versions_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.page_versions
    ADD CONSTRAINT page_versions_pkey PRIMARY KEY (page_id, version_seq);


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
-- Name: docs_workspace_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX docs_workspace_idx ON public.docs USING btree (workspace_id);


--
-- Name: issue_comments_author_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX issue_comments_author_idx ON public.issue_comments USING btree (author_id);


--
-- Name: issue_comments_issue_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX issue_comments_issue_idx ON public.issue_comments USING btree (issue_id);


--
-- Name: issue_comments_parent_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX issue_comments_parent_idx ON public.issue_comments USING btree (parent_comment_id) WHERE (parent_comment_id IS NOT NULL);


--
-- Name: issue_comments_workspace_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX issue_comments_workspace_idx ON public.issue_comments USING btree (workspace_id);


--
-- Name: page_versions_workspace_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX page_versions_workspace_idx ON public.page_versions USING btree (workspace_id);


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
-- Name: pages_workspace_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX pages_workspace_idx ON public.pages USING btree (workspace_id);


--
-- Name: stickies_project_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX stickies_project_idx ON public.stickies USING btree (project_id) WHERE (project_id IS NOT NULL);


--
-- Name: stickies_promoted_doc_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX stickies_promoted_doc_idx ON public.stickies USING btree (promoted_to_doc_id) WHERE (promoted_to_doc_id IS NOT NULL);


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
-- Name: issue_comments issue_comments_workspace_biu_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER issue_comments_workspace_biu_trg BEFORE INSERT OR UPDATE ON public.issue_comments FOR EACH ROW EXECUTE FUNCTION public.issue_comments_workspace_biu();


--
-- Name: page_versions page_versions_immutable_bud_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER page_versions_immutable_bud_trg BEFORE DELETE OR UPDATE ON public.page_versions FOR EACH ROW EXECUTE FUNCTION public.page_versions_immutable_bud();


--
-- Name: pages pages_hierarchy_au_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER pages_hierarchy_au_trg AFTER UPDATE OF parent_page_id, doc_id ON public.pages FOR EACH ROW WHEN ((old.hierarchy_path IS DISTINCT FROM new.hierarchy_path)) EXECUTE FUNCTION public.pages_hierarchy_au();


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
-- Name: issue_comments issue_comments_author_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.issue_comments
    ADD CONSTRAINT issue_comments_author_id_fkey FOREIGN KEY (author_id) REFERENCES public.principals(id) ON DELETE RESTRICT;


--
-- Name: issue_comments issue_comments_issue_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.issue_comments
    ADD CONSTRAINT issue_comments_issue_id_fkey FOREIGN KEY (issue_id) REFERENCES public.issues(id) ON DELETE RESTRICT;


--
-- Name: issue_comments issue_comments_parent_comment_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.issue_comments
    ADD CONSTRAINT issue_comments_parent_comment_id_fkey FOREIGN KEY (parent_comment_id) REFERENCES public.issue_comments(id) ON DELETE RESTRICT;


--
-- Name: issue_comments issue_comments_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.issue_comments
    ADD CONSTRAINT issue_comments_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE RESTRICT;


--
-- Name: page_versions page_versions_created_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.page_versions
    ADD CONSTRAINT page_versions_created_by_id_fkey FOREIGN KEY (created_by_id) REFERENCES public.principals(id) ON DELETE SET NULL;


--
-- Name: page_versions page_versions_page_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.page_versions
    ADD CONSTRAINT page_versions_page_id_fkey FOREIGN KEY (page_id) REFERENCES public.pages(id) ON DELETE CASCADE;


--
-- Name: page_versions page_versions_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.page_versions
    ADD CONSTRAINT page_versions_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE RESTRICT;


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
-- Name: TABLE docs; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.docs TO kanban_app;
GRANT SELECT ON TABLE public.docs TO app_rls_reader;


--
-- Name: TABLE issue_comments; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.issue_comments TO kanban_app;
GRANT SELECT ON TABLE public.issue_comments TO app_rls_reader;


--
-- Name: TABLE page_versions; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.page_versions TO kanban_app;
GRANT SELECT ON TABLE public.page_versions TO app_rls_reader;


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

\unrestrict zEWdQMdE4jFLfbHP2MKQccVLtGZv5SGqNvaivNOHH9gK7OiJSrar6PEzSOQlERK

