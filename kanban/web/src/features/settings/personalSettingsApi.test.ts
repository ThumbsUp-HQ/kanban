// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import * as clientModule from '../../api/client';
import {
  fetchMyProfile,
  updateMyProfile,
  uploadAvatar,
  deleteAvatar,
  changePassword,
  fetchMfaStatus,
  fetchPasskeys,
  renamePasskey,
  deletePasskey,
  fetchWebauthnRegistrationOptions,
  verifyWebauthnRegistration,
  fetchWebauthnAuthenticationOptions,
  verifyWebauthnAuthentication,
  enrollTotp,
  confirmTotp,
  deleteTotp,
  regenerateRecoveryCodes,
  fetchExternalIdentities,
  startLinkIdentity,
  linkLdapIdentity,
  unlinkIdentity,
} from './personalSettingsApi';

describe('personalSettingsApi', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('fetchMyProfile invokes apiFetch with GET /api/v1/auth/me', async () => {
    const mockProfile = { principal_id: 'u-1', display_name: 'Test' };
    const apiFetchSpy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue(mockProfile);

    const res = await fetchMyProfile();
    expect(apiFetchSpy).toHaveBeenCalledWith('GET', '/api/v1/auth/me');
    expect(res).toEqual(mockProfile);
  });

  it('updateMyProfile invokes apiFetch with PATCH /api/v1/auth/me', async () => {
    const mockProfile = { principal_id: 'u-1', display_name: 'Updated' };
    const apiFetchSpy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue(mockProfile);

    const payload = { display_name: 'Updated', timezone: 'UTC' };
    const res = await updateMyProfile(payload);
    expect(apiFetchSpy).toHaveBeenCalledWith('PATCH', '/api/v1/auth/me', {
      body: JSON.stringify(payload),
      headers: { 'Content-Type': 'application/json' },
    });
    expect(res).toEqual(mockProfile);
  });

  it('uploadAvatar builds FormData and invokes PUT /api/v1/auth/me/avatar', async () => {
    const mockProfile = { principal_id: 'u-1', avatar_url: '/avatar.png' };
    const apiFetchSpy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue(mockProfile);

    const file = new File(['image-bytes'], 'avatar.png', { type: 'image/png' });
    const res = await uploadAvatar(file);

    expect(apiFetchSpy).toHaveBeenCalledWith(
      'PUT',
      '/api/v1/auth/me/avatar',
      expect.anything(),
    );
    const callOpts = apiFetchSpy.mock.calls[0]?.[2] as { body?: unknown } | undefined;
    expect(callOpts?.body).toBeInstanceOf(FormData);
    expect(res).toEqual(mockProfile);
  });

  it('deleteAvatar invokes DELETE /api/v1/auth/me/avatar', async () => {
    const mockProfile = { principal_id: 'u-1', avatar_url: null };
    const apiFetchSpy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue(mockProfile);

    const res = await deleteAvatar();
    expect(apiFetchSpy).toHaveBeenCalledWith('DELETE', '/api/v1/auth/me/avatar');
    expect(res).toEqual(mockProfile);
  });

  it('changePassword invokes POST /api/v1/auth/me/password', async () => {
    const mockRes = { ok: true, message: 'Password updated' };
    const apiFetchSpy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue(mockRes);

    const payload = { current_password: 'oldpassword123', new_password: 'newpassword123' };
    const res = await changePassword(payload);

    expect(apiFetchSpy).toHaveBeenCalledWith('POST', '/api/v1/auth/me/password', {
      body: JSON.stringify(payload),
      headers: { 'Content-Type': 'application/json' },
    });
    expect(res).toEqual(mockRes);
  });

  it('fetchMfaStatus invokes GET /api/v1/auth/mfa/status', async () => {
    const mockStatus = {
      totp_enabled: true,
      passkeys_count: 2,
      recovery_codes_remaining: 8,
      preferred_method: 'webauthn' as const,
    };
    const apiFetchSpy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue(mockStatus);

    const res = await fetchMfaStatus();
    expect(apiFetchSpy).toHaveBeenCalledWith('GET', '/api/v1/auth/mfa/status');
    expect(res).toEqual(mockStatus);
  });

  it('fetchPasskeys returns array directly or unwraps credentials object', async () => {
    const mockCredentials = [
      { id: 'pk-1', nickname: 'Key 1', created_at: '2026-01-01', last_used_at: null, aaguid: null },
    ];
    const apiFetchSpy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue(mockCredentials);

    const res1 = await fetchPasskeys();
    expect(res1).toEqual(mockCredentials);

    apiFetchSpy.mockResolvedValue({ credentials: mockCredentials });
    const res2 = await fetchPasskeys();
    expect(res2).toEqual(mockCredentials);
  });

  it('renamePasskey invokes PATCH with params and JSON body', async () => {
    const mockCred = { id: 'pk-1', nickname: 'New Name', created_at: '2026-01-01', last_used_at: null, aaguid: null };
    const apiFetchSpy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue(mockCred);

    const res = await renamePasskey('pk-1', 'New Name');
    expect(apiFetchSpy).toHaveBeenCalledWith(
      'PATCH',
      '/api/v1/auth/webauthn/credentials/{credential_id}',
      {
        params: { credential_id: 'pk-1' },
        body: JSON.stringify({ nickname: 'New Name' }),
        headers: { 'Content-Type': 'application/json' },
      },
    );
    expect(res).toEqual(mockCred);
  });

  it('deletePasskey invokes DELETE with credential_id param', async () => {
    const apiFetchSpy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue(undefined);

    await deletePasskey('pk-2');
    expect(apiFetchSpy).toHaveBeenCalledWith(
      'DELETE',
      '/api/v1/auth/webauthn/credentials/{credential_id}',
      {
        params: { credential_id: 'pk-2' },
      },
    );
  });

  it('fetchWebauthnRegistrationOptions invokes POST with attachment hint or empty body', async () => {
    const mockOpts = { challenge: 'chall1', rp: { name: 'KB' }, user: { id: 'u1', name: 'u', displayName: 'U' }, pubKeyCredParams: [] };
    const apiFetchSpy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue(mockOpts);

    const resWithAttach = await fetchWebauthnRegistrationOptions('platform');
    expect(apiFetchSpy).toHaveBeenCalledWith(
      'POST',
      '/api/v1/auth/webauthn/register/options',
      {
        body: JSON.stringify({ authenticator_attachment: 'platform' }),
        headers: { 'Content-Type': 'application/json' },
      },
    );
    expect(resWithAttach).toEqual(mockOpts);

    const resWithoutAttach = await fetchWebauthnRegistrationOptions();
    expect(apiFetchSpy).toHaveBeenCalledWith(
      'POST',
      '/api/v1/auth/webauthn/register/options',
      {
        body: JSON.stringify({}),
        headers: { 'Content-Type': 'application/json' },
      },
    );
    expect(resWithoutAttach).toEqual(mockOpts);
  });

  it('verifyWebauthnRegistration invokes POST /api/v1/auth/webauthn/register/verify', async () => {
    const mockVerifyRes = { verified: true, credential_id: 'cred-123', nickname: 'My Key' };
    const apiFetchSpy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue(mockVerifyRes);

    const payload = {
      nickname: 'My Key',
      credential: {
        id: 'c1',
        rawId: 'c1',
        type: 'public-key',
        response: { clientDataJSON: 'cd', attestationObject: 'att' },
      },
    };
    const res = await verifyWebauthnRegistration(payload);
    expect(apiFetchSpy).toHaveBeenCalledWith(
      'POST',
      '/api/v1/auth/webauthn/register/verify',
      {
        body: JSON.stringify(payload),
        headers: { 'Content-Type': 'application/json' },
      },
    );
    expect(res).toEqual(mockVerifyRes);
  });

  it('fetchWebauthnAuthenticationOptions invokes POST /api/v1/auth/webauthn/authenticate/options', async () => {
    const mockAuthOpts = { challenge: 'chall-auth', rpId: 'localhost' };
    const apiFetchSpy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue(mockAuthOpts);

    const res = await fetchWebauthnAuthenticationOptions();
    expect(apiFetchSpy).toHaveBeenCalledWith(
      'POST',
      '/api/v1/auth/webauthn/authenticate/options',
      {
        body: JSON.stringify({}),
        headers: { 'Content-Type': 'application/json' },
      },
    );
    expect(res).toEqual(mockAuthOpts);
  });

  it('verifyWebauthnAuthentication invokes POST /api/v1/auth/webauthn/authenticate/verify', async () => {
    const mockAuthVerify = { verified: true, credential_id: 'c1', aal_level: 2 };
    const apiFetchSpy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue(mockAuthVerify);

    const payload = {
      credential: {
        id: 'c1',
        rawId: 'c1',
        type: 'public-key',
        response: { clientDataJSON: 'cd', authenticatorData: 'ad', signature: 'sig', userHandle: null },
      },
    };
    const res = await verifyWebauthnAuthentication(payload);
    expect(apiFetchSpy).toHaveBeenCalledWith(
      'POST',
      '/api/v1/auth/webauthn/authenticate/verify',
      {
        body: JSON.stringify(payload),
        headers: { 'Content-Type': 'application/json' },
      },
    );
    expect(res).toEqual(mockAuthVerify);
  });

  it('enrollTotp invokes POST /api/v1/auth/mfa/totp/enroll', async () => {
    const mockEnroll = { secret: 'SECRET123', provisioning_uri: 'otpauth://...' };
    const apiFetchSpy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue(mockEnroll);

    const res = await enrollTotp();
    expect(apiFetchSpy).toHaveBeenCalledWith('POST', '/api/v1/auth/mfa/totp/enroll');
    expect(res).toEqual(mockEnroll);
  });

  it('confirmTotp invokes POST /api/v1/auth/mfa/totp/confirm', async () => {
    const mockVerify = { ok: true, recovery_codes: ['code-1'] };
    const apiFetchSpy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue(mockVerify);

    const res = await confirmTotp('123456');
    expect(apiFetchSpy).toHaveBeenCalledWith('POST', '/api/v1/auth/mfa/totp/confirm', {
      body: JSON.stringify({ code: '123456' }),
      headers: { 'Content-Type': 'application/json' },
    });
    expect(res).toEqual(mockVerify);
  });

  it('deleteTotp invokes DELETE /api/v1/auth/mfa/totp', async () => {
    const apiFetchSpy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue(undefined);

    await deleteTotp();
    expect(apiFetchSpy).toHaveBeenCalledWith('DELETE', '/api/v1/auth/mfa/totp');
  });

  it('regenerateRecoveryCodes invokes POST /api/v1/auth/mfa/recovery/regenerate', async () => {
    const mockCodes = { recovery_codes: ['c1', 'c2'] };
    const apiFetchSpy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue(mockCodes);

    const res = await regenerateRecoveryCodes();
    expect(apiFetchSpy).toHaveBeenCalledWith('POST', '/api/v1/auth/mfa/recovery/regenerate');
    expect(res).toEqual(mockCodes);
  });

  it('fetchExternalIdentities returns identities on success and empty array on error', async () => {
    const mockData = {
      identities: [
        {
          id: 'i-1',
          card_slug: 'github',
          card_display_name: 'GitHub Enterprise',
          provider_kind: 'oauth2',
          subject_email_at_link: 'user@example.com',
          immutable_subject_id: 'sub-1',
          created_at: '2026-01-01T00:00:00Z',
          last_login_at: '2026-01-01T12:00:00Z',
        },
      ],
    };
    const apiFetchSpy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue(mockData);

    const res1 = await fetchExternalIdentities();
    expect(apiFetchSpy).toHaveBeenCalledWith('GET', '/api/v1/auth/identities');
    expect(res1).toEqual(mockData.identities);

    // Empty fallback
    apiFetchSpy.mockResolvedValue(undefined);
    expect(await fetchExternalIdentities()).toEqual([]);

    // Error catch fallback
    apiFetchSpy.mockRejectedValue(new Error('Network error'));
    expect(await fetchExternalIdentities()).toEqual([]);
  });

  it('startLinkIdentity invokes POST /api/v1/auth/identities/link/start', async () => {
    const mockResult = { mode: 'oauth', authorize_url: 'https://auth.example.com' };
    const apiFetchSpy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue(mockResult);

    const res = await startLinkIdentity('corp-oauth');
    expect(apiFetchSpy).toHaveBeenCalledWith('POST', '/api/v1/auth/identities/link/start', {
      body: JSON.stringify({ card_slug: 'corp-oauth' }),
      headers: { 'Content-Type': 'application/json' },
    });
    expect(res).toEqual(mockResult);
  });

  it('linkLdapIdentity invokes POST /api/v1/auth/identities/link/ldap', async () => {
    const mockResult = { linked: true };
    const apiFetchSpy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue(mockResult);

    const res = await linkLdapIdentity('intent-1', 'john_doe', 'Secret123!');
    expect(apiFetchSpy).toHaveBeenCalledWith('POST', '/api/v1/auth/identities/link/ldap', {
      body: JSON.stringify({ link_intent_id: 'intent-1', username: 'john_doe', password: 'Secret123!' }),
      headers: { 'Content-Type': 'application/json' },
    });
    expect(res).toEqual(mockResult);
  });

  it('unlinkIdentity invokes DELETE /api/v1/auth/identities/{identity_id}', async () => {
    const apiFetchSpy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue(undefined);

    await unlinkIdentity('ident-99');
    expect(apiFetchSpy).toHaveBeenCalledWith('DELETE', '/api/v1/auth/identities/{identity_id}', {
      params: { identity_id: 'ident-99' },
    });
  });
});
