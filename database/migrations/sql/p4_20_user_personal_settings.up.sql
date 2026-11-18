-- Migration p4_20_user_personal_settings (UP)
-- User preferences (timezone, avatar) and profile update helper functions.

-- 1. user_preferences table
CREATE TABLE IF NOT EXISTS public.user_preferences (
    principal_id UUID PRIMARY KEY REFERENCES public.principals(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    timezone TEXT NOT NULL DEFAULT 'UTC',
    avatar_storage_key TEXT,
    avatar_content_type TEXT,
    avatar_sha256 BYTEA,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

ALTER TABLE public.user_preferences OWNER TO kanban_migrator;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.user_preferences TO kb_auth_owner, kanban_app;

-- Enable and Force RLS
ALTER TABLE public.user_preferences ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_preferences FORCE ROW LEVEL SECURITY;

-- Allow kb_auth_owner full access for SECURITY DEFINER routines
CREATE POLICY user_preferences_kb_auth_owner ON public.user_preferences
    FOR ALL TO kb_auth_owner
    USING (true)
    WITH CHECK (true);

-- RLS Policies on user_preferences:
-- SELECT allowed within current workspace
CREATE POLICY user_preferences_select_policy ON public.user_preferences
    FOR SELECT TO kanban_app
    USING (workspace_id = app_current_workspace_id());

-- INSERT allowed for own principal_id within current workspace
CREATE POLICY user_preferences_insert_policy ON public.user_preferences
    FOR INSERT TO kanban_app
    WITH CHECK (
        principal_id = app_current_principal_id()
        AND workspace_id = app_current_workspace_id()
    );

-- UPDATE allowed for own principal_id
CREATE POLICY user_preferences_update_policy ON public.user_preferences
    FOR UPDATE TO kanban_app
    USING (
        principal_id = app_current_principal_id()
        AND workspace_id = app_current_workspace_id()
    )
    WITH CHECK (
        principal_id = app_current_principal_id()
        AND workspace_id = app_current_workspace_id()
    );

-- DELETE allowed for own principal_id
CREATE POLICY user_preferences_delete_policy ON public.user_preferences
    FOR DELETE TO kanban_app
    USING (
        principal_id = app_current_principal_id()
        AND workspace_id = app_current_workspace_id()
    );


-- 2. SECURITY DEFINER helper to update own profile (display_name & timezone)
CREATE OR REPLACE FUNCTION kb_auth.user_update_own_profile(
    p_principal_id UUID,
    p_display_name TEXT,
    p_timezone TEXT
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_caller_id UUID;
    v_workspace_id UUID;
BEGIN
    v_caller_id := app_current_principal_id();
    IF v_caller_id IS NULL OR v_caller_id <> p_principal_id THEN
        RAISE EXCEPTION 'PERMISSION_DENIED: Cannot update profile for another user'
            USING ERRCODE = '42501';
    END IF;

    IF p_display_name IS NULL OR length(trim(p_display_name)) = 0 OR length(p_display_name) > 120 THEN
        RAISE EXCEPTION 'INVALID_DISPLAY_NAME: Display name must be between 1 and 120 characters'
            USING ERRCODE = '22000';
    END IF;

    SELECT workspace_id INTO v_workspace_id
    FROM public.principals
    WHERE id = p_principal_id;

    IF v_workspace_id IS NULL THEN
        RAISE EXCEPTION 'USER_NOT_FOUND: Principal % does not exist', p_principal_id
            USING ERRCODE = 'P0002';
    END IF;

    -- Update principals display_name
    UPDATE public.principals
    SET display_name = trim(p_display_name)
    WHERE id = p_principal_id;

    -- Upsert user_preferences
    INSERT INTO public.user_preferences (principal_id, workspace_id, timezone, updated_at)
    VALUES (p_principal_id, v_workspace_id, coalesce(trim(p_timezone), 'UTC'), clock_timestamp())
    ON CONFLICT (principal_id) DO UPDATE
    SET timezone = coalesce(trim(EXCLUDED.timezone), 'UTC'),
        updated_at = clock_timestamp();
END;
$$;

ALTER FUNCTION kb_auth.user_update_own_profile(UUID, TEXT, TEXT) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.user_update_own_profile(UUID, TEXT, TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.user_update_own_profile(UUID, TEXT, TEXT) TO kanban_app;


-- 3. SECURITY DEFINER helper to look up local credential by principal_id
CREATE OR REPLACE FUNCTION kb_auth.local_get_credential_by_principal(
    p_principal_id UUID
)
RETURNS TABLE (
    principal_id UUID,
    username TEXT,
    password_hash TEXT,
    pepper_kid TEXT
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    RETURN QUERY
    SELECT c.principal_id, c.username, c.password_hash, c.pepper_kid
    FROM local_admin_credentials c
    WHERE c.principal_id = p_principal_id;
END;
$$;

ALTER FUNCTION kb_auth.local_get_credential_by_principal(UUID) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.local_get_credential_by_principal(UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.local_get_credential_by_principal(UUID) TO kanban_app;


-- 4. SECURITY DEFINER helper to update webauthn credential nickname
CREATE OR REPLACE FUNCTION kb_auth.webauthn_credential_update_nickname(
    p_credential_id_uuid UUID,
    p_principal_id UUID,
    p_nickname TEXT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    UPDATE webauthn_credentials
    SET nickname = nullif(trim(p_nickname), '')
    WHERE id = p_credential_id_uuid
      AND principal_id = p_principal_id;

    RETURN FOUND;
END;
$$;

ALTER FUNCTION kb_auth.webauthn_credential_update_nickname(UUID, UUID, TEXT) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.webauthn_credential_update_nickname(UUID, UUID, TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.webauthn_credential_update_nickname(UUID, UUID, TEXT) TO kanban_app;


-- 5. SECURITY DEFINER helper to revoke all sessions except current session
CREATE OR REPLACE FUNCTION kb_auth.session_revoke_all_except(
    p_principal_id UUID,
    p_except_session_id UUID
)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_count INT;
BEGIN
    UPDATE sessions
    SET revoked_at = clock_timestamp()
    WHERE principal_id = p_principal_id
      AND (p_except_session_id IS NULL OR id <> p_except_session_id)
      AND revoked_at IS NULL;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$;

ALTER FUNCTION kb_auth.session_revoke_all_except(UUID, UUID) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.session_revoke_all_except(UUID, UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.session_revoke_all_except(UUID, UUID) TO kanban_app;


-- 6. SECURITY DEFINER helper to retrieve user avatar metadata
CREATE OR REPLACE FUNCTION kb_auth.user_get_avatar(p_principal_id UUID)
RETURNS TABLE (
    avatar_storage_key TEXT,
    avatar_content_type TEXT
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    RETURN QUERY
    SELECT u.avatar_storage_key, u.avatar_content_type
    FROM public.user_preferences u
    WHERE u.principal_id = p_principal_id;
END;
$$;

ALTER FUNCTION kb_auth.user_get_avatar(UUID) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.user_get_avatar(UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.user_get_avatar(UUID) TO kanban_app;



