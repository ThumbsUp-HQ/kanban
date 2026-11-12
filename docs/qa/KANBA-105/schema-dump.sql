--
-- PostgreSQL database dump
--

\restrict NwN17dJj6c8m8buIXFXVYDd903TJtAtoXG7rNEgXd7306JkvoRr4ZTrNnwhSWE1

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
-- Name: oauth_authorization_codes; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.oauth_authorization_codes (
    id uuid DEFAULT public.uuidv7() NOT NULL,
    code_sha256 bytea NOT NULL,
    grant_id uuid,
    client_id uuid NOT NULL,
    principal_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    code_challenge text NOT NULL,
    code_challenge_method text NOT NULL,
    resource text NOT NULL,
    redirect_uri text NOT NULL,
    surface text NOT NULL,
    scopes text[] NOT NULL,
    allowed_projects uuid[],
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    consumed_at timestamp with time zone,
    CONSTRAINT oauth_authorization_codes_code_challenge_method_check CHECK ((code_challenge_method = 'S256'::text)),
    CONSTRAINT oauth_authorization_codes_code_sha256_check CHECK ((octet_length(code_sha256) = 32)),
    CONSTRAINT oauth_authorization_codes_surface_check CHECK ((surface = ANY (ARRAY['agent'::text, 'docs'::text, 'admin'::text])))
);

ALTER TABLE ONLY public.oauth_authorization_codes FORCE ROW LEVEL SECURITY;


ALTER TABLE public.oauth_authorization_codes OWNER TO kanban_migrator;

--
-- Name: oauth_clients; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.oauth_clients (
    id uuid DEFAULT public.uuidv7() NOT NULL,
    client_id text NOT NULL,
    client_name text NOT NULL,
    client_type text DEFAULT 'public'::text NOT NULL,
    redirect_uris text[] NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    workspace_id uuid,
    created_by_id uuid,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT oauth_clients_client_type_check CHECK ((client_type = 'public'::text)),
    CONSTRAINT oauth_clients_status_check CHECK ((status = ANY (ARRAY['active'::text, 'pending_admin_approval'::text, 'disabled'::text])))
);

ALTER TABLE ONLY public.oauth_clients FORCE ROW LEVEL SECURITY;


ALTER TABLE public.oauth_clients OWNER TO kanban_migrator;

--
-- Name: oauth_grants; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.oauth_grants (
    id uuid DEFAULT public.uuidv7() NOT NULL,
    workspace_id uuid NOT NULL,
    principal_id uuid NOT NULL,
    client_id uuid NOT NULL,
    surface text NOT NULL,
    scopes text[] NOT NULL,
    allowed_projects uuid[],
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    revoked_at timestamp with time zone,
    CONSTRAINT oauth_grants_surface_check CHECK ((surface = ANY (ARRAY['agent'::text, 'docs'::text, 'admin'::text])))
);

ALTER TABLE ONLY public.oauth_grants FORCE ROW LEVEL SECURITY;


ALTER TABLE public.oauth_grants OWNER TO kanban_migrator;

--
-- Name: oauth_refresh_tokens; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.oauth_refresh_tokens (
    id uuid DEFAULT public.uuidv7() NOT NULL,
    token_sha256 bytea NOT NULL,
    grant_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    client_id uuid NOT NULL,
    principal_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    revoked_at timestamp with time zone,
    CONSTRAINT oauth_refresh_tokens_token_sha256_check CHECK ((octet_length(token_sha256) = 32))
);

ALTER TABLE ONLY public.oauth_refresh_tokens FORCE ROW LEVEL SECURITY;


ALTER TABLE public.oauth_refresh_tokens OWNER TO kanban_migrator;

--
-- Name: oauth_revoked_jtis; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.oauth_revoked_jtis (
    jti uuid NOT NULL,
    grant_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    revoked_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL
);

ALTER TABLE ONLY public.oauth_revoked_jtis FORCE ROW LEVEL SECURITY;


ALTER TABLE public.oauth_revoked_jtis OWNER TO kanban_migrator;

--
-- Name: oauth_authorization_codes oauth_authorization_codes_code_sha256_key; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.oauth_authorization_codes
    ADD CONSTRAINT oauth_authorization_codes_code_sha256_key UNIQUE (code_sha256);


--
-- Name: oauth_authorization_codes oauth_authorization_codes_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.oauth_authorization_codes
    ADD CONSTRAINT oauth_authorization_codes_pkey PRIMARY KEY (id);


--
-- Name: oauth_clients oauth_clients_client_id_key; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.oauth_clients
    ADD CONSTRAINT oauth_clients_client_id_key UNIQUE (client_id);


--
-- Name: oauth_clients oauth_clients_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.oauth_clients
    ADD CONSTRAINT oauth_clients_pkey PRIMARY KEY (id);


--
-- Name: oauth_grants oauth_grants_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.oauth_grants
    ADD CONSTRAINT oauth_grants_pkey PRIMARY KEY (id);


--
-- Name: oauth_refresh_tokens oauth_refresh_tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.oauth_refresh_tokens
    ADD CONSTRAINT oauth_refresh_tokens_pkey PRIMARY KEY (id);


--
-- Name: oauth_refresh_tokens oauth_refresh_tokens_token_sha256_key; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.oauth_refresh_tokens
    ADD CONSTRAINT oauth_refresh_tokens_token_sha256_key UNIQUE (token_sha256);


--
-- Name: oauth_revoked_jtis oauth_revoked_jtis_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.oauth_revoked_jtis
    ADD CONSTRAINT oauth_revoked_jtis_pkey PRIMARY KEY (jti);


--
-- Name: oauth_authorization_codes oauth_authorization_codes_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.oauth_authorization_codes
    ADD CONSTRAINT oauth_authorization_codes_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.oauth_clients(id) ON DELETE CASCADE;


--
-- Name: oauth_authorization_codes oauth_authorization_codes_grant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.oauth_authorization_codes
    ADD CONSTRAINT oauth_authorization_codes_grant_id_fkey FOREIGN KEY (grant_id) REFERENCES public.oauth_grants(id) ON DELETE CASCADE;


--
-- Name: oauth_authorization_codes oauth_authorization_codes_principal_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.oauth_authorization_codes
    ADD CONSTRAINT oauth_authorization_codes_principal_id_fkey FOREIGN KEY (principal_id) REFERENCES public.principals(id) ON DELETE CASCADE;


--
-- Name: oauth_authorization_codes oauth_authorization_codes_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.oauth_authorization_codes
    ADD CONSTRAINT oauth_authorization_codes_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;


--
-- Name: oauth_clients oauth_clients_created_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.oauth_clients
    ADD CONSTRAINT oauth_clients_created_by_id_fkey FOREIGN KEY (created_by_id) REFERENCES public.principals(id) ON DELETE SET NULL;


--
-- Name: oauth_clients oauth_clients_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.oauth_clients
    ADD CONSTRAINT oauth_clients_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;


--
-- Name: oauth_grants oauth_grants_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.oauth_grants
    ADD CONSTRAINT oauth_grants_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.oauth_clients(id) ON DELETE CASCADE;


--
-- Name: oauth_grants oauth_grants_principal_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.oauth_grants
    ADD CONSTRAINT oauth_grants_principal_id_fkey FOREIGN KEY (principal_id) REFERENCES public.principals(id) ON DELETE CASCADE;


--
-- Name: oauth_grants oauth_grants_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.oauth_grants
    ADD CONSTRAINT oauth_grants_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;


--
-- Name: oauth_refresh_tokens oauth_refresh_tokens_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.oauth_refresh_tokens
    ADD CONSTRAINT oauth_refresh_tokens_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.oauth_clients(id) ON DELETE CASCADE;


--
-- Name: oauth_refresh_tokens oauth_refresh_tokens_grant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.oauth_refresh_tokens
    ADD CONSTRAINT oauth_refresh_tokens_grant_id_fkey FOREIGN KEY (grant_id) REFERENCES public.oauth_grants(id) ON DELETE CASCADE;


--
-- Name: oauth_refresh_tokens oauth_refresh_tokens_principal_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.oauth_refresh_tokens
    ADD CONSTRAINT oauth_refresh_tokens_principal_id_fkey FOREIGN KEY (principal_id) REFERENCES public.principals(id) ON DELETE CASCADE;


--
-- Name: oauth_refresh_tokens oauth_refresh_tokens_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.oauth_refresh_tokens
    ADD CONSTRAINT oauth_refresh_tokens_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;


--
-- Name: oauth_revoked_jtis oauth_revoked_jtis_grant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.oauth_revoked_jtis
    ADD CONSTRAINT oauth_revoked_jtis_grant_id_fkey FOREIGN KEY (grant_id) REFERENCES public.oauth_grants(id) ON DELETE CASCADE;


--
-- Name: oauth_revoked_jtis oauth_revoked_jtis_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.oauth_revoked_jtis
    ADD CONSTRAINT oauth_revoked_jtis_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;


--
-- Name: oauth_authorization_codes; Type: ROW SECURITY; Schema: public; Owner: kanban_migrator
--

ALTER TABLE public.oauth_authorization_codes ENABLE ROW LEVEL SECURITY;

--
-- Name: oauth_clients; Type: ROW SECURITY; Schema: public; Owner: kanban_migrator
--

ALTER TABLE public.oauth_clients ENABLE ROW LEVEL SECURITY;

--
-- Name: oauth_clients oauth_clients_workspace_policy; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY oauth_clients_workspace_policy ON public.oauth_clients USING (((workspace_id IS NULL) OR (public.app_current_workspace_id() IS NULL) OR (workspace_id = public.app_current_workspace_id()))) WITH CHECK (((workspace_id IS NULL) OR (public.app_current_workspace_id() IS NULL) OR (workspace_id = public.app_current_workspace_id())));


--
-- Name: oauth_authorization_codes oauth_codes_workspace_policy; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY oauth_codes_workspace_policy ON public.oauth_authorization_codes USING (((public.app_current_workspace_id() IS NULL) OR (workspace_id = public.app_current_workspace_id()))) WITH CHECK (((public.app_current_workspace_id() IS NULL) OR (workspace_id = public.app_current_workspace_id())));


--
-- Name: oauth_grants; Type: ROW SECURITY; Schema: public; Owner: kanban_migrator
--

ALTER TABLE public.oauth_grants ENABLE ROW LEVEL SECURITY;

--
-- Name: oauth_grants oauth_grants_workspace_policy; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY oauth_grants_workspace_policy ON public.oauth_grants USING (((public.app_current_workspace_id() IS NULL) OR (workspace_id = public.app_current_workspace_id()))) WITH CHECK (((public.app_current_workspace_id() IS NULL) OR (workspace_id = public.app_current_workspace_id())));


--
-- Name: oauth_refresh_tokens; Type: ROW SECURITY; Schema: public; Owner: kanban_migrator
--

ALTER TABLE public.oauth_refresh_tokens ENABLE ROW LEVEL SECURITY;

--
-- Name: oauth_refresh_tokens oauth_refresh_workspace_policy; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY oauth_refresh_workspace_policy ON public.oauth_refresh_tokens USING (((public.app_current_workspace_id() IS NULL) OR (workspace_id = public.app_current_workspace_id()))) WITH CHECK (((public.app_current_workspace_id() IS NULL) OR (workspace_id = public.app_current_workspace_id())));


--
-- Name: oauth_revoked_jtis; Type: ROW SECURITY; Schema: public; Owner: kanban_migrator
--

ALTER TABLE public.oauth_revoked_jtis ENABLE ROW LEVEL SECURITY;

--
-- Name: oauth_revoked_jtis oauth_revoked_jtis_workspace_policy; Type: POLICY; Schema: public; Owner: kanban_migrator
--

CREATE POLICY oauth_revoked_jtis_workspace_policy ON public.oauth_revoked_jtis USING (((public.app_current_workspace_id() IS NULL) OR (workspace_id = public.app_current_workspace_id()))) WITH CHECK (((public.app_current_workspace_id() IS NULL) OR (workspace_id = public.app_current_workspace_id())));


--
-- Name: TABLE oauth_authorization_codes; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.oauth_authorization_codes TO kanban_app;
GRANT SELECT ON TABLE public.oauth_authorization_codes TO app_rls_reader;


--
-- Name: TABLE oauth_clients; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.oauth_clients TO kanban_app;
GRANT SELECT ON TABLE public.oauth_clients TO app_rls_reader;


--
-- Name: TABLE oauth_grants; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.oauth_grants TO kanban_app;
GRANT SELECT ON TABLE public.oauth_grants TO app_rls_reader;


--
-- Name: TABLE oauth_refresh_tokens; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.oauth_refresh_tokens TO kanban_app;
GRANT SELECT ON TABLE public.oauth_refresh_tokens TO app_rls_reader;


--
-- Name: TABLE oauth_revoked_jtis; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.oauth_revoked_jtis TO kanban_app;
GRANT SELECT ON TABLE public.oauth_revoked_jtis TO app_rls_reader;


--
-- PostgreSQL database dump complete
--

\unrestrict NwN17dJj6c8m8buIXFXVYDd903TJtAtoXG7rNEgXd7306JkvoRr4ZTrNnwhSWE1

