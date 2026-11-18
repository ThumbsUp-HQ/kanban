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
  enrollTotp,
  confirmTotp,
  deleteTotp,
  regenerateRecoveryCodes,
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
    const mockStatus = { totp_enabled: true, passkeys_count: 2, recovery_codes_remaining: 8 };
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

  it('enrollTotp invokes POST /api/v1/auth/mfa/totp/enroll', async () => {
    const mockEnroll = { secret: 'SECRET123', provisioning_uri: 'otpauth://...' };
    const apiFetchSpy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue(mockEnroll);

    const res = await enrollTotp();
    expect(apiFetchSpy).toHaveBeenCalledWith('POST', '/api/v1/auth/mfa/totp/enroll');
    expect(res).toEqual(mockEnroll);
  });

  it('confirmTotp invokes POST /api/v1/auth/mfa/totp/verify', async () => {
    const mockVerify = { ok: true, recovery_codes: ['code-1'] };
    const apiFetchSpy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue(mockVerify);

    const res = await confirmTotp('123456');
    expect(apiFetchSpy).toHaveBeenCalledWith('POST', '/api/v1/auth/mfa/totp/verify', {
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
});
