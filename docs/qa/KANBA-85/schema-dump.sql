--
-- PostgreSQL database dump
--

\restrict UuShv7voSWalR45dOd8opCZniCPZ8pjBcelnxF9IbNWTyCnhodFZi1f98MgtETA

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
-- Name: comment_reactions; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.comment_reactions (
    comment_id uuid NOT NULL,
    principal_id uuid NOT NULL,
    emoji text NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL
);

ALTER TABLE ONLY public.comment_reactions FORCE ROW LEVEL SECURITY;


ALTER TABLE public.comment_reactions OWNER TO kanban_migrator;

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

ALTER TABLE ONLY public.issue_comments FORCE ROW LEVEL SECURITY;


ALTER TABLE public.issue_comments OWNER TO kanban_migrator;

--
-- Name: comment_reactions comment_reactions_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.comment_reactions
    ADD CONSTRAINT comment_reactions_pkey PRIMARY KEY (comment_id, principal_id, emoji);


--
-- Name: issue_comments issue_comments_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.issue_comments
    ADD CONSTRAINT issue_comments_pkey PRIMARY KEY (id);


--
-- Name: comment_reactions_comment_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX comment_reactions_comment_idx ON public.comment_reactions USING btree (comment_id);


--
-- Name: comment_reactions_principal_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX comment_reactions_principal_idx ON public.comment_reactions USING btree (principal_id);


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
-- Name: issue_comments issue_comments_workspace_biu_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER issue_comments_workspace_biu_trg BEFORE INSERT OR UPDATE ON public.issue_comments FOR EACH ROW EXECUTE FUNCTION public.issue_comments_workspace_biu();


--
-- Name: comment_reactions comment_reactions_comment_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.comment_reactions
    ADD CONSTRAINT comment_reactions_comment_id_fkey FOREIGN KEY (comment_id) REFERENCES public.issue_comments(id) ON DELETE CASCADE;


--
-- Name: comment_reactions comment_reactions_principal_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.comment_reactions
    ADD CONSTRAINT comment_reactions_principal_id_fkey FOREIGN KEY (principal_id) REFERENCES public.principals(id) ON DELETE CASCADE;


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
-- Name: comment_reactions; Type: ROW SECURITY; Schema: public; Owner: kanban_migrator
--

ALTER TABLE public.comment_reactions ENABLE ROW LEVEL SECURITY;

--
-- Name: comment_reactions comment_reactions_delete_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY comment_reactions_delete_rls ON public.comment_reactions FOR DELETE USING (((principal_id = COALESCE((NULLIF(current_setting('app.principal_id'::text, true), ''::text))::uuid, public.app_current_principal_id())) AND (EXISTS ( SELECT 1
   FROM public.issue_comments ic
  WHERE ((ic.id = comment_reactions.comment_id) AND (ic.workspace_id = public.app_current_workspace_id()) AND public.app_has_object_capability(ic.issue_id, 1))))));


--
-- Name: comment_reactions comment_reactions_insert_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY comment_reactions_insert_rls ON public.comment_reactions FOR INSERT WITH CHECK (((principal_id = COALESCE((NULLIF(current_setting('app.principal_id'::text, true), ''::text))::uuid, public.app_current_principal_id())) AND (EXISTS ( SELECT 1
   FROM public.issue_comments ic
  WHERE ((ic.id = comment_reactions.comment_id) AND (ic.workspace_id = public.app_current_workspace_id()) AND public.app_has_object_capability(ic.issue_id, 1))))));


--
-- Name: comment_reactions comment_reactions_select_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY comment_reactions_select_rls ON public.comment_reactions FOR SELECT USING ((EXISTS ( SELECT 1
   FROM public.issue_comments ic
  WHERE ((ic.id = comment_reactions.comment_id) AND (ic.workspace_id = public.app_current_workspace_id()) AND public.app_has_object_capability(ic.issue_id, 1)))));


--
-- Name: issue_comments; Type: ROW SECURITY; Schema: public; Owner: kanban_migrator
--

ALTER TABLE public.issue_comments ENABLE ROW LEVEL SECURITY;

--
-- Name: issue_comments issue_comments_delete_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY issue_comments_delete_rls ON public.issue_comments FOR DELETE USING (((workspace_id = public.app_current_workspace_id()) AND (((author_id = public.app_current_principal_id()) AND public.app_has_object_capability(issue_id, 2)) OR public.app_has_object_capability(issue_id, 64))));


--
-- Name: issue_comments issue_comments_insert_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY issue_comments_insert_rls ON public.issue_comments FOR INSERT WITH CHECK (((workspace_id = public.app_current_workspace_id()) AND (author_id = public.app_current_principal_id()) AND public.app_has_object_capability(issue_id, 2)));


--
-- Name: issue_comments issue_comments_select_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY issue_comments_select_rls ON public.issue_comments FOR SELECT USING (((workspace_id = public.app_current_workspace_id()) AND public.app_has_object_capability(issue_id, 1)));


--
-- Name: issue_comments issue_comments_update_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY issue_comments_update_rls ON public.issue_comments FOR UPDATE USING (((workspace_id = public.app_current_workspace_id()) AND (((author_id = public.app_current_principal_id()) AND public.app_has_object_capability(issue_id, 2)) OR public.app_has_object_capability(issue_id, 64)))) WITH CHECK (((workspace_id = public.app_current_workspace_id()) AND (((author_id = public.app_current_principal_id()) AND public.app_has_object_capability(issue_id, 2)) OR public.app_has_object_capability(issue_id, 64))));


--
-- Name: TABLE comment_reactions; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.comment_reactions TO kanban_app;
GRANT SELECT ON TABLE public.comment_reactions TO app_rls_reader;


--
-- Name: TABLE issue_comments; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.issue_comments TO kanban_app;
GRANT SELECT ON TABLE public.issue_comments TO app_rls_reader;


--
-- PostgreSQL database dump complete
--

\unrestrict UuShv7voSWalR45dOd8opCZniCPZ8pjBcelnxF9IbNWTyCnhodFZi1f98MgtETA

