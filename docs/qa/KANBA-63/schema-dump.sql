--
-- PostgreSQL database dump
--

\restrict pgKK0l2tWn5wmsb4CSpEUQdRKxfffsDprcUzNfUYqEq390oOSt4kpRQsN2EnNhB

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
-- Name: object_embeddings; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.object_embeddings (
    object_id uuid NOT NULL,
    object_type public.object_kind NOT NULL,
    chunk_index smallint NOT NULL,
    workspace_id uuid NOT NULL,
    project_id uuid,
    content_sha256 bytea NOT NULL,
    model_id text NOT NULL,
    embedding public.vector(384) NOT NULL,
    updated_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT object_embeddings_chunk_index_check CHECK (((chunk_index >= 0) AND (chunk_index <= 63))),
    CONSTRAINT object_embeddings_content_sha256_check CHECK ((octet_length(content_sha256) = 32))
);

ALTER TABLE ONLY public.object_embeddings FORCE ROW LEVEL SECURITY;


ALTER TABLE public.object_embeddings OWNER TO kanban_migrator;

--
-- Name: object_embeddings object_embeddings_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.object_embeddings
    ADD CONSTRAINT object_embeddings_pkey PRIMARY KEY (object_id, chunk_index);


--
-- Name: object_embeddings_hnsw; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX object_embeddings_hnsw ON public.object_embeddings USING hnsw (embedding public.vector_cosine_ops) WITH (m='16', ef_construction='64');


--
-- Name: object_embeddings_scope; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX object_embeddings_scope ON public.object_embeddings USING btree (workspace_id, project_id);


--
-- Name: object_embeddings object_embeddings_set_updated_at; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER object_embeddings_set_updated_at BEFORE UPDATE ON public.object_embeddings FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: object_embeddings object_embeddings_object_id_object_type_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.object_embeddings
    ADD CONSTRAINT object_embeddings_object_id_object_type_fkey FOREIGN KEY (object_id, object_type) REFERENCES public.objects(id, object_type) ON DELETE CASCADE;


--
-- Name: object_embeddings object_embeddings_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.object_embeddings
    ADD CONSTRAINT object_embeddings_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;


--
-- Name: object_embeddings; Type: ROW SECURITY; Schema: public; Owner: kanban_migrator
--

ALTER TABLE public.object_embeddings ENABLE ROW LEVEL SECURITY;

--
-- Name: object_embeddings object_embeddings_delete_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY object_embeddings_delete_rls ON public.object_embeddings FOR DELETE USING (((workspace_id = public.app_current_workspace_id()) AND (public.app_current_principal_id() IS NOT NULL) AND (public.app_current_principal_id() = public.app_embedding_indexer_principal())));


--
-- Name: object_embeddings object_embeddings_insert_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY object_embeddings_insert_rls ON public.object_embeddings FOR INSERT WITH CHECK (((workspace_id = public.app_current_workspace_id()) AND (public.app_current_principal_id() IS NOT NULL) AND (public.app_current_principal_id() = public.app_embedding_indexer_principal())));


--
-- Name: object_embeddings object_embeddings_select_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY object_embeddings_select_rls ON public.object_embeddings FOR SELECT USING (((workspace_id = public.app_current_workspace_id()) AND (EXISTS ( SELECT 1
   FROM public.effective_resource_access era
  WHERE ((era.object_id = object_embeddings.object_id) AND (era.principal_id = ANY (public.app_effective_principal_set())) AND ((era.allow_mask & 1) = 1) AND ((era.deny_mask & 1) = 0))))));


--
-- Name: object_embeddings object_embeddings_update_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY object_embeddings_update_rls ON public.object_embeddings FOR UPDATE USING (((workspace_id = public.app_current_workspace_id()) AND (public.app_current_principal_id() IS NOT NULL) AND (public.app_current_principal_id() = public.app_embedding_indexer_principal()))) WITH CHECK (((workspace_id = public.app_current_workspace_id()) AND (public.app_current_principal_id() IS NOT NULL) AND (public.app_current_principal_id() = public.app_embedding_indexer_principal())));


--
-- Name: TABLE object_embeddings; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.object_embeddings TO kanban_app;
GRANT SELECT ON TABLE public.object_embeddings TO app_rls_reader;


--
-- PostgreSQL database dump complete
--

\unrestrict pgKK0l2tWn5wmsb4CSpEUQdRKxfffsDprcUzNfUYqEq390oOSt4kpRQsN2EnNhB

