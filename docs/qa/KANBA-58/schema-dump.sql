--
-- PostgreSQL database dump
--

\restrict GeeTtJKjIQBcBneRbiLTIGzeoysXNswqGsLwzy5Zyln3sHerfr3beUh14ZS8bhh

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
-- Name: auth_provider_cards; Type: TABLE; Schema: public; Owner: kb_auth_owner
--

CREATE TABLE public.auth_provider_cards (
    id uuid DEFAULT public.uuidv7() NOT NULL,
    workspace_id uuid,
    provider_kind text NOT NULL,
    slug text NOT NULL,
    display_name text NOT NULL,
    button_subtext text,
    icon_preset text DEFAULT 'key'::text NOT NULL,
    is_enabled boolean DEFAULT false NOT NULL,
    sort_rank text NOT NULL COLLATE pg_catalog."C",
    auto_provision_users boolean DEFAULT false NOT NULL,
    allowed_email_domains text[] DEFAULT '{}'::text[] NOT NULL,
    public_config jsonb DEFAULT '{}'::jsonb NOT NULL,
    encrypted_secret_blob bytea,
    wrapped_dek bytea,
    dek_kid text DEFAULT 'kek-v1'::text NOT NULL,
    last_health_status text DEFAULT 'UNVERIFIED'::text NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT auth_provider_cards_check CHECK (((encrypted_secret_blob IS NULL) = (wrapped_dek IS NULL))),
    CONSTRAINT auth_provider_cards_provider_kind_check CHECK ((provider_kind = ANY (ARRAY['OIDC'::text, 'OAUTH2'::text, 'LDAP'::text, 'LOCAL_ADMIN'::text]))),
    CONSTRAINT auth_provider_cards_slug_check CHECK ((slug ~ '^[a-z0-9][a-z0-9-]{1,46}[a-z0-9]$'::text))
);

ALTER TABLE ONLY public.auth_provider_cards FORCE ROW LEVEL SECURITY;


ALTER TABLE public.auth_provider_cards OWNER TO kb_auth_owner;

--
-- Name: auth_provider_cards auth_provider_cards_pkey; Type: CONSTRAINT; Schema: public; Owner: kb_auth_owner
--

ALTER TABLE ONLY public.auth_provider_cards
    ADD CONSTRAINT auth_provider_cards_pkey PRIMARY KEY (id);


--
-- Name: auth_provider_cards auth_provider_cards_slug_key; Type: CONSTRAINT; Schema: public; Owner: kb_auth_owner
--

ALTER TABLE ONLY public.auth_provider_cards
    ADD CONSTRAINT auth_provider_cards_slug_key UNIQUE (slug);


--
-- Name: auth_provider_cards auth_provider_cards_set_updated_at; Type: TRIGGER; Schema: public; Owner: kb_auth_owner
--

CREATE TRIGGER auth_provider_cards_set_updated_at BEFORE UPDATE ON public.auth_provider_cards FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: auth_provider_cards auth_provider_cards_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kb_auth_owner
--

ALTER TABLE ONLY public.auth_provider_cards
    ADD CONSTRAINT auth_provider_cards_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;


--
-- Name: auth_provider_cards; Type: ROW SECURITY; Schema: public; Owner: kb_auth_owner
--

ALTER TABLE public.auth_provider_cards ENABLE ROW LEVEL SECURITY;

--
-- Name: auth_provider_cards kb_auth_owner_all; Type: POLICY; Schema: public; Owner: kb_auth_owner
--

CREATE POLICY kb_auth_owner_all ON public.auth_provider_cards TO kb_auth_owner USING (true) WITH CHECK (true);


--
-- PostgreSQL database dump complete
--

\unrestrict GeeTtJKjIQBcBneRbiLTIGzeoysXNswqGsLwzy5Zyln3sHerfr3beUh14ZS8bhh

--
-- PostgreSQL database dump
--

\restrict 4qTbkXUh552k0WHbTXPcAt0XTKpR4ASC4lFD3Eg9ehXhm9if47i2eNogLrcChOp

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

--
-- Name: kb_auth; Type: SCHEMA; Schema: -; Owner: kb_auth_owner
--

CREATE SCHEMA kb_auth;


ALTER SCHEMA kb_auth OWNER TO kb_auth_owner;

--
-- Name: card_admin_get(uuid); Type: FUNCTION; Schema: kb_auth; Owner: kb_auth_owner
--

CREATE FUNCTION kb_auth.card_admin_get(p_id uuid) RETURNS SETOF public.auth_provider_cards
    LANGUAGE plpgsql STABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $$
BEGIN
    IF NOT (
        EXISTS (
            SELECT 1
            FROM role_bindings rb
            WHERE rb.principal_id = ANY (app_effective_principal_set())
              AND rb.role = 'SERVER_ADMIN'
        )
        AND current_setting('app.aal_level', true) = '2'
    ) THEN
        RAISE EXCEPTION 'insufficient_privilege: SERVER_ADMIN with AAL2 required'
            USING ERRCODE = '42501';
    END IF;

    RETURN QUERY
    SELECT *
    FROM auth_provider_cards c
    WHERE c.id = p_id;
END;
$$;


ALTER FUNCTION kb_auth.card_admin_get(p_id uuid) OWNER TO kb_auth_owner;

--
-- Name: card_admin_list(); Type: FUNCTION; Schema: kb_auth; Owner: kb_auth_owner
--

CREATE FUNCTION kb_auth.card_admin_list() RETURNS SETOF public.auth_provider_cards
    LANGUAGE plpgsql STABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $$
BEGIN
    IF NOT (
        EXISTS (
            SELECT 1
            FROM role_bindings rb
            WHERE rb.principal_id = ANY (app_effective_principal_set())
              AND rb.role = 'SERVER_ADMIN'
        )
        AND current_setting('app.aal_level', true) = '2'
    ) THEN
        RAISE EXCEPTION 'insufficient_privilege: SERVER_ADMIN with AAL2 required'
            USING ERRCODE = '42501';
    END IF;

    RETURN QUERY
    SELECT *
    FROM auth_provider_cards c
    ORDER BY c.sort_rank COLLATE "C" ASC, c.id ASC;
END;
$$;


ALTER FUNCTION kb_auth.card_admin_list() OWNER TO kb_auth_owner;

--
-- Name: card_admin_upsert(uuid, uuid, text, text, text, text, text, boolean, text, boolean, text[], jsonb, bytea, bytea, text, text); Type: FUNCTION; Schema: kb_auth; Owner: kb_auth_owner
--

CREATE FUNCTION kb_auth.card_admin_upsert(p_id uuid, p_workspace_id uuid, p_provider_kind text, p_slug text, p_display_name text, p_button_subtext text, p_icon_preset text, p_is_enabled boolean, p_sort_rank text, p_auto_provision_users boolean, p_allowed_email_domains text[], p_public_config jsonb, p_encrypted_secret_blob bytea, p_wrapped_dek bytea, p_dek_kid text, p_last_health_status text DEFAULT 'UNVERIFIED'::text) RETURNS uuid
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $$
DECLARE
    v_id UUID;
BEGIN
    IF NOT (
        EXISTS (
            SELECT 1
            FROM role_bindings rb
            WHERE rb.principal_id = ANY (app_effective_principal_set())
              AND rb.role = 'SERVER_ADMIN'
        )
        AND current_setting('app.aal_level', true) = '2'
    ) THEN
        RAISE EXCEPTION 'insufficient_privilege: SERVER_ADMIN with AAL2 required'
            USING ERRCODE = '42501';
    END IF;

    v_id := COALESCE(p_id, uuidv7());

    INSERT INTO auth_provider_cards (
        id,
        workspace_id,
        provider_kind,
        slug,
        display_name,
        button_subtext,
        icon_preset,
        is_enabled,
        sort_rank,
        auto_provision_users,
        allowed_email_domains,
        public_config,
        encrypted_secret_blob,
        wrapped_dek,
        dek_kid,
        last_health_status
    ) VALUES (
        v_id,
        p_workspace_id,
        p_provider_kind,
        p_slug,
        p_display_name,
        p_button_subtext,
        COALESCE(p_icon_preset, 'key'),
        COALESCE(p_is_enabled, FALSE),
        p_sort_rank,
        COALESCE(p_auto_provision_users, FALSE),
        COALESCE(p_allowed_email_domains, '{}'),
        COALESCE(p_public_config, '{}'::jsonb),
        p_encrypted_secret_blob,
        p_wrapped_dek,
        COALESCE(p_dek_kid, 'kek-v1'),
        COALESCE(p_last_health_status, 'UNVERIFIED')
    )
    ON CONFLICT (id) DO UPDATE SET
        workspace_id            = EXCLUDED.workspace_id,
        provider_kind           = EXCLUDED.provider_kind,
        slug                    = EXCLUDED.slug,
        display_name            = EXCLUDED.display_name,
        button_subtext          = EXCLUDED.button_subtext,
        icon_preset             = EXCLUDED.icon_preset,
        is_enabled              = EXCLUDED.is_enabled,
        sort_rank               = EXCLUDED.sort_rank,
        auto_provision_users    = EXCLUDED.auto_provision_users,
        allowed_email_domains   = EXCLUDED.allowed_email_domains,
        public_config           = EXCLUDED.public_config,
        encrypted_secret_blob   = CASE
            WHEN EXCLUDED.encrypted_secret_blob IS NOT NULL THEN EXCLUDED.encrypted_secret_blob
            ELSE auth_provider_cards.encrypted_secret_blob
        END,
        wrapped_dek             = CASE
            WHEN EXCLUDED.wrapped_dek IS NOT NULL THEN EXCLUDED.wrapped_dek
            ELSE auth_provider_cards.wrapped_dek
        END,
        dek_kid                 = CASE
            WHEN EXCLUDED.wrapped_dek IS NOT NULL THEN EXCLUDED.dek_kid
            ELSE auth_provider_cards.dek_kid
        END,
        last_health_status      = EXCLUDED.last_health_status,
        updated_at              = clock_timestamp();

    RETURN v_id;
END;
$$;


ALTER FUNCTION kb_auth.card_admin_upsert(p_id uuid, p_workspace_id uuid, p_provider_kind text, p_slug text, p_display_name text, p_button_subtext text, p_icon_preset text, p_is_enabled boolean, p_sort_rank text, p_auto_provision_users boolean, p_allowed_email_domains text[], p_public_config jsonb, p_encrypted_secret_blob bytea, p_wrapped_dek bytea, p_dek_kid text, p_last_health_status text) OWNER TO kb_auth_owner;

--
-- Name: card_get_for_login(text); Type: FUNCTION; Schema: kb_auth; Owner: kb_auth_owner
--

CREATE FUNCTION kb_auth.card_get_for_login(p_slug text) RETURNS SETOF public.auth_provider_cards
    LANGUAGE plpgsql STABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $$
BEGIN
    RETURN QUERY
    SELECT *
    FROM auth_provider_cards c
    WHERE c.slug = p_slug
      AND c.is_enabled = TRUE;
END;
$$;


ALTER FUNCTION kb_auth.card_get_for_login(p_slug text) OWNER TO kb_auth_owner;

--
-- Name: card_list_enabled_public(); Type: FUNCTION; Schema: kb_auth; Owner: kb_auth_owner
--

CREATE FUNCTION kb_auth.card_list_enabled_public() RETURNS TABLE(slug text, display_name text, button_subtext text, icon_preset text, provider_kind text, sort_rank text)
    LANGUAGE plpgsql STABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $$
BEGIN
    RETURN QUERY
    SELECT
        c.slug,
        c.display_name,
        c.button_subtext,
        c.icon_preset,
        c.provider_kind,
        c.sort_rank
    FROM auth_provider_cards c
    WHERE c.is_enabled = TRUE
    ORDER BY c.sort_rank COLLATE "C" ASC, c.id ASC;
END;
$$;


ALTER FUNCTION kb_auth.card_list_enabled_public() OWNER TO kb_auth_owner;

--
-- Name: card_rewrap(uuid, bytea, text, text); Type: FUNCTION; Schema: kb_auth; Owner: kb_auth_owner
--

CREATE FUNCTION kb_auth.card_rewrap(p_id uuid, p_wrapped_dek bytea, p_old_kid text, p_new_kid text) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $$
DECLARE
    v_count INT;
BEGIN
    IF NOT (
        EXISTS (
            SELECT 1
            FROM role_bindings rb
            WHERE rb.principal_id = ANY (app_effective_principal_set())
              AND rb.role = 'SERVER_ADMIN'
        )
        AND current_setting('app.aal_level', true) = '2'
    ) THEN
        RAISE EXCEPTION 'insufficient_privilege: SERVER_ADMIN with AAL2 required'
            USING ERRCODE = '42501';
    END IF;

    UPDATE auth_provider_cards
    SET wrapped_dek = p_wrapped_dek,
        dek_kid     = p_new_kid,
        updated_at  = clock_timestamp()
    WHERE id = p_id
      AND dek_kid = p_old_kid;

    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count > 0;
END;
$$;


ALTER FUNCTION kb_auth.card_rewrap(p_id uuid, p_wrapped_dek bytea, p_old_kid text, p_new_kid text) OWNER TO kb_auth_owner;

--
-- Name: SCHEMA kb_auth; Type: ACL; Schema: -; Owner: kb_auth_owner
--

GRANT USAGE ON SCHEMA kb_auth TO kanban_app;
GRANT ALL ON SCHEMA kb_auth TO kanban_migrator;


--
-- Name: FUNCTION card_admin_get(p_id uuid); Type: ACL; Schema: kb_auth; Owner: kb_auth_owner
--

REVOKE ALL ON FUNCTION kb_auth.card_admin_get(p_id uuid) FROM PUBLIC;
GRANT ALL ON FUNCTION kb_auth.card_admin_get(p_id uuid) TO kanban_app;


--
-- Name: FUNCTION card_admin_list(); Type: ACL; Schema: kb_auth; Owner: kb_auth_owner
--

REVOKE ALL ON FUNCTION kb_auth.card_admin_list() FROM PUBLIC;
GRANT ALL ON FUNCTION kb_auth.card_admin_list() TO kanban_app;


--
-- Name: FUNCTION card_admin_upsert(p_id uuid, p_workspace_id uuid, p_provider_kind text, p_slug text, p_display_name text, p_button_subtext text, p_icon_preset text, p_is_enabled boolean, p_sort_rank text, p_auto_provision_users boolean, p_allowed_email_domains text[], p_public_config jsonb, p_encrypted_secret_blob bytea, p_wrapped_dek bytea, p_dek_kid text, p_last_health_status text); Type: ACL; Schema: kb_auth; Owner: kb_auth_owner
--

REVOKE ALL ON FUNCTION kb_auth.card_admin_upsert(p_id uuid, p_workspace_id uuid, p_provider_kind text, p_slug text, p_display_name text, p_button_subtext text, p_icon_preset text, p_is_enabled boolean, p_sort_rank text, p_auto_provision_users boolean, p_allowed_email_domains text[], p_public_config jsonb, p_encrypted_secret_blob bytea, p_wrapped_dek bytea, p_dek_kid text, p_last_health_status text) FROM PUBLIC;
GRANT ALL ON FUNCTION kb_auth.card_admin_upsert(p_id uuid, p_workspace_id uuid, p_provider_kind text, p_slug text, p_display_name text, p_button_subtext text, p_icon_preset text, p_is_enabled boolean, p_sort_rank text, p_auto_provision_users boolean, p_allowed_email_domains text[], p_public_config jsonb, p_encrypted_secret_blob bytea, p_wrapped_dek bytea, p_dek_kid text, p_last_health_status text) TO kanban_app;


--
-- Name: FUNCTION card_get_for_login(p_slug text); Type: ACL; Schema: kb_auth; Owner: kb_auth_owner
--

REVOKE ALL ON FUNCTION kb_auth.card_get_for_login(p_slug text) FROM PUBLIC;
GRANT ALL ON FUNCTION kb_auth.card_get_for_login(p_slug text) TO kanban_app;


--
-- Name: FUNCTION card_list_enabled_public(); Type: ACL; Schema: kb_auth; Owner: kb_auth_owner
--

REVOKE ALL ON FUNCTION kb_auth.card_list_enabled_public() FROM PUBLIC;
GRANT ALL ON FUNCTION kb_auth.card_list_enabled_public() TO kanban_app;


--
-- Name: FUNCTION card_rewrap(p_id uuid, p_wrapped_dek bytea, p_old_kid text, p_new_kid text); Type: ACL; Schema: kb_auth; Owner: kb_auth_owner
--

REVOKE ALL ON FUNCTION kb_auth.card_rewrap(p_id uuid, p_wrapped_dek bytea, p_old_kid text, p_new_kid text) FROM PUBLIC;
GRANT ALL ON FUNCTION kb_auth.card_rewrap(p_id uuid, p_wrapped_dek bytea, p_old_kid text, p_new_kid text) TO kanban_app;


--
-- PostgreSQL database dump complete
--

\unrestrict 4qTbkXUh552k0WHbTXPcAt0XTKpR4ASC4lFD3Eg9ehXhm9if47i2eNogLrcChOp

