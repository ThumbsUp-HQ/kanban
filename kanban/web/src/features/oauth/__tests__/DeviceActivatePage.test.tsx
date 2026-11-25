// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router';
import { DeviceActivatePage, formatUserCodeInput } from '../DeviceActivatePage';
import * as oauthApi from '../oauthApi';

describe('DeviceActivatePage (KB-P4-16)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  describe('formatUserCodeInput helper', () => {
    it('filters non-consonant characters and formats XXXX-XXXX', () => {
      expect(formatUserCodeInput('wdjbmjht')).toBe('WDJB-MJHT');
      expect(formatUserCodeInput('w d j b - m j h t')).toBe('WDJB-MJHT');
      // Vowels and numbers filtered
      expect(formatUserCodeInput('A1E8O0')).toBe('');
      expect(formatUserCodeInput('ABCD')).toBe('BCD');
      expect(formatUserCodeInput('BCDFGHJKLM')).toBe('BCDF-GHJK');
    });
  });

  it('renders input field, accepts user code, and fetches device info (Test Case 1)', async () => {
    const PROJECT_UUID = '01a1f738-f55e-77f8-94bd-4a5c7960f807';
    const mockInfo: oauthApi.DeviceCodeInfoResponse = {
      user_code: 'WDJB-MJHT',
      client_name: 'Antigravity CLI',
      client_id: 'client_123',
      resource: 'https://kanban.example.com/mcp/agent',
      surface: 'agent',
      requested_scopes: ['agent:read', 'agent:write'],
      allowed_projects: [PROJECT_UUID],
      expires_at: new Date(Date.now() + 600000).toISOString(),
    };

    vi.spyOn(oauthApi, 'fetchDeviceCodeInfo').mockResolvedValue(mockInfo);
    vi.spyOn(oauthApi, 'submitDeviceActivation').mockResolvedValue({ status: 'approved' });

    render(
      <MemoryRouter initialEntries={['/activate']}>
        <DeviceActivatePage />
      </MemoryRouter>,
    );

    const input = screen.getByTestId<HTMLInputElement>('user-code-input');
    fireEvent.change(input, { target: { value: 'WDJBMJHT' } });
    expect(input.value).toBe('WDJB-MJHT');

    const lookupBtn = screen.getByTestId<HTMLButtonElement>('lookup-button');
    expect(lookupBtn.disabled).toBe(false);
    fireEvent.click(lookupBtn);

    await waitFor(() => {
      expect(screen.getByTestId('consent-section')).not.toBeNull();
    });

    expect(screen.getByTestId('client-name').textContent).toContain('Antigravity CLI');
    expect(screen.getByTestId('verified-code').textContent).toContain('WDJB-MJHT');
    expect(screen.getByTestId('resource-target').textContent).toContain('/mcp/agent');

    // Narrow scopes and projects
    const scopeWrite = screen.getByTestId('scope-checkbox-agent:write');
    const scopeRead = screen.getByTestId('scope-checkbox-agent:read');
    fireEvent.click(scopeWrite); // Uncheck write
    fireEvent.click(scopeWrite); // Re-check write
    fireEvent.click(scopeWrite); // Uncheck write again

    // Uncheck read to test empty scopes disabling approve button
    fireEvent.click(scopeRead);
    const approveBtn = screen.getByTestId<HTMLButtonElement>('approve-button');
    expect(approveBtn.disabled).toBe(true);
    fireEvent.click(scopeRead); // Re-check read
    expect(approveBtn.disabled).toBe(false);

    // Toggle project using valid UUID
    const projBox = screen.getByTestId(`project-checkbox-${PROJECT_UUID}`);
    fireEvent.click(projBox); // Uncheck project
    fireEvent.click(projBox); // Check project back

    fireEvent.click(approveBtn);

    await waitFor(() => {
      expect(oauthApi.submitDeviceActivation).toHaveBeenCalledWith({
        user_code: 'WDJB-MJHT',
        approved: true,
        scopes: ['agent:read'],
        allowed_projects: [PROJECT_UUID],
      });
      const submittedProjects = (
        vi.mocked(oauthApi.submitDeviceActivation).mock.calls[0]?.[0]
      )?.allowed_projects;
      expect(submittedProjects).toHaveLength(1);
      expect(submittedProjects?.[0]).toMatch(
        /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i,
      );
      expect(screen.getByTestId('completion-approved')).not.toBeNull();
    });
  });

  it('displays consonant-only helper caption and non-destructive feedback on vowel/digit entry', () => {
    render(
      <MemoryRouter initialEntries={['/activate']}>
        <DeviceActivatePage />
      </MemoryRouter>,
    );

    // Verify helper caption
    const helper = screen.getByTestId('user-code-helper');
    expect(helper.textContent).toContain('BCDFGHJKLMNPQRSTVWXZ');

    const input = screen.getByTestId<HTMLInputElement>('user-code-input');

    // Type a vowel or digit
    fireEvent.change(input, { target: { value: 'A1E' } });
    expect(screen.getByTestId('user-code-input-notice').textContent).toContain(
      'Vowels (A, E, I, O, U) and numbers are not used',
    );

    // Type valid consonants
    fireEvent.change(input, { target: { value: 'BCDF' } });
    expect(screen.queryByTestId('user-code-input-notice')).toBeNull();
    expect(input.value).toBe('BCDF');
  });

  it('auto-loads device info when pre-filled via query parameter', async () => {
    const mockInfo: oauthApi.DeviceCodeInfoResponse = {
      user_code: 'BCDF-GHJK',
      client_name: 'Claude Code',
      client_id: 'client_claude',
      resource: 'https://kanban.example.com/mcp/agent',
      surface: 'agent',
      requested_scopes: ['agent:read'],
      allowed_projects: null,
      expires_at: new Date().toISOString(),
    };

    vi.spyOn(oauthApi, 'fetchDeviceCodeInfo').mockResolvedValue(mockInfo);

    render(
      <MemoryRouter initialEntries={['/activate?user_code=bcdfghjk']}>
        <DeviceActivatePage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('consent-section')).not.toBeNull();
      expect(screen.getByTestId('client-name').textContent).toContain('Claude Code');
    });
  });

  it('handles query param with short code or failed auto-lookup', async () => {
    // 1. Short code query param
    const { unmount } = render(
      <MemoryRouter initialEntries={['/activate?user_code=short']}>
        <DeviceActivatePage />
      </MemoryRouter>,
    );
    expect(screen.getByTestId('user-code-input')).not.toBeNull();
    unmount();

    // 2. Failed auto-lookup via query param (expired)
    vi.spyOn(oauthApi, 'fetchDeviceCodeInfo').mockRejectedValueOnce({
      code: 'EXPIRED_CODE',
    });

    const { unmount: unmount2 } = render(
      <MemoryRouter initialEntries={['/activate?user_code=bcdfghjk']}>
        <DeviceActivatePage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('error-banner').textContent).toContain(
        'This user code has expired. Please initiate device login again.',
      );
    });
    unmount2();

    // 3. Failed auto-lookup via query param (rate limited)
    vi.spyOn(oauthApi, 'fetchDeviceCodeInfo').mockRejectedValueOnce({
      code: 'RATE_LIMIT_EXCEEDED',
    });
    const { unmount: unmount3 } = render(
      <MemoryRouter initialEntries={['/activate?user_code=bcdfghjk']}>
        <DeviceActivatePage />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('error-banner').textContent).toContain('Too many attempts.');
    });
    unmount3();

    // 4. Failed auto-lookup via query param (already processed)
    vi.spyOn(oauthApi, 'fetchDeviceCodeInfo').mockRejectedValueOnce({
      code: 'ALREADY_PROCESSED',
    });
    const { unmount: unmount4 } = render(
      <MemoryRouter initialEntries={['/activate?user_code=bcdfghjk']}>
        <DeviceActivatePage />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('error-banner').textContent).toContain('already been approved');
    });
    unmount4();

    // 5. Failed auto-lookup via query param (generic error)
    vi.spyOn(oauthApi, 'fetchDeviceCodeInfo').mockRejectedValueOnce(new Error('Unknown failure'));
    render(
      <MemoryRouter initialEntries={['/activate?user_code=bcdfghjk']}>
        <DeviceActivatePage />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('error-banner').textContent).toContain('Unknown failure');
    });
  });

  it('handles user denial decision', async () => {
    const mockInfo: oauthApi.DeviceCodeInfoResponse = {
      user_code: 'WDJB-MJHT',
      client_name: 'Test CLI',
      client_id: 'client_test',
      resource: 'https://kanban.example.com/mcp/agent',
      surface: 'agent',
      requested_scopes: ['agent:read'],
      allowed_projects: null,
      expires_at: new Date().toISOString(),
    };

    vi.spyOn(oauthApi, 'fetchDeviceCodeInfo').mockResolvedValue(mockInfo);
    vi.spyOn(oauthApi, 'submitDeviceActivation').mockResolvedValue({ status: 'denied' });

    render(
      <MemoryRouter initialEntries={['/activate?user_code=WDJB-MJHT']}>
        <DeviceActivatePage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('deny-button')).not.toBeNull();
    });

    fireEvent.click(screen.getByTestId('deny-button'));

    await waitFor(() => {
      expect(oauthApi.submitDeviceActivation).toHaveBeenCalledWith({
        user_code: 'WDJB-MJHT',
        approved: false,
        scopes: undefined,
        allowed_projects: undefined,
      });
      expect(screen.getByTestId('completion-denied')).not.toBeNull();
    });
  });

  it('displays AAL2 banner and handles AAL2 step-up requirement (Test Case 2)', async () => {
    const mockAdminInfo: oauthApi.DeviceCodeInfoResponse = {
      user_code: 'WDJB-MJHT',
      client_name: 'Admin CLI',
      client_id: 'client_admin',
      resource: 'https://kanban.example.com/mcp/admin',
      surface: 'admin',
      requested_scopes: ['admin:read'],
      allowed_projects: null,
      expires_at: new Date().toISOString(),
    };

    vi.spyOn(oauthApi, 'fetchDeviceCodeInfo').mockResolvedValue(mockAdminInfo);
    vi.spyOn(oauthApi, 'submitDeviceActivation').mockRejectedValue({
      code: 'AAL2_REQUIRED',
      message: 'AAL2 required',
    });

    render(
      <MemoryRouter initialEntries={['/activate?user_code=WDJB-MJHT']}>
        <DeviceActivatePage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('aal2-banner')).not.toBeNull();
    });

    fireEvent.click(screen.getByTestId('approve-button'));

    await waitFor(() => {
      expect(screen.getByTestId('error-banner').textContent).toContain(
        'AAL2 Passkey or TOTP verification required',
      );
    });
  });

  it('displays appropriate errors for rate limiting, expiration, and already processed codes', async () => {
    vi.spyOn(oauthApi, 'fetchDeviceCodeInfo').mockRejectedValueOnce({
      code: 'RATE_LIMIT_EXCEEDED',
    });

    render(
      <MemoryRouter initialEntries={['/activate']}>
        <DeviceActivatePage />
      </MemoryRouter>,
    );

    const input = screen.getByTestId('user-code-input');
    fireEvent.change(input, { target: { value: 'WDJBMJHT' } });
    fireEvent.click(screen.getByTestId('lookup-button'));

    await waitFor(() => {
      expect(screen.getByTestId('error-banner').textContent).toContain(
        'Too many attempts. Please wait 5 minutes before trying again.',
      );
    });

    // Test expired code
    vi.spyOn(oauthApi, 'fetchDeviceCodeInfo').mockRejectedValueOnce({
      code: 'EXPIRED_CODE',
    });
    fireEvent.click(screen.getByTestId('lookup-button'));
    await waitFor(() => {
      expect(screen.getByTestId('error-banner').textContent).toContain(
        'This user code has expired.',
      );
    });

    // Test already processed code
    vi.spyOn(oauthApi, 'fetchDeviceCodeInfo').mockRejectedValueOnce({
      code: 'ALREADY_PROCESSED',
    });
    fireEvent.click(screen.getByTestId('lookup-button'));
    await waitFor(() => {
      expect(screen.getByTestId('error-banner').textContent).toContain(
        'This device code has already been approved or denied.',
      );
    });

    // Test generic fallback error
    vi.spyOn(oauthApi, 'fetchDeviceCodeInfo').mockRejectedValueOnce(new Error('Network offline'));
    fireEvent.click(screen.getByTestId('lookup-button'));
    await waitFor(() => {
      expect(screen.getByTestId('error-banner').textContent).toContain('Network offline');
    });

    // Test fallback message when errObj.message is undefined
    vi.spyOn(oauthApi, 'fetchDeviceCodeInfo').mockRejectedValueOnce({});
    fireEvent.click(screen.getByTestId('lookup-button'));
    await waitFor(() => {
      expect(screen.getByTestId('error-banner').textContent).toContain('Invalid code or code not found.');
    });
  });

  it('handles generic activation error and button disabled state for short codes', async () => {
    const mockInfo: oauthApi.DeviceCodeInfoResponse = {
      user_code: 'WDJB-MJHT',
      client_name: 'Failing CLI',
      client_id: 'client_fail',
      resource: 'https://kanban.example.com/mcp/agent',
      surface: 'agent',
      requested_scopes: ['agent:read'],
      allowed_projects: ['01a1f738-f55e-77f8-94bd-4a5c7960f807'],
      expires_at: new Date().toISOString(),
    };

    vi.spyOn(oauthApi, 'fetchDeviceCodeInfo').mockResolvedValue(mockInfo);
    vi.spyOn(oauthApi, 'submitDeviceActivation').mockRejectedValueOnce({});

    render(
      <MemoryRouter initialEntries={['/activate?user_code=WDJB-MJHT']}>
        <DeviceActivatePage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('approve-button')).not.toBeNull();
    });

    fireEvent.click(screen.getByTestId('approve-button'));

    await waitFor(() => {
      expect(screen.getByTestId('error-banner').textContent).toContain(
        'An error occurred while processing approval.',
      );
    });
  });

  it('does not set state if unmounted during query param auto-lookup', () => {
    let resolvePromise!: (val: oauthApi.DeviceCodeInfoResponse) => void;
    let rejectPromise!: (err: unknown) => void;

    // 1. Resolve after unmount
    vi.spyOn(oauthApi, 'fetchDeviceCodeInfo').mockReturnValueOnce(
      new Promise((resolve) => {
        resolvePromise = resolve;
      }),
    );

    const { unmount: unmount1 } = render(
      <MemoryRouter initialEntries={['/activate?user_code=bcdfghjk']}>
        <DeviceActivatePage />
      </MemoryRouter>,
    );

    unmount1();
    resolvePromise({
      user_code: 'BCDF-GHJK',
      client_name: 'Unmounted',
      client_id: 'client_unmounted',
      resource: 'https://kanban.example.com/mcp/agent',
      surface: 'agent',
      requested_scopes: ['agent:read'],
      allowed_projects: null,
      expires_at: new Date().toISOString(),
    });

    // 2. Reject after unmount
    vi.spyOn(oauthApi, 'fetchDeviceCodeInfo').mockReturnValueOnce(
      new Promise((_resolve, reject) => {
        rejectPromise = reject;
      }),
    );

    const { unmount: unmount2 } = render(
      <MemoryRouter initialEntries={['/activate?user_code=bcdfghjk']}>
        <DeviceActivatePage />
      </MemoryRouter>,
    );

    unmount2();
    rejectPromise(new Error('Rejected after unmount'));
  });

  it('renders hostile client names strictly as escaped text nodes (Anti-XSS)', async () => {
    const hostileName = '<img src=x onerror=alert(1)> Hostile App';
    const mockInfo: oauthApi.DeviceCodeInfoResponse = {
      user_code: 'WDJB-MJHT',
      client_name: hostileName,
      client_id: 'client_xss',
      resource: 'https://kanban.example.com/mcp/agent',
      surface: 'agent',
      requested_scopes: ['agent:read'],
      allowed_projects: null,
      expires_at: new Date().toISOString(),
    };

    vi.spyOn(oauthApi, 'fetchDeviceCodeInfo').mockResolvedValue(mockInfo);

    render(
      <MemoryRouter initialEntries={['/activate?user_code=WDJB-MJHT']}>
        <DeviceActivatePage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      const clientNameEl = screen.getByTestId('client-name');
      expect(clientNameEl.textContent).toBe(hostileName);
      expect(clientNameEl.querySelector('img')).toBeNull();
    });
  });

  it('fetches real workspace projects from /api/v1/projects when allowed_projects is not specified', async () => {
    const KAN_UUID = '01a1f738-f55e-77f8-94bd-4a5c7960f807';
    const OPS_UUID = '01a1f738-f55e-77f8-94bd-4a5c7960f808';
    const mockInfo: oauthApi.DeviceCodeInfoResponse = {
      user_code: 'WDJB-MJHT',
      client_name: 'Test Device Client',
      client_id: 'client_live',
      resource: 'https://kanban.example.com/mcp/agent',
      surface: 'agent',
      requested_scopes: ['agent:read'],
      allowed_projects: null,
      expires_at: new Date().toISOString(),
    };

    vi.spyOn(oauthApi, 'fetchDeviceCodeInfo').mockResolvedValue(mockInfo);

    const mockFetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/api/v1/projects')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              items: [
                { id: KAN_UUID, identifier: 'KAN' },
                { id: OPS_UUID, identifier: 'OPS' },
              ],
            }),
        });
      }
      return Promise.reject(new Error('Unknown url'));
    });
    vi.stubGlobal('fetch', mockFetch);

    render(
      <MemoryRouter initialEntries={['/activate?user_code=WDJB-MJHT']}>
        <DeviceActivatePage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId(`project-checkbox-${KAN_UUID}`)).not.toBeNull();
      expect(screen.getByTestId(`project-checkbox-${OPS_UUID}`)).not.toBeNull();
      expect(screen.getByText('Project: KAN')).not.toBeNull();
      expect(screen.getByText('Project: OPS')).not.toBeNull();
    });

    vi.unstubAllGlobals();
  });

  it('populates workspace projects during manual code lookup and handles fetch failures', async () => {
    // 1. Manual code lookup populates workspace projects from fetch
    const PROJ_X_UUID = '01a1f738-f55e-77f8-94bd-4a5c7960f809';
    const mockInfo: oauthApi.DeviceCodeInfoResponse = {
      user_code: 'WDJB-MJHT',
      client_name: 'Manual Client',
      client_id: 'client_manual',
      resource: 'https://kanban.example.com/mcp/agent',
      surface: 'agent',
      requested_scopes: ['agent:read'],
      allowed_projects: null,
      expires_at: new Date().toISOString(),
    };
    vi.spyOn(oauthApi, 'fetchDeviceCodeInfo').mockResolvedValue(mockInfo);

    const mockFetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/api/v1/projects')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ id: PROJ_X_UUID, identifier: 'PROJECT_X' }]),
        });
      }
      return Promise.reject(new Error('Fail'));
    });
    vi.stubGlobal('fetch', mockFetch);

    const { unmount } = render(
      <MemoryRouter initialEntries={['/activate']}>
        <DeviceActivatePage />
      </MemoryRouter>,
    );

    const input = screen.getByTestId<HTMLInputElement>('user-code-input');
    fireEvent.change(input, { target: { value: 'WDJBMJHT' } });
    fireEvent.click(screen.getByTestId('lookup-button'));

    await waitFor(() => {
      expect(screen.getByTestId(`project-checkbox-${PROJ_X_UUID}`)).not.toBeNull();
      expect(screen.getByText('Project: PROJECT_X')).not.toBeNull();
    });
    unmount();

    // 2. HTTP 500 on projects endpoint
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }));
    const { unmount: u2 } = render(
      <MemoryRouter initialEntries={['/activate?user_code=WDJB-MJHT']}>
        <DeviceActivatePage />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('client-name')).not.toBeNull();
    });
    u2();

    // 3. Network error on projects endpoint
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Network error')));
    const { unmount: u3 } = render(
      <MemoryRouter initialEntries={['/activate?user_code=WDJB-MJHT']}>
        <DeviceActivatePage />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('client-name')).not.toBeNull();
    });
    u3();

    // 4. Identifier mapping and cached workspaceProjects branch in handleLookup
    const ID_PROJ_UUID = '01a1f738-f55e-77f8-94bd-4a5c7960f810';
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ items: [{ id: ID_PROJ_UUID, identifier: 'ID_PROJECT' }] }),
      }),
    );
    const { unmount: u4 } = render(
      <MemoryRouter initialEntries={['/activate']}>
        <DeviceActivatePage />
      </MemoryRouter>,
    );

    await act(async () => {
      await Promise.resolve();
    });

    const input4 = screen.getByTestId<HTMLInputElement>('user-code-input');
    fireEvent.change(input4, { target: { value: 'WDJBMJHT' } });
    fireEvent.click(screen.getByTestId('lookup-button'));

    await waitFor(() => {
      expect(screen.getByTestId(`project-checkbox-${ID_PROJ_UUID}`)).not.toBeNull();
      expect(screen.getByText('Project: ID_PROJECT')).not.toBeNull();
    });
    u4();

    // 5. Query param error with no message or code fallback
    vi.spyOn(oauthApi, 'fetchDeviceCodeInfo').mockRejectedValueOnce({});
    const { unmount: u5 } = render(
      <MemoryRouter initialEntries={['/activate?user_code=BCDFGHJK']}>
        <DeviceActivatePage />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('error-banner').textContent).toContain(
        'Invalid code or code not found.',
      );
    });
    u5();

    // 6. fetchWorkspaceProjects with empty data object and empty items
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({}),
      }),
    );
    const { unmount: u6 } = render(
      <MemoryRouter initialEntries={['/activate']}>
        <DeviceActivatePage />
      </MemoryRouter>,
    );
    await act(async () => {
      await Promise.resolve();
    });
    u6();

    vi.unstubAllGlobals();
  });

  it('covers project caching on second lookup after failure and identifier fallbacks', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: () =>
          Promise.resolve([
            { key: 'PROJ-KEY-ONLY', name: 'Key Project' },
            { identifier: 'PROJ-IDENT-ONLY', name: 'Ident Project' },
          ]),
      }),
    );

    const mockInfo: oauthApi.DeviceCodeInfoResponse = {
      user_code: 'WDJB-MJHT',
      client_name: 'Antigravity CLI',
      client_id: 'client_123',
      resource: 'https://kanban.example.com/mcp/agent',
      surface: 'agent',
      requested_scopes: ['agent:read'],
      allowed_projects: ['PROJ-KEY-ONLY'],
      expires_at: new Date(Date.now() + 600000).toISOString(),
    };
    // First lookup fails
    vi.spyOn(oauthApi, 'fetchDeviceCodeInfo')
      .mockRejectedValueOnce(new Error('Code not found'))
      .mockResolvedValueOnce(mockInfo);

    render(
      <MemoryRouter initialEntries={['/activate']}>
        <DeviceActivatePage />
      </MemoryRouter>,
    );

    const input = screen.getByTestId<HTMLInputElement>('user-code-input');
    fireEvent.change(input, { target: { value: 'WDJBMJHT' } });
    fireEvent.click(screen.getByTestId('lookup-button'));

    await waitFor(() => {
      expect(screen.getByText('Code not found')).toBeDefined();
    });

    // Lookup second code while projects are already cached in ref from first call
    fireEvent.change(input, { target: { value: 'BCDFGHJK' } });
    fireEvent.click(screen.getByTestId('lookup-button'));

    await waitFor(() => {
      expect(screen.getByTestId('consent-section')).not.toBeNull();
      expect(oauthApi.fetchDeviceCodeInfo).toHaveBeenCalledTimes(2);
    });

    vi.unstubAllGlobals();
  });
});
