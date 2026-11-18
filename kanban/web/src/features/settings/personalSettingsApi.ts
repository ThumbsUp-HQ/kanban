// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { apiFetch } from '../../api/client';

export interface UserProfileResponse {
  principal_id: string;
  display_name: string;
  username: string;
  email: string | null;
  timezone: string;
  avatar_url: string | null;
  roles: string[];
  is_server_admin: boolean;
  has_local_password?: boolean;
}

export interface UpdateProfileRequest {
  display_name?: string;
  timezone?: string;
}

export interface ChangePasswordRequest {
  current_password: string;
  new_password: string;
}

export interface WebauthnCredentialItem {
  id: string;
  nickname: string;
  created_at: string;
  last_used_at: string | null;
  aaguid: string | null;
}

export interface MfaStatusResponse {
  totp_enabled: boolean;
  passkeys_count: number;
  recovery_codes_remaining: number;
}

export interface TotpEnrollResponse {
  secret?: string;
  otpauth_url?: string;
  provisioning_uri?: string;
  recovery_codes?: string[];
  challenge_id?: string;
}

export interface RecoveryCodesResponse {
  recovery_codes: string[];
}

export async function fetchMyProfile(): Promise<UserProfileResponse> {
  return (await apiFetch('GET', '/api/v1/auth/me' as never)) as UserProfileResponse;
}

export async function updateMyProfile(
  payload: UpdateProfileRequest,
): Promise<UserProfileResponse> {
  return (await apiFetch('PATCH', '/api/v1/auth/me' as never, {
    body: JSON.stringify(payload),
    headers: { 'Content-Type': 'application/json' },
  })) as UserProfileResponse;
}

export async function uploadAvatar(file: File): Promise<UserProfileResponse> {
  const formData = new FormData();
  formData.append('file', file);
  return (await apiFetch('PUT', '/api/v1/auth/me/avatar' as never, {
    body: formData,
  })) as UserProfileResponse;
}

export async function deleteAvatar(): Promise<UserProfileResponse> {
  return (await apiFetch('DELETE', '/api/v1/auth/me/avatar' as never)) as UserProfileResponse;
}

export async function changePassword(
  payload: ChangePasswordRequest,
): Promise<{ ok: boolean; message: string }> {
  return (await apiFetch('POST', '/api/v1/auth/me/password' as never, {
    body: JSON.stringify(payload),
    headers: { 'Content-Type': 'application/json' },
  })) as { ok: boolean; message: string };
}

export async function fetchMfaStatus(): Promise<MfaStatusResponse> {
  return (await apiFetch('GET', '/api/v1/auth/mfa/status' as never)) as MfaStatusResponse;
}

export async function fetchPasskeys(): Promise<WebauthnCredentialItem[]> {
  const res = (await apiFetch('GET', '/api/v1/auth/webauthn/credentials' as never)) as
    | WebauthnCredentialItem[]
    | { credentials: WebauthnCredentialItem[] };
  return Array.isArray(res) ? res : res.credentials;
}

export async function renamePasskey(
  credentialId: string,
  nickname: string,
): Promise<WebauthnCredentialItem> {
  return (await apiFetch(
    'PATCH',
    '/api/v1/auth/webauthn/credentials/{credential_id}' as never,
    {
      params: { credential_id: credentialId },
      body: JSON.stringify({ nickname }),
      headers: { 'Content-Type': 'application/json' },
    },
  )) as WebauthnCredentialItem;
}

export async function deletePasskey(credentialId: string): Promise<void> {
  await apiFetch('DELETE', '/api/v1/auth/webauthn/credentials/{credential_id}' as never, {
    params: { credential_id: credentialId },
  });
}

export async function enrollTotp(): Promise<TotpEnrollResponse> {
  return (await apiFetch('POST', '/api/v1/auth/mfa/totp/enroll' as never)) as TotpEnrollResponse;
}

export async function confirmTotp(
  code: string,
): Promise<{ ok: boolean; recovery_codes: string[] }> {
  return (await apiFetch('POST', '/api/v1/auth/mfa/totp/verify' as never, {
    body: JSON.stringify({ code }),
    headers: { 'Content-Type': 'application/json' },
  })) as { ok: boolean; recovery_codes: string[] };
}

export async function deleteTotp(): Promise<void> {
  await apiFetch('DELETE', '/api/v1/auth/mfa/totp' as never);
}

export async function regenerateRecoveryCodes(): Promise<RecoveryCodesResponse> {
  return (await apiFetch(
    'POST',
    '/api/v1/auth/mfa/recovery/regenerate' as never,
  )) as RecoveryCodesResponse;
}
