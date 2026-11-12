--
-- PostgreSQL database dump
--

\restrict K1RURsf74h4ZC6Bn9oBU3y8rtmDlE28LJ6VUyrebxgPD8hRjfcVxzgFNftLcOfx

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
    CONSTRAINT issues_check CHECK (((due_date IS NULL) OR (start_date IS NULL) OR (due_date >= start_date))),
    CONSTRAINT issues_description_markdown_check CHECK ((octet_length(description_markdown) <= 1048576)),
    CONSTRAINT issues_object_type_check CHECK ((object_type = 'issue'::public.object_kind)),
    CONSTRAINT issues_summary_check CHECK (((char_length(btrim(summary)) >= 1) AND (char_length(btrim(summary)) <= 500)))
);


ALTER TABLE public.issues OWNER TO kanban_migrator;

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
-- Name: issues issues_validate_biu_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER issues_validate_biu_trg BEFORE INSERT OR UPDATE ON public.issues FOR EACH ROW EXECUTE FUNCTION public.issues_validate_biu();


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
-- Name: TABLE issues; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.issues TO kanban_app;
GRANT SELECT ON TABLE public.issues TO app_rls_reader;


--
-- PostgreSQL database dump complete
--

\unrestrict K1RURsf74h4ZC6Bn9oBU3y8rtmDlE28LJ6VUyrebxgPD8hRjfcVxzgFNftLcOfx


-- Function definitions
CREATE OR REPLACE FUNCTION public.build_markdown_tsvector(md text)
 RETURNS tsvector
 LANGUAGE plpgsql
 IMMUTABLE PARALLEL SAFE
AS $function$
DECLARE
    v_text text := coalesce(md, '');
BEGIN
    -- 1. Remove fence delimiter lines and their info strings
    v_text := regexp_replace(v_text, '(?m)^\s{0,3}(```|~~~).*$', '', 'g');
    -- 2. Images and links -> link text, reference definitions -> empty
    v_text := regexp_replace(v_text, '!\[([^\]]*)\]\([^)]*\)', '\1', 'g');
    v_text := regexp_replace(v_text, '\[([^\]]*)\]\([^)]*\)', '\1', 'g');
    v_text := regexp_replace(v_text, '(?m)^\s{0,3}\[[^\]]+\]:\s*\S+.*$', '', 'g');
    -- 3. Autolinks and bare URLs -> empty
    v_text := regexp_replace(v_text, '<https?://[^>]+>', '', 'g');
    v_text := regexp_replace(v_text, 'https?://\S+', '', 'g');
    -- 4. Markdown punctuation -> space
    v_text := regexp_replace(v_text, '[#*_>`|~]', ' ', 'g');
    -- 5. Return tsvector
    RETURN to_tsvector('english'::regconfig, v_text);
END;
$function$

CREATE OR REPLACE FUNCTION public.allocate_issue_sequence(p_project_id uuid)
 RETURNS bigint
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    v_seq bigint;
BEGIN
    UPDATE projects SET issue_seq_counter = issue_seq_counter + 1
     WHERE id = p_project_id RETURNING issue_seq_counter INTO v_seq;
    IF v_seq IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'PROJECT_NOT_FOUND';
    END IF;
    RETURN v_seq;
END;
$function$
