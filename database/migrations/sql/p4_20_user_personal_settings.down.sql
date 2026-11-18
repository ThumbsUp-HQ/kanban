-- Migration p4_20_user_personal_settings (DOWN)
-- Revert user preferences and profile update helper functions.

DROP FUNCTION IF EXISTS kb_auth.user_get_avatar(UUID);
DROP FUNCTION IF EXISTS kb_auth.session_revoke_all_except(UUID, UUID);
DROP FUNCTION IF EXISTS kb_auth.webauthn_credential_update_nickname(UUID, UUID, TEXT);
DROP FUNCTION IF EXISTS kb_auth.local_get_credential_by_principal(UUID);
DROP FUNCTION IF EXISTS kb_auth.user_update_own_profile(UUID, TEXT, TEXT);
DROP TABLE IF EXISTS public.user_preferences;
