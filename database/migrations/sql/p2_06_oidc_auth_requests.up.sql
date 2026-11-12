-- Phase 2 / Auth: OIDC and OAuth2 authentication requests and state tracking (KB-P2-06)

-- 1. Table: oidc_auth_requests
CREATE TABLE oidc_auth_requests (
    id                    UUID PRIMARY KEY DEFAULT uuidv7(),
    card_id               UUID NOT NULL REFERENCES auth_provider_cards(id) ON DELETE CASCADE,
    state_hash            BYTEA NOT NULL UNIQUE CHECK (octet_length(state_hash) = 32),
    nonce                 BYTEA NOT NULL CHECK (octet_length(nonce) = 16),
    code_verifier_sealed  BYTEA NOT NULL,
    browser_binding_hash  BYTEA NOT NULL CHECK (octet_length(browser_binding_hash) = 32),
    return_to             TEXT NOT NULL DEFAULT '/',
    link_intent_id        UUID REFERENCES principals(id) ON DELETE SET NULL,
    expires_at            TIMESTAMPTZ NOT NULL,
    consumed_at           TIMESTAMPTZ,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX oidc_auth_requests_card_id_idx ON oidc_auth_requests (card_id);
CREATE INDEX oidc_auth_requests_expires_at_idx ON oidc_auth_requests (expires_at);

-- Ownership and permissions
ALTER TABLE oidc_auth_requests OWNER TO kb_auth_owner;
REVOKE ALL ON oidc_auth_requests FROM PUBLIC, kanban_app, app_rls_reader;

-- RLS
ALTER TABLE oidc_auth_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE oidc_auth_requests FORCE ROW LEVEL SECURITY;
CREATE POLICY kb_auth_owner_all ON oidc_auth_requests
    FOR ALL TO kb_auth_owner USING (true) WITH CHECK (true);

-- 2. Functions in schema kb_auth (owned by kb_auth_owner, SECURITY DEFINER)

-- Function 1: oidc_request_create
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

-- Function 2: oidc_request_consume
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
