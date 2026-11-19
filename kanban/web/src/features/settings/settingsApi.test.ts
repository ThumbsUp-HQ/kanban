// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, expect, it, vi, beforeEach } from 'vitest';
import * as clientModule from '../../api/client';
import {
  fetchConnectedApps,
  fetchPersonalMcpKeys,
  mintPersonalMcpKey,
  revokeConnectedApp,
  revokePersonalMcpKey,
} from './settingsApi';

describe('settingsApi', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('fetchPersonalMcpKeys handles both wrapped { keys } and direct array responses with fallback defaults', async () => {
    const spy = vi.spyOn(clientModule, 'apiFetch');
    spy.mockResolvedValueOnce({
      keys: [
        {
          id: 'k-1',
          surface: 'agent',
          display_hint: 'kb_pat_123',
        },
      ],
    });

    const res1 = await fetchPersonalMcpKeys();
    expect(res1).toEqual([
      {
        id: 'k-1',
        label: 'kb_pat_123',
        display_hint: 'kb_pat_123',
        surface: 'agent',
        scope_tier: 'personal_user',
        scopes: [],
        allowed_projects: null,
        created_at: '',
        expires_at: null,
        disabled_tools: [],
        allowed_tools: null,
        last_used_at: null,
        revoked_at: null,
      },
    ]);

    spy.mockResolvedValueOnce([
      {
        id: 'k-2',
        surface: 'docs',
      },
    ] as never);

    const res2 = await fetchPersonalMcpKeys();
    expect(res2[0]?.label).toBe('MCP Key');
    expect(res2[0]?.display_hint).toBe('');
  });

  it('mintPersonalMcpKey normalizes created key and preserves raw_key and fallback label', async () => {
    const spy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValueOnce({
      id: 'k-3',
      surface: 'admin',
      raw_key: 'kb_pat_secret',
    });

    const created = await mintPersonalMcpKey({
      label: 'My Admin Key',
      surface: 'admin',
      scopes: ['admin:read'],
      expires_in_days: 30,
    });

    expect(spy).toHaveBeenCalledWith('POST', '/api/v1/auth/mcp-keys', expect.any(Object));
    expect(created.label).toBe('My Admin Key');
    expect(created.raw_key).toBe('kb_pat_secret');
  });

  it('revokePersonalMcpKey, fetchConnectedApps, and revokeConnectedApp call expected endpoints', async () => {
    const spy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue([] as never);

    await revokePersonalMcpKey('k-99');
    expect(spy).toHaveBeenCalledWith('DELETE', '/api/v1/auth/mcp-keys/{key_id}', {
      params: { key_id: 'k-99' },
    });

    const apps = await fetchConnectedApps();
    expect(apps).toEqual([]);
    expect(spy).toHaveBeenCalledWith('GET', '/api/v1/auth/oauth-grants');

    await revokeConnectedApp('g-77');
    expect(spy).toHaveBeenCalledWith('DELETE', '/api/v1/auth/oauth-grants/{grant_id}', {
      params: { grant_id: 'g-77' },
    });
  });

  it('supports global tier for fetchPersonalMcpKeys, mintPersonalMcpKey, and revokePersonalMcpKey', async () => {
    const spy = vi.spyOn(clientModule, 'apiFetch');
    spy.mockResolvedValueOnce({
      keys: [{ id: 'k-glob', surface: 'agent', display_hint: 'glob123' }],
    });

    const res = await fetchPersonalMcpKeys('global');
    expect(spy).toHaveBeenCalledWith('GET', '/api/v1/admin/mcp-keys');
    expect(res[0]?.id).toBe('k-glob');

    spy.mockResolvedValueOnce({ id: 'k-glob-2', surface: 'admin', raw_key: 'raw_secret' });
    const minted = await mintPersonalMcpKey(
      { label: 'Global Server Key', surface: 'admin', scopes: [] },
      'global',
    );
    expect(spy).toHaveBeenCalledWith('POST', '/api/v1/admin/mcp-keys', expect.any(Object));
    expect(minted.id).toBe('k-glob-2');

    spy.mockResolvedValueOnce({});
    await revokePersonalMcpKey('k-glob-2', 'global');
    expect(spy).toHaveBeenCalledWith('DELETE', '/api/v1/admin/mcp-keys/{key_id}', {
      params: { key_id: 'k-glob-2' },
    });
  });
});
