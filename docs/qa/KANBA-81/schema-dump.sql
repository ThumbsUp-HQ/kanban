-- ========================================================
-- Schema Dump: totp_factors, recovery_codes & kb_auth.totp_* / recovery_*
-- Ticket: KB-P2-05a / KANBA-81
-- ========================================================

-- Table: totp_factors
-- Columns:
--   id uuid NULLABLE=NO DEFAULT=uuidv7()
--   principal_id uuid NULLABLE=NO DEFAULT=None
--   status text NULLABLE=NO DEFAULT='PENDING'::text
--   encrypted_secret_blob bytea NULLABLE=NO DEFAULT=None
--   wrapped_dek bytea NULLABLE=NO DEFAULT=None
--   dek_kid text NULLABLE=NO DEFAULT='kek-v1'::text
--   last_accepted_step bigint NULLABLE=NO DEFAULT=0
--   created_at timestamp with time zone NULLABLE=NO DEFAULT=clock_timestamp()
--   updated_at timestamp with time zone NULLABLE=NO DEFAULT=clock_timestamp()
-- Constraints:
--   totp_factors_pkey: PRIMARY KEY (id)
--   totp_factors_principal_id_fkey: FOREIGN KEY (principal_id) REFERENCES principals(id) ON DELETE CASCADE
--   totp_factors_status_check: CHECK ((status = ANY (ARRAY['PENDING'::text, 'ACTIVE'::text, 'REVOKED'::text])))
-- RLS: rowsecurity=True forcerowsecurity=True
-- Policies:
--   kb_auth_owner_all: ROLES=['kb_auth_owner'] USING=true WITH_CHECK=true
-- Grants:
--   GRANTEE: kb_auth_owner -> DELETE
--   GRANTEE: kb_auth_owner -> INSERT
--   GRANTEE: kb_auth_owner -> REFERENCES
--   GRANTEE: kb_auth_owner -> SELECT
--   GRANTEE: kb_auth_owner -> TRIGGER
--   GRANTEE: kb_auth_owner -> TRUNCATE
--   GRANTEE: kb_auth_owner -> UPDATE

-- Table: recovery_codes
-- Columns:
--   id uuid NULLABLE=NO DEFAULT=uuidv7()
--   principal_id uuid NULLABLE=NO DEFAULT=None
--   code_hmac bytea NULLABLE=NO DEFAULT=None
--   used_at timestamp with time zone NULLABLE=YES DEFAULT=None
--   created_at timestamp with time zone NULLABLE=NO DEFAULT=clock_timestamp()
-- Constraints:
--   recovery_codes_code_hmac_key: UNIQUE (code_hmac)
--   recovery_codes_pkey: PRIMARY KEY (id)
--   recovery_codes_principal_id_fkey: FOREIGN KEY (principal_id) REFERENCES principals(id) ON DELETE CASCADE
-- RLS: rowsecurity=True forcerowsecurity=True
-- Policies:
--   kb_auth_owner_all: ROLES=['kb_auth_owner'] USING=true WITH_CHECK=true
-- Grants:
--   GRANTEE: kb_auth_owner -> DELETE
--   GRANTEE: kb_auth_owner -> INSERT
--   GRANTEE: kb_auth_owner -> REFERENCES
--   GRANTEE: kb_auth_owner -> SELECT
--   GRANTEE: kb_auth_owner -> TRIGGER
--   GRANTEE: kb_auth_owner -> TRUNCATE
--   GRANTEE: kb_auth_owner -> UPDATE

-- Functions in kb_auth:

-- Function: kb_auth.mfa_status
CREATE OR REPLACE FUNCTION kb_auth.mfa_status(p_principal_id uuid)
 RETURNS TABLE(has_active_totp boolean, unused_recovery_codes integer)
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public'
AS $function$
BEGIN
    RETURN QUERY
    SELECT
        EXISTS (
            SELECT 1 FROM totp_factors
            WHERE principal_id = p_principal_id AND status = 'ACTIVE'
        ) AS has_active_totp,
        (
            SELECT count(*)::INTEGER FROM recovery_codes
            WHERE principal_id = p_principal_id AND used_at IS NULL
        ) AS unused_recovery_codes;
END;
$function$;

-- Function: kb_auth.recovery_code_consume
CREATE OR REPLACE FUNCTION kb_auth.recovery_code_consume(p_principal_id uuid, p_code_hmac bytea)
 RETURNS integer
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public'
AS $function$
DECLARE
    v_remaining INTEGER;
BEGIN
    UPDATE recovery_codes
    SET used_at = clock_timestamp()
    WHERE principal_id = p_principal_id
      AND code_hmac = p_code_hmac
      AND used_at IS NULL;

    IF NOT FOUND THEN
        RETURN -1;
    END IF;

    SELECT count(*)::INTEGER INTO v_remaining
    FROM recovery_codes
    WHERE principal_id = p_principal_id
      AND used_at IS NULL;

    RETURN v_remaining;
END;
$function$;

-- Function: kb_auth.recovery_codes_replace
CREATE OR REPLACE FUNCTION kb_auth.recovery_codes_replace(p_principal_id uuid, p_code_hmacs bytea[])
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public'
AS $function$
BEGIN
    DELETE FROM recovery_codes
    WHERE principal_id = p_principal_id;

    INSERT INTO recovery_codes (
        principal_id,
        code_hmac
    )
    SELECT p_principal_id, unnest(p_code_hmacs);
END;
$function$;

-- Function: kb_auth.totp_confirm
CREATE OR REPLACE FUNCTION kb_auth.totp_confirm(p_factor_id uuid, p_step bigint)
 RETURNS boolean
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public'
AS $function$
DECLARE
    v_principal_id UUID;
BEGIN
    SELECT principal_id INTO v_principal_id
    FROM totp_factors
    WHERE id = p_factor_id
      AND status = 'PENDING'
      AND created_at >= clock_timestamp() - interval '600 seconds';

    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;

    -- Revoke previously active factors
    UPDATE totp_factors
    SET status = 'REVOKED', updated_at = clock_timestamp()
    WHERE principal_id = v_principal_id
      AND id != p_factor_id
      AND status = 'ACTIVE';

    -- Activate confirmed factor
    UPDATE totp_factors
    SET status = 'ACTIVE',
        last_accepted_step = p_step,
        updated_at = clock_timestamp()
    WHERE id = p_factor_id;

    RETURN TRUE;
END;
$function$;

-- Function: kb_auth.totp_delete
CREATE OR REPLACE FUNCTION kb_auth.totp_delete(p_principal_id uuid)
 RETURNS boolean
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public'
AS $function$
BEGIN
    UPDATE totp_factors
    SET status = 'REVOKED',
        updated_at = clock_timestamp()
    WHERE principal_id = p_principal_id
      AND status = 'ACTIVE';

    RETURN FOUND;
END;
$function$;

-- Function: kb_auth.totp_enroll
CREATE OR REPLACE FUNCTION kb_auth.totp_enroll(p_principal_id uuid, p_encrypted_blob bytea, p_wrapped_dek bytea, p_dek_kid text)
 RETURNS uuid
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public'
AS $function$
DECLARE
    v_id UUID := uuidv7();
BEGIN
    DELETE FROM totp_factors
    WHERE principal_id = p_principal_id
      AND status = 'PENDING';

    INSERT INTO totp_factors (
        id,
        principal_id,
        status,
        encrypted_secret_blob,
        wrapped_dek,
        dek_kid
    ) VALUES (
        v_id,
        p_principal_id,
        'PENDING',
        p_encrypted_blob,
        p_wrapped_dek,
        p_dek_kid
    );

    RETURN v_id;
END;
$function$;

-- Function: kb_auth.totp_get_active
CREATE OR REPLACE FUNCTION kb_auth.totp_get_active(p_principal_id uuid)
 RETURNS TABLE(id uuid, encrypted_secret_blob bytea, wrapped_dek bytea, dek_kid text, last_accepted_step bigint)
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public'
AS $function$
BEGIN
    RETURN QUERY
    SELECT f.id, f.encrypted_secret_blob, f.wrapped_dek, f.dek_kid, f.last_accepted_step
    FROM totp_factors f
    WHERE f.principal_id = p_principal_id
      AND f.status = 'ACTIVE'
    ORDER BY f.created_at DESC
    LIMIT 1;
END;
$function$;

-- Function: kb_auth.totp_get_pending
CREATE OR REPLACE FUNCTION kb_auth.totp_get_pending(p_principal_id uuid)
 RETURNS TABLE(id uuid, encrypted_secret_blob bytea, wrapped_dek bytea, dek_kid text, created_at timestamp with time zone)
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public'
AS $function$
BEGIN
    RETURN QUERY
    SELECT f.id, f.encrypted_secret_blob, f.wrapped_dek, f.dek_kid, f.created_at
    FROM totp_factors f
    WHERE f.principal_id = p_principal_id
      AND f.status = 'PENDING'
      AND f.created_at >= clock_timestamp() - interval '600 seconds'
    ORDER BY f.created_at DESC
    LIMIT 1;
END;
$function$;

-- Function: kb_auth.totp_update_step
CREATE OR REPLACE FUNCTION kb_auth.totp_update_step(p_factor_id uuid, p_step bigint)
 RETURNS boolean
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public'
AS $function$
BEGIN
    UPDATE totp_factors
    SET last_accepted_step = p_step,
        updated_at = clock_timestamp()
    WHERE id = p_factor_id
      AND status = 'ACTIVE'
      AND last_accepted_step < p_step;

    RETURN FOUND;
END;
$function$;
