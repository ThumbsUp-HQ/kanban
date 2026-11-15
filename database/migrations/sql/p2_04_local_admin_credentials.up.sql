-- Phase 2 / Auth: Local Admin card credentials and kb_auth functions (KB-P2-04)

-- 1. Table: local_admin_credentials
CREATE TABLE local_admin_credentials (
    principal_id   UUID PRIMARY KEY REFERENCES principals(id) ON DELETE CASCADE,
    username       TEXT NOT NULL UNIQUE CHECK (username ~ '^[a-z0-9][a-z0-9._-]{2,62}$'),
    password_hash  TEXT NOT NULL CHECK (password_hash LIKE '$argon2id$%'),
    pepper_kid     TEXT NOT NULL DEFAULT 'pepper-v1',
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- Ownership and permissions
ALTER TABLE local_admin_credentials OWNER TO kb_auth_owner;
REVOKE ALL ON local_admin_credentials FROM PUBLIC, kanban_app, app_rls_reader;
GRANT SELECT (principal_id, username) ON TABLE local_admin_credentials TO kanban_app;

-- RLS
ALTER TABLE local_admin_credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE local_admin_credentials FORCE ROW LEVEL SECURITY;
CREATE POLICY kb_auth_owner_all ON local_admin_credentials
    FOR ALL TO kb_auth_owner USING (true) WITH CHECK (true);
CREATE POLICY kanban_app_select_own_local_admin ON local_admin_credentials
    FOR SELECT TO kanban_app
    USING (principal_id = ANY (app_effective_principal_set()));

-- Allow kb_auth_owner to check principal status on login
GRANT SELECT ON TABLE principals TO kb_auth_owner;
CREATE POLICY kb_auth_owner_select_principals ON principals
    FOR SELECT TO kb_auth_owner USING (true);

-- 2. Functions in schema kb_auth (owned by kb_auth_owner, SECURITY DEFINER)

-- Function 1: local_get_credential(p_username text)
CREATE OR REPLACE FUNCTION kb_auth.local_get_credential(p_username TEXT)
RETURNS TABLE (
    principal_id UUID,
    password_hash TEXT,
    pepper_kid TEXT
)
LANGUAGE plpgsql
STABLE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    RETURN QUERY
    SELECT c.principal_id, c.password_hash, c.pepper_kid
    FROM local_admin_credentials c
    JOIN principals p ON p.id = c.principal_id
    WHERE c.username = p_username
      AND p.status = 'ACTIVE';
END;
$$;

ALTER FUNCTION kb_auth.local_get_credential(TEXT) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.local_get_credential(TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.local_get_credential(TEXT) TO kanban_app;

-- Function 2: local_set_password_hash(p_principal uuid, p_hash text)
CREATE OR REPLACE FUNCTION kb_auth.local_set_password_hash(p_principal UUID, p_hash TEXT)
RETURNS VOID
LANGUAGE plpgsql
VOLATILE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    UPDATE local_admin_credentials
    SET password_hash = p_hash,
        updated_at = clock_timestamp()
    WHERE principal_id = p_principal;
END;
$$;

ALTER FUNCTION kb_auth.local_set_password_hash(UUID, TEXT) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.local_set_password_hash(UUID, TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.local_set_password_hash(UUID, TEXT) TO kanban_app;

-- Function 3: local_admin_create(...)
CREATE OR REPLACE FUNCTION kb_auth.local_admin_create(
    p_principal_id   UUID,
    p_username       TEXT,
    p_password_hash  TEXT,
    p_pepper_kid     TEXT DEFAULT 'pepper-v1'
)
RETURNS VOID
LANGUAGE plpgsql
VOLATILE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF NOT (
        (
            EXISTS (
                SELECT 1
                FROM role_bindings rb
                WHERE rb.principal_id = ANY (app_effective_principal_set())
                  AND rb.role = 'SERVER_ADMIN'
            )
            AND current_setting('app.aal_level', true) = '2'
        )
        OR current_setting('app.is_setup_claim', true) = 'true'
    ) THEN
        RAISE EXCEPTION 'insufficient_privilege: SERVER_ADMIN with AAL2 or setup-claim context required'
            USING ERRCODE = '42501';
    END IF;

    DELETE FROM local_admin_credentials WHERE username = p_username;

    INSERT INTO local_admin_credentials (
        principal_id,
        username,
        password_hash,
        pepper_kid,
        updated_at
    ) VALUES (
        p_principal_id,
        p_username,
        p_password_hash,
        COALESCE(p_pepper_kid, 'pepper-v1'),
        clock_timestamp()
    );
END;
$$;

ALTER FUNCTION kb_auth.local_admin_create(UUID, TEXT, TEXT, TEXT) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.local_admin_create(UUID, TEXT, TEXT, TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.local_admin_create(UUID, TEXT, TEXT, TEXT) TO kanban_app;
