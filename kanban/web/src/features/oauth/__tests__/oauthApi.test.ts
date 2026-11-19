// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, expect, it, vi, beforeEach } from 'vitest';
import * as clientModule from '../../../api/client';
import {
  fetchDeviceCodeInfo,
  submitDeviceActivation,
  fetchAdminOAuthClients,
  patchAdminOAuthClient,
  deleteAdminOAuthClient,
} from '../oauthApi';

describe('oauthApi', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('fetchDeviceCodeInfo calls GET /api/v1/oauth/device/info with query', async () => {
    const spy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValueOnce({
      user_code: 'WDJB-MJHT',
      client_name: 'Cursor IDE',
    });

    const res = await fetchDeviceCodeInfo('WDJB-MJHT');
    expect(spy).toHaveBeenCalledWith('GET', '/api/v1/oauth/device/info', {
      query: { user_code: 'WDJB-MJHT' },
    });
    expect(res.user_code).toBe('WDJB-MJHT');
  });

  it('submitDeviceActivation calls POST /api/v1/oauth/device/activate', async () => {
    const spy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValueOnce({
      status: 'approved',
      grant_id: 'grant-123',
    });

    const res = await submitDeviceActivation({
      user_code: 'WDJB-MJHT',
      approved: true,
      scopes: ['agent:read'],
    });

    expect(spy).toHaveBeenCalledWith('POST', '/api/v1/oauth/device/activate', {
      body: JSON.stringify({
        user_code: 'WDJB-MJHT',
        approved: true,
        scopes: ['agent:read'],
      }),
      headers: { 'Content-Type': 'application/json' },
    });
    expect(res.status).toBe('approved');
  });

  it('fetchAdminOAuthClients calls GET /api/v1/admin/oauth-clients', async () => {
    const spy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValueOnce([
      { client_id: 'c1', client_type: 'confidential', status: 'active' },
    ]);

    const res = await fetchAdminOAuthClients();
    expect(spy).toHaveBeenCalledWith('GET', '/api/v1/admin/oauth-clients');
    expect(res).toHaveLength(1);
  });

  it('patchAdminOAuthClient and deleteAdminOAuthClient call expected routes', async () => {
    const spy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue({});

    await patchAdminOAuthClient('c1', { status: 'suspended' });
    expect(spy).toHaveBeenCalledWith('PATCH', '/api/v1/admin/oauth-clients/{client_id}', {
      params: { client_id: 'c1' },
      body: JSON.stringify({ status: 'suspended' }),
      headers: { 'Content-Type': 'application/json' },
    });

    await deleteAdminOAuthClient('c1');
    expect(spy).toHaveBeenCalledWith('DELETE', '/api/v1/admin/oauth-clients/{client_id}', {
      params: { client_id: 'c1' },
    });
  });
});
