-- Schema dump for KANBA-98 (p2_08_user_identities)
-- Generated automatically from live migration test DB

-- ========================================================
-- Table: user_identities
-- ========================================================
CREATE TABLE public.user_identities (
    id uuid DEFAULT uuidv7() NOT NULL,
    workspace_id uuid NOT NULL,
    principal_id uuid NOT NULL,
    auth_card_id uuid NOT NULL,
    immutable_subject_id text NOT NULL,
    subject_email_at_link text NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    last_login_at timestamp with time zone NULL
);

-- Constraints for user_identities
ALTER TABLE public.user_identities ADD CONSTRAINT user_identities_immutable_subject_id_check CHECK (((char_length(btrim(immutable_subject_id)) >= 1) AND (char_length(btrim(immutable_subject_id)) <= 255)));
ALTER TABLE public.user_identities ADD CONSTRAINT user_identities_pkey PRIMARY KEY (id);
ALTER TABLE public.user_identities ADD CONSTRAINT user_identities_auth_card_id_immutable_subject_id_key UNIQUE (auth_card_id, immutable_subject_id);
ALTER TABLE public.user_identities ADD CONSTRAINT user_identities_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE;
ALTER TABLE public.user_identities ADD CONSTRAINT user_identities_principal_id_fkey FOREIGN KEY (principal_id) REFERENCES principals(id) ON DELETE CASCADE;
ALTER TABLE public.user_identities ADD CONSTRAINT user_identities_auth_card_id_fkey FOREIGN KEY (auth_card_id) REFERENCES auth_provider_cards(id) ON DELETE RESTRICT;

-- Row Level Security: enabled=True, force=True

-- Grants for user_identities
-- GRANT INSERT TO kb_auth_owner
-- GRANT SELECT TO kb_auth_owner
-- GRANT UPDATE TO kb_auth_owner
-- GRANT DELETE TO kb_auth_owner
-- GRANT TRUNCATE TO kb_auth_owner
-- GRANT REFERENCES TO kb_auth_owner
-- GRANT TRIGGER TO kb_auth_owner

-- ========================================================
-- Table: identity_link_intents
-- ========================================================
CREATE TABLE public.identity_link_intents (
    id uuid DEFAULT uuidv7() NOT NULL,
    principal_id uuid NOT NULL,
    session_id uuid NOT NULL,
    target_card_id uuid NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    consumed_at timestamp with time zone NULL
);

-- Constraints for identity_link_intents
ALTER TABLE public.identity_link_intents ADD CONSTRAINT identity_link_intents_pkey PRIMARY KEY (id);
ALTER TABLE public.identity_link_intents ADD CONSTRAINT identity_link_intents_principal_id_fkey FOREIGN KEY (principal_id) REFERENCES principals(id) ON DELETE CASCADE;
ALTER TABLE public.identity_link_intents ADD CONSTRAINT identity_link_intents_session_id_fkey FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE;
ALTER TABLE public.identity_link_intents ADD CONSTRAINT identity_link_intents_target_card_id_fkey FOREIGN KEY (target_card_id) REFERENCES auth_provider_cards(id) ON DELETE CASCADE;

-- Row Level Security: enabled=True, force=True

-- Grants for identity_link_intents
-- GRANT INSERT TO kb_auth_owner
-- GRANT SELECT TO kb_auth_owner
-- GRANT UPDATE TO kb_auth_owner
-- GRANT DELETE TO kb_auth_owner
-- GRANT TRUNCATE TO kb_auth_owner
-- GRANT REFERENCES TO kb_auth_owner
-- GRANT TRIGGER TO kb_auth_owner

-- ========================================================
-- Functions in kb_auth created by p2_08_user_identities
-- ========================================================
-- Function: kb_auth.card_get_by_id (SECURITY DEFINER)
CREATE OR REPLACE FUNCTION kb_auth.card_get_by_id(p_id uuid)
 RETURNS TABLE(id uuid, workspace_id uuid, provider_kind text, slug text, display_name text, button_subtext text, icon_preset text, is_enabled boolean, sort_rank text, auto_provision_users boolean, allowed_email_domains text[], public_config jsonb)
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public'
AS $function$
BEGIN
    RETURN QUERY
    SELECT
        c.id,
        c.workspace_id,
        c.provider_kind,
        c.slug,
        c.display_name,
        c.button_subtext,
        c.icon_preset,
        c.is_enabled,
        c.sort_rank::TEXT,
        c.auto_provision_users,
        c.allowed_email_domains,
        c.public_config
    FROM auth_provider_cards c
    WHERE c.id = p_id;
END;
$function$


-- Function: kb_auth.identity_link_consume_and_bind (SECURITY DEFINER)
CREATE OR REPLACE FUNCTION kb_auth.identity_link_consume_and_bind(p_intent_id uuid, p_principal_id uuid, p_session_id uuid, p_card_id uuid, p_subject text, p_email text DEFAULT NULL::text)
 RETURNS uuid
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public'
AS $function$
DECLARE
    v_intent RECORD;
    v_workspace_id UUID;
    v_identity_id UUID;
BEGIN
    IF p_intent_id IS NULL OR p_principal_id IS NULL OR p_session_id IS NULL OR p_card_id IS NULL OR p_subject IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'LINK_INTENT_INVALID';
    END IF;

    SELECT * INTO v_intent
    FROM identity_link_intents
    WHERE id = p_intent_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'LINK_INTENT_INVALID';
    END IF;

    IF v_intent.consumed_at IS NOT NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'LINK_INTENT_INVALID';
    END IF;

    IF v_intent.expires_at <= clock_timestamp() THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'LINK_INTENT_INVALID';
    END IF;

    IF v_intent.principal_id != p_principal_id OR v_intent.session_id != p_session_id OR v_intent.target_card_id != p_card_id THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'LINK_INTENT_INVALID';
    END IF;

    IF EXISTS (
        SELECT 1 FROM user_identities
        WHERE auth_card_id = p_card_id AND immutable_subject_id = p_subject
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '23505', MESSAGE = 'IDENTITY_ALREADY_LINKED';
    END IF;

    UPDATE identity_link_intents
    SET consumed_at = clock_timestamp()
    WHERE id = p_intent_id;

    SELECT workspace_id INTO v_workspace_id FROM principals WHERE id = p_principal_id;
    IF v_workspace_id IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'PRINCIPAL_NOT_FOUND';
    END IF;

    v_identity_id := uuidv7();
    INSERT INTO user_identities (
        id, workspace_id, principal_id, auth_card_id, immutable_subject_id, subject_email_at_link, created_at, last_login_at
    ) VALUES (
        v_identity_id, v_workspace_id, p_principal_id, p_card_id, p_subject, p_email, clock_timestamp(), clock_timestamp()
    );

    RETURN v_identity_id;
END;
$function$


-- Function: kb_auth.identity_link_intent_create (SECURITY DEFINER)
CREATE OR REPLACE FUNCTION kb_auth.identity_link_intent_create(p_principal_id uuid, p_session_id uuid, p_target_card_id uuid, p_ttl_seconds integer DEFAULT 300, p_id uuid DEFAULT NULL::uuid)
 RETURNS uuid
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public'
AS $function$
DECLARE
    v_id UUID;
    v_ttl INT;
BEGIN
    IF p_principal_id IS NULL OR p_session_id IS NULL OR p_target_card_id IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'NULL_ARGUMENT';
    END IF;

    v_id := COALESCE(p_id, uuidv7());
    v_ttl := GREATEST(COALESCE(p_ttl_seconds, 300), 1);

    INSERT INTO identity_link_intents (
        id, principal_id, session_id, target_card_id, expires_at, consumed_at
    ) VALUES (
        v_id, p_principal_id, p_session_id, p_target_card_id,
        clock_timestamp() + (v_ttl::text || ' seconds')::interval,
        NULL
    );
    RETURN v_id;
END;
$function$


-- Function: kb_auth.identity_link_intent_get (SECURITY DEFINER)
CREATE OR REPLACE FUNCTION kb_auth.identity_link_intent_get(p_intent_id uuid)
 RETURNS TABLE(id uuid, principal_id uuid, session_id uuid, target_card_id uuid, expires_at timestamp with time zone, consumed_at timestamp with time zone)
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public'
AS $function$
BEGIN
    RETURN QUERY
    SELECT i.id, i.principal_id, i.session_id, i.target_card_id, i.expires_at, i.consumed_at
    FROM identity_link_intents i
    WHERE i.id = p_intent_id;
END;
$function$


-- Function: kb_auth.identity_list_for_principal (SECURITY DEFINER)
CREATE OR REPLACE FUNCTION kb_auth.identity_list_for_principal(p_principal uuid)
 RETURNS TABLE(id uuid, auth_card_id uuid, card_slug text, card_display_name text, provider_kind text, immutable_subject_id text, subject_email_at_link text, created_at timestamp with time zone, last_login_at timestamp with time zone)
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public'
AS $function$
BEGIN
    RETURN QUERY
    SELECT
        ui.id,
        ui.auth_card_id,
        c.slug AS card_slug,
        c.display_name AS card_display_name,
        c.provider_kind,
        ui.immutable_subject_id,
        ui.subject_email_at_link,
        ui.created_at,
        ui.last_login_at
    FROM user_identities ui
    JOIN auth_provider_cards c ON c.id = ui.auth_card_id
    WHERE ui.principal_id = p_principal
    ORDER BY ui.created_at ASC;
END;
$function$


-- Function: kb_auth.identity_lookup (SECURITY DEFINER)
CREATE OR REPLACE FUNCTION kb_auth.identity_lookup(p_card_id uuid, p_subject text)
 RETURNS TABLE(id uuid, workspace_id uuid, principal_id uuid, status text, last_login_at timestamp with time zone, subject_email_at_link text, user_email text, display_name text)
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public'
AS $function$
BEGIN
    RETURN QUERY
    SELECT
        ui.id,
        ui.workspace_id,
        ui.principal_id,
        p.status,
        ui.last_login_at,
        ui.subject_email_at_link,
        u.email AS user_email,
        p.display_name
    FROM user_identities ui
    JOIN principals p ON p.id = ui.principal_id
    JOIN users u ON u.id = ui.principal_id
    WHERE ui.auth_card_id = p_card_id
      AND ui.immutable_subject_id = p_subject;
END;
$function$


-- Function: kb_auth.identity_provision_new_user (SECURITY DEFINER)
CREATE OR REPLACE FUNCTION kb_auth.identity_provision_new_user(p_workspace_id uuid, p_card_id uuid, p_subject text, p_email text, p_display_name text)
 RETURNS TABLE(principal_id uuid, identity_id uuid)
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public'
AS $function$
DECLARE
    v_principal_id UUID;
    v_identity_id UUID;
    v_clean_display TEXT;
    v_clean_key TEXT;
BEGIN
    IF p_workspace_id IS NULL OR p_card_id IS NULL OR p_subject IS NULL OR p_email IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'NULL_ARGUMENT';
    END IF;

    -- Zero email auto-merge invariant: never auto-attach to existing user
    IF EXISTS (
        SELECT 1 FROM users
        WHERE workspace_id = p_workspace_id
          AND lower(email) = lower(p_email)
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '23505', MESSAGE = 'IDENTITY_LINK_REQUIRED';
    END IF;

    -- Verify card subject is not already bound
    IF EXISTS (
        SELECT 1 FROM user_identities
        WHERE auth_card_id = p_card_id
          AND immutable_subject_id = p_subject
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '23505', MESSAGE = 'IDENTITY_ALREADY_LINKED';
    END IF;

    v_principal_id := uuidv7();
    v_identity_id := uuidv7();
    v_clean_display := substr(COALESCE(NULLIF(btrim(p_display_name), ''), p_email), 1, 200);
    v_clean_key := substr(lower(p_email), 1, 200);

    INSERT INTO principals (id, principal_type, workspace_id, status, display_name)
    VALUES (v_principal_id, 'USER', p_workspace_id, 'ACTIVE', v_clean_display);

    INSERT INTO objects (id, object_type, workspace_id, project_id, canonical_key, display_title, created_by_id)
    VALUES (v_principal_id, 'user'::object_kind, p_workspace_id, NULL, v_clean_key, v_clean_display, v_principal_id);

    INSERT INTO users (id, object_type, principal_type, workspace_id, email)
    VALUES (v_principal_id, 'user', 'USER', p_workspace_id, lower(p_email));

    INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type)
    VALUES (p_workspace_id, v_principal_id, 'WORKSPACE_MEMBER'::rbac_role, 'workspace');

    INSERT INTO user_identities (
        id, workspace_id, principal_id, auth_card_id, immutable_subject_id, subject_email_at_link, created_at, last_login_at
    ) VALUES (
        v_identity_id, p_workspace_id, v_principal_id, p_card_id, p_subject, p_email, clock_timestamp(), clock_timestamp()
    );

    RETURN QUERY SELECT v_principal_id, v_identity_id;
END;
$function$


-- Function: kb_auth.identity_record_login (SECURITY DEFINER)
CREATE OR REPLACE FUNCTION kb_auth.identity_record_login(p_identity_id uuid)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public'
AS $function$
BEGIN
    UPDATE user_identities
    SET last_login_at = clock_timestamp()
    WHERE id = p_identity_id;
END;
$function$


-- Function: kb_auth.identity_unlink (SECURITY DEFINER)
CREATE OR REPLACE FUNCTION kb_auth.identity_unlink(p_principal uuid, p_identity_id uuid)
 RETURNS boolean
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public'
AS $function$
DECLARE
    v_ident_count INT;
    v_local_count INT;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM user_identities
        WHERE id = p_identity_id AND principal_id = p_principal
    ) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'IDENTITY_NOT_FOUND';
    END IF;

    SELECT count(*) INTO v_ident_count FROM user_identities WHERE principal_id = p_principal;
    SELECT count(*) INTO v_local_count FROM local_admin_credentials WHERE principal_id = p_principal;

    IF v_ident_count <= 1 AND v_local_count = 0 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'LAST_AUTH_METHOD';
    END IF;

    DELETE FROM user_identities WHERE id = p_identity_id AND principal_id = p_principal;
    RETURN TRUE;
END;
$function$

