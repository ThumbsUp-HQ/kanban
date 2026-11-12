-- ========================================================
-- Schema Dump: local_admin_credentials & kb_auth.local_*
-- Ticket: KB-P2-04 / KANBA-72
-- ========================================================

-- Table Columns:
--   principal_id uuid NULLABLE=NO DEFAULT=None
--   username text NULLABLE=NO DEFAULT=None
--   password_hash text NULLABLE=NO DEFAULT=None
--   pepper_kid text NULLABLE=NO DEFAULT='pepper-v1'::text
--   updated_at timestamp with time zone NULLABLE=NO DEFAULT=clock_timestamp()

-- Table Constraints:
--   local_admin_credentials_password_hash_check: CHECK ((password_hash ~~ '$argon2id$%'::text))
--   local_admin_credentials_pkey: PRIMARY KEY (principal_id)
--   local_admin_credentials_principal_id_fkey: FOREIGN KEY (principal_id) REFERENCES principals(id) ON DELETE CASCADE
--   local_admin_credentials_username_check: CHECK ((username ~ '^[a-z0-9][a-z0-9._-]{2,62}$'::text))
--   local_admin_credentials_username_key: UNIQUE (username)

-- Row-Level Security Policies:
--   kb_auth_owner_all (b'*'): ROLES=['kb_auth_owner'] USING=true WITH CHECK=true

-- Table Grants:
--   GRANTEE: kb_auth_owner -> TRIGGER
--   GRANTEE: kb_auth_owner -> REFERENCES
--   GRANTEE: kb_auth_owner -> TRUNCATE
--   GRANTEE: kb_auth_owner -> DELETE
--   GRANTEE: kb_auth_owner -> UPDATE
--   GRANTEE: kb_auth_owner -> SELECT
--   GRANTEE: kb_auth_owner -> INSERT

-- Functions in kb_auth:

-- Function: kb_auth.local_admin_create(p_principal_id uuid, p_username text, p_password_hash text, p_pepper_kid text) [OWNER=kb_auth_owner, SECURITY DEFINER=True]
CREATE OR REPLACE FUNCTION kb_auth.local_admin_create(p_principal_id uuid, p_username text, p_password_hash text, p_pepper_kid text DEFAULT 'pepper-v1'::text)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public'
AS $function$
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
$function$

;

-- Function: kb_auth.local_get_credential(p_username text) [OWNER=kb_auth_owner, SECURITY DEFINER=True]
CREATE OR REPLACE FUNCTION kb_auth.local_get_credential(p_username text)
 RETURNS TABLE(principal_id uuid, password_hash text, pepper_kid text)
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public'
AS $function$
BEGIN
    RETURN QUERY
    SELECT c.principal_id, c.password_hash, c.pepper_kid
    FROM local_admin_credentials c
    JOIN principals p ON p.id = c.principal_id
    WHERE c.username = p_username
      AND p.status = 'ACTIVE';
END;
$function$

;

-- Function: kb_auth.local_set_password_hash(p_principal uuid, p_hash text) [OWNER=kb_auth_owner, SECURITY DEFINER=True]
CREATE OR REPLACE FUNCTION kb_auth.local_set_password_hash(p_principal uuid, p_hash text)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public'
AS $function$
BEGIN
    UPDATE local_admin_credentials
    SET password_hash = p_hash,
        updated_at = clock_timestamp()
    WHERE principal_id = p_principal;
END;
$function$

;

