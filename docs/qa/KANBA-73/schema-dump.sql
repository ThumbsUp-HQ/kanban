--
-- PostgreSQL database dump
--

\restrict BSqCs4l1a4W4gXaJX5gdM25cMkLwNXrdylcI6KumiX6aFn2KqzSoP9wSwam2nDw

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
-- Name: oidc_auth_requests; Type: TABLE; Schema: public; Owner: kb_auth_owner
--

CREATE TABLE public.oidc_auth_requests (
    id uuid DEFAULT public.uuidv7() NOT NULL,
    card_id uuid NOT NULL,
    state_hash bytea NOT NULL,
    nonce bytea NOT NULL,
    code_verifier_sealed bytea NOT NULL,
    browser_binding_hash bytea NOT NULL,
    return_to text DEFAULT '/'::text NOT NULL,
    link_intent_id uuid,
    expires_at timestamp with time zone NOT NULL,
    consumed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT oidc_auth_requests_browser_binding_hash_check CHECK ((octet_length(browser_binding_hash) = 32)),
    CONSTRAINT oidc_auth_requests_nonce_check CHECK ((octet_length(nonce) = 16)),
    CONSTRAINT oidc_auth_requests_state_hash_check CHECK ((octet_length(state_hash) = 32))
);

ALTER TABLE ONLY public.oidc_auth_requests FORCE ROW LEVEL SECURITY;


ALTER TABLE public.oidc_auth_requests OWNER TO kb_auth_owner;

--
-- Name: oidc_auth_requests oidc_auth_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: kb_auth_owner
--

ALTER TABLE ONLY public.oidc_auth_requests
    ADD CONSTRAINT oidc_auth_requests_pkey PRIMARY KEY (id);


--
-- Name: oidc_auth_requests oidc_auth_requests_state_hash_key; Type: CONSTRAINT; Schema: public; Owner: kb_auth_owner
--

ALTER TABLE ONLY public.oidc_auth_requests
    ADD CONSTRAINT oidc_auth_requests_state_hash_key UNIQUE (state_hash);


--
-- Name: oidc_auth_requests_card_id_idx; Type: INDEX; Schema: public; Owner: kb_auth_owner
--

CREATE INDEX oidc_auth_requests_card_id_idx ON public.oidc_auth_requests USING btree (card_id);


--
-- Name: oidc_auth_requests_expires_at_idx; Type: INDEX; Schema: public; Owner: kb_auth_owner
--

CREATE INDEX oidc_auth_requests_expires_at_idx ON public.oidc_auth_requests USING btree (expires_at);


--
-- Name: oidc_auth_requests oidc_auth_requests_card_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kb_auth_owner
--

ALTER TABLE ONLY public.oidc_auth_requests
    ADD CONSTRAINT oidc_auth_requests_card_id_fkey FOREIGN KEY (card_id) REFERENCES public.auth_provider_cards(id) ON DELETE CASCADE;


--
-- Name: oidc_auth_requests oidc_auth_requests_link_intent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kb_auth_owner
--

ALTER TABLE ONLY public.oidc_auth_requests
    ADD CONSTRAINT oidc_auth_requests_link_intent_id_fkey FOREIGN KEY (link_intent_id) REFERENCES public.principals(id) ON DELETE SET NULL;


--
-- Name: oidc_auth_requests kb_auth_owner_all; Type: POLICY; Schema: public; Owner: kb_auth_owner
--

CREATE POLICY kb_auth_owner_all ON public.oidc_auth_requests TO kb_auth_owner USING (true) WITH CHECK (true);


--
-- Name: oidc_auth_requests; Type: ROW SECURITY; Schema: public; Owner: kb_auth_owner
--

ALTER TABLE public.oidc_auth_requests ENABLE ROW LEVEL SECURITY;

--
-- PostgreSQL database dump complete
--

\unrestrict BSqCs4l1a4W4gXaJX5gdM25cMkLwNXrdylcI6KumiX6aFn2KqzSoP9wSwam2nDw


--
-- kb_auth security definer functions for oidc_auth_requests
--

CREATE OR REPLACE FUNCTION kb_auth.oidc_request_create(
    p_card_id UUID,
    p_state_hash BYTEA,
    p_nonce BYTEA,
    p_code_verifier_sealed BYTEA,
    p_browser_binding_hash BYTEA,
    p_return_to TEXT,
    p_link_intent_id UUID,
    p_expires_at TIMESTAMPTZ,
    p_id UUID DEFAULT NULL
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_id UUID;
BEGIN
    v_id := COALESCE(p_id, uuidv7());
    INSERT INTO oidc_auth_requests (
        id,
        card_id,
        state_hash,
        nonce,
        code_verifier_sealed,
        browser_binding_hash,
        return_to,
        link_intent_id,
        expires_at,
        consumed_at,
        created_at
    ) VALUES (
        v_id,
        p_card_id,
        p_state_hash,
        p_nonce,
        p_code_verifier_sealed,
        p_browser_binding_hash,
        COALESCE(p_return_to, '/'),
        p_link_intent_id,
        p_expires_at,
        NULL,
        clock_timestamp()
    );
    RETURN v_id;
END;
$$;

ALTER FUNCTION kb_auth.oidc_request_create(UUID, BYTEA, BYTEA, BYTEA, BYTEA, TEXT, UUID, TIMESTAMPTZ, UUID) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.oidc_request_create(UUID, BYTEA, BYTEA, BYTEA, BYTEA, TEXT, UUID, TIMESTAMPTZ, UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.oidc_request_create(UUID, BYTEA, BYTEA, BYTEA, BYTEA, TEXT, UUID, TIMESTAMPTZ, UUID) TO kanban_app;

CREATE OR REPLACE FUNCTION kb_auth.oidc_request_consume(
    p_state_hash BYTEA,
    p_browser_binding_hash BYTEA
)
RETURNS TABLE (
    id UUID,
    card_id UUID,
    nonce BYTEA,
    code_verifier_sealed BYTEA,
    return_to TEXT,
    link_intent_id UUID,
    status TEXT
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_rec RECORD;
BEGIN
    SELECT r.id, r.card_id, r.nonce, r.code_verifier_sealed, r.browser_binding_hash,
           r.return_to, r.link_intent_id, r.expires_at, r.consumed_at
    INTO v_rec
    FROM oidc_auth_requests r
    WHERE r.state_hash = p_state_hash
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN QUERY SELECT NULL::UUID, NULL::UUID, NULL::BYTEA, NULL::BYTEA, NULL::TEXT, NULL::UUID, 'NOT_FOUND'::TEXT;
        RETURN;
    END IF;

    IF v_rec.consumed_at IS NOT NULL THEN
        RETURN QUERY SELECT NULL::UUID, NULL::UUID, NULL::BYTEA, NULL::BYTEA, NULL::TEXT, NULL::UUID, 'ALREADY_CONSUMED'::TEXT;
        RETURN;
    END IF;

    IF v_rec.expires_at <= clock_timestamp() THEN
        RETURN QUERY SELECT NULL::UUID, NULL::UUID, NULL::BYTEA, NULL::BYTEA, NULL::TEXT, NULL::UUID, 'EXPIRED'::TEXT;
        RETURN;
    END IF;

    IF v_rec.browser_binding_hash != p_browser_binding_hash THEN
        RETURN QUERY SELECT NULL::UUID, NULL::UUID, NULL::BYTEA, NULL::BYTEA, NULL::TEXT, NULL::UUID, 'BINDING_MISMATCH'::TEXT;
        RETURN;
    END IF;

    UPDATE oidc_auth_requests
    SET consumed_at = clock_timestamp()
    WHERE oidc_auth_requests.id = v_rec.id;

    RETURN QUERY SELECT v_rec.id, v_rec.card_id, v_rec.nonce, v_rec.code_verifier_sealed,
                        v_rec.return_to, v_rec.link_intent_id, 'OK'::TEXT;
END;
$$;

ALTER FUNCTION kb_auth.oidc_request_consume(BYTEA, BYTEA) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.oidc_request_consume(BYTEA, BYTEA) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.oidc_request_consume(BYTEA, BYTEA) TO kanban_app;
