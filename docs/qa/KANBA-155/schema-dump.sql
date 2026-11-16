-- ============================================================================
-- 👍kanban KANBA-155 Schema Forensic Proof
-- Tables: remote_runner_enrollment_tokens, remote_runners
-- Invariants: ENABLE RLS, FORCE RLS, UUIDv7 PK, SHA-256 cert fingerprint UQ
-- ============================================================================

-- 1. Table Definitions
                                                  Table "public.remote_runner_enrollment_tokens"
        Column         |           Type           | Collation | Nullable |      Default      | Storage  | Compression | Stats target | Description 
-----------------------+--------------------------+-----------+----------+-------------------+----------+-------------+--------------+-------------
 id                    | uuid                     |           | not null | uuidv7()          | plain    |             |              | 
 workspace_id          | uuid                     |           | not null |                   | plain    |             |              | 
 pool_slug             | text                     |           | not null |                   | extended |             |              | 
 token_sha256          | bytea                    |           | not null |                   | extended |             |              | 
 created_by_id         | uuid                     |           | not null |                   | plain    |             |              | 
 expires_at            | timestamp with time zone |           | not null |                   | plain    |             |              | 
 consumed_at           | timestamp with time zone |           |          |                   | plain    |             |              | 
 consumed_by_runner_id | uuid                     |           |          |                   | plain    |             |              | 
 created_at            | timestamp with time zone |           | not null | clock_timestamp() | plain    |             |              | 
Indexes:
    "remote_runner_enrollment_tokens_pkey" PRIMARY KEY, btree (id)
    "idx_remote_runner_tokens_workspace_pool" btree (workspace_id, pool_slug)
    "remote_runner_enrollment_tokens_token_sha256_key" UNIQUE CONSTRAINT, btree (token_sha256)
Check constraints:
    "remote_runner_enrollment_tokens_pool_slug_check" CHECK (pool_slug ~ '^[a-z0-9][a-z0-9-]{1,62}$'::text)
    "remote_runner_enrollment_tokens_token_sha256_check" CHECK (octet_length(token_sha256) = 32)
Foreign-key constraints:
    "remote_runner_enrollment_tokens_created_by_id_fkey" FOREIGN KEY (created_by_id) REFERENCES principals(id)
    "remote_runner_enrollment_tokens_workspace_id_fkey" FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
Policies (forced row security enabled):
    POLICY "remote_runner_enrollment_tokens_delete_rls" FOR DELETE
      USING (((workspace_id = app_current_workspace_id()) AND app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text])))
    POLICY "remote_runner_enrollment_tokens_insert_rls" FOR INSERT
      WITH CHECK (((workspace_id = app_current_workspace_id()) AND app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text])))
    POLICY "remote_runner_enrollment_tokens_select_rls" FOR SELECT
      USING (((workspace_id = app_current_workspace_id()) AND app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text])))
    POLICY "remote_runner_enrollment_tokens_update_rls" FOR UPDATE
      USING (((workspace_id = app_current_workspace_id()) AND app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text])))
      WITH CHECK (((workspace_id = app_current_workspace_id()) AND app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text])))
Access method: heap

                                                         Table "public.remote_runners"
       Column       |           Type           | Collation | Nullable |      Default      | Storage  | Compression | Stats target | Description 
--------------------+--------------------------+-----------+----------+-------------------+----------+-------------+--------------+-------------
 id                 | uuid                     |           | not null | uuidv7()          | plain    |             |              | 
 workspace_id       | uuid                     |           | not null |                   | plain    |             |              | 
 pool_slug          | text                     |           | not null |                   | extended |             |              | 
 hostname           | text                     |           | not null |                   | extended |             |              | 
 client_cert_sha256 | bytea                    |           | not null |                   | extended |             |              | 
 cert_expires_at    | timestamp with time zone |           | not null |                   | plain    |             |              | 
 capabilities_json  | jsonb                    |           | not null | '{}'::jsonb       | extended |             |              | 
 status             | text                     |           | not null | 'offline'::text   | extended |             |              | 
 last_heartbeat_at  | timestamp with time zone |           |          |                   | plain    |             |              | 
 revoked_at         | timestamp with time zone |           |          |                   | plain    |             |              | 
 revoked_by_id      | uuid                     |           |          |                   | plain    |             |              | 
 created_at         | timestamp with time zone |           | not null | clock_timestamp() | plain    |             |              | 
Indexes:
    "remote_runners_pkey" PRIMARY KEY, btree (id)
    "idx_remote_runners_client_cert_sha256" btree (client_cert_sha256)
    "idx_remote_runners_workspace_pool" btree (workspace_id, pool_slug, status)
    "remote_runners_client_cert_sha256_key" UNIQUE CONSTRAINT, btree (client_cert_sha256)
Check constraints:
    "remote_runners_client_cert_sha256_check" CHECK (octet_length(client_cert_sha256) = 32)
    "remote_runners_hostname_check" CHECK (char_length(btrim(hostname)) >= 1 AND char_length(btrim(hostname)) <= 253)
    "remote_runners_pool_slug_check" CHECK (pool_slug ~ '^[a-z0-9][a-z0-9-]{1,62}$'::text)
    "remote_runners_status_check" CHECK (status = ANY (ARRAY['online'::text, 'offline'::text, 'revoked'::text]))
Foreign-key constraints:
    "remote_runners_revoked_by_id_fkey" FOREIGN KEY (revoked_by_id) REFERENCES principals(id)
    "remote_runners_workspace_id_fkey" FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
Policies (forced row security enabled):
    POLICY "remote_runners_delete_rls" FOR DELETE
      USING (((workspace_id = app_current_workspace_id()) AND app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text])))
    POLICY "remote_runners_insert_rls" FOR INSERT
      WITH CHECK (((workspace_id = app_current_workspace_id()) AND app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text])))
    POLICY "remote_runners_select_rls" FOR SELECT
      USING (((workspace_id = app_current_workspace_id()) AND app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text])))
    POLICY "remote_runners_update_rls" FOR UPDATE
      USING (((workspace_id = app_current_workspace_id()) AND app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text])))
      WITH CHECK (((workspace_id = app_current_workspace_id()) AND app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text])))
Access method: heap


-- 2. Row-Level Security Verification (ENABLE RLS + FORCE RLS)
             relname             | relrowsecurity | relforcerowsecurity 
---------------------------------+----------------+---------------------
 remote_runner_enrollment_tokens | t              | t
 remote_runners                  | t              | t
(2 rows)


-- 3. Tenant Isolation RLS Policies
 schemaname |            tablename            |                 policyname                 | permissive |  roles   |  cmd   |                                                                    qual                                                                    |                                                                 with_check                                                                 
------------+---------------------------------+--------------------------------------------+------------+----------+--------+--------------------------------------------------------------------------------------------------------------------------------------------+--------------------------------------------------------------------------------------------------------------------------------------------
 public     | remote_runner_enrollment_tokens | remote_runner_enrollment_tokens_delete_rls | PERMISSIVE | {public} | DELETE | ((workspace_id = app_current_workspace_id()) AND app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text])) | 
 public     | remote_runner_enrollment_tokens | remote_runner_enrollment_tokens_insert_rls | PERMISSIVE | {public} | INSERT |                                                                                                                                            | ((workspace_id = app_current_workspace_id()) AND app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text]))
 public     | remote_runner_enrollment_tokens | remote_runner_enrollment_tokens_select_rls | PERMISSIVE | {public} | SELECT | ((workspace_id = app_current_workspace_id()) AND app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text])) | 
 public     | remote_runner_enrollment_tokens | remote_runner_enrollment_tokens_update_rls | PERMISSIVE | {public} | UPDATE | ((workspace_id = app_current_workspace_id()) AND app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text])) | ((workspace_id = app_current_workspace_id()) AND app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text]))
 public     | remote_runners                  | remote_runners_delete_rls                  | PERMISSIVE | {public} | DELETE | ((workspace_id = app_current_workspace_id()) AND app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text])) | 
 public     | remote_runners                  | remote_runners_insert_rls                  | PERMISSIVE | {public} | INSERT |                                                                                                                                            | ((workspace_id = app_current_workspace_id()) AND app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text]))
 public     | remote_runners                  | remote_runners_select_rls                  | PERMISSIVE | {public} | SELECT | ((workspace_id = app_current_workspace_id()) AND app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text])) | 
 public     | remote_runners                  | remote_runners_update_rls                  | PERMISSIVE | {public} | UPDATE | ((workspace_id = app_current_workspace_id()) AND app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text])) | ((workspace_id = app_current_workspace_id()) AND app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text]))
(8 rows)


-- 4. Table DDL Dump
--
-- PostgreSQL database dump
--

\restrict rJUx3hZpqLBs9kobtzkvZslyIUZ3ZGInfhd1XlDuRTzjZ9lFviY8vLm6AEQ3icj

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
-- Name: remote_runner_enrollment_tokens; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.remote_runner_enrollment_tokens (
    id uuid DEFAULT public.uuidv7() NOT NULL,
    workspace_id uuid NOT NULL,
    pool_slug text NOT NULL,
    token_sha256 bytea NOT NULL,
    created_by_id uuid NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    consumed_at timestamp with time zone,
    consumed_by_runner_id uuid,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT remote_runner_enrollment_tokens_pool_slug_check CHECK ((pool_slug ~ '^[a-z0-9][a-z0-9-]{1,62}$'::text)),
    CONSTRAINT remote_runner_enrollment_tokens_token_sha256_check CHECK ((octet_length(token_sha256) = 32))
);

ALTER TABLE ONLY public.remote_runner_enrollment_tokens FORCE ROW LEVEL SECURITY;


ALTER TABLE public.remote_runner_enrollment_tokens OWNER TO kanban_migrator;

--
-- Name: remote_runners; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.remote_runners (
    id uuid DEFAULT public.uuidv7() NOT NULL,
    workspace_id uuid NOT NULL,
    pool_slug text NOT NULL,
    hostname text NOT NULL,
    client_cert_sha256 bytea NOT NULL,
    cert_expires_at timestamp with time zone NOT NULL,
    capabilities_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    status text DEFAULT 'offline'::text NOT NULL,
    last_heartbeat_at timestamp with time zone,
    revoked_at timestamp with time zone,
    revoked_by_id uuid,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT remote_runners_client_cert_sha256_check CHECK ((octet_length(client_cert_sha256) = 32)),
    CONSTRAINT remote_runners_hostname_check CHECK (((char_length(btrim(hostname)) >= 1) AND (char_length(btrim(hostname)) <= 253))),
    CONSTRAINT remote_runners_pool_slug_check CHECK ((pool_slug ~ '^[a-z0-9][a-z0-9-]{1,62}$'::text)),
    CONSTRAINT remote_runners_status_check CHECK ((status = ANY (ARRAY['online'::text, 'offline'::text, 'revoked'::text])))
);

ALTER TABLE ONLY public.remote_runners FORCE ROW LEVEL SECURITY;


ALTER TABLE public.remote_runners OWNER TO kanban_migrator;

--
-- Name: remote_runner_enrollment_tokens remote_runner_enrollment_tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.remote_runner_enrollment_tokens
    ADD CONSTRAINT remote_runner_enrollment_tokens_pkey PRIMARY KEY (id);


--
-- Name: remote_runner_enrollment_tokens remote_runner_enrollment_tokens_token_sha256_key; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.remote_runner_enrollment_tokens
    ADD CONSTRAINT remote_runner_enrollment_tokens_token_sha256_key UNIQUE (token_sha256);


--
-- Name: remote_runners remote_runners_client_cert_sha256_key; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.remote_runners
    ADD CONSTRAINT remote_runners_client_cert_sha256_key UNIQUE (client_cert_sha256);


--
-- Name: remote_runners remote_runners_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.remote_runners
    ADD CONSTRAINT remote_runners_pkey PRIMARY KEY (id);


--
-- Name: idx_remote_runner_tokens_workspace_pool; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX idx_remote_runner_tokens_workspace_pool ON public.remote_runner_enrollment_tokens USING btree (workspace_id, pool_slug);


--
-- Name: idx_remote_runners_client_cert_sha256; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX idx_remote_runners_client_cert_sha256 ON public.remote_runners USING btree (client_cert_sha256);


--
-- Name: idx_remote_runners_workspace_pool; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX idx_remote_runners_workspace_pool ON public.remote_runners USING btree (workspace_id, pool_slug, status);


--
-- Name: remote_runner_enrollment_tokens remote_runner_enrollment_tokens_created_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.remote_runner_enrollment_tokens
    ADD CONSTRAINT remote_runner_enrollment_tokens_created_by_id_fkey FOREIGN KEY (created_by_id) REFERENCES public.principals(id);


--
-- Name: remote_runner_enrollment_tokens remote_runner_enrollment_tokens_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.remote_runner_enrollment_tokens
    ADD CONSTRAINT remote_runner_enrollment_tokens_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;


--
-- Name: remote_runners remote_runners_revoked_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.remote_runners
    ADD CONSTRAINT remote_runners_revoked_by_id_fkey FOREIGN KEY (revoked_by_id) REFERENCES public.principals(id);


--
-- Name: remote_runners remote_runners_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.remote_runners
    ADD CONSTRAINT remote_runners_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;


--
-- Name: remote_runner_enrollment_tokens; Type: ROW SECURITY; Schema: public; Owner: kanban_migrator
--

ALTER TABLE public.remote_runner_enrollment_tokens ENABLE ROW LEVEL SECURITY;

--
-- Name: remote_runner_enrollment_tokens remote_runner_enrollment_tokens_delete_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY remote_runner_enrollment_tokens_delete_rls ON public.remote_runner_enrollment_tokens FOR DELETE USING (((workspace_id = public.app_current_workspace_id()) AND public.app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text])));


--
-- Name: remote_runner_enrollment_tokens remote_runner_enrollment_tokens_insert_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY remote_runner_enrollment_tokens_insert_rls ON public.remote_runner_enrollment_tokens FOR INSERT WITH CHECK (((workspace_id = public.app_current_workspace_id()) AND public.app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text])));


--
-- Name: remote_runner_enrollment_tokens remote_runner_enrollment_tokens_select_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY remote_runner_enrollment_tokens_select_rls ON public.remote_runner_enrollment_tokens FOR SELECT USING (((workspace_id = public.app_current_workspace_id()) AND public.app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text])));


--
-- Name: remote_runner_enrollment_tokens remote_runner_enrollment_tokens_update_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY remote_runner_enrollment_tokens_update_rls ON public.remote_runner_enrollment_tokens FOR UPDATE USING (((workspace_id = public.app_current_workspace_id()) AND public.app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text]))) WITH CHECK (((workspace_id = public.app_current_workspace_id()) AND public.app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text])));


--
-- Name: remote_runners; Type: ROW SECURITY; Schema: public; Owner: kanban_migrator
--

ALTER TABLE public.remote_runners ENABLE ROW LEVEL SECURITY;

--
-- Name: remote_runners remote_runners_delete_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY remote_runners_delete_rls ON public.remote_runners FOR DELETE USING (((workspace_id = public.app_current_workspace_id()) AND public.app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text])));


--
-- Name: remote_runners remote_runners_insert_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY remote_runners_insert_rls ON public.remote_runners FOR INSERT WITH CHECK (((workspace_id = public.app_current_workspace_id()) AND public.app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text])));


--
-- Name: remote_runners remote_runners_select_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY remote_runners_select_rls ON public.remote_runners FOR SELECT USING (((workspace_id = public.app_current_workspace_id()) AND public.app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text])));


--
-- Name: remote_runners remote_runners_update_rls; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY remote_runners_update_rls ON public.remote_runners FOR UPDATE USING (((workspace_id = public.app_current_workspace_id()) AND public.app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text]))) WITH CHECK (((workspace_id = public.app_current_workspace_id()) AND public.app_principal_has_role(NULL::uuid, ARRAY['SERVER_ADMIN'::text, 'WORKSPACE_ADMIN'::text])));


--
-- Name: TABLE remote_runner_enrollment_tokens; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.remote_runner_enrollment_tokens TO kanban_app;
GRANT SELECT ON TABLE public.remote_runner_enrollment_tokens TO app_rls_reader;


--
-- Name: TABLE remote_runners; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.remote_runners TO kanban_app;
GRANT SELECT ON TABLE public.remote_runners TO app_rls_reader;


--
-- PostgreSQL database dump complete
--

\unrestrict rJUx3hZpqLBs9kobtzkvZslyIUZ3ZGInfhd1XlDuRTzjZ9lFviY8vLm6AEQ3icj

