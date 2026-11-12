-- Schema Dump: sessions table (KB-P2-02)
--
-- PostgreSQL database dump
--

\restrict Ab4pIeR4BDKUqVGAwWzBPcSPh47o7D9Cn1TGICshwsTQ0So78luIlA1ak2mx8Zj

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
-- Name: sessions; Type: TABLE; Schema: public; Owner: kb_auth_owner
--

CREATE TABLE public.sessions (
    id uuid DEFAULT public.uuidv7() NOT NULL,
    token_sha256 bytea NOT NULL,
    principal_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    auth_card_id uuid,
    aal_level smallint NOT NULL,
    aal2_verified_at timestamp with time zone,
    mfa_pending boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    last_seen_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    idle_expires_at timestamp with time zone NOT NULL,
    absolute_expires_at timestamp with time zone NOT NULL,
    revoked_at timestamp with time zone,
    rotated_from_id uuid,
    CONSTRAINT sessions_aal_level_check CHECK ((aal_level = ANY (ARRAY[1, 2]))),
    CONSTRAINT sessions_token_sha256_check CHECK ((octet_length(token_sha256) = 32))
);

ALTER TABLE ONLY public.sessions FORCE ROW LEVEL SECURITY;


ALTER TABLE public.sessions OWNER TO kb_auth_owner;

--
-- Name: sessions sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: kb_auth_owner
--

ALTER TABLE ONLY public.sessions
    ADD CONSTRAINT sessions_pkey PRIMARY KEY (id);


--
-- Name: sessions sessions_token_sha256_key; Type: CONSTRAINT; Schema: public; Owner: kb_auth_owner
--

ALTER TABLE ONLY public.sessions
    ADD CONSTRAINT sessions_token_sha256_key UNIQUE (token_sha256);


--
-- Name: sessions_principal_id_idx; Type: INDEX; Schema: public; Owner: kb_auth_owner
--

CREATE INDEX sessions_principal_id_idx ON public.sessions USING btree (principal_id);


--
-- Name: sessions sessions_auth_card_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kb_auth_owner
--

ALTER TABLE ONLY public.sessions
    ADD CONSTRAINT sessions_auth_card_id_fkey FOREIGN KEY (auth_card_id) REFERENCES public.auth_provider_cards(id) ON DELETE CASCADE;


--
-- Name: sessions sessions_principal_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kb_auth_owner
--

ALTER TABLE ONLY public.sessions
    ADD CONSTRAINT sessions_principal_id_fkey FOREIGN KEY (principal_id) REFERENCES public.principals(id) ON DELETE CASCADE;


--
-- Name: sessions kb_auth_owner_all; Type: POLICY; Schema: public; Owner: kb_auth_owner
--

CREATE POLICY kb_auth_owner_all ON public.sessions TO kb_auth_owner USING (true) WITH CHECK (true);


--
-- Name: sessions; Type: ROW SECURITY; Schema: public; Owner: kb_auth_owner
--

ALTER TABLE public.sessions ENABLE ROW LEVEL SECURITY;

--
-- PostgreSQL database dump complete
--

\unrestrict Ab4pIeR4BDKUqVGAwWzBPcSPh47o7D9Cn1TGICshwsTQ0So78luIlA1ak2mx8Zj



-- Function Definitions: kb_auth.session_*
                                                                                                                                                                                                                                                                                                                                                                                                                                              List of functions
 Schema  |               Name               |                                                                                                                                                                                      Result data type                                                                                                                                                                                      |                                                                                                                                                       Argument data types                                                                                                                                                       | Type | Volatility | Parallel |     Owner     | Security |       Access privileges       | Language | Internal name | Description 
---------+----------------------------------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+------+------------+----------+---------------+----------+-------------------------------+----------+---------------+-------------
 kb_auth | session_create                   | uuid                                                                                                                                                                                                                                                                                                                                                                                       | p_id uuid, p_token_sha256 bytea, p_principal_id uuid, p_workspace_id uuid, p_auth_card_id uuid, p_aal_level smallint, p_aal2_verified_at timestamp with time zone, p_mfa_pending boolean, p_idle_expires_at timestamp with time zone, p_absolute_expires_at timestamp with time zone, p_rotated_from_id uuid DEFAULT NULL::uuid | func | volatile   | unsafe   | kb_auth_owner | definer  | kb_auth_owner=X/kb_auth_owner+| plpgsql  |               | 
         |                                  |                                                                                                                                                                                                                                                                                                                                                                                            |                                                                                                                                                                                                                                                                                                                                 |      |            |          |               |          | kanban_app=X/kb_auth_owner    |          |               | 
 kb_auth | session_resolve                  | TABLE(id uuid, principal_id uuid, workspace_id uuid, auth_card_id uuid, aal_level smallint, aal2_verified_at timestamp with time zone, mfa_pending boolean, created_at timestamp with time zone, last_seen_at timestamp with time zone, idle_expires_at timestamp with time zone, absolute_expires_at timestamp with time zone, revoked_at timestamp with time zone, rotated_from_id uuid) | p_token_sha256 bytea                                                                                                                                                                                                                                                                                                            | func | volatile   | unsafe   | kb_auth_owner | definer  | kb_auth_owner=X/kb_auth_owner+| plpgsql  |               | 
         |                                  |                                                                                                                                                                                                                                                                                                                                                                                            |                                                                                                                                                                                                                                                                                                                                 |      |            |          |               |          | kanban_app=X/kb_auth_owner    |          |               | 
 kb_auth | session_revoke                   | boolean                                                                                                                                                                                                                                                                                                                                                                                    | p_id uuid                                                                                                                                                                                                                                                                                                                       | func | volatile   | unsafe   | kb_auth_owner | definer  | kb_auth_owner=X/kb_auth_owner+| plpgsql  |               | 
         |                                  |                                                                                                                                                                                                                                                                                                                                                                                            |                                                                                                                                                                                                                                                                                                                                 |      |            |          |               |          | kanban_app=X/kb_auth_owner    |          |               | 
 kb_auth | session_revoke_all_for_principal | integer                                                                                                                                                                                                                                                                                                                                                                                    | p_principal_id uuid                                                                                                                                                                                                                                                                                                             | func | volatile   | unsafe   | kb_auth_owner | definer  | kb_auth_owner=X/kb_auth_owner+| plpgsql  |               | 
         |                                  |                                                                                                                                                                                                                                                                                                                                                                                            |                                                                                                                                                                                                                                                                                                                                 |      |            |          |               |          | kanban_app=X/kb_auth_owner    |          |               | 
 kb_auth | session_rotate                   | uuid                                                                                                                                                                                                                                                                                                                                                                                       | p_old_id uuid, p_new_token_sha256 bytea, p_aal smallint                                                                                                                                                                                                                                                                         | func | volatile   | unsafe   | kb_auth_owner | definer  | kb_auth_owner=X/kb_auth_owner+| plpgsql  |               | 
         |                                  |                                                                                                                                                                                                                                                                                                                                                                                            |                                                                                                                                                                                                                                                                                                                                 |      |            |          |               |          | kanban_app=X/kb_auth_owner    |          |               | 
(5 rows)

